# Návod na integráciu pre 24design.sk

Postup od začiatku do konca, ako napojiť `stripe-faktura` na existujúci flow
24design.sk (Stripe Checkout + Brevo voucher emaily).

## Architektúra po integrácii

```
   24design.sk (website_sk)
            │
            ▼  Stripe Checkout platba
   Stripe webhook ── checkout.session.completed ──┬─► existujúci /stripe-webhook (Brevo)
                                                  │     ↳ vytvorí voucher pre zákazníka
                                                  │     ↳ pošle email adminovi + voucher
                                                  │
                                                  └─► NOVÝ /webhook/stripe (stripe-faktura)
                                                        ↳ načíta zákazníka + položky zo Stripe
                                                        ↳ vygeneruje SK PDF faktúru
                                                        ↳ pošle ju zákazníkovi emailom
```

Oba webhooky pália nezávisle. Žiadne prepojenie, žiadny zdieľaný stav.

## Postup

### 1. Nasaď stripe-faktura na Coolify

V projekte **Agency / production**:

- Vytvor novú aplikáciu z GitHubu: `iOSDevSK/stripe-faktura` (vetva `main`).
- Build pack: **Dockerfile**.
- Doména: `faktura.24design.sk` (wildcard CNAME `*.24design.sk` na Cloudflare to pokrýva).
- Trvalý volume: `/data` → ~1 GB.
- Environment premenné z `.env.example`. Pre 24design.sk konkrétne:

```env
STRIPE_API_KEY=sk_live_...                    # produkčný Stripe key
STRIPE_WEBHOOK_SECRET=whsec_...                # vyplníš v kroku 3

SUPPLIER_NAME=BELNEM s.r.o.
SUPPLIER_STREET=Beckovská 5
SUPPLIER_CITY=Bratislava
SUPPLIER_ZIP=82104
SUPPLIER_COUNTRY=SK
SUPPLIER_ICO=53713486
SUPPLIER_DIC=                                  # vyplň ak je pridelené
SUPPLIER_VAT_REGISTERED=false                  # prepneš keď sa staneš platcom DPH
SUPPLIER_REGISTRATION=Okresný súd Bratislava III, oddiel: Sro, vložka: 152437/B
SUPPLIER_BANK_NAME=...
SUPPLIER_IBAN=SK...
SUPPLIER_BIC=...
SUPPLIER_EMAIL=hello@24design.sk
SUPPLIER_PHONE=+421940877997
SUPPLIER_LOGO_URL=https://24design.sk/icon.png

# Použijeme rovnaký Brevo účet aký ide cez /order a /contact
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=hello@24design.sk
BREVO_SENDER_NAME=24design.sk
```

Nasaď. Over že `https://faktura.24design.sk/healthz` vráti `{"status":"ok"}`.

### 2. Uprav konfiguráciu Stripe Checkout Session

Uprav vytváranie Stripe Payment Linku alebo Checkout Session aby zahŕňalo:

- `billing_address_collection: 'required'`
- `tax_id_collection: { enabled: true }`
- `customer_creation: 'always'` (už nastavené podľa `STRIPE_INTEGRATION.md`)

Ak používaš Payment Link `plink_1TR5...`, uprav ho v Stripe Dashboarde:
- ✅ Zapni "Collect customer addresses" → Required
- ✅ Zapni "Collect tax IDs" → On

### 3. Pridaj druhý Stripe webhook endpoint

V Stripe Dashboarde → **Developers → Webhooks → Add endpoint**:

- URL: `https://faktura.24design.sk/webhook/stripe`
- Udalosti: `checkout.session.completed`
- Klikni **Save** → skopíruj nový **Signing secret** → nastav ako
  `STRIPE_WEBHOOK_SECRET` v Coolify env premenných stripe-faktura → redeploy.

Existujúci Brevo webhook (`<host>/stripe-webhook`) zostáva nedotknutý.
Stripe paralelne pália obidva endpointy.

### 4. Otestuj end-to-end

1. Otvor `https://24design.sk` v incognito režime.
2. Klikni "Web na kľúč 349 €" → Stripe Checkout.
3. Zaplať reálnou test kartou (alebo `4242 4242 4242 4242` v test móde), zadaj:
   - reálny email,
   - fakturačnú adresu,
   - voliteľne IČ DPH (napr. `SK2024567890`).
4. Do pár sekúnd over:
   - **Stránka `/thank-you`** sa zobrazí korektne (existujúce).
   - **Voucher email** príde do schránky zákazníka (existujúci Brevo flow).
   - **Email s faktúrou** príde do tej istej schránky s prílohou `faktura-20260001.pdf` (NOVÉ).
   - PDF obsahuje správne údaje dodávateľa, meno + adresu zákazníka + IČO/IČ DPH ak boli zadané, súčty, IBAN, VS.
5. Over zo strany stripe-faktura:
   - `GET https://faktura.24design.sk/invoices` zobrazuje nový riadok.
   - `GET https://faktura.24design.sk/invoices/20260001/pdf` vráti PDF.

### 5. (Voliteľné) Preskočiť faktúru pri voucheroch / refundoch

Niektoré Stripe sessiony by faktúru produkovať nemali (zadarmo vouchery,
interné testy a pod.). Nastav `metadata.no_invoice=true` na takých sessiónoch
a stripe-faktura ich ticho preskočí.

## Kde čo žije

| Funkcia | Služba | Súbor / lokácia |
|---|---|---|
| Vytvorenie voucheru + emaily | brevo-webhook (existujúci) | `helpers/brevo_order_webhook.py` |
| SK PDF faktúra + emaily | stripe-faktura (nový) | repo `iOSDevSK/stripe-faktura` |
| Konfigurácia Stripe Checkout | website_sk | `components/hero-section.tsx` + Payment Link config v Stripe Dashboarde |
| DNS | Cloudflare | wildcard `*.24design.sk` (proxied) |
