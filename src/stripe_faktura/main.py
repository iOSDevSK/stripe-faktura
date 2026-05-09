"""FastAPI aplikácia — routy a startup."""

from __future__ import annotations

import logging
from typing import Annotated

import stripe
from fastapi import FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import ValidationError
from sqlalchemy import desc, select

from . import __version__, email as email_dispatcher
from . import pdf as pdf_render
from . import pdf_token, webhook
from .checkout import CheckoutRequest, create_checkout
from .config import get_settings
from .db import InvoiceRecord, get_session, init_db
from .invoice import Address, Customer, Invoice, LineItem
from .numbering import variable_symbol_from

log = logging.getLogger("stripe_faktura")
logging.basicConfig(level=get_settings().log_level)

app = FastAPI(
    title="stripe-faktura",
    version=__version__,
    description="Generátor slovenských faktúr pre Stripe platby",
    docs_url="/docs",
    redoc_url=None,
)

_origins = get_settings().allowed_origins_list
if _origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=_origins,
        allow_credentials=False,
        allow_methods=["POST", "OPTIONS"],
        allow_headers=["Content-Type"],
        max_age=3600,
    )


@app.on_event("startup")
def _startup() -> None:
    init_db()
    log.info("stripe-faktura %s spustená", __version__)


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/webhook/stripe")
async def stripe_webhook(request: Request) -> JSONResponse:
    """Stripe webhook receiver. Overuje HMAC podpis cez `Stripe-Signature` hlavičku
    a timestamp toleranciu (5 min) — bez webhook secret-u nikto iný nepošle valid request.
    """
    settings = get_settings()
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    try:
        event = stripe.Webhook.construct_event(
            payload=payload,
            sig_header=sig_header,
            secret=settings.stripe_webhook_secret,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail="neplatné telo požiadavky") from e
    except stripe.SignatureVerificationError as e:
        raise HTTPException(status_code=400, detail="neplatný podpis") from e

    event_type = event["type"]
    if event_type != "checkout.session.completed":
        return JSONResponse({"ok": True, "ignored": event_type})

    try:
        result = webhook.handle_checkout_completed(event)
    except Exception as e:  # noqa: BLE001
        log.exception("spracovanie webhooku zlyhalo pre event %s", event["id"])
        raise HTTPException(status_code=500, detail="chyba spracovania") from e

    return JSONResponse(result)


@app.post("/checkout")
async def create_checkout_session(request: Request) -> JSONResponse:
    """Vytvorí Stripe Customer + Checkout Session s SK billing údajmi.

    Bezpečnosť (defense in depth):
      - Origin musí byť v ALLOWED_ORIGINS (CORS middleware už blokuje cudzie origins,
        ale serverový check je dodatočná vrstva).
      - price_id musí byť v ALLOWED_PRICE_IDS — útočník nemôže vytvoriť 0 € session.
      - Validácia formátu IČO/DIČ/IČ DPH cez pydantic.
    """
    settings = get_settings()

    # Server-side Origin check (CORS sa preklíkne pri preflight, ale Origin sa posiela aj na POST)
    origin = request.headers.get("origin", "")
    if settings.allowed_origins_list and origin not in settings.allowed_origins_list:
        log.warning("/checkout odmietnutý — origin %r nie je povolený", origin)
        raise HTTPException(status_code=403, detail="origin nie je povolený")

    if not settings.allowed_price_ids_set:
        raise HTTPException(
            status_code=503,
            detail="ALLOWED_PRICE_IDS nie je nakonfigurované — endpoint je vypnutý",
        )

    body = await request.json()
    try:
        req = CheckoutRequest(**body)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=e.errors()) from e

    try:
        result = create_checkout(req)
    except ValueError as e:
        # napr. price_id nie je v allowliste
        raise HTTPException(status_code=403, detail=str(e)) from e
    except stripe.StripeError as e:
        log.exception("Stripe API zlyhalo v /checkout")
        raise HTTPException(status_code=502, detail="Stripe API chyba") from e

    return JSONResponse(result)


def _require_api_key(x_api_key: str | None) -> None:
    """Overí X-API-Key hlavičku proti READ_API_KEY (povinné)."""
    expected = get_settings().read_api_key
    if x_api_key != expected:
        raise HTTPException(status_code=401, detail="neautorizovaný prístup")


