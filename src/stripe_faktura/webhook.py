"""Handler Stripe webhooku — orchestrácia celého pipeline.

Tok pri `checkout.session.completed`:
  1. Overí podpis (rieši FastAPI route cez stripe.Webhook.construct_event).
  2. Preskočí ak metadata.no_invoice == "true" (escape hatch pre vouchery atď.).
  3. Preskočí ak pre tento session_id už faktúra existuje (idempotentnosť).
  4. Načíta zákazníka + položky zo Stripe.
  5. Postaví doménový Invoice objekt.
  6. Vyrenderuje PDF.
  7. Uloží (storage + DB).
  8. Pošle email zákazníkovi (best-effort; zlyhanie NEROBÍ rollback faktúry).
"""

from __future__ import annotations

import base64
import datetime as dt
import logging

import stripe
from sqlalchemy import select

from . import airtable
from . import email as email_dispatcher
from . import pdf as pdf_render
from . import storage, stripe_client, telegram
from .config import get_settings
from .db import InvoiceRecord, get_session
from .invoice import Address, Invoice, Supplier
from .numbering import next_invoice_number, variable_symbol_from

log = logging.getLogger(__name__)


def _supplier_from_settings() -> Supplier:
    s = get_settings()
    return Supplier(
        name=s.supplier_name,
        address=Address(
            line1=s.supplier_street,
            city=s.supplier_city,
            zip=s.supplier_zip,
            country=s.supplier_country,
        ),
        ico=s.supplier_ico,
        dic=s.supplier_dic,
        vat_registered=s.supplier_vat_registered,
        vat_id=s.supplier_vat_id,
        registration=s.supplier_registration,
        bank_name=s.supplier_bank_name,
        iban=s.supplier_iban,
        bic=s.supplier_bic,
        ks=s.supplier_ks,
        email=s.supplier_email,
        phone=s.supplier_phone,
        logo_url=s.supplier_logo_url,
        logo_path=s.supplier_logo_path,
    )


def _decode_client_reference_id(s: str | None, *, max_chars: int = 50) -> str:
    """Decode base64url client_reference_id (set by frontend modal).

    Frontend posiela URL/popis biznisu user-a base64url-encoded ako
    client_reference_id. Po decode-u skrátime na max_chars (50 default).
    Vracia prázdny string ak decode zlyhá.
    """
    if not s:
        return ""
    try:
        pad = len(s) % 4
        padded = s + ("=" * (4 - pad)) if pad else s
        text = base64.urlsafe_b64decode(padded).decode("utf-8")
    except Exception:  # noqa: BLE001
        return ""
    text = text.strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1].rstrip() + "…"
    return text


