# stripe-faktura

> Generátor slovenských faktúr pre Stripe platby. Open-source. Self-hosted.

`stripe-faktura` je malý FastAPI server, ktorý počúva na Stripe webhooky a po
úspešnej platbe automaticky vystaví **PDF faktúru so všetkými náležitosťami
podľa slovenskej legislatívy** (§ 74 zákona č. 222/2004 Z. z. o DPH a § 10
zákona č. 431/2002 Z. z. o účtovníctve) a pošle ju zákazníkovi emailom.

Podporuje oba režimy DPH:
- **Neplatca DPH** — pridáva zákonný text *"Nie som platiteľom DPH podľa § 4
  zákona č. 222/2004 Z. z."*
- **Platca DPH** — rozpisuje cenu na základ + 20 % DPH + cenu s DPH.

**Stripe je jediným zdrojom pravdy.** Všetky údaje (meno, adresa, IČO, DIČ,
IČ DPH, položky, sumy) sa preberajú zo Stripe API. Stačí v Checkout Session
zapnúť zber adresy a daňových IČ.

---

## Načo to je?

Vstavané faktúry a potvrdenia od Stripe neobsahujú polia, ktoré slovenský
zákon vyžaduje: variabilný symbol, dátum dodania (DUZP), rozpis DPH v EUR,
IČO/DIČ oboch strán, oznámenie *"neplatca DPH"* atď.

Existujúce slovenské fakturačné služby (SuperFaktura, iKros, Pohoda) fungujú,
ale uzamykajú ťa do svojho UI a mesačných poplatkov. Toto je drobná
self-hosted alternatíva ušitá presne pre Stripe.

---

## Funkcie (v0.1)

- ✅ Stripe webhook receiver s HMAC overením podpisu
- ✅ Automatické čítanie zákazníka + položiek zo Stripe API
- ✅ Sekvenčné číslovanie faktúr s ročným resetom (`20260001`)
- ✅ WeasyPrint HTML→PDF rendering, plne upraviteľné šablóny
- ✅ Idempotentnosť (rovnaký Stripe session nevygeneruje dve faktúry)
- ✅ Doručovanie emailom cez Brevo alebo SMTP (na výber)
- ✅ Trvalé úložisko (predvolene SQLite + lokálne PDF)
- ✅ REST API na výpis faktúr a stiahnutie PDF
- ✅ Docker + docker-compose ready, jednoobrazový deploy

### Roadmap (v0.2+)

- Outbound webhook (po vystavení POST na tvoju URL)
- S3 / MinIO / R2 úložisko
- Postgres podpora
- Refund → automatický dobropis (credit note)
- Multi-tenant API (jeden server, viacero dodávateľov)
- Český režim DPH (CZ DPH 21 %)

---

## Rýchly štart

### 1. Klonuj a nakonfiguruj

```bash
git clone https://github.com/iOSDevSK/stripe-faktura.git
cd stripe-faktura
cp .env.example .env
# Uprav .env — vyplň SUPPLIER_*, STRIPE_*, voliteľne BREVO_*
```

### 2. Spusti cez Docker

```bash
docker compose up -d
# kontrola dostupnosti
curl http://localhost:8000/healthz
# {"status":"ok","version":"0.1.0"}
```

### 3. Nasmeruj naňho Stripe

V Stripe dashboarde → **Developers → Webhooks → Add endpoint**:

- URL: `https://tvoj-host/webhook/stripe`
- Udalosti: `checkout.session.completed`
- Skopíruj **Signing secret** (`whsec_...`) do premennej `STRIPE_WEBHOOK_SECRET`.

### 4. Nakonfiguruj Checkout Session

Aby služba mala všetky potrebné údaje na vystavenie SK faktúry:

```js
const session = await stripe.checkout.sessions.create({
  mode: 'payment',
  line_items: [{ price: 'price_xxx', quantity: 1 }],
  customer_creation: 'always',
  billing_address_collection: 'required',   // ← POVINNÉ pre faktúry
  tax_id_collection: { enabled: true },     // ← aby IČ DPH prišlo zo Stripe
  success_url: '...',
  cancel_url: '...',
});
```

Pri B2B zákazníkoch zapíš **IČO** do `customer.metadata` (cez Stripe API,
buď pred Checkout Session alebo po jej dokončení):

```js
await stripe.customers.update(session.customer, {
  metadata: { ico: '12345678', dic: '2012345678' },
});
```

### 5. Otestuj

Zaplať 0,50 € testovacou kartou na svojom Stripe Checkoute. Do pár sekúnd by si mal vidieť:
- PDF faktúru v `data/pdfs/2026/20260001.pdf`.
- Záznam vo výpise `GET /invoices`.
- Email s PDF prílohou (ak je nakonfigurovaný Brevo/SMTP).

---

## Konfigurácia

Všetka konfigurácia je cez environment premenné. Plný zoznam je v [`.env.example`](.env.example).

