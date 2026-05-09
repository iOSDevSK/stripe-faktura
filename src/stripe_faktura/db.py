"""Setup SQLAlchemy a ORM modely pre záznamy faktúr."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import Column, DateTime, Integer, String, UniqueConstraint, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


class InvoiceRecord(Base):
    __tablename__ = "invoices"
    __table_args__ = (UniqueConstraint("stripe_session_id", name="ux_invoices_session"),)

    id = Column(Integer, primary_key=True, autoincrement=True)
    number = Column(String(32), unique=True, nullable=False, index=True)
    stripe_session_id = Column(String(128), nullable=False, index=True)
    stripe_customer_id = Column(String(128), nullable=True, index=True)
    stripe_payment_intent_id = Column(String(128), nullable=True)
    customer_email = Column(String(320), nullable=True, index=True)
    customer_name = Column(String(255), nullable=True)
    total_minor = Column(Integer, nullable=False)  # v haléroch (centoch)
    currency = Column(String(8), nullable=False)
    vat_mode = Column(String(16), nullable=False)  # 'platca' | 'neplatca'
    pdf_path = Column(String(1024), nullable=False)
    issued_at = Column(DateTime, nullable=False, default=dt.datetime.utcnow)
    emailed_at = Column(DateTime, nullable=True)


class NumberSequence(Base):
    __tablename__ = "number_sequences"

    year = Column(Integer, primary_key=True)
    last_seq = Column(Integer, nullable=False, default=0)


_engine = None
_SessionLocal: sessionmaker[Session] | None = None


def _build_engine():
    """Postaví SQLAlchemy engine, rešpektuje SQLite-špecifické connect args."""
    url = get_settings().database_url
    connect_args: dict = {}
    if url.startswith("sqlite"):
        connect_args["check_same_thread"] = False
    return create_engine(url, connect_args=connect_args, future=True)


def init_db() -> None:
    """Vytvorí tabuľky. Volaj raz pri štarte aplikácie."""
    global _engine, _SessionLocal
    if _engine is None:
        _engine = _build_engine()
        _SessionLocal = sessionmaker(bind=_engine, autoflush=False, autocommit=False)
    Base.metadata.create_all(_engine)


def get_session() -> Session:
    """Pomocník pre prístup k DB session — caller je zodpovedný za zatvorenie."""
    if _SessionLocal is None:
        init_db()
    assert _SessionLocal is not None
    return _SessionLocal()
