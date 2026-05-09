# Bezpečnostný model

Tento dokument popisuje, ako `stripe-faktura` chráni endpointy a dáta.

## Hrozby ktoré riešime

| Hrozba | Ochrana |
|---|---|
| Útočník volá `/webhook/stripe` s falošným payloadom | Stripe HMAC-SHA256 podpis — blok bez `STRIPE_WEBHOOK_SECRET` |
| Replay útok so starým validným payloadom | Stripe timestamp tolerance (5 min) |
| Únik webhook secret-u (logy, leak v repe) | Idempotentnosť (`stripe_session_id` unique) zablokuje duplicitné faktúry; `fetch_session()` overuje session reálnym Stripe API callom |
| Neautorizovaný prístup k zoznamu/detailu faktúr | `READ_API_KEY` povinný (validácia na štarte) |
| Útočník uhádne predvídateľné číslo faktúry (`20260001`) a stiahne PDF | HMAC token v PDF URL — bez tokenu 401 |
| MITM na sieti | TLS terminuje reverse proxy (Coolify Traefik) — vždy HTTPS v produkcii |

## Vrstva 1 — Webhook endpoint (`POST /webhook/stripe`)

Stripe podpisuje každý webhook hlavičkou `Stripe-Signature: t=<ts>,v1=<hmac>`.
Knižnica `stripe.Webhook.construct_event()` overuje:

1. **HMAC-SHA256** payloadu cez `STRIPE_WEBHOOK_SECRET` (constant-time compare).
2. **Timestamp tolerance** — odmietne ak je `t` starší ako 5 minút (anti-replay).
3. Bez validného secret-u nemá útočník šancu — vráti sa `400 neplatný podpis`,
   žiadny DB zápis, žiadny Stripe API call.

Aj keby útočník získal webhook secret:
- Ak vytvorí fake `session_id`, naše `fetch_session(id)` cez Stripe API
  vráti 404 → výnimka → 500 → žiadna faktúra.
- Ak použije skutočný `session_id` z inej platby, idempotentnosť
  (`UniqueConstraint("stripe_session_id")` v `db.py`) zablokuje duplicitné
  faktúry pre už spracované sessiony.
- Replay starého validného webhooku zablokuje 5-min timestamp window.

## Vrstva 2 — Admin read endpointy

`GET /invoices` a `GET /invoices/{number}` vyžadujú hlavičku
`X-API-Key: <READ_API_KEY>`. Bez nej `401 neautorizovaný prístup`.

`READ_API_KEY` má **povinnú validáciu na štarte** (`config.py`):
- Min. 16 znakov.
- Bez nej app nenaštartuje a vráti chybu so vzorovým snippetom na vygenerovanie:
  ```
  python -c "import secrets; print(secrets.token_urlsafe(32))"
  ```

## Vrstva 3 — Verejné PDF linky (HMAC token)

Linky v emailoch zákazníkom musia fungovať bez API kľúča (zákazník ho nedostane).
Riešenie: `?token=<HMAC-SHA256(invoice_number, secret)>`.

```
https://faktura.example.com/invoices/20260042/pdf?token=<base64url_HMAC>
```

- Token je **deterministický** pre danú faktúru → linky platia trvale
  (čo je správne pre archívne dokumenty s 10-ročnou retenciou).
- **Constant-time porovnanie** (`hmac.compare_digest`) bráni timing útokom.
- Bez tokenu alebo so zlým tokenom → `401`.
- Bez `PDF_TOKEN_SECRET` (alebo derivácie zo `STRIPE_WEBHOOK_SECRET`) sa
  token nedá uhádnuť ani brute-force vypočítať (HMAC-SHA256, 256-bit output).

PDF endpoint akceptuje **buď** `X-API-Key` (admin) **alebo** `?token=` (zákazník):

```python
api_key_ok = x_api_key == settings.read_api_key
token_ok = pdf_token.verify_pdf_token(number, token or "")
if not (api_key_ok or token_ok):
    raise HTTPException(401)
```

## Rotácia tajomstiev

- **`STRIPE_WEBHOOK_SECRET`** — rotácia v Stripe Dashboarde → **Developers → Webhooks → Roll secret**. Stripe ti dá nový secret (nový aj starý platia ~30 min). Aktualizuj env premennú a redeploy.
- **`READ_API_KEY`** — rotuj kedykoľvek; len aktualizuj env premennú a redeploy. Klienti (admin nástroje) musia použiť nový kľúč.
- **`PDF_TOKEN_SECRET`** (alebo zmena `STRIPE_WEBHOOK_SECRET` keď je `PDF_TOKEN_SECRET` prázdne) — invaliduje **všetky existujúce PDF linky**. Zákazníci s linkami v starých emailoch dostanú 401 a musia si vyžiadať nový. Ak ti to nevadí, je to bonus security feature.

## TLS / HTTPS

Aplikácia samotná počúva na HTTP (port 8000). V produkcii **musí** byť za
HTTPS reverse proxy (Coolify Traefik, nginx, Caddy...). Bez TLS je
`STRIPE_WEBHOOK_SECRET` zraniteľný na MITM.

## Logovanie

Webhook handler logguje session ID, číslo faktúry a chybové stavy.
**Nelogguje**:
- payload obsah (môže obsahovať PII zákazníka)
- API kľúče
- Stripe secrets

Pred deployom skontroluj `LOG_LEVEL` — v `INFO` ide len osídlené info,
v `DEBUG` by mohli proletovať detaily Stripe odpovedí.

## Hlásenie zraniteľností

Pošli email na **filip.dvoran@gmail.com** so subjectom `[stripe-faktura security]`.
Zaplátame a vydáme patch release pred zverejnením CVE.

## Audit log (roadmap v0.2)

Plánovaná feature:
- Tabuľka `audit_log` ktorá zachytáva každý read/download s: timestamp, IP, X-API-Key prefix, invoice number.
- Pomôže detekovať brute-force pokusy a dohľadať kto/kedy stiahol konkrétnu faktúru.
