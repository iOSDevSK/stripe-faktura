# 24design.sk integration guide

End-to-end steps to plug `stripe-faktura` into the existing 24design.sk
payment flow (Stripe Checkout + Brevo voucher emails).

## Architecture after integration

```
   24design.sk (website_sk)
            │
            ▼  Stripe Checkout payment
   Stripe webhook ── checkout.session.completed ──┬─► existing /stripe-webhook (Brevo)
                                                  │     ↳ creates per-customer voucher
                                                  │     ↳ emails admin + voucher
                                                  │
                                                  └─► NEW /webhook/stripe (stripe-faktura)
                                                        ↳ pulls customer + items from Stripe
                                                        ↳ generates SK PDF invoice
                                                        ↳ emails customer with PDF
```

Both webhooks fire independently. No coupling, no shared state.

## Steps

### 1. Deploy stripe-faktura on Coolify

In project **Agency / production**:

- Create a new application from GitHub: `iOSDevSK/stripe-faktura` (main branch).
- Build pack: **Dockerfile**.
- Domain: `faktura.24design.sk` (the `*.24design.sk` wildcard CNAME on Cloudflare covers it).
- Persistent volume: `/data` → ~1 GB.
- Env vars from `.env.example`, with these specifically for 24design.sk:

```env
STRIPE_API_KEY=sk_live_...                    # production Stripe key
STRIPE_WEBHOOK_SECRET=whsec_...                # set after step 3

SUPPLIER_NAME=BELNEM s.r.o.
SUPPLIER_STREET=Beckovská 5
SUPPLIER_CITY=Bratislava
SUPPLIER_ZIP=82104
SUPPLIER_COUNTRY=SK
SUPPLIER_ICO=53713486
SUPPLIER_DIC=                                  # fill if assigned
SUPPLIER_VAT_REGISTERED=false                  # toggle when registered
SUPPLIER_REGISTRATION=Okresný súd Bratislava III, oddiel: Sro, vložka: 152437/B
SUPPLIER_BANK_NAME=...
SUPPLIER_IBAN=SK...
SUPPLIER_BIC=...
SUPPLIER_EMAIL=hello@24design.sk
SUPPLIER_PHONE=+421940877997
SUPPLIER_LOGO_URL=https://24design.sk/icon.png

# Reuse the same Brevo account that powers /order and /contact
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=hello@24design.sk
BREVO_SENDER_NAME=24design.sk
```

Deploy. Verify `https://faktura.24design.sk/healthz` returns `{"status":"ok"}`.

### 2. Update the Stripe Checkout Session config

Edit the Stripe Payment Link or Checkout Session creation to include:

- `billing_address_collection: 'required'`
- `tax_id_collection: { enabled: true }`
- `customer_creation: 'always'` (already set per `STRIPE_INTEGRATION.md`)

If you use the Payment Link `plink_1TR5...`, edit it in the Stripe Dashboard:
- ✅ Toggle "Collect customer addresses" → Required
- ✅ Toggle "Collect tax IDs" → On

### 3. Add the second Stripe webhook endpoint

In Stripe Dashboard → **Developers → Webhooks → Add endpoint**:

- URL: `https://faktura.24design.sk/webhook/stripe`
- Events: `checkout.session.completed`
- Click **Save** → copy the new **Signing secret** → set as
  `STRIPE_WEBHOOK_SECRET` in stripe-faktura Coolify env vars → redeploy.

The existing Brevo webhook (`<host>/stripe-webhook`) stays untouched.
Stripe fires both endpoints in parallel.

### 4. Test end-to-end

1. Open `https://24design.sk` in incognito.
2. Click "Web na kľúč 349 €" → Stripe Checkout.
3. Pay with a real test card (or 4242 4242 4242 4242 in test mode), enter:
   - real email,
   - billing address,
   - optionally a VAT ID (e.g. `SK2024567890`).
4. Within a few seconds, verify:
   - **`/thank-you`** page renders correctly (existing).
   - **Voucher email** lands in customer inbox (existing Brevo flow).
   - **Invoice email** lands in same inbox with `faktura-20260001.pdf` attached (NEW).
   - The PDF includes correct supplier info, customer name + address + IČO/IČ DPH if entered, totals, IBAN, VS.
5. Verify on stripe-faktura side:
   - `GET https://faktura.24design.sk/invoices` lists the new row.
   - `GET https://faktura.24design.sk/invoices/20260001/pdf` returns the PDF.

### 5. (Optional) Skip invoice for vouchers / refunds

Some Stripe sessions shouldn't produce invoices (free vouchers, internal tests, etc.).
Set `metadata.no_invoice=true` on those sessions and stripe-faktura will skip them silently.

## Where things live

| Concern | Service | File / location |
|---|---|---|
| Voucher creation + emails | brevo-webhook (existing) | `helpers/brevo_order_webhook.py` |
| SK PDF invoice + emails | stripe-faktura (new) | `iOSDevSK/stripe-faktura` repo |
| Stripe Checkout config | website_sk | `components/hero-section.tsx` + Stripe Dashboard Payment Link config |
| DNS | Cloudflare | wildcard `*.24design.sk` (proxied) |