def _to_dict(obj):
    """Rekurzívne konvertuje Stripe StripeObject (v11) na plain Python dict.

    Stripe SDK v11+ má StripeObject ktorý:
      - neexposí `.get()` ani `dict(obj)`,
      - má `keys()` method, `__iter__`, `__getitem__`,
      - private atribúty (_data) sú zatienené `__getattr__` ktorý dvíha
        AttributeError pre kľúče začínajúce podtržníkom.
    Túto funkciu preto iterujeme cez verejné `keys()`.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    keys_fn = getattr(obj, "keys", None)
    if callable(keys_fn):
        try:
            return {k: _to_dict(obj[k]) for k in list(keys_fn())}
        except Exception:  # noqa: BLE001
            return obj
    return obj


def _resolve_design_customer(full_session: dict) -> dict | None:
    """Ak upgrade session uplatnil voucher (promotion_code), dohľadá
    pôvodného €49 dizajn-Customera a vráti jeho Stripe payload.

    Reťaz: session.discounts[].promotion_code
    → PromotionCode.metadata.design_session_id
    → Checkout.Session.customer
    → Customer (s expandovanými tax_ids).

    Pozn.: `session.discounts[]` je top-level a obsahuje promotion_code
    ako string ID bez expansie. `total_details.breakdown.discounts[]`
    je oddelená cesta dostupná iba s `expand[]=total_details.breakdown`,
    inak je breakdown None — preto siaháme priamo na top-level discounts.

    Pri akomkoľvek zlyhaní v reťazi vráti None — caller spadne na
    upgrade-session Customer a invariant „faktúra sa vždy vystaví"
    zostáva zachovaný.
    """
    for d in full_session.get("discounts") or []:
        promo = d.get("promotion_code")
        promo_id = promo if isinstance(promo, str) else (promo or {}).get("id")
        if not promo_id:
            continue
        try:
            promo_obj = stripe_client.fetch_promotion_code(promo_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("nepodarilo sa načítať promotion_code %s: %s", promo_id, exc)
            return None
        design_session_id = (promo_obj.get("metadata") or {}).get("design_session_id")
        if not design_session_id:
            return None
        try:
            design_session = stripe_client.fetch_session(design_session_id)
        except Exception as exc:  # noqa: BLE001
            log.warning(
                "nepodarilo sa načítať pôvodný design session %s: %s",
                design_session_id, exc,
            )
            return None
        design_customer = design_session.get("customer")
        if isinstance(design_customer, dict):
            return design_customer
        if isinstance(design_customer, str):
            try:
                return stripe_client.fetch_customer(design_customer)
            except Exception as exc:  # noqa: BLE001
                log.warning(
                    "nepodarilo sa načítať pôvodný customer %s: %s",
                    design_customer, exc,
                )
                return None
        return None
    return None


def handle_checkout_completed(event) -> dict:
    settings = get_settings()
    # Stripe v11 StripeObject neexposí .get()/dict() — konvertujeme cez to_dict_recursive
    session = _to_dict(event["data"]["object"])
    session_id = session["id"]
    metadata = session.get("metadata") or {}

    if str(metadata.get("no_invoice", "")).lower() == "true":
        log.info("preskakujem session %s: metadata.no_invoice=true", session_id)
        return {"ok": True, "skipped": "no_invoice flag"}

    db = get_session()
    try:
        existing = db.scalars(
            select(InvoiceRecord).where(InvoiceRecord.stripe_session_id == session_id)
        ).first()
        if existing:
            log.info(
                "preskakujem session %s: faktúra %s už existuje",
                session_id,
                existing.number,
            )
            return {"ok": True, "skipped": "duplicate", "invoice_number": existing.number}

        # Znovu načítame session s expansiami (webhook payload je plytký)
        full_session = stripe_client.fetch_session(session_id)

        customer_id = full_session.get("customer")
        if isinstance(customer_id, dict):
            stripe_customer = customer_id  # už expandovaný
        elif customer_id:
            stripe_customer = stripe_client.fetch_customer(customer_id)
        else:
            log.warning(
                "session %s nemá zákazníka; fallback na customer_details", session_id
            )
            cd = full_session.get("customer_details") or {}
            stripe_customer = {
                "name": cd.get("name") or "",
                "email": cd.get("email") or "",
                "address": dict(cd.get("address") or {}),
                "metadata": {},
                "tax_ids": {"data": []},
            }

        customer = stripe_client.build_customer(stripe_customer)

        # Voucher upgrade flow: ak €349 session aplikoval promotion_code z
        # €49 dizajn-objednávky, dotiahni chýbajúce fakturačné polia
        # (adresa, IČO, DIČ, IČ DPH) z pôvodného Customera. Stripe Payment
        # Link tieto polia natívne nezbiera, takže by inak na upgrade
        # faktúre chýbali.
        design_customer_data = _resolve_design_customer(full_session)
        if design_customer_data:
            customer = stripe_client.merge_customer_billing(
                primary=customer,
                fallback=stripe_client.build_customer(design_customer_data),
            )
            log.info(
                "session %s: prenesené billing údaje z dizajn-customera (voucher upgrade)",
                session_id,
            )

        currency = (full_session.get("currency") or "eur").lower()
        items = stripe_client.build_line_items(stripe_client.fetch_line_items(session_id), currency)

        if not items:
            log.warning("session %s nemá žiadne položky; preskakujem", session_id)
            return {"ok": False, "error": "no line items"}

        # Pripojíme user-ov vstup z modalu (URL alebo popis biznisu) do
        # popisu prvej položky — max 50 znakov.
        client_input = _decode_client_reference_id(full_session.get("client_reference_id"))
        if client_input and items:
            from .invoice import LineItem  # local to avoid cycles
            head = items[0]
            items[0] = LineItem(
                description=f"{head.description} — {client_input}",
                quantity=head.quantity,
                unit_price_minor=head.unit_price_minor,
                currency=head.currency,
            )

        # Atomická alokácia čísla faktúry spolu s DB záznamom
        number = next_invoice_number(db)
        issued_at = stripe_client.session_paid_at(full_session)

        invoice = Invoice(
            number=number,
            variable_symbol=variable_symbol_from(number),
            issued_at=issued_at,
            delivered_at=issued_at,
            due_at=issued_at,
            supplier=_supplier_from_settings(),
            customer=customer,
            items=items,
            currency=currency,
            vat_rate=settings.vat_rate,
            vat_registered=settings.supplier_vat_registered,
            payment_method="Platba kartou (Stripe)",
            is_paid=True,
        )

        pdf_bytes = pdf_render.render_invoice_pdf(invoice)
        pdf_path = storage.store_pdf(
            year=issued_at.year, invoice_number=number, pdf_bytes=pdf_bytes
        )

        record = InvoiceRecord(
            number=number,
            stripe_session_id=session_id,
            stripe_customer_id=str(customer_id) if isinstance(customer_id, str) else None,
            stripe_payment_intent_id=str(full_session.get("payment_intent") or "") or None,
            customer_email=customer.email or None,
            customer_name=customer.name or None,
            total_minor=invoice.total_minor,
            currency=currency,
            vat_mode="platca" if settings.supplier_vat_registered else "neplatca",
            pdf_path=pdf_path,
            issued_at=dt.datetime.utcnow(),
        )
        db.add(record)
        db.commit()

        # Airtable CRM upsert — fakturačná identita + invoice link.
        # Brevo backend predtým upsertol order/voucher info na ten istý
        # `Stripe session ID` merge key, takže Airtable ich zlúči.
        airtable.upsert_invoice(invoice=invoice, stripe_session_id=session_id)

        # Telegram — krátka správa s číslom FA + download linkom (best-effort)
        telegram.notify_invoice_issued(invoice)

        # Best-effort email (zlyhanie zalogujeme, webhook neumrie)
        emailed = False
        if settings.email_enabled and customer.email:
            try:
                provider = email_dispatcher.send_invoice_email(
                    invoice=invoice, pdf_bytes=pdf_bytes
                )
                emailed = provider != "none"
                if emailed:
                    record.emailed_at = dt.datetime.utcnow()
                    db.commit()
            except Exception as exc:  # noqa: BLE001
                log.exception("odoslanie emailu zlyhalo pre faktúru %s: %s", number, exc)

        return {
            "ok": True,
            "invoice_number": number,
            "pdf_path": pdf_path,
            "emailed": emailed,
        }
    finally:
        db.close()
