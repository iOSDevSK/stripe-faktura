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

import httpx
import stripe

from .config import get_settings
from .invoice import Address, Customer, LineItem

# Stripe SDK v11 StripeObject je nepríjemný (StripeObject neexposí .get()/dict()).
# Voláme Stripe REST API priamo — vracia plain JSON dict ktorý sa s Pythonom správa
# normálne. SDK necháme len na construct_event() podpisu vo webhook handleri.


def _api_get(path: str, params: dict | None = None) -> dict:
    settings = get_settings()
    with httpx.Client(timeout=30.0, auth=(settings.stripe_api_key, "")) as c:
        r = c.get(f"https://api.stripe.com/v1{path}", params=params or {})
        r.raise_for_status()
        return r.json()


def fetch_session(session_id: str) -> dict:
    return _api_get(
        f"/checkout/sessions/{session_id}",
        {"expand[]": ["customer", "payment_intent"]},
    )


def fetch_customer(customer_id: str) -> dict:
    return _api_get(f"/customers/{customer_id}", {"expand[]": ["tax_ids"]})


def fetch_promotion_code(promo_id: str) -> dict:
    return _api_get(f"/promotion_codes/{promo_id}")


def fetch_line_items(session_id: str) -> list[dict]:
    items: list[dict] = []
    starting_after = None
    while True:
        params: dict = {"limit": 100}
        if starting_after:
            params["starting_after"] = starting_after
        page = _api_get(f"/checkout/sessions/{session_id}/line_items", params)
        data = page.get("data") or []
        items.extend(data)
        if not page.get("has_more") or not data:
            break
        starting_after = data[-1]["id"]
    return items


def _to_dict(obj):
    """Rekurzívne konvertuje Stripe StripeObject (v11) na plain dict.

    Stripe v11 StripeObject má `keys()` (verejné) ale `_data` je za
    `__getattr__` ktorý raisuje pre `_*` mená. Iterujeme cez `keys()`.
    """
    if obj is None or isinstance(obj, (str, int, float, bool)):
        return obj
    if isinstance(obj, list):
        return [_to_dict(x) for x in obj]
    if isinstance(obj, dict):
        return {k: _to_dict(v) for k, v in obj.items()}
    keys_fn = getattr(obj, "keys", None)
    if callable(keys_fn):
        try:
            return {k: _to_dict(obj[k]) for k in list(keys_fn())}
        except Exception:  # noqa: BLE001
            return obj
    return obj


def build_customer(stripe_customer: dict) -> Customer:
    """Konvertuje Stripe Customer (plain JSON dict) → doménový Customer."""
    stripe_customer = stripe_customer or {}
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
    tax_data = tax_ids.get("data") if isinstance(tax_ids, dict) else []
    for tid in tax_data or []:
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


def merge_customer_billing(*, primary: Customer, fallback: Customer) -> Customer:
    """Vyplní prázdne polia `primary` zákazníka hodnotami z `fallback`.

    Používané pri voucher upgrade flow: Stripe Payment Link pri €349
    objednávke vytvára čerstvý Customer ktorý typicky nemá IČO/DIČ
    (Stripe ich pre SK natívne nezbiera) a často ani úplnú adresu.
    Pôvodný €49 dizajn-Customer bol vytvorený cez náš /checkout endpoint
    s plnou fakturačnou identitou, takže slúži ako fallback.

    Pravidlo: explicitná hodnota na primary vyhráva (rešpektujeme to čo
    klient zadal pri upgrade checkoute), prázdne polia sa doplnia z
    fallback-u.
    """
    return Customer(
        name=primary.name or fallback.name,
        email=primary.email or fallback.email,
        address=primary.address or fallback.address,
        ico=primary.ico or fallback.ico,
        dic=primary.dic or fallback.dic,
        vat_id=primary.vat_id or fallback.vat_id,
    )


def build_line_items(stripe_items: list[dict], currency: str) -> list[LineItem]:
    """Konvertuje Stripe LineItems (plain JSON dicts) → doménové LineItems.

    Stripe `amount_total` na položke je suma s DPH (qty * unit) v haléroch.
    """
    out: list[LineItem] = []
    for li in stripe_items or []:
        qty = int(li.get("quantity") or 1)
        amount_total = int(li.get("amount_total") or 0)
        unit_minor = amount_total // qty if qty else amount_total
        description = li.get("description") or "Produkt"
        price = li.get("price") or {}
        prod = price.get("product") if isinstance(price, dict) else None
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


def session_paid_at(session: dict) -> dt.date:
    """Vráti dátum platby ako UTC dátum (session je plain JSON dict zo Stripe API)."""
    pi = session.get("payment_intent")
    created = None
    if isinstance(pi, dict) and pi.get("created"):
        created = pi["created"]
    elif session.get("created"):
        created = session["created"]
    if created:
        return dt.datetime.utcfromtimestamp(int(created)).date()
    return dt.datetime.utcnow().date()
