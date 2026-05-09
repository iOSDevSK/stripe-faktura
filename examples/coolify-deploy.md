# Deploying stripe-faktura on Coolify

Step-by-step for any Coolify v4+ instance.

## 1. Create the application

In Coolify dashboard:

1. Project → **+ New Resource** → **Public Repository** (or **Private GitHub App** if you've installed Coolify on your GitHub account).
2. Repository: `https://github.com/iOSDevSK/stripe-faktura` (or your fork).
3. Branch: `main`
4. Build pack: **Dockerfile** (auto-detected from the `Dockerfile` in repo root).
5. Domain: e.g. `faktura.example.com`.
6. Port: `8000`.

## 2. Add a persistent volume

In the new app's **Storage** tab:

- Click **+ Add** → **Persistent Volume**.
- Mount path: `/data`
- Size: 1 GB (raise as your invoice archive grows).

This stores the SQLite DB + all generated PDFs. Surviving redeploys.

## 3. Configure environment variables

Copy the keys from `.env.example` into Coolify's **Environment Variables**.
At a minimum:

```
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...   # filled in step 5

SUPPLIER_NAME=...
SUPPLIER_STREET=...
SUPPLIER_CITY=...
SUPPLIER_ZIP=...
SUPPLIER_COUNTRY=SK
SUPPLIER_ICO=...
SUPPLIER_VAT_REGISTERED=false
SUPPLIER_BANK_NAME=...
SUPPLIER_IBAN=...
SUPPLIER_BIC=...
SUPPLIER_EMAIL=...

# Pick one email path:
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=hello@yourcompany.sk
BREVO_SENDER_NAME=Your Company
```

Click **Save** → **Redeploy**.

## 4. Verify health

```bash
curl https://faktura.example.com/healthz
# {"status":"ok","version":"0.1.0"}
```

If you see a Cloudflare 502 or similar, check Coolify logs for the container.
Likely missing env vars (config validation fails on startup).

## 5. Register the Stripe webhook

In Stripe Dashboard → **Developers → Webhooks → + Add endpoint**:

- Endpoint URL: `https://faktura.example.com/webhook/stripe`
- Events to send: `checkout.session.completed`
- Save → copy the **Signing secret** (`whsec_...`) into the
  `STRIPE_WEBHOOK_SECRET` env var in Coolify → redeploy.

## 6. Behind Cloudflare?

If `faktura.example.com` is proxied by Cloudflare (orange cloud), make sure:

- **Bot Fight Mode** is **OFF** (or scope a Skip rule for this hostname);
  Stripe-Signature requests look bot-ish to Cloudflare's heuristics.
- **Cache Rules**: not strictly needed (the app sets `cache-control: no-cache`),
  but adding a "Bypass cache" rule for this hostname is a nice safety net.

## 7. (Optional) Restrict reads

Set `READ_API_KEY=...` to require an `X-API-Key` header on all `GET /invoices*`
routes. The Stripe webhook is always open (Stripe authenticates via signature).
