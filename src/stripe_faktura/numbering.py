"""Sekvenčné číslovanie faktúr s ročným resetom, transakčné v SQLite/Postgres."""

from __future__ import annotations

import datetime as dt

from sqlalchemy.orm import Session

from .config import get_settings
from .db import NumberSequence


def next_invoice_number(session: Session, *, now: dt.datetime | None = None) -> str:
    """
    Vráti nasledujúce číslo faktúry naformátované podľa INVOICE_NUMBER_FORMAT.

    Sekvencia sa resetuje každý kalendárny rok. Bezpečné pri konkurencii v rámci
    jednej DB transakcie (caller commitne). Pre multi-replica deployment použi
    Postgres so SELECT FOR UPDATE — túto funkciu zodpovedajúco uprav.
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
    Slovenský variabilný symbol musí byť numerický (max 10 cifier). Z čísla
    faktúry vyhodí všetky nečíslicové znaky a vráti posledných 10 cifier.
    """
    digits = "".join(ch for ch in invoice_number if ch.isdigit())
    return digits[-10:] if len(digits) > 10 else digits
