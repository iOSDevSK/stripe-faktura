# Slovenská faktúra — zákonné náležitosti

Rýchla referencia, čo slovenský zákon vyžaduje na B2B / B2C faktúre.
Tento dokument je **informatívny** — pre tvoj konkrétny prípad si over s účtovníkom.

## Zdroje

- **Zákon č. 222/2004 Z. z.** — o dani z pridanej hodnoty (zákon o DPH)
- **Zákon č. 431/2002 Z. z.** — o účtovníctve
- **Zákon č. 18/2018 Z. z.** — o ochrane osobných údajov (slovenský ekvivalent GDPR)

## Povinné polia (§ 74 z. č. 222/2004 — pre platcu DPH)

Faktúra platcu DPH musí obsahovať:

1. Obchodné meno a adresu **dodávateľa**
2. **IČ DPH dodávateľa**
3. Obchodné meno a adresu **odberateľa**
4. **IČ DPH odberateľa** (ak má pridelené)
5. **Poradové číslo** faktúry
6. **Dátum dodania** tovaru/služby (DUZP — alebo dátum prijatia platby ak skôr)
7. **Dátum vystavenia** faktúry
8. **Množstvo a druh** dodaného tovaru/služby
9. **Základ dane** pre každú sadzbu DPH zvlášť (čistá cena)
10. **Sadzba DPH** alebo informácia o oslobodení od DPH s odkazom na § zákona
11. **Suma DPH** v EUR
12. (Pri špeciálnych prípadoch) odkaz na faktúru, ktorá bola opravená — pri dobropisoch

## Povinné polia (zákon o účtovníctve — pre neplatcu DPH)

Ak dodávateľ **nie je platcom DPH**, faktúra (resp. "doklad") musí obsahovať:

1. Označenie dokladu (typicky "Faktúra")
2. Obsah a peňažnú sumu
3. Dátum vyhotovenia
4. Dátum uskutočnenia účtovného prípadu (≈ DUZP)
5. **Identifikáciu dodávateľa a odberateľa** (meno/firma + adresa, IČO ak má)
6. Podpisový záznam (pri elektronických faktúrach netreba)

Plus **zákonné oznámenie**:
> "Nie som platiteľom DPH podľa § 4 zákona č. 222/2004 Z. z. v platnom znení."

## Konvenčne tiež zahrnuté (zákonom nepovinné, ale očakávané)

| Pole | Účel |
|---|---|
| **Variabilný symbol** | Číselný identifikátor pre spárovanie bankového prevodu (typicky číslo faktúry) |
| **Konštantný symbol** | `0308` pre faktúry |
| **Špecifický symbol** | Voliteľné, niekedy projektový kód |
| **IBAN + BIC** | Aby zákazník vedel uhradiť |
| **Dátum splatnosti** | Termín úhrady (= dátum vystavenia ak vopred uhradené) |
| **Spôsob úhrady** | "Prevodom" / "Platba kartou" / "Hotovosť" |
| **Pečiatka a podpis** | Povinné len pri papierových; e-faktúry nepotrebujú |
| **Zápis v obchodnom registri** | Povinné na všetkých obchodných listinách podľa § 3a Obch. zák. |

## Špecifické pre Stripe

- **Variabilný symbol** musí byť numerický a ≤ 10 cifier.
  Použi číslo faktúry; ak tvoj formát obsahuje písmená/pomlčky, odstráň ich.
  (`stripe_faktura.numbering.variable_symbol_from()` to robí.)
- **DUZP** pre digitálne služby = okamih platby (Stripe `payment_intent.created`).
- **Mena**: faktúra môže byť vystavená v akejkoľvek mene, ale ak si slovenský platca DPH,
  **suma DPH musí byť vyjadrená v EUR** aj na faktúre v cudzej mene
  (použi referenčný kurz ECB k DUZP).

## Prenos daňovej povinnosti (B2B EU)

Pri fakturácii VAT-registered EU firmám mimo Slovenska:
- Neúčtuj DPH.
- Pridaj zákonný text:
  > "Prenesenie daňovej povinnosti — Reverse charge (čl. 196 smernice 2006/112/ES)"
- Uveď IČ DPH oboch strán.
- Vykáž to v **Súhrnnom výkaze DPH**.

`stripe-faktura` v0.1 reverse charge logiku **nedokáže** zautomatizovať — pre
predaj mimo SK nastav `SUPPLIER_VAT_REGISTERED=false`, alebo manuálne uprav.
Vylepšenie je v pláne pre v0.3.

## Archivácia

Zákon o účtovníctve § 35 vyžaduje archiváciu faktúr:
- **10 rokov** (všeobecné účtovné doklady)
- **20 rokov** pre DPH záznamy "dlhodobého hmotného majetku"

`stripe-faktura` ukladá PDF na nakonfigurovaný volume natrvalo (žiadne
automatické mazanie). Tento volume zálohuj.
