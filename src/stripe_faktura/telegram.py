"""Telegram notifikácia po vystavení faktúry — best-effort.

Brevo backend posiela samostatnú „nová objednávka" správu s detailmi
zákazníka, vouchera a sumou. Tento modul posiela komplementárnu krátku
správu s číslom faktúry + HMAC-podpísaným download linkom, hneď ako
stripe-faktura PDF vyrenderuje.

Bez `telegram_bot_token` + `telegram_chat_id` config sa preskočí.
"""

from __future__ import annotations

import logging

import httpx

from .config import get_settings
from .invoice import Invoice
from . import pdf_token

log = logging.getLogger(__name__)


def _escape(s: str) -> str:
    """HTML escape pre Telegram parse_mode=HTML."""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def notify_invoice_issued(invoice: Invoice) -> None:
    s = get_settings()
    if not (s.telegram_bot_token and s.telegram_chat_id):
        return

    pdf_link = pdf_token.pdf_url(invoice.number) if s.base_url else ""
    customer_label = (invoice.customer.name or invoice.customer.email or "—").strip()
    text = (
        f"📄 <b>Faktúra č. {_escape(invoice.number)}</b> vystavená\n"
        f"👤 {_escape(customer_label)}\n"
        f"💶 {invoice.total:.2f} {_escape(invoice.currency.upper())}\n"
    )
    if pdf_link:
        text += f'🔗 <a href="{_escape(pdf_link)}">Stiahnuť PDF</a>'

    url = f"https://api.telegram.org/bot{s.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": s.telegram_chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    try:
        with httpx.Client(timeout=10.0) as client:
            resp = client.post(url, json=payload)
        if resp.status_code >= 300:
            log.warning(
                "telegram sendMessage FAILED %s: %s",
                resp.status_code, resp.text[:300],
            )
    except Exception as exc:  # noqa: BLE001
        log.warning("telegram sendMessage exception: %r", exc)
