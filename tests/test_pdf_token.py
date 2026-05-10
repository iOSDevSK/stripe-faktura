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


def test_token_s_expiraciou_prejde_pred_uplynutim():
    import time
    exp = int(time.time()) + 60
    t = make_pdf_token("20260001", exp=exp)
    assert verify_pdf_token("20260001", t, exp=exp) is True


def test_expirovany_token_neprejde():
    import time
    exp = int(time.time()) - 1
    t = make_pdf_token("20260001", exp=exp)
    assert verify_pdf_token("20260001", t, exp=exp) is False


def test_token_bez_exp_neprejde_proti_overeniu_s_exp():
    import time
    exp = int(time.time()) + 60
    t_no_exp = make_pdf_token("20260001")
    # Server očakáva exp v HMAC, dostal token bez neho → fail
    assert verify_pdf_token("20260001", t_no_exp, exp=exp) is False


def test_klient_nemoze_predlzit_exp_swapom():
    """Útočník chytí URL s exp=100 a skúsi exp=999999. Token je naviazaný
    na pôvodné exp v HMAC, takže swap padne."""
    import time
    real_exp = int(time.time()) + 60
    t = make_pdf_token("20260001", exp=real_exp)
    forged_exp = real_exp + 86400
    assert verify_pdf_token("20260001", t, exp=forged_exp) is False


def test_pdf_url_s_ttl_obsahuje_exp():
    url = pdf_url("20260001", ttl_seconds=300)
    assert "&exp=" in url
    # Roztiahni query a over
    qs = url.split("?", 1)[1]
    parts = dict(p.split("=", 1) for p in qs.split("&"))
    assert verify_pdf_token("20260001", parts["token"], exp=int(parts["exp"])) is True
