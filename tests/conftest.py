"""Test fixtures — minimálne env premenné aby config.Settings nepadlo pri importe."""

from __future__ import annotations

import os
import tempfile

import pytest


def _set_test_env() -> None:
    os.environ.setdefault("STRIPE_API_KEY", "sk_test_dummy")
    os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "whsec_dummy")
    os.environ.setdefault("SUPPLIER_NAME", "BELNEM s.r.o.")
    os.environ.setdefault("SUPPLIER_STREET", "Beckovská 5")
    os.environ.setdefault("SUPPLIER_CITY", "Bratislava")
    os.environ.setdefault("SUPPLIER_ZIP", "82104")
    os.environ.setdefault("SUPPLIER_COUNTRY", "SK")
    os.environ.setdefault("SUPPLIER_ICO", "53713486")
    os.environ.setdefault("SUPPLIER_DIC", "")
    os.environ.setdefault("SUPPLIER_VAT_REGISTERED", "false")
    os.environ.setdefault("SUPPLIER_BANK_NAME", "Slovenská sporiteľňa")
    os.environ.setdefault("SUPPLIER_IBAN", "SK00 0000 0000 0000 0000 0000")
    os.environ.setdefault("SUPPLIER_BIC", "GIBASKBX")
    os.environ.setdefault("SUPPLIER_EMAIL", "hello@test.sk")
    os.environ.setdefault("SUPPLIER_PHONE", "+421900000000")
    os.environ.setdefault("SUPPLIER_REGISTRATION", "OS BA III, Sro 152437/B")


_set_test_env()


@pytest.fixture
def tmp_db_url() -> str:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return f"sqlite:///{path}"
