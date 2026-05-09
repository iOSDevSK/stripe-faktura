"""Smoke test: WeasyPrint vie vyrenderovať obe šablóny bez chýb.

Automaticky preskočí ak chýbajú systémové závislosti WeasyPrint (Cairo/Pango).
"""

from __future__ import annotations

import datetime as dt

import pytest

from stripe_faktura.invoice import Address, Customer, Invoice, LineItem, Supplier

pytest.importorskip("weasyprint")


def _make_invoice(*, vat_registered: bool) -> Invoice:
    return Invoice(
        number="20260042",
        variable_symbol="20260042",
        issued_at=dt.date(2026, 5, 9),
        delivered_at=dt.date(2026, 5, 9),
        due_at=dt.date(2026, 5, 9),
        supplier=Supplier(
            name="BELNEM s.r.o.",
            address=Address(line1="Beckovská 5", city="Bratislava", zip="82104", country="SK"),
            ico="53713486",
            dic="2024567890",
            vat_registered=vat_registered,
            vat_id="SK2024567890" if vat_registered else "",
            registration="OS Bratislava III, Sro 152437/B",
            bank_name="Slovenská sporiteľňa",
            iban="SK00 0900 0000 0000 0000 0000",
            bic="GIBASKBX",
            email="hello@24design.sk",
            phone="+421940877997",
        ),
        customer=Customer(
            name="Acme s.r.o.",
            email="objednavka@acme.sk",
            address=Address(line1="Hlavná 1", city="Košice", zip="04001", country="SK"),
            ico="12345678",
            dic="2012345678",
            vat_id="SK2012345678",
        ),
        items=[
            LineItem("Web na kľúč — 24design.sk", 1, 34900, "eur"),
        ],
        currency="eur",
        vat_rate=20,
        vat_registered=vat_registered,
    )


def test_render_pdf_neplatca():
    from stripe_faktura.pdf import render_invoice_pdf

    pdf_bytes = render_invoice_pdf(_make_invoice(vat_registered=False))
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 5000


def test_render_pdf_platca():
    from stripe_faktura.pdf import render_invoice_pdf

    pdf_bytes = render_invoice_pdf(_make_invoice(vat_registered=True))
    assert pdf_bytes[:4] == b"%PDF"
    assert len(pdf_bytes) > 5000
