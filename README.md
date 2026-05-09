# stripe-faktura

> Slovak-compliant invoice generator for Stripe payments. Open-source. Self-hosted.

`stripe-faktura` is a small FastAPI service that listens to Stripe webhooks and
emits **Slovak-law-compliant PDF invoices** (zákon č. 222/2004 Z.z. o DPH,
zákon č. 431/2002 Z.z. o účtovníctve) directly to your customer's email after
a successful Checkout payment.

It supports both VAT modes:
- **Neplatca DPH** — adds the legal note "Nie som platiteľom DPH podľa § 4 z.č. 222/2004 Z.z."
- **Platca DPH** — breaks each line into base + 20 % VAT + gross.

**Stripe is the single source of truth.** All customer data (name, address,
IČO, DIČ, IČ DPH, line items, totals) is pulled from the Stripe API.
You just need to configure your Checkout to collect billing addresses
and tax IDs.

---

## Why?

Stripe's built-in invoices and receipts don't include fields the Slovak tax
authority requires: variabilný symbol, dátum dodania (DUZP), DPH breakdown
in EUR, IČO/DIČ of both parties, the "neplatca DPH" disclosure, etc.

Existing Slovak invoicing services (SuperFaktura, iKros, Pohoda) work fine
but lock you into their UI and pricing. This is a tiny self-hosted alternative
purpose-built for Stripe.

---

## Features (v0.1)

