"""Thin wrapper around the Stripe SDK — fetch customer + line items.

Per project decision: Stripe is the single source of truth.
- Customer name, email, address → stripe.Customer
- Customer IČO          → customer.metadata['ico']
- Customer DIČ          → customer.metadata['dic']
- Customer IČ DPH       → customer.tax_ids (type='eu_vat')
- Line items            → checkout_session.list_line_items
- Payment date          → payment_intent.created
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


def build_customer(stripe_customer: stripe.Customer) -> Customer:
    """Convert Stripe Customer → domain Customer."""
    addr = stripe_customer.get("address") or {}
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
    tax_ids = stripe_customer.get("tax_ids") or {}
    vat_id = ""
    for tid in tax_ids.get("data", []) if isinstance(tax_ids, dict) else []:
        # Slovak EU VAT prefix is "SK..."; accept any eu_vat type
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


def build_line_items(stripe_items: list[stripe.LineItem], currency: str) -> list[LineItem]:
    """Convert Stripe LineItems → domain LineItems.

    Stripe's `amount_total` on a line item is the gross total (qty * unit) in minor units.
    """
    out: list[LineItem] = []
    for li in stripe_items:
        qty = int(li.get("quantity") or 1)
        amount_total = int(li.get("amount_total") or 0)
        unit_minor = amount_total // qty if qty else amount_total
        description = li.get("description") or "Produkt"
        # Prefer the canonical product name when available
        if "price" in li and li.price and li.price.get("product"):
            prod = li.price.get("product")
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


def session_paid_at(session: stripe.checkout.Session) -> dt.date:
    """Return the payment date as a UTC date."""
    pi = session.get("payment_intent")
    created = None
    if isinstance(pi, dict) and pi.get("created"):
        created = pi["created"]
    elif session.get("created"):
        created = session["created"]
    if created:
        return dt.datetime.utcfromtimestamp(int(created)).date()
    return dt.datetime.utcnow().date()
