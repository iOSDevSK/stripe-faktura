"""Test VAT extraction math on the Invoice domain object."""

from __future__ import annotations

import datetime as dt

from stripe_faktura.invoice import Address, Customer, Invoice, LineItem, Supplier


def _supplier(*, vat_registered: bool, vat_id: str = "") -> Supplier:
    return Supplier(
        name="BELNEM s.r.o.",
        address=Address(line1="X", city="Y", zip="0", country="SK"),
        ico="53713486",
        dic="",
        vat_registered=vat_registered,
        vat_id=vat_id,
        registration="",
        bank_name="x",
        iban="x",
        bic="",
        email="x@x.sk",
        phone="",
    )


def _customer() -> Customer:
    return Customer(name="Acme", email="acme@x.sk", address=None)


def _invoice(items: list[LineItem], *, vat_registered: bool, vat_rate: int = 20) -> Invoice:
    return Invoice(
        number="20260001",
        variable_symbol="20260001",
        issued_at=dt.date(2026, 1, 1),
        delivered_at=dt.date(2026, 1, 1),
        due_at=dt.date(2026, 1, 1),
        supplier=_supplier(vat_registered=vat_registered),
        customer=_customer(),
        items=items,
        currency="eur",
        vat_rate=vat_rate,
        vat_registered=vat_registered,
    )


def test_neplatca_no_vat():
    inv = _invoice(
        [LineItem("Web", 1, 34900, "eur")],
        vat_registered=False,
    )
    assert inv.subtotal_minor == 34900
    assert inv.vat_amount_minor == 0
    assert inv.base_amount_minor == 34900
    assert inv.total_minor == 34900


def test_platca_vat_extracted_from_gross():
    # 349,00 € total, VAT 20% extracted: base = 290,83 €, VAT = 58,17 €
    inv = _invoice(
        [LineItem("Web", 1, 34900, "eur")],
        vat_registered=True,
        vat_rate=20,
    )
    assert inv.total_minor == 34900
    assert inv.vat_amount_minor == 5817   # 58,17 €
    assert inv.base_amount_minor == 29083  # 290,83 €
    assert inv.base_amount_minor + inv.vat_amount_minor == inv.total_minor


def test_platca_multi_item():
    items = [
        LineItem("A", 2, 1000, "eur"),  # 20,00 € total
        LineItem("B", 1, 500, "eur"),   # 5,00 € total
    ]
    inv = _invoice(items, vat_registered=True, vat_rate=20)
    # gross 25,00 € = base 20,83 € + VAT 4,17 €
    assert inv.subtotal_minor == 2500
    assert inv.vat_amount_minor == 417
    assert inv.base_amount_minor == 2083