- ✅ Stripe webhook receiver with HMAC signature verification
- ✅ Auto-fetches customer + line items from Stripe API
- ✅ Sequential invoice numbering with year reset (`20260001`)
- ✅ WeasyPrint HTML→PDF rendering, fully customizable templates
- ✅ Idempotent (won't double-issue for the same Stripe session)
- ✅ Brevo or SMTP email delivery (your choice)
- ✅ Persistent storage (SQLite + local PDFs by default)
- ✅ REST API to list / fetch invoices and download PDFs
- ✅ Docker + docker-compose ready, single-image deploy

### Roadmap (v0.2+)

- Outbound webhook ("invoice ready" → POST your URL)
- S3 / MinIO / R2 storage
- Postgres support
- Refund → automatic credit note (dobropis)
- Multi-tenant API (one server, many suppliers)
- Czech VAT mode (CZ DPH 21 %)

---

## Quick start

### 1. Clone & configure

```bash
git clone https://github.com/iOSDevSK/stripe-faktura.git
cd stripe-faktura
cp .env.example .env
# Edit .env — fill in SUPPLIER_*, STRIPE_*, optionally BREVO_*
```

### 2. Run with Docker

```bash
docker compose up -d
# health check
curl http://localhost:8000/healthz
# {"status":"ok","version":"0.1.0"}
```

### 3. Point Stripe at it

In your Stripe dashboard → **Developers → Webhooks → Add endpoint**:

- URL: `https://your-host/webhook/stripe`
- Events: `checkout.session.completed`
- Copy the **Signing secret** (`whsec_...`) into `STRIPE_WEBHOOK_SECRET`.

### 4. Configure your Checkout Sessions

So the service has the data it needs to build a SK-compliant invoice:

```js
const session = await stripe.checkout.sessions.create({
  mode: 'payment',
  line_items: [{ price: 'price_xxx', quantity: 1 }],
  customer_creation: 'always',
  billing_address_collection: 'required',   // ← REQUIRED for invoices
  tax_id_collection: { enabled: true },     // ← so VAT IDs flow in
  success_url: '...',
  cancel_url: '...',
});
```

For B2B customers, also write `IČO` to `customer.metadata` after the session completes
(or before, if you create the Customer yourself):

```js
await stripe.customers.update(session.customer, {
  metadata: { ico: '12345678', dic: '2012345678' },
});
```

### 5. Test

Pay 0,50 € with a test card on your Stripe Checkout. Within seconds you should see:
- An invoice PDF in `data/pdfs/2026/20260001.pdf`.
- A row in `GET /invoices`.
- An email with the PDF attached (if Brevo/SMTP configured).

---

## Configuration

All configuration is via environment variables. See [`.env.example`](.env.example) for the full list.

### Required

| Variable | Description |
|---|---|
| `STRIPE_API_KEY` | Stripe secret key (`sk_test_...` or `sk_live_...`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (`whsec_...`) |
| `SUPPLIER_NAME` | Your company name |
| `SUPPLIER_STREET` `SUPPLIER_CITY` `SUPPLIER_ZIP` `SUPPLIER_COUNTRY` | Your address |
| `SUPPLIER_ICO` | Your IČO (Slovak company registration number) |
| `SUPPLIER_IBAN` | Bank account for invoices |
| `SUPPLIER_EMAIL` | Reply-to email for invoices |
| `SUPPLIER_VAT_REGISTERED` | `true` / `false` — switches VAT mode |

### Optional: VAT mode

If you're a VAT payer (`SUPPLIER_VAT_REGISTERED=true`):
- `SUPPLIER_VAT_ID` — your IČ DPH (e.g. `SK2024567890`)
- `VAT_RATE` — defaults to `20`

### Optional: Email

Pick one path. If both are unset, the service will store PDFs but won't email.

```env
# A) Brevo
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=hello@yourcompany.sk
BREVO_SENDER_NAME=Your Company

# B) SMTP
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=hello@yourcompany.sk
SMTP_FROM_NAME=Your Company
```

---

## API endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/webhook/stripe` | Stripe webhook receiver. Verifies `Stripe-Signature`. |
| `GET` | `/invoices` | List invoices (paginated). |
| `GET` | `/invoices/{number}` | Invoice metadata as JSON. |
| `GET` | `/invoices/{number}/pdf` | Download PDF. |
| `GET` | `/healthz` | Health check. |
| `GET` | `/docs` | Interactive OpenAPI docs (Swagger UI). |

If `READ_API_KEY` is set, all `GET /invoices*` endpoints require an
`X-API-Key` header.

---

## Stripe data mapping

| SK invoice field | Stripe source |
|---|---|
| Customer name / email | `customer.name` / `customer.email` |
| Customer address | `customer.address` (collected via `billing_address_collection`) |
| Customer IČO | `customer.metadata.ico` |
| Customer DIČ | `customer.metadata.dic` |
| Customer IČ DPH | `customer.tax_ids[].value` (type `eu_vat`) |
| Line items | `checkout.session.list_line_items` |
| Total + currency | `session.amount_total` + `session.currency` |
| Date of supply (DUZP) | `payment_intent.created` |

To skip invoice generation for a particular session, set
`metadata.no_invoice=true` on the Checkout Session.

---

## Development

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check src/ tests/
```

WeasyPrint requires Cairo + Pango. On macOS:
```bash
brew install cairo pango gdk-pixbuf libffi
```

---

## Deploy

Any Docker-compatible host works (Coolify, Fly.io, Railway, plain VPS).

For Coolify: see [`examples/coolify-deploy.md`](examples/coolify-deploy.md).
For 24design.sk-style integration: see [`examples/24design-sk-integration.md`](examples/24design-sk-integration.md).

---

## License

MIT — see [LICENSE](LICENSE).

---

## Slovak summary

`stripe-faktura` je open-source FastAPI server, ktorý po zaplatení cez Stripe
automaticky vystaví **slovenskú PDF faktúru so všetkými náležitosťami**
podľa § 74 zákona č. 222/2004 Z. z. (DPH) a § 10 zákona č. 431/2002 Z. z.
(účtovníctvo). Faktúra obsahuje IČO/DIČ/IČ DPH dodávateľa aj odberateľa,
DUZP, IBAN, variabilný a konštantný symbol, podporuje platcov aj neplatcov DPH.
Self-hosted, žiadne mesačné poplatky, PDF generuje WeasyPrint cez upraviteľné
HTML šablóny.

**Stripe je jediným zdrojom pravdy** — všetky údaje (zákazník, adresa, IČO,
DIČ, IČ DPH, položky) prídu zo Stripe API. Stačí v Checkout Session zapnúť
`billing_address_collection: 'required'` a `tax_id_collection: { enabled: true }`.

Pre **24design.sk** integrácia: nasadiť cez Coolify, pridať Stripe webhook na
`https://faktura.24design.sk/webhook/stripe`, hotovo.
