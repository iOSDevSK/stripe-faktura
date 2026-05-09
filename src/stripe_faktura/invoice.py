"""Invoice domain model — pure, framework-agnostic dataclasses."""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal


@dataclass(frozen=True)
class Address:
    line1: str
    city: str
    zip: str
    country: str
    line2: str = ""


@dataclass(frozen=True)
class Supplier:
    name: str
    address: Address
    ico: str
    dic: str
    vat_registered: bool
    vat_id: str
    registration: str
    bank_name: str
    iban: str
    bic: str
    email: str
    phone: str
    logo_url: str = ""


@dataclass(frozen=True)
class Customer:
    name: str
    email: str
    address: Address | None
    ico: str = ""
    dic: str = ""
    vat_id: str = ""


@dataclass(frozen=True)
class LineItem:
    description: str
    quantity: int
    unit_price_minor: int   # in minor units (cents)
    currency: str

    @property
    def unit_price(self) -> Decimal:
        return Decimal(self.unit_price_minor) / Decimal(100)

    @property
    def total_minor(self) -> int:
        return self.unit_price_minor * self.quantity

    @property
    def total(self) -> Decimal:
        return Decimal(self.total_minor) / Decimal(100)


@dataclass(frozen=True)
class Invoice:
    number: str
    variable_symbol: str
    issued_at: dt.date
    delivered_at: dt.date
    due_at: dt.date
    supplier: Supplier
    customer: Customer
    items: list[LineItem]
    currency: str
    vat_rate: int                  # whole percent, e.g. 20
    vat_registered: bool           # supplier VAT mode
    payment_method: str = "Platba kartou (Stripe)"
    is_paid: bool = True
    notes: str = ""

    @property
    def subtotal_minor(self) -> int:
        return sum(item.total_minor for item in self.items)

    @property
    def subtotal(self) -> Decimal:
        return Decimal(self.subtotal_minor) / Decimal(100)

    @property
    def vat_amount_minor(self) -> int:
        if not self.vat_registered:
            return 0
        # VAT extracted from a gross-inclusive total: gross * rate / (100 + rate)
        gross = Decimal(self.subtotal_minor)
        rate = Decimal(self.vat_rate)
        vat = (gross * rate / (Decimal(100) + rate)).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        return int(vat)

    @property
    def vat_amount(self) -> Decimal:
        return Decimal(self.vat_amount_minor) / Decimal(100)

    @property
    def base_amount_minor(self) -> int:
        # Net amount = gross - VAT (or whole if non-VAT)
        return self.subtotal_minor - self.vat_amount_minor

    @property
    def base_amount(self) -> Decimal:
        return Decimal(self.base_amount_minor) / Decimal(100)

    @property
    def total_minor(self) -> int:
        return self.subtotal_minor

    @property
    def total(self) -> Decimal:
        return self.subtotal
