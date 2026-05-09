"""Tenký wrapper okolo Stripe SDK — načíta zákazníka + položky.

Podľa rozhodnutia projektu: Stripe je jediný zdroj pravdy.
- Meno, email, adresa zákazníka  → stripe.Customer
- IČO zákazníka                   → customer.metadata['ico']
- DIČ zákazníka                   → customer.metadata['dic']
- IČ DPH zákazníka                → customer.tax_ids (type='eu_vat')
- Položky                         → checkout_session.list_line_items
- Dátum platby                    → payment_intent.created
"""

from __future__ import annotations

import datetime as dt

import stripe

from .config import get_settings
from .invoice import Address, Customer, LineItem


def _init() -> None:
    stripe.api_key = get_settings().stripe_api_key


def fetch_session(session_id: str) -> stripe.checkout.Session:
    _init()
    return stripe.checkout.Session.retrieve(session_id, expand=["customer", "payment_intent"])


def fetch_customer(customer_id: str) -> stripe.Customer:
    _init()
    return stripe.Customer.retrieve(customer_id, expand=["tax_ids"])


def fetch_line_items(session_id: str) -> list[stripe.LineItem]:
    _init()
    items = stripe.checkout.Session.list_line_items(session_id, limit=100)
    return list(items.auto_paging_iter())


def build_customer(stripe_customer) -> Customer:
    """Konvertuje Stripe Customer → doménový Customer.

    `stripe_customer` môže byť plain dict alebo StripeObject — convertujeme.
    """
    if hasattr(stripe_customer, "_data"):
        stripe_customer = dict(stripe_customer)
    addr = stripe_customer.get("address") or {}
    if hasattr(addr, "_data"):
        addr = dict(addr)
    address: Address | None = None
    if addr and addr.get("line1"):
        address = Address(
            line1=addr.get("line1") or "",
            line2=addr.get("line2") or "",
            city=addr.get("city") or "",
            zip=addr.get("postal_code") or "",
            country=addr.get("country") or "",
        )

    metadata = stripe_customer.get("metadata") or {}
    if hasattr(metadata, "_data"):
        metadata = dict(metadata)
    tax_ids = stripe_customer.get("tax_ids") or {}
    if hasattr(tax_ids, "_data"):
        tax_ids = dict(tax_ids)
    vat_id = ""
    tax_data = tax_ids.get("data") if isinstance(tax_ids, dict) else []
    for tid in tax_data or []:
        if hasattr(tid, "_data"):
            tid = dict(tid)
        # Slovenské EU VAT začína na "SK..."; akceptujeme akýkoľvek typ eu_vat
        if tid.get("type") == "eu_vat":
            vat_id = tid.get("value") or ""
            break

    return Customer(
        name=stripe_customer.get("name") or "",
        email=stripe_customer.get("email") or "",
        address=address,
        ico=str(metadata.get("ico") or ""),
        dic=str(metadata.get("dic") or ""),
        vat_id=vat_id,
    )


def build_line_items(stripe_items, currency: str) -> list[LineItem]:
    """Konvertuje Stripe LineItems → doménové LineItems.

    Stripe `amount_total` na položke je suma s DPH (qty * unit) v haléroch.
    """
    out: list[LineItem] = []
    for li in stripe_items:
        if hasattr(li, "_data"):
            li = dict(li)
        qty = int(li.get("quantity") or 1)
        amount_total = int(li.get("amount_total") or 0)
        unit_minor = amount_total // qty if qty else amount_total
        description = li.get("description") or "Produkt"
        # Uprednostni kanonický názov produktu ak je dostupný
        price = li.get("price")
        if hasattr(price, "_data"):
            price = dict(price)
        if price:
            prod = price.get("product")
            if hasattr(prod, "_data"):
                prod = dict(prod)
            if isinstance(prod, dict) and prod.get("name"):
                description = prod["name"]
        out.append(
            LineItem(
                description=description,
                quantity=qty,
                unit_price_minor=unit_minor,
                currency=currency,
            )
        )
    return out


def session_paid_at(session) -> dt.date:
    """Vráti dátum platby ako UTC dátum."""
    if hasattr(session, "_data"):
        session = dict(session)
    pi = session.get("payment_intent")
    if hasattr(pi, "_data"):
        pi = dict(pi)
    created = None
    if isinstance(pi, dict) and pi.get("created"):
        created = pi["created"]
    elif session.get("created"):
        created = session["created"]
    if created:
        return dt.datetime.utcfromtimestamp(int(created)).date()
    return dt.datetime.utcnow().date()
