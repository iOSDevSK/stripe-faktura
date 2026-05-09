"""Posielanie emailu s faktúrou cez Brevo Transactional API."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from .config import get_settings
from .invoice import Invoice

_BREVO_API = "https://api.brevo.com/v3/smtp/email"


def send_invoice_email(*, invoice: Invoice, pdf_bytes: bytes) -> dict[str, Any]:
    """Pošle faktúru ako PDF prílohu zákazníkovi.

    Vracia odpoveď z Brevo ako dict. Caller je zodpovedný za logovanie.
    Vyhodí httpx.HTTPStatusError pri non-2xx odpovedi.
    """
    settings = get_settings()
    if not settings.brevo_api_key:
        raise RuntimeError("BREVO_API_KEY nie je nakonfigurované")
    if not invoice.customer.email:
        raise ValueError("customer.email je prázdny — nedá sa odoslať")

    pdf_b64 = base64.b64encode(pdf_bytes).decode("ascii")
    filename = f"faktura-{invoice.number}.pdf"

    subject = f"Faktúra č. {invoice.number} — {settings.supplier_name}"
    body_text = (
        f"Dobrý deň,\n\n"
        f"v prílohe nájdete faktúru č. {invoice.number} za platbu prijatú dňa "
        f"{invoice.issued_at.isoformat()}.\n\n"
        f"Suma: {invoice.total:.2f} {invoice.currency.upper()}.\n\n"
        f"S pozdravom,\n{settings.supplier_name}\n"
        f"{settings.supplier_email}"
    )

    payload = {
        "sender": {
            "email": settings.brevo_sender_email or settings.supplier_email,
            "name": settings.brevo_sender_name or settings.supplier_name,
        },
        "to": [{"email": invoice.customer.email, "name": invoice.customer.name or ""}],
        "subject": subject,
        "textContent": body_text,
        "attachment": [{"name": filename, "content": pdf_b64}],
    }

    with httpx.Client(timeout=30.0) as client:
        r = client.post(
            _BREVO_API,
            json=payload,
            headers={
                "api-key": settings.brevo_api_key,
                "content-type": "application/json",
            },
        )
        r.raise_for_status()
        return r.json()