### Povinné

| Premenná | Popis |
|---|---|
| `STRIPE_API_KEY` | Stripe secret key (`sk_test_...` alebo `sk_live_...`) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret (`whsec_...`) |
| `SUPPLIER_NAME` | Názov tvojej firmy |
| `SUPPLIER_STREET` `SUPPLIER_CITY` `SUPPLIER_ZIP` `SUPPLIER_COUNTRY` | Tvoja adresa |
| `SUPPLIER_ICO` | Tvoje IČO |
| `SUPPLIER_IBAN` | Bankový účet pre faktúry |
| `SUPPLIER_EMAIL` | Reply-to email pre faktúry |
| `SUPPLIER_VAT_REGISTERED` | `true` / `false` — prepína režim DPH |

### Voliteľné: režim DPH

Ak si platca DPH (`SUPPLIER_VAT_REGISTERED=true`):
- `SUPPLIER_VAT_ID` — tvoje IČ DPH (napr. `SK2024567890`)
- `VAT_RATE` — predvolene `20`

### Voliteľné: email

Vyber jednu cestu. Ak nie je nastavená žiadna, služba PDF uloží, ale nepošle email.

```env
# A) Brevo
BREVO_API_KEY=xkeysib-...
BREVO_SENDER_EMAIL=hello@tvojafirma.sk
BREVO_SENDER_NAME=Tvoja firma

# B) SMTP
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USER=...
SMTP_PASSWORD=...
SMTP_FROM_EMAIL=hello@tvojafirma.sk
SMTP_FROM_NAME=Tvoja firma
```

---

## Bezpečnosť — kto môže volať API?

Service má **3 vrstvy ochrany**:

| Vrstva | Endpoint | Mechanizmus |
|---|---|---|
| **1** | `POST /webhook/stripe` | Stripe HMAC podpis + timestamp (5 min) — bez `STRIPE_WEBHOOK_SECRET` neprejde žiadny request |
| **2** | `GET /invoices`, `GET /invoices/{number}` | `X-API-Key` hlavička s `READ_API_KEY` (povinný, min. 16 znakov, validovaný pri štarte) |
| **3** | `GET /invoices/{number}/pdf` | `X-API-Key` (admin) **alebo** `?token=<HMAC>` (verejný link v emaili zákazníkovi) |

Detail v [SECURITY.md](SECURITY.md). Útočník bez webhook secret-u nezvládne
sfalšovať platbu, bez API kľúča sa nedostane k zoznamu faktúr, a bez HMAC tokenu
nestiahne PDF — aj keď čísla faktúr sú predvídateľné (`20260001`, `20260002`...).

## API endpointy

| Metóda | Cesta | Popis |
|---|---|---|
| `POST` | `/webhook/stripe` | Stripe webhook receiver. Overuje `Stripe-Signature`. |
| `GET` | `/invoices` | Výpis faktúr (paginovaný). |
| `GET` | `/invoices/{number}` | Metadáta faktúry ako JSON. |
| `GET` | `/invoices/{number}/pdf` | Stiahne PDF. |
| `GET` | `/healthz` | Kontrola dostupnosti. |
| `GET` | `/docs` | Interaktívna OpenAPI dokumentácia (Swagger UI). |

Ak je nastavená premenná `READ_API_KEY`, všetky `GET /invoices*` endpointy
vyžadujú hlavičku `X-API-Key`.

---

## Mapovanie údajov zo Stripe

| Pole na SK faktúre | Zdroj v Stripe |
|---|---|
| Meno / email zákazníka | `customer.name` / `customer.email` |
| Adresa zákazníka | `customer.address` (zbiera sa cez `billing_address_collection`) |
| IČO zákazníka | `customer.metadata.ico` |
| DIČ zákazníka | `customer.metadata.dic` |
| IČ DPH zákazníka | `customer.tax_ids[].value` (typ `eu_vat`) |
| Položky | `checkout.session.list_line_items` |
| Spolu + mena | `session.amount_total` + `session.currency` |
| Dátum dodania (DUZP) | `payment_intent.created` |

Ak chceš pre konkrétny session faktúru preskočiť, nastav
`metadata.no_invoice=true` na Checkout Session.

---

## Vývoj

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e '.[dev]'
pytest
ruff check src/ tests/
```

WeasyPrint potrebuje Cairo + Pango. Na macOS:
```bash
brew install cairo pango gdk-pixbuf libffi
```

---

## Nasadenie

Funguje na akomkoľvek hostovi s Dockerom (Coolify, Fly.io, Railway, klasický VPS).

Pre Coolify: pozri [`examples/coolify-deploy.md`](examples/coolify-deploy.md).
Pre integráciu typu 24design.sk: pozri [`examples/24design-sk-integration.md`](examples/24design-sk-integration.md).

---

## Licencia

MIT — pozri [LICENSE](LICENSE).
