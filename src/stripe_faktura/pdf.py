"""Vyrenderuje Invoice do PDF cez Jinja2 + WeasyPrint."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from weasyprint import HTML

from .invoice import Invoice

_TEMPLATE_DIR = Path(__file__).parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(["html", "xml"]),
    trim_blocks=True,
    lstrip_blocks=True,
)


def _format_money(amount: int | float, currency: str = "EUR") -> str:
    """Sformátuje sumu v haléroch ako `1 234,56 €` (slovenská konvencia)."""
    if isinstance(amount, int):
        whole, frac = divmod(amount, 100)
    else:
        # Decimal/float: rozdelí podľa desatinnej čiarky
        whole = int(amount)
        frac = int(round((float(amount) - whole) * 100))
    sign = "-" if whole < 0 else ""
    whole = abs(whole)
    s = f"{whole:,}".replace(",", " ")  # medzera ako tisícny oddeľovač
    sym = "€" if currency.upper() == "EUR" else currency.upper()
    return f"{sign}{s},{frac:02d} {sym}"


_env.filters["money"] = _format_money


def render_invoice_pdf(invoice: Invoice) -> bytes:
    """Vyber správnu šablónu podľa režimu DPH, vyrenderuj HTML, vyrob PDF."""
    template_name = (
        "invoice_sk_platca.html" if invoice.vat_registered else "invoice_sk_neplatca.html"
    )
    template = _env.get_template(template_name)
    html_str = template.render(invoice=invoice)
    return HTML(
        string=html_str,
        base_url=str(_TEMPLATE_DIR),
    ).write_pdf()
