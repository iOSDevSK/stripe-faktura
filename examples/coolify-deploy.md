# Nasadenie stripe-faktura na Coolify

Krok-za-krokom pre akúkoľvek Coolify v4+ inštanciu.

## 1. Vytvor aplikáciu

V Coolify dashboarde:

1. Project → **+ New Resource** → **Public Repository** (alebo **Private GitHub App** ak máš Coolify napojené na svoj GitHub účet).
2. Repository: `https://github.com/iOSDevSK/stripe-faktura` (alebo tvoj fork).
3. Vetva: `main`
4. Build pack: **Dockerfile** (autodetekcia z `Dockerfile` v koreňi repa).
5. Doména: napr. `faktura.example.com`.
6. Port: `8000`.

## 2. Pridaj trvalý volume

V karte **Storage** novej aplikácie:

- Klikni **+ Add** → **Persistent Volume**.
- Mount path: `/data`
- Veľkosť: 1 GB (zvýš keď ti rastie archív faktúr).

Tu sa ukladá SQLite DB + všetky vygenerované PDF. Prežije redeploy.

## 3. Nakonfiguruj environment premenné

Skopíruj kľúče z `.env.example` do **Environment Variables** v Coolify.
Minimálne:

```
STRIPE_API_KEY=sk_live_...
STRIPE_WEBHOOK_SECRET=whsec_...   # vyplníš v kroku 5

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

# Vyber jednu email cestu:
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=hello@tvojafirma.sk
BREVO_SENDER_NAME=Tvoja firma
```

Klikni **Save** → **Redeploy**.

## 4. Over dostupnosť

```bash
curl https://faktura.example.com/healthz
# {"status":"ok","version":"0.1.0"}
```

Ak vidíš Cloudflare 502 alebo podobne, skontroluj logy containera v Coolify.
Pravdepodobne chýbajú env premenné (validácia konfigurácie pri štarte zlyhá).

## 5. Zaregistruj Stripe webhook

V Stripe Dashboarde → **Developers → Webhooks → + Add endpoint**:

- Endpoint URL: `https://faktura.example.com/webhook/stripe`
- Udalosti: `checkout.session.completed`
- Save → skopíruj **Signing secret** (`whsec_...`) do
  `STRIPE_WEBHOOK_SECRET` env premennej v Coolify → redeploy.

## 6. Za Cloudflare-om?

Ak je `faktura.example.com` proxied cez Cloudflare (oranžový mrak), uisti sa že:

- **Bot Fight Mode** je **VYPNUTÝ** (alebo daj Skip rule pre tento hostname);
  Stripe-Signature requesty môžu CF heuristikam vyzerať ako boti.
- **Cache Rules**: nie je striktne potrebné (app posiela `cache-control: no-cache`),
  ale "Bypass cache" rule pre tento hostname je príjemná poistka.

## 7. (Voliteľné) Obmedz čítanie

Nastav `READ_API_KEY=...` aby všetky `GET /invoices*` routy vyžadovali hlavičku
`X-API-Key`. Stripe webhook je vždy otvorený (Stripe sa autentifikuje cez podpis).
