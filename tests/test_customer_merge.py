"""Test merge fakturačnej identity pri voucher upgrade flow."""

from __future__ import annotations

from stripe_faktura.invoice import Address, Customer
from stripe_faktura.stripe_client import merge_customer_billing


def _customer(
    *,
    name: str = "",
    email: str = "",
    address: Address | None = None,
    ico: str = "",
    dic: str = "",
    vat_id: str = "",
) -> Customer:
    return Customer(
        name=name, email=email, address=address, ico=ico, dic=dic, vat_id=vat_id
    )


def test_fallback_fills_empty_fields_on_primary() -> None:
    primary = _customer(name="Jano Mrkvička", email="jano@example.sk")
    fallback = _customer(
        name="Iné meno",
        email="iny@example.sk",
        address=Address(line1="Beckovská 5", city="Bratislava", zip="82104", country="SK"),
        ico="53713486",
        dic="2123456789",
        vat_id="SK2123456789",
    )

    merged = merge_customer_billing(primary=primary, fallback=fallback)

    assert merged.name == "Jano Mrkvička"  # primary wins
    assert merged.email == "jano@example.sk"  # primary wins
    assert merged.address == fallback.address  # primary empty → fallback
    assert merged.ico == "53713486"
    assert merged.dic == "2123456789"
    assert merged.vat_id == "SK2123456789"


def test_primary_wins_when_present() -> None:
    primary = _customer(
        name="Firma A s.r.o.",
        email="kontakt@firmaa.sk",
        address=Address(line1="Hlavná 1", city="Košice", zip="04001", country="SK"),
        ico="11111111",
        dic="2099999999",
        vat_id="SK2099999999",
    )
    fallback = _customer(
        name="Firma B",
        email="b@b.sk",
        address=Address(line1="Iná 9", city="Žilina", zip="01001", country="SK"),
        ico="22222222",
        dic="2088888888",
        vat_id="SK2088888888",
    )

    merged = merge_customer_billing(primary=primary, fallback=fallback)

    assert merged.name == "Firma A s.r.o."
    assert merged.email == "kontakt@firmaa.sk"
    assert merged.address == primary.address
    assert merged.ico == "11111111"
    assert merged.dic == "2099999999"
    assert merged.vat_id == "SK2099999999"


def test_empty_primary_returns_fallback_identity() -> None:
    primary = _customer()  # úplne prázdny
    fallback = _customer(
        name="Klient",
        email="k@k.sk",
        address=Address(line1="A 1", city="BA", zip="81101", country="SK"),
        ico="12345678",
    )

    merged = merge_customer_billing(primary=primary, fallback=fallback)

    assert merged.name == "Klient"
    assert merged.email == "k@k.sk"
    assert merged.address == fallback.address
    assert merged.ico == "12345678"
    assert merged.dic == ""
    assert merged.vat_id == ""
