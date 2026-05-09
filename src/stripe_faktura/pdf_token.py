"""HMAC-podpísané tokeny pre stiahnutie PDF cez verejnú URL.

Token = base64url(HMAC-SHA256(invoice_number, pdf_token_secret)).
Stateless overenie — žiadny DB lookup, žiadna expiracia.
Číslo faktúry samo o sebe nestačí; útočník potrebuje aj `PDF_TOKEN_SECRET`.

Rotácia tajomstva = všetky existujúce linky 401. Akceptovateľné
(zákazník dostane novú URL na požiadanie).
"""

from __future__ import annotations

import base64
import hashlib
import hmac

from .config import get_settings


def _secret_bytes() -> bytes:
    s = get_settings()
    # Ak nie je nastavený dedikovaný secret, odvodíme z webhook secret-u.
    raw = s.pdf_token_secret or (s.stripe_webhook_secret + "::pdf_url")
    return raw.encode("utf-8")


def make_pdf_token(invoice_number: str) -> str:
    """Vygeneruje HMAC token pre dané číslo faktúry."""
    digest = hmac.new(_secret_bytes(), invoice_number.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def verify_pdf_token(invoice_number: str, token: str) -> bool:
    """Constant-time porovnanie tokenu."""
    if not token:
        return False
    expected = make_pdf_token(invoice_number)
    return hmac.compare_digest(expected, token)


def pdf_url(invoice_number: str) -> str:
    """Plnú URL na stiahnutie PDF (s tokenom). Vyžaduje BASE_URL v configu."""
    base = get_settings().base_url.rstrip("/")
    if not base:
        # Bez BASE_URL vraciame relatívnu cestu (napr. v testoch)
        return f"/invoices/{invoice_number}/pdf?token={make_pdf_token(invoice_number)}"
    return f"{base}/invoices/{invoice_number}/pdf?token={make_pdf_token(invoice_number)}"
