"""Test HMAC tokenov pre verejné PDF URL."""

from __future__ import annotations

from stripe_faktura.pdf_token import make_pdf_token, pdf_url, verify_pdf_token


def test_token_je_deterministicky():
    a = make_pdf_token("20260001")
    b = make_pdf_token("20260001")
    assert a == b


def test_rozne_cisla_rozne_tokeny():
    assert make_pdf_token("20260001") != make_pdf_token("20260002")


def test_overenie_validneho_tokenu():
    t = make_pdf_token("20260042")
    assert verify_pdf_token("20260042", t) is True


def test_overenie_zleho_tokenu():
    assert verify_pdf_token("20260042", "fake_token") is False
    assert verify_pdf_token("20260042", "") is False
    assert verify_pdf_token("20260042", make_pdf_token("99999999")) is False


def test_token_pre_inu_fakturu_neprejde():
    t = make_pdf_token("20260001")
    assert verify_pdf_token("20260002", t) is False


def test_pdf_url_obsahuje_token():
    url = pdf_url("20260001")
    assert "/invoices/20260001/pdf?token=" in url
    # Token zo URL musí prejsť overením
    token = url.split("?token=")[1]
    assert verify_pdf_token("20260001", token) is True
