"""Airtable CRM upsert — best-effort zápis order detailu po vystavení faktúry.

Brevo backend a stripe-faktura zapisujú do tej istej tabuľky cez
`Stripe session ID` ako merge key. Brevo posiela order/voucher data,
stripe-faktura dopĺňa fakturačnú identitu a invoice link.

Best-effort: pri akejkoľvek chybe iba zalogujeme — webhook nesmie
spadnúť kvôli CRM zápisu (Stripe by potom retryoval a duplicitne
vystavil faktúru).
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

from .config import get_settings
from .invoice import Invoice
from . import pdf_token

log = logging.getLogger(__name__)


def _customer_type_label(ico: str) -> str:
    """Heuristika: ak má IČO → firma, inak fyzická osoba."""
    return "Firma" if ico.strip() else "Fyzická osoba"


def _format_address(addr: Any) -> str:
    """Single-line / multi-line adresa do plain textu pre Airtable."""
    if not addr:
        return ""
    parts = [
        addr.line1,
        addr.line2,
        f"{addr.zip} {addr.city}".strip(),
        addr.country,
    ]
    return "\n".join(p for p in parts if p)


def upsert_invoice(*, invoice: Invoice, stripe_session_id: str) -> None:
    """Upsert fakturačné polia do Airtable po vystavení faktúry.

    Volá sa po `pdf_render.render_invoice_pdf` a `storage.store_pdf`,
    NIE pred — ak PDF zlyhá, faktúra v Airtable by bola sirota bez linku.
    """
    s = get_settings()
    if not (s.airtable_api_key and s.airtable_base_id and s.airtable_table_id):
        return
    if not stripe_session_id:
        return

    cust = invoice.customer
    fields: dict[str, Any] = {
        "Stripe session ID": stripe_session_id,
        "Faktúra číslo": invoice.number,
        "Faktúra link": pdf_token.pdf_url(invoice.number) if s.base_url else "",
        "Zákazník": cust.name or cust.email or "",
        "Email": cust.email or "",
        "Telefón": cust.phone or "",
        "Typ zákazníka": _customer_type_label(cust.ico),
        "Adresa": _format_address(cust.address),
        "IČO": cust.ico or "",
        "DIČ": cust.dic or "",
        "IČ DPH": cust.vat_id or "",
    }
    # Drop empty optional polia aby sme neprepísali to čo brevo backend
    # nasadil predtým (napr. project_input description)
    fields = {k: v for k, v in fields.items() if v not in ("", None)}

    if "Stripe session ID" not in fields:
        return  # session_id zmizol počas filtrovania → nenechaj vytvoriť sirotu
    payload = {
        "performUpsert": {"fieldsToMergeOn": ["Stripe session ID"]},
        "records": [{"fields": fields}],
    }
    url = f"https://api.airtable.com/v0/{s.airtable_base_id}/{s.airtable_table_id}"
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.patch(
                url,
                headers={
                    "Authorization": f"Bearer {s.airtable_api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
        if resp.status_code >= 300:
            log.warning(
                "airtable upsert FAILED %s sid=%s fields=%s resp=%s",
                resp.status_code, stripe_session_id[:30],
                list(fields.keys()), resp.text[:400],
            )
        else:
            data = resp.json()
            created = data.get("createdRecords") or []
            updated = data.get("updatedRecords") or []
            log.info(
                "airtable upsert OK sid=%s created=%s updated=%s fields=%d",
                stripe_session_id[:30], created, updated, len(fields),
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("airtable upsert exception sid=%s: %r", stripe_session_id[:30], exc)
