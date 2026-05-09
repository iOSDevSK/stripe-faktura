"""Email dispatcher — picks Brevo or SMTP based on env config."""

from __future__ import annotations

from .config import get_settings
from .invoice import Invoice


def send_invoice_email(*, invoice: Invoice, pdf_bytes: bytes) -> str:
    """Dispatch to the configured provider. Returns the provider name used."""
    settings = get_settings()
    provider = settings.email_provider
    if provider == "brevo":
        from . import email_brevo

        email_brevo.send_invoice_email(invoice=invoice, pdf_bytes=pdf_bytes)
        return "brevo"
    if provider == "smtp":
        from . import email_smtp

        email_smtp.send_invoice_email(invoice=invoice, pdf_bytes=pdf_bytes)
        return "smtp"
    return "none"
