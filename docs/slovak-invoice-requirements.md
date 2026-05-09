# Slovak invoice — legal requirements

Quick reference for what Slovak law requires on a B2B / B2C invoice.
This is **informational** — verify with your accountant for your specific case.

## Sources

- **Zákon č. 222/2004 Z. z.** — o dani z pridanej hodnoty (VAT Act)
- **Zákon č. 431/2002 Z. z.** — o účtovníctve (Accounting Act)
- **Zákon č. 18/2018 Z. z.** — o ochrane osobných údajov (GDPR-equivalent)

## Required fields (§ 74 z.č. 222/2004 — VAT payer)

A VAT-payer invoice must include:

1. Obchodné meno a adresa **dodávateľa**
2. **IČ DPH dodávateľa**
3. Obchodné meno a adresa **odberateľa**
4. **IČ DPH odberateľa** (if assigned)
5. **Poradové číslo faktúry**
6. **Dátum dodania tovaru/služby** (DUZP — alebo dátum prijatia platby ak skôr)
7. **Dátum vystavenia** faktúry
8. **Množstvo a druh** dodaného tovaru/služby
9. **Základ dane** pre každú sadzbu DPH zvlášť (čistá cena)
10. **Sadzba DPH** alebo informácia o oslobodení od DPH s odkazom na § zákona
11. **Suma DPH** v EUR
12. (For special cases) odkaz na faktúru, ktorá bola opravená — pri dobropisoch

## Required fields (zákon o účtovníctve — neplatca DPH)

If the supplier is **not a VAT payer**, the invoice (or "doklad") must include:

1. Označenie dokladu (typicky "Faktúra")
2. Obsah a peňažnú sumu
3. Dátum vyhotovenia
4. Dátum uskutočnenia účtovného prípadu (≈ DUZP)
5. **Identifikácia dodávateľa a odberateľa** (meno/firma + adresa, IČO ak má)
6. Podpisový záznam (pri elektronických faktúrach netreba)

Plus the **legal disclosure**:
> "Nie som platiteľom DPH podľa § 4 zákona č. 222/2004 Z. z. v platnom znení."

## Conventionally also included (not legally required, but expected)

| Field | Purpose |
|---|---|
| **Variabilný symbol** | Numeric ID for matching the bank transfer (typically the invoice number) |
| **Konštantný symbol** | `0308` for invoices |
| **Špecifický symbol** | Optional, sometimes used for project codes |
| **IBAN + BIC** | So the customer can pay |
| **Dátum splatnosti** | Due date (= issue date when prepaid) |
| **Spôsob úhrady** | "Prevodom" / "Platba kartou" / "Hotovosť" |
| **Pečiatka a podpis** | Required only on paper; e-invoices don't need them |
| **Zápis v obchodnom registri** | Required on all business correspondence by § 3a Obch. zák. |

## Stripe-specific notes

- **Variabilný symbol** must be numeric and ≤10 digits.
  Use the invoice number; if your format includes letters/dashes, strip them.
  (`stripe_faktura.numbering.variable_symbol_from()` does this.)
- **DUZP** for digital services = the moment of payment (Stripe `payment_intent.created`).
- **Currency**: invoice can be issued in any currency, but if you're a Slovak VAT payer,
  the **VAT amount must be expressed in EUR** even on a foreign-currency invoice
  (use the ECB reference rate of the DUZP date).

## Reverse charge (B2B EU)

When invoicing a VAT-registered EU business outside Slovakia:
- Don't charge VAT.
- Add the legal text:
  > "Prenesenie daňovej povinnosti — Reverse charge (čl. 196 smernice 2006/112/ES)"
- Include both parties' VAT IDs.
- Report it in your **VAT recapitulative statement** (Súhrnný výkaz).

`stripe-faktura` v0.1 does **not** automate reverse charge logic — you'd need to
set `SUPPLIER_VAT_REGISTERED=false` for non-EU sales, or manually adjust.
Improvement scheduled for v0.3.

## Storage retention

Slovak Accounting Act § 35 requires invoice retention for:
- **10 years** (general accounting documents)
- **20 years** for VAT records of "long-term tangible assets"

`stripe-faktura` stores PDFs on the configured volume forever (no automatic
deletion). Backup that volume.
