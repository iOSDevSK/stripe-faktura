"""Endpoint na vytvorenie Stripe Checkout Session s SK billing údajmi.

Frontend (napr. formulár na 24design.sk) odošle billing data zákazníka
(meno/firma, IČO, DIČ, IČ DPH, adresa, email) + Stripe price_id.
Tento endpoint:

  1. Overí Origin proti ALLOWED_ORIGINS allowlistu.
  2. Overí price_id proti ALLOWED_PRICE_IDS allowlistu (anti-tampering).
  3. Validuje SK-špecifické polia (IČO formát, IČ DPH prefix).
  4. Vytvorí Stripe Customer s metadata.ico/dic + adresou + tax_ids (ak IČ DPH).
  5. Vytvorí Stripe Checkout Session priviazanú na tohto Customer.
  6. Vráti checkout_url — frontend len redirectne.

Po platbe Stripe pošle webhook → existujúci handler vystaví SK PDF faktúru
priamo zo Stripe Customer dát.
"""

from __future__ import annotations

import logging
import re
from typing import Literal

import stripe
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator

from .config import get_settings

log = logging.getLogger(__name__)

_ICO_RE = re.compile(r"^\d{8}$")
_DIC_RE = re.compile(r"^\d{9,10}$")
_VAT_RE = re.compile(r"^[A-Z]{2}\d{8,12}$")  # napr. SK2024567890


class CheckoutRequest(BaseModel):
    price_id: str
    quantity: int = Field(default=1, ge=1, le=100)
    customer_type: Literal["firma", "osoba"]

    email: EmailStr

    # Common (povinné pre oba typy)
    address_line1: str = Field(min_length=1, max_length=255)
    address_city: str = Field(min_length=1, max_length=100)
    address_zip: str = Field(min_length=3, max_length=20)
    address_country: str = Field(default="SK", min_length=2, max_length=2)

    # Pre customer_type="osoba"
    name: str | None = None

    # Pre customer_type="firma"
    company_name: str | None = None
    ico: str | None = None
    dic: str | None = None
    vat_id: str | None = None  # IČ DPH, napr. "SK2024567890"

    success_url: str
    cancel_url: str

    # Voliteľná metadata propagovaná do Checkout Session (napr. project_input)
    metadata: dict[str, str] = Field(default_factory=dict)

    # Stripe-natívne polia ktoré frontend môže nastaviť
    client_reference_id: str | None = None        # Stripe ho echo-uje vo webhook payload
    allow_promotion_codes: bool = False           # pre voucher tier (napr. 24design 349 €)

    @field_validator("ico")
    @classmethod
    def _validate_ico(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.replace(" ", "")
        if not _ICO_RE.match(v):
            raise ValueError("IČO musí byť 8-ciferné číslo")
        return v

    @field_validator("dic")
    @classmethod
    def _validate_dic(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.replace(" ", "")
        if not _DIC_RE.match(v):
            raise ValueError("DIČ musí byť 9-10 ciferné číslo")
        return v

    @field_validator("vat_id")
    @classmethod
    def _validate_vat_id(cls, v: str | None) -> str | None:
        if v is None or v == "":
            return None
        v = v.replace(" ", "").upper()
        if not _VAT_RE.match(v):
            raise ValueError(
                "IČ DPH musí mať formát 2-pismenovej krajiny + 8-12 cifier (napr. SK2024567890)"
            )
        return v

    @field_validator("address_country")
    @classmethod
    def _validate_country(cls, v: str) -> str:
        return v.upper()

    @model_validator(mode="after")
    def _check_type_specific(self) -> CheckoutRequest:
        if self.customer_type == "firma":
            if not self.company_name or not self.company_name.strip():
                raise ValueError("Pre firmu je povinné pole 'company_name'")
            if not self.ico:
                raise ValueError("Pre firmu je povinné IČO")
        else:  # osoba
            if not self.name or not self.name.strip():
                raise ValueError("Pre fyzickú osobu je povinné pole 'name'")
        return self


def _customer_payload(req: CheckoutRequest) -> dict:
    """Postaví Stripe Customer create payload zo žiadosti."""
    settings = get_settings()  # noqa: F841 — referencia pre čitateľnosť
    metadata: dict[str, str] = {
        "customer_type": req.customer_type,
    }
    if req.customer_type == "firma":
        metadata["ico"] = req.ico or ""
        if req.dic:
            metadata["dic"] = req.dic
        display_name = req.company_name or req.name or req.email
    else:
        display_name = req.name or req.email

    payload: dict = {
        "email": str(req.email),
        "name": display_name,
        "address": {
            "line1": req.address_line1,
            "city": req.address_city,
            "postal_code": req.address_zip,
            "country": req.address_country,
        },
        "metadata": metadata,
    }
    return payload


def create_checkout(req: CheckoutRequest) -> dict:
    """Vytvorí Stripe Customer + Checkout Session, vráti checkout_url + session_id."""
    settings = get_settings()
    stripe.api_key = settings.stripe_api_key

    if req.price_id not in settings.allowed_price_ids_set:
        log.warning("price_id %s nie je v ALLOWED_PRICE_IDS", req.price_id)
        raise ValueError("price_id nie je povolený")

    customer = stripe.Customer.create(**_customer_payload(req))

    # Pridáme tax_id (IČ DPH) cez samostatný API call ak je vyplnený
    if req.vat_id:
        try:
            stripe.Customer.create_tax_id(customer.id, type="eu_vat", value=req.vat_id)
        except stripe.StripeError as e:
            # Stripe odmietne neplatné EU VAT — nezhadzujeme celý checkout, len logujeme
            log.warning(
                "Stripe odmietol IČ DPH %s pre customer %s: %s", req.vat_id, customer.id, e
            )

    session_args: dict = {
        "mode": "payment",
        "customer": customer.id,
        "line_items": [{"price": req.price_id, "quantity": req.quantity}],
        "success_url": req.success_url,
        "cancel_url": req.cancel_url,
        "metadata": {
            **req.metadata,
            "customer_type": req.customer_type,
            "price_id": req.price_id,
        },
        # billing_address_collection sa neuplatní (Customer ju má), ale pre istotu:
        "billing_address_collection": "auto",
        # Potlačíme Stripe receipt — SK faktúru si pošleme sami cez Brevo.
        # (Pozn.: pre úplnú istotu je potrebné aj Account-level Settings →
        # Customer emails → Successful payments OFF v Stripe dashboarde.)
        "payment_intent_data": {"receipt_email": ""},
    }
    if req.client_reference_id:
        session_args["client_reference_id"] = req.client_reference_id
    if req.allow_promotion_codes:
        session_args["allow_promotion_codes"] = True

    session = stripe.checkout.Session.create(**session_args)

    log.info(
        "vytvorený checkout session %s pre customer %s (%s)",
        session.id,
        customer.id,
        req.customer_type,
    )

    return {
        "checkout_url": session.url,
        "session_id": session.id,
        "customer_id": customer.id,
    }
