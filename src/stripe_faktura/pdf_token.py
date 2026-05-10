"""HMAC-podpísané tokeny pre stiahnutie PDF cez verejnú URL.

Token = base64url(HMAC-SHA256(message, pdf_token_secret)) kde message je:
  - `invoice_number`              — bez expirácie (link platný do rotácie secret-u)
  - `invoice_number|<exp_unix>`   — s expiráciou (link prestane fungovať po `exp`)

Stateless overenie — žiadny DB lookup. Číslo faktúry samo o sebe nestačí;
útočník potrebuje aj `PDF_TOKEN_SECRET`.

Rotácia tajomstva = všetky existujúce linky 401. Akceptovateľné
(zákazník dostane novú URL na požiadanie).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time

from .config import get_settings


def _secret_bytes() -> bytes:
    s = get_settings()
    # Ak nie je nastavený dedikovaný secret, odvodíme z webhook secret-u.
    raw = s.pdf_token_secret or (s.stripe_webhook_secret + "::pdf_url")
    return raw.encode("utf-8")


def _hmac(message: str) -> str:
    digest = hmac.new(_secret_bytes(), message.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def make_pdf_token(invoice_number: str, *, exp: int | None = None) -> str:
    """HMAC token pre faktúru, voliteľne s expiráciou.

    `exp` je unix timestamp (sekundy). Ak je daný, je súčasťou HMAC inputu
    aj URL — server musí dostať tú istú hodnotu inak validácia padne.
    """
    message = invoice_number if exp is None else f"{invoice_number}|{exp}"
    return _hmac(message)


def verify_pdf_token(invoice_number: str, token: str, *, exp: int | None = None) -> bool:
    """Constant-time HMAC porovnanie + kontrola expirácie ak je `exp` daný."""
    if not token:
        return False
    if exp is not None and exp < int(time.time()):
        return False
    expected = make_pdf_token(invoice_number, exp=exp)
    return hmac.compare_digest(expected, token)


def pdf_url(invoice_number: str, *, ttl_seconds: int | None = None) -> str:
    """Plnú URL na stiahnutie PDF (s tokenom).

    `ttl_seconds` (voliteľné) — link bude platný túto dobu od teraz a
    server odmietne neskoršie volania. Bez `ttl_seconds` link platí
    neobmedzene (do rotácie `PDF_TOKEN_SECRET`).
    Vyžaduje `BASE_URL` v configu pre absolútnu URL.
    """
    exp = int(time.time()) + ttl_seconds if ttl_seconds else None
    token = make_pdf_token(invoice_number, exp=exp)
    qs = f"token={token}" + (f"&exp={exp}" if exp else "")
    base = get_settings().base_url.rstrip("/")
    path = f"/invoices/{invoice_number}/pdf?{qs}"
    return f"{base}{path}" if base else path
