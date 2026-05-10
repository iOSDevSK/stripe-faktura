"""Test pre _resolve_design_customer — orchestrácia voucher-prenos reťaze.

Tieto testy sa primárne pýtajú: rozumieme správne tvaru Stripe Checkout
Session JSON-u? Konkrétne: kde žije promotion_code v session payload-e
(top-level `discounts[]`, nie `total_details.breakdown.discounts[]`).
"""

from __future__ import annotations

from unittest.mock import patch

from stripe_faktura.webhook import _resolve_design_customer


def test_returns_none_when_no_discounts() -> None:
    assert _resolve_design_customer({"id": "cs_x"}) is None
    assert _resolve_design_customer({"id": "cs_x", "discounts": []}) is None
    assert _resolve_design_customer({"id": "cs_x", "discounts": None}) is None


def test_resolves_full_chain_from_top_level_discounts() -> None:
    """Realistický payload: discounts je top-level pole s promo string ID."""
    session_payload = {
        "id": "cs_test_upgrade",
        "discounts": [{"coupon": None, "promotion_code": "promo_abc"}],
        # total_details.breakdown is None (Stripe nepopuluje bez expansie)
        "total_details": {
            "amount_discount": 4900,
            "amount_shipping": 0,
            "amount_tax": 0,
        },
    }
    promo_payload = {
        "id": "promo_abc",
        "metadata": {
            "design_session_id": "cs_test_design",
            "customer_email": "k@x.sk",
        },
    }
    design_session = {
        "id": "cs_test_design",
        "customer": {
            "id": "cus_design",
            "name": "Klient",
            "email": "k@x.sk",
            "address": {"line1": "Hlavná 1", "city": "BA", "postal_code": "81101", "country": "SK"},
            "metadata": {"customer_type": "osoba"},
        },
    }

    with patch("stripe_faktura.stripe_client.fetch_promotion_code", return_value=promo_payload), \
         patch("stripe_faktura.stripe_client.fetch_session", return_value=design_session):
        result = _resolve_design_customer(session_payload)

    assert result is not None
    assert result["id"] == "cus_design"
    assert result["address"]["line1"] == "Hlavná 1"


def test_returns_none_when_promo_metadata_missing_design_session_id() -> None:
    session_payload = {
        "id": "cs_x",
        "discounts": [{"promotion_code": "promo_legacy"}],
    }
    promo_payload = {"id": "promo_legacy", "metadata": {}}  # starý voucher bez metadát

    with patch("stripe_faktura.stripe_client.fetch_promotion_code", return_value=promo_payload):
        assert _resolve_design_customer(session_payload) is None


def test_fetches_customer_when_design_session_returns_string_id() -> None:
    """Defensive: ak design session nemá expandovaný customer (len string ID),
    dotiahneme ho cez fetch_customer."""
    session_payload = {
        "id": "cs_upgrade",
        "discounts": [{"promotion_code": "promo_x"}],
    }
    promo_payload = {
        "id": "promo_x",
        "metadata": {"design_session_id": "cs_design"},
    }
    design_session = {"id": "cs_design", "customer": "cus_string_id"}
    customer_payload = {"id": "cus_string_id", "email": "x@y.sk"}

    with patch("stripe_faktura.stripe_client.fetch_promotion_code", return_value=promo_payload), \
         patch("stripe_faktura.stripe_client.fetch_session", return_value=design_session), \
         patch("stripe_faktura.stripe_client.fetch_customer", return_value=customer_payload) as mock_fc:
        result = _resolve_design_customer(session_payload)

    assert result == customer_payload
    mock_fc.assert_called_once_with("cus_string_id")


def test_swallows_promo_fetch_failure() -> None:
    session_payload = {
        "id": "cs_x",
        "discounts": [{"promotion_code": "promo_404"}],
    }
    with patch(
        "stripe_faktura.stripe_client.fetch_promotion_code",
        side_effect=RuntimeError("Stripe 404"),
    ):
        assert _resolve_design_customer(session_payload) is None
