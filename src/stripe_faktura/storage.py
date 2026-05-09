"""PDF storage backend — local filesystem for MVP, S3 hookable later."""

from __future__ import annotations

from pathlib import Path

from .config import get_settings


def store_pdf(*, year: int, invoice_number: str, pdf_bytes: bytes) -> str:
    """Persist PDF and return its absolute path (or s3 URL later)."""
    settings = get_settings()
    if settings.storage_backend != "local":
        raise NotImplementedError(f"storage_backend={settings.storage_backend} not yet supported")

    base = Path(settings.storage_local_path) / str(year)
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / f"{invoice_number}.pdf"
    out_path.write_bytes(pdf_bytes)
    return str(out_path)


def read_pdf(path: str) -> bytes:
    p = Path(path)
    return p.read_bytes()
