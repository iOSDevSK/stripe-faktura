"""Test validácie CheckoutRequest schémy — IČO/DIČ/IČ DPH a podmienené polia."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from stripe_faktura.checkout import CheckoutRequest


def _valid_firma_payload() -> dict:
    return {
        "price_id": "price_test_123",
        "customer_type": "firma",
        "email": "info@acme.sk",
        "company_name": "Acme s.r.o.",
        "ico": "12345678",
        "dic": "2012345678",
        "vat_id": "SK2012345678",
        "address_line1": "Hlavná 1",
        "address_city": "Bratislava",
        "address_zip": "82104",
        "address_country": "SK",
        "success_url": "https://24design.sk/thank-you",
        "cancel_url": "https://24design.sk/cennik",
    }


def _valid_osoba_payload() -> dict:
    return {
        "price_id": "price_test_123",
        "customer_type": "osoba",
        "email": "janko@example.sk",
        "name": "Janko Hraško",
        "address_line1": "Lipová 5",
        "address_city": "Košice",
        "address_zip": "04001",
        "address_country": "SK",
        "success_url": "https://24design.sk/thank-you",
        "cancel_url": "https://24design.sk/cennik",
    }


def test_validna_firma_prejde():
    req = CheckoutRequest(**_valid_firma_payload())
    assert req.customer_type == "firma"
    assert req.ico == "12345678"
    assert req.vat_id == "SK2012345678"


def test_validna_osoba_prejde():
    req = CheckoutRequest(**_valid_osoba_payload())
    assert req.customer_type == "osoba"
    assert req.name == "Janko Hraško"


def test_firma_bez_ico_zlyha():
    p = _valid_firma_payload()
    p["ico"] = None
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_firma_bez_company_name_zlyha():
    p = _valid_firma_payload()
    p["company_name"] = None
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_osoba_bez_mena_zlyha():
    p = _valid_osoba_payload()
    p["name"] = None
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_neplatne_ico_zlyha():
    p = _valid_firma_payload()
    p["ico"] = "1234"  # 4 cifry — nie 8
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_neplatne_ic_dph_zlyha():
    p = _valid_firma_payload()
    p["vat_id"] = "12345"  # bez krajinového prefixu
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_ic_dph_sa_uppercasuje():
    p = _valid_firma_payload()
    p["vat_id"] = "sk2012345678"
    req = CheckoutRequest(**p)
    assert req.vat_id == "SK2012345678"


def test_country_sa_uppercasuje():
    p = _valid_firma_payload()
    p["address_country"] = "sk"
    req = CheckoutRequest(**p)
    assert req.address_country == "SK"


def test_ico_s_medzerami_sa_normalizuje():
    p = _valid_firma_payload()
    p["ico"] = "1234 5678"
    req = CheckoutRequest(**p)
    assert req.ico == "12345678"


def test_neplatny_email_zlyha():
    p = _valid_firma_payload()
    p["email"] = "nie-je-email"
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_chybajuci_email_zlyha():
    p = _valid_firma_payload()
    del p["email"]
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_quantity_minimum():
    p = _valid_osoba_payload()
    p["quantity"] = 0
    with pytest.raises(ValidationError):
        CheckoutRequest(**p)


def test_dic_volitelny():
    p = _valid_firma_payload()
    p["dic"] = None
    p["vat_id"] = None
    req = CheckoutRequest(**p)
    assert req.dic is None
    assert req.vat_id is None
