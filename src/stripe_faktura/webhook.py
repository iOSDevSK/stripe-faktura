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

import datetime as dt
import logging

import stripe
from sqlalchemy import select

from . import email as email_dispatcher
from . import pdf as pdf_render
from . import storage, stripe_client
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


def _to_dict(obj):
    """Konvertuje Stripe StripeObject (v11) na plain dict rekurzívne."""
    if obj is None:
        return None
    if hasattr(obj, "to_dict_recursive"):
        return obj.to_dict_recursive()
    if isinstance(obj, dict):
        return obj
    if hasattr(obj, "_data"):
        try:
            return dict(obj._data)
        except Exception:  # noqa: BLE001
            pass
    return obj


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
        currency = (full_session.get("currency") or "eur").lower()
        items = stripe_client.build_line_items(stripe_client.fetch_line_items(session_id), currency)

        if not items:
            log.warning("session %s nemá žiadne položky; preskakujem", session_id)
            return {"ok": False, "error": "no line items"}

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
