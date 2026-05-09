"""Settings loaded from environment variables (and .env in dev)."""

from __future__ import annotations

from pydantic import Field
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

    # Supplier
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

    # Invoice
    invoice_number_format: str = "{year}{seq:04d}"
    invoice_language: str = "sk"
    vat_rate: int = 20

    # Database
    database_url: str = "sqlite:////data/invoices.db"

    # Storage
    storage_backend: str = "local"  # local | s3
    storage_local_path: str = "/data/pdfs"
    s3_endpoint: str = ""
    s3_bucket: str = ""
    s3_key: str = ""
    s3_secret: str = ""

    # Email — Brevo (option A)
    brevo_api_key: str = ""
    brevo_sender_email: str = ""
    brevo_sender_name: str = ""

    # Email — SMTP (option B)
    smtp_host: str = ""
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from_email: str = ""
    smtp_from_name: str = ""

    # Auth
    read_api_key: str = ""

    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    log_level: str = "INFO"

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
