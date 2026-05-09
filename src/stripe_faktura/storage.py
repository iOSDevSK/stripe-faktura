"""Backend pre úložisko PDF — pre MVP lokálny filesystem, S3 pripravený neskôr."""

from __future__ import annotations

from pathlib import Path

from .config import get_settings


def store_pdf(*, year: int, invoice_number: str, pdf_bytes: bytes) -> str:
    """Uloží PDF a vráti jeho absolútnu cestu (alebo s3 URL neskôr)."""
    settings = get_settings()
    if settings.storage_backend != "local":
        raise NotImplementedError(f"storage_backend={settings.storage_backend} zatiaľ nie je podporované")

    base = Path(settings.storage_local_path) / str(year)
    base.mkdir(parents=True, exist_ok=True)
    out_path = base / f"{invoice_number}.pdf"
    out_path.write_bytes(pdf_bytes)
    return str(out_path)


def read_pdf(path: str) -> bytes:
    p = Path(path)
    return p.read_bytes()
