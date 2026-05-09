"""Year-resetting sequential invoice numbering, transactional via SQLite/Postgres."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .config import get_settings
from .db import NumberSequence


def next_invoice_number(session: Session, *, now: dt.datetime | None = None) -> str:
    """
    Return the next invoice number formatted via INVOICE_NUMBER_FORMAT.

    Sequence resets each calendar year. Concurrency-safe within a single DB
    transaction (caller commits). For multi-replica deployments, use Postgres
    with SELECT FOR UPDATE — adapt this function accordingly.
    """
    fmt = get_settings().invoice_number_format
    now = now or dt.datetime.utcnow()
    year = now.year

    row = session.get(NumberSequence, year)
    if row is None:
        row = NumberSequence(year=year, last_seq=0)
        session.add(row)
        session.flush()

    row.last_seq = (row.last_seq or 0) + 1
    seq = row.last_seq
    session.flush()

    return fmt.format(year=year, seq=seq)


def variable_symbol_from(invoice_number: str) -> str:
    """
    Slovak Variabilný symbol must be numeric (max 10 digits). Strip non-digits
    from the invoice number to produce a valid VS.
    """
    digits = "".join(ch for ch in invoice_number if ch.isdigit())
    return digits[-10:] if len(digits) > 10 else digits
