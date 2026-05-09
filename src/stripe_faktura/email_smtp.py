"""Send invoice email via SMTP."""

from __future__ import annotations

import smtplib
from email.message import EmailMessage

from .config import get_settings
from .invoice import Invoice


def send_invoice_email(*, invoice: Invoice, pdf_bytes: bytes) -> None:
    """Send invoice as PDF attachment to the customer via SMTP."""
    settings = get_settings()
    if not settings.smtp_host:
        raise RuntimeError("SMTP_HOST is not configured")
    if not invoice.customer.email:
        raise ValueError("customer.email is empty — cannot send")

    msg = EmailMessage()
    msg["Subject"] = f"Faktúra č. {invoice.number} — {settings.supplier_name}"
    msg["From"] = (
        f"{settings.smtp_from_name or settings.supplier_name} "
        f"<{settings.smtp_from_email or settings.supplier_email}>"
    )
    msg["To"] = invoice.customer.email
    msg.set_content(
        f"Dobrý deň,\n\n"
        f"v prílohe nájdete faktúru č. {invoice.number} za platbu prijatú dňa "
        f"{invoice.issued_at.isoformat()}.\n\n"
        f"Suma: {invoice.total:.2f} {invoice.currency.upper()}.\n\n"
        f"S pozdravom,\n{settings.supplier_name}\n"
        f"{settings.supplier_email}"
    )
    msg.add_attachment(
        pdf_bytes,
        maintype="application",
        subtype="pdf",
        filename=f"faktura-{invoice.number}.pdf",
    )

    with smtplib.SMTP(settings.smtp_host, settings.smtp_port) as smtp:
        smtp.starttls()
        if settings.smtp_user:
            smtp.login(settings.smtp_user, settings.smtp_password)
        smtp.send_message(msg)