@app.get("/invoices")
def list_invoices(
    x_api_key: Annotated[str | None, Header()] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    """Výpis všetkých faktúr — admin operácia, vyžaduje X-API-Key."""
    _require_api_key(x_api_key)
    db = get_session()
    try:
        rows = db.scalars(
            select(InvoiceRecord).order_by(desc(InvoiceRecord.id)).limit(limit).offset(offset)
        ).all()
        return {
            "items": [
                {
                    "number": r.number,
                    "customer_email": r.customer_email,
                    "total_minor": r.total_minor,
                    "currency": r.currency,
                    "vat_mode": r.vat_mode,
                    "issued_at": r.issued_at.isoformat() if r.issued_at else None,
                    "emailed_at": r.emailed_at.isoformat() if r.emailed_at else None,
                    "stripe_session_id": r.stripe_session_id,
                    "pdf_url": pdf_token.pdf_url(r.number),
                }
                for r in rows
            ]
        }
    finally:
        db.close()


@app.get("/invoices/{number}")
def get_invoice(
    number: str,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Detail faktúry — admin operácia, vyžaduje X-API-Key."""
    _require_api_key(x_api_key)
    db = get_session()
    try:
        r = db.scalars(select(InvoiceRecord).where(InvoiceRecord.number == number)).first()
        if not r:
            raise HTTPException(status_code=404, detail="faktúra nenájdená")
        return {
            "number": r.number,
            "customer_email": r.customer_email,
            "customer_name": r.customer_name,
            "total_minor": r.total_minor,
            "currency": r.currency,
            "vat_mode": r.vat_mode,
            "issued_at": r.issued_at.isoformat() if r.issued_at else None,
            "emailed_at": r.emailed_at.isoformat() if r.emailed_at else None,
            "stripe_session_id": r.stripe_session_id,
            "stripe_customer_id": r.stripe_customer_id,
            "stripe_payment_intent_id": r.stripe_payment_intent_id,
            "pdf_url": pdf_token.pdf_url(r.number),
        }
    finally:
        db.close()


@app.post("/admin/test-send-invoice")
async def admin_test_send_invoice(
    request: Request,
    x_api_key: Annotated[str | None, Header()] = None,
) -> dict:
    """Admin endpoint pre sanity test PDF + email pipeline.

    NEVYTVÁRA Stripe Customer/Session a NEZAPISUJE do DB ako reálnu faktúru.
    Slúži na overenie že WeasyPrint správne vyrenderuje SK template
    a Brevo/SMTP pošle email s prílohou. Vyžaduje X-API-Key.

    Body príklad:
      {
        "customer": {
          "name": "Filip Dvoran",
          "email": "filip.dvoran@gmail.com",
          "address": {"line1": "Čilžská 1", "city": "Bratislava", "zip": "82107", "country": "SK"},
          "ico": "12345678",   // voliteľné
          "dic": "",           // voliteľné
          "vat_id": ""         // voliteľné, IČ DPH
        },
        "items": [
          {"description": "Web na kľúč", "quantity": 1, "unit_price_minor": 34900, "currency": "eur"}
        ],
        "send_email": true     // ak false, len vráti info o vyrenderovanom PDF
      }
    """
    import datetime as dt

    _require_api_key(x_api_key)
    settings = get_settings()
    body = await request.json()

    cust_data = body.get("customer") or {}
    items_data = body.get("items") or []
    if not cust_data.get("email"):
        raise HTTPException(status_code=400, detail="customer.email je povinné")
    if not items_data:
        raise HTTPException(status_code=400, detail="items[] musí mať aspoň 1 položku")

    addr_data = cust_data.get("address") or {}
    customer = Customer(
        name=cust_data.get("name") or "",
        email=cust_data.get("email"),
        address=(
            Address(
                line1=addr_data.get("line1", ""),
                city=addr_data.get("city", ""),
                zip=addr_data.get("zip", ""),
                country=addr_data.get("country", "SK"),
            )
            if addr_data
            else None
        ),
        ico=cust_data.get("ico") or "",
        dic=cust_data.get("dic") or "",
        vat_id=cust_data.get("vat_id") or "",
    )

    items = [
        LineItem(
            description=i["description"],
            quantity=int(i["quantity"]),
            unit_price_minor=int(i["unit_price_minor"]),
            currency=i.get("currency", "eur"),
        )
        for i in items_data
    ]

    today = dt.date.today()
    test_number = "TEST-" + dt.datetime.now().strftime("%Y%m%d-%H%M%S")
    invoice = Invoice(
        number=test_number,
        variable_symbol=variable_symbol_from(test_number) or "9999999999",
        issued_at=today,
        delivered_at=today,
        due_at=today,
        supplier=webhook._supplier_from_settings(),
        customer=customer,
        items=items,
        currency=items[0].currency,
        vat_rate=settings.vat_rate,
        vat_registered=settings.supplier_vat_registered,
        payment_method="Platba kartou (Stripe) — TEST",
        is_paid=True,
    )

    pdf_bytes = pdf_render.render_invoice_pdf(invoice)

    emailed_via = "none"
    email_error: str | None = None
    if body.get("send_email", True) and settings.email_enabled:
        try:
            emailed_via = email_dispatcher.send_invoice_email(
                invoice=invoice, pdf_bytes=pdf_bytes
            )
        except Exception as e:  # noqa: BLE001
            log.exception("test send-invoice: email zlyhalo")
            email_error = str(e)

    return {
        "ok": True,
        "test_invoice_number": test_number,
        "pdf_size_bytes": len(pdf_bytes),
        "vat_mode": "platca" if settings.supplier_vat_registered else "neplatca",
        "emailed_via": emailed_via,
        "email_error": email_error,
        "customer_email": customer.email,
    }


@app.get("/invoices/{number}/pdf")
def get_invoice_pdf(
    number: str,
    token: Annotated[str | None, Query()] = None,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Response:
    """Stiahnutie PDF — autorizácia jedným z dvoch spôsobov:
    1. `X-API-Key` hlavička s `READ_API_KEY` (pre admin / interné systémy).
    2. `?token=<HMAC>` query param (pre verejné linky v emailoch zákazníkom).
    """
    settings = get_settings()
    api_key_ok = x_api_key == settings.read_api_key
    token_ok = pdf_token.verify_pdf_token(number, token or "")
    if not (api_key_ok or token_ok):
        raise HTTPException(status_code=401, detail="neautorizovaný prístup")

    db = get_session()
    try:
        r = db.scalars(select(InvoiceRecord).where(InvoiceRecord.number == number)).first()
        if not r:
            raise HTTPException(status_code=404, detail="faktúra nenájdená")
        return FileResponse(
            r.pdf_path,
            media_type="application/pdf",
            filename=f"faktura-{r.number}.pdf",
        )
    finally:
        db.close()
