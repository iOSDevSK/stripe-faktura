"""Test sequential invoice numbering with year reset."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from stripe_faktura.db import Base
from stripe_faktura.numbering import next_invoice_number, variable_symbol_from


def _session_factory(url: str):
    engine = create_engine(url, connect_args={"check_same_thread": False}, future=True)
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, autocommit=False)


def test_sequence_starts_at_one(tmp_db_url):
    SessionLocal = _session_factory(tmp_db_url)
    s = SessionLocal()
    try:
        n = next_invoice_number(s, now=dt.datetime(2026, 1, 1))
        s.commit()
        assert n == "20260001"
    finally:
        s.close()


def test_sequence_increments(tmp_db_url):
    SessionLocal = _session_factory(tmp_db_url)
    s = SessionLocal()
    try:
        a = next_invoice_number(s, now=dt.datetime(2026, 5, 9))
        b = next_invoice_number(s, now=dt.datetime(2026, 5, 9))
        c = next_invoice_number(s, now=dt.datetime(2026, 5, 9))
        s.commit()
        assert a == "20260001"
        assert b == "20260002"
        assert c == "20260003"
    finally:
        s.close()


def test_sequence_resets_each_year(tmp_db_url):
    SessionLocal = _session_factory(tmp_db_url)
    s = SessionLocal()
    try:
        a = next_invoice_number(s, now=dt.datetime(2026, 12, 31))
        b = next_invoice_number(s, now=dt.datetime(2026, 12, 31))
        c = next_invoice_number(s, now=dt.datetime(2027, 1, 1))
        d = next_invoice_number(s, now=dt.datetime(2027, 1, 1))
        s.commit()
        assert a == "20260001"
        assert b == "20260002"
        assert c == "20270001"
        assert d == "20270002"
    finally:
        s.close()


def test_variable_symbol_strips_non_digits():
    assert variable_symbol_from("20260042") == "20260042"
    assert variable_symbol_from("FA-2026-0042") == "20260042"
    assert variable_symbol_from("2026/0042") == "20260042"
