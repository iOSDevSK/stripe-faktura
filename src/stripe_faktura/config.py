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
    supplier_bank_name: str = ""
    supplier_iban: str = ""
    supplier_bic: str = ""
    supplier_ks: str = ""           # konštantný symbol; pre faktúry "0308"
    supplier_email: str
    supplier_phone: str = ""
    supplier_logo_url: str = ""
    # Lokálny súbor s logom — relatívne k templates/ adresáru, alebo absolutná cesta.
    # Príklad: "logo-24design.svg" (bundled v repe). Má prednosť pred supplier_logo_url.
    supplier_logo_path: str = ""

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

    # Comma-separated zoznam admin emailov ktoré dostanú BCC kópiu
    # každej odoslanej zákazníckej faktúry (s rovnakým PDF v prílohe).
    # Príklad: "hello@24design.sk,filip@designreadystudio.com"
    # Prázdne = žiadna admin kópia.
    admin_bcc_emails: str = ""

    # Airtable CRM — voliteľné. Ak je nakonfigurované, po vystavení faktúry
    # sa upsertne row do tabuľky cez `Stripe session ID` ako merge key.
    # Zápis je best-effort — pri zlyhaní sa loguje ale neblokuje webhook.
    airtable_api_key: str = ""
    airtable_base_id: str = ""
    airtable_table_id: str = ""

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

    # Checkout endpoint — bezpečnostný allowlist
    # Comma-separated zoznam origins ktorí smú volať POST /checkout.
    # Príklad: "https://24design.sk,https://24design.cz"
    allowed_origins: str = ""
    # Comma-separated zoznam Stripe price_id ktoré smú byť použité v /checkout.
    # Bráni útočníkovi vytvoriť session pre 0 € fake produkt.
    # Príklad: "price_1TR5miQ1nUjRL12CV3uVek2D,price_1TR5mSQ1nUjRL12C1OgEUkYj"
    allowed_price_ids: str = ""

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

    @property
    def admin_bcc_list(self) -> list[str]:
        return [e.strip() for e in self.admin_bcc_emails.split(",") if e.strip()]

    @property
    def allowed_origins_list(self) -> list[str]:
        return [o.strip() for o in self.allowed_origins.split(",") if o.strip()]

    @property
    def allowed_price_ids_set(self) -> set[str]:
        return {p.strip() for p in self.allowed_price_ids.split(",") if p.strip()}


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings


def generate_api_key() -> str:
    """Pomocná funkcia — vygeneruje silný náhodný API kľúč."""
    return secrets.token_urlsafe(32)
