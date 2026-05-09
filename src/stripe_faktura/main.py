"""FastAPI aplikácia — routy a startup."""

from __future__ import annotations

import logging
from typing import Annotated

import stripe
from fastapi import FastAPI, Header, HTTPException, Request, Response
from fastapi.responses import FileResponse, JSONResponse
from sqlalchemy import desc, select

from . import __version__, webhook
from .config import get_settings
from .db import InvoiceRecord, get_session, init_db

log = logging.getLogger("stripe_faktura")
logging.basicConfig(level=get_settings().log_level)

app = FastAPI(
    title="stripe-faktura",
    version=__version__,
    description="Generátor slovenských faktúr pre Stripe platby",
    docs_url="/docs",
    redoc_url=None,
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
        # Potvrdíme príjem bez akcie — Stripe očakáva 2xx
        return JSONResponse({"ok": True, "ignored": event_type})

    try:
        result = webhook.handle_checkout_completed(event)
    except Exception as e:  # noqa: BLE001
        log.exception("spracovanie webhooku zlyhalo pre event %s", event["id"])
        # 5xx spôsobí že Stripe pošle webhook znova — to chceme
        raise HTTPException(status_code=500, detail="chyba spracovania") from e

    return JSONResponse(result)


def _check_read_auth(x_api_key: str | None) -> None:
    expected = get_settings().read_api_key
    if expected and x_api_key != expected:
        raise HTTPException(status_code=401, detail="neautorizovaný prístup")


@app.get("/invoices")
def list_invoices(
    x_api_key: Annotated[str | None, Header()] = None,
    limit: int = 50,
    offset: int = 0,
) -> dict:
    _check_read_auth(x_api_key)
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
    _check_read_auth(x_api_key)
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
            "pdf_url": f"/invoices/{r.number}/pdf",
        }
    finally:
        db.close()


@app.get("/invoices/{number}/pdf")
def get_invoice_pdf(
    number: str,
    x_api_key: Annotated[str | None, Header()] = None,
) -> Response:
    _check_read_auth(x_api_key)
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
