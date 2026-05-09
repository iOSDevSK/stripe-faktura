"""Konfigurácia načítaná z environment premenných (a `.env` v dev móde)."""

from __future__ import annotations

import secrets

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Stripe
    stripe_api_key: str
    stripe_webhook_secret: str

    # Dodávateľ
    supplier_name: str
    supplier_street: str
    supplier_city: str
    supplier_zip: str
    supplier_country: str = "SK"
    supplier_ico: str
    supplier_dic: str = ""
    supplier_vat_registered: bool = False
    supplier_vat_id: str = ""
    supplier_registration: str = ""
    supplier_bank_name: str
    supplier_iban: str
    supplier_bic: str = ""
    supplier_email: str
    supplier_phone: str = ""
    supplier_logo_url: str = ""

    # Faktúra
    invoice_number_format: str = "{year}{seq:04d}"
    invoice_language: str = "sk"
    vat_rate: int = 20

    # Databáza
    database_url: str = "sqlite:////data/invoices.db"

    # Úložisko
    storage_backend: str = "local"  # local | s3
    storage_local_path: str = "/data/pdfs"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_key: str = ""
    s3_secret: str = ""

    # Email — Brevo (možnosť A)
    brevo_api_key: str = ""
    brevo_sender_email: str = ""
    brevo_sender_name: str = ""

    # Email — SMTP (možnosť B)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = ""

    # Bezpečnosť — POVINNÉ
    # Bez READ_API_KEY by čítacie endpointy boli verejné a ktokoľvek
    # by uhádol postupné čísla faktúr (20260001...) a stiahol PII.
    read_api_key: str
    # Voliteľný dedikovaný secret pre HMAC PDF tokeny.
    # Ak prázdne, odvodí sa zo STRIPE_WEBHOOK_SECRET.
    pdf_token_secret: str = ""

    # Verejná URL aplikácie (pre linky v emaili). Napr. https://faktura.24design.sk
    base_url: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

    @field_validator("read_api_key")
    @classmethod
    def _read_api_key_strong(cls, v: str) -> str:
        if not v or len(v) < 16:
            raise ValueError(
                "READ_API_KEY musí byť nastavený a mať aspoň 16 znakov. "
                "Vygeneruj cez: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
            )
        return v

    @property
    def email_enabled(self) -> bool:
        return bool(self.brevo_api_key) or bool(self.smtp_host)

    @property
    def email_provider(self) -> str:
        if self.brevo_api_key:
            return "brevo"
        if self.smtp_host:
            return "smtp"
        return "none"


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def generate_api_key() -> str:
    """Pomocná funkcia — vygeneruje silný náhodný API kľúč."""
    return secrets.token_urlsafe(32)
