FROM python:3.12-slim AS base

# WeasyPrint runtime deps: Cairo, Pango, GDK-PixBuf, fonts
# (see https://doc.courtbouillon.org/weasyprint/stable/first_steps.html)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    fonts-dejavu \
    fonts-liberation \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps separately for better layer caching
COPY pyproject.toml ./
RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir \
        "fastapi>=0.115" \
        "uvicorn[standard]>=0.32" \
        "pydantic>=2.9" \
        "pydantic-settings>=2.6" \
        "stripe>=11.0" \
        "weasyprint>=63" \
        "jinja2>=3.1" \
        "sqlalchemy>=2.0" \
        "httpx>=0.27" \
        "python-multipart>=0.0.12"

# Copy source
COPY src/ ./src/

# Persistent data volume (SQLite + PDFs)
RUN mkdir -p /data/pdfs && chmod 755 /data
VOLUME ["/data"]

ENV PYTHONPATH=/app/src
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import httpx; httpx.get('http://localhost:8000/healthz').raise_for_status()" || exit 1

CMD ["uvicorn", "stripe_faktura.main:app", "--host", "0.0.0.0", "--port", "8000"]
