# Case study ground truth

Workbook: `case_study_aug2026.xlsx` (assumptions set 2026-08-01, market inputs at close of 2026-07-31). Owner: Matthew.

Company: Calder & Finch Home, Inc. (fictional US furniture wholesaler that sources from Vietnam, Canada and the EU). Tabs: `Cover`, `Assumptions`, `P&L`, `DCF`. As built, FY2026E EBITDA is $106.0M and enterprise value (NPV) is $905.5M.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` checks against this.

## Planted market drivers

"Today" means the latest value available on 2026-10-10. Impacts are one at a time against the as-built model.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| P&L!C35:G35 (buried: `=0.0366+Assumptions!$B$29`) | SOFR, the floating base rate on the term loan | 3.66% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-07-31) | 3.87% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-10-08). The Fed raised its target range 25bp to 3.75–4.00% on 2026-09-16 ([FRED DFEDTARU](https://fred.stlouisfed.org/series/DFEDTARU)) | Yes; +21bp. EBITDA unchanged, net income -$0.5M, EV -$5.1M |
| DCF!B6 | Risk-free rate, 10-year US Treasury | 4.75% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-07-31) | 5.22% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-10-08) | Yes; +47bp. EV -$41.5M |
| Assumptions!B20 | Brent crude, $/bbl (drives foam, poly, packaging and diesel cost) | $96.95 ([FRED DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU), 2026-07-31) | $125.44 EIA spot ([FRED DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU), 2026-10-06). The front-month future is lower, $104.72 on 2026-10-09 ([Investing.com](https://www.investing.com/commodities/brent-oil-historical-data)) | Yes; +29.4% on spot. EBITDA -$12.0M, EV -$137.3M (-$3.3M and -$37.5M on the future) |
| Assumptions!B21 | EUR/USD, $ per € (EU supplier contracts are priced in EUR) | 1.1519 ([FRED DEXUSEU](https://fred.stlouisfed.org/series/DEXUSEU), 2026-07-31) | 1.1259 ([FRED DEXUSEU](https://fred.stlouisfed.org/series/DEXUSEU), 2026-10-02, latest H.10 print). Market close 1.1206 on 2026-10-09 ([Yahoo Finance](https://finance.yahoo.com/quote/EURUSD=X/history/)) | Yes; -2.3%. EBITDA +$1.9M, EV +$22.1M (a weaker euro helps) |
| P&L!C18:G18 (buried: `=C17*5739/1000000`) | Ocean freight per 40ft container, Asia to US West Coast (Drewry WCI Shanghai–Los Angeles) | $5,739 (Drewry WCI, 2026-07-30 assessment, via [Shipping Telegraph](https://shippingtelegraph.com/freight-news/drewry-the-world-container-index-decreased-3-this-week-31-2026/)) | $7,624 (Drewry WCI, 2026-10-08 assessment, via [Daily Cargo News](https://thedcn.com.au/news/world-container-index-8-october-2026)) | Yes; +32.8%. EBITDA -$18.5M, EV -$212.0M |
| Assumptions!B23 | US tariff on Canada-origin furniture | 0.0% (USMCA-qualifying goods entered duty-free) | 50% Section 338 duty, in force 2026-08-22; seating and furniture were added to the covered list 2026-09-15 ([CBP CSMS #69606660](https://content.govdelivery.com/accounts/USDHSCBP/bulletins/4261d04), [Zonos summary](https://zonos.com/docs/guides/country-guides/united-states/section-338-canada-tariffs)) | Yes; +50pp. EBITDA -$48.1M, EV -$552.4M |

## Controls (should not be flagged)

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B22 | US tariff on Vietnam-origin furniture (Section 301 forced-labor action) | 12.5% (in force 2026-07-24) | 12.5%, unchanged. The separate Section 301 excess-capacity probe had produced no tariff as of late September ([C.H. Robinson](https://www.chrobinson.com/en-us/resources/insights-and-advisories/client-advisories/2026q3/07-24-26-client-advisory-new-section-301-forced-labor-tariffs-now-in-effect/), [DFDL](https://www.dfdl.com/insights/legal-and-tax-updates/us-section-301-tariffs-asean-implications/)) | No (fresh control); 0.0% |
| Assumptions!B24 | US federal corporate income tax rate | 21.0% | 21.0%, unchanged ([26 U.S.C. § 11(b)](https://www.law.cornell.edu/uscode/text/26/11)) | No (fresh control); 0.0% |

## Other hardcoded inputs (not market drivers)

None of these should be flagged as stale. They are company plans, contract terms or house views.

| Cell | Driver | Value in model |
|---|---|---|
| Assumptions!B5 | FY2025A net revenue | $812.0M |
| Assumptions!B6:B8 | Non-EU purchases as % of revenue; Vietnam and Canada shares | 38.0%; 50.0%; 30.0% |
| Assumptions!B10 | EU supplier contract volume, FY2026E | €74.0M |
| Assumptions!B11 | Containers imported from Asia, FY2026E | 9,800 FEU |
| Assumptions!B12 | Oil-linked consumption, FY2026E | 420k bbl-equivalent |
| Assumptions!B13:B17 | SG&A, warehousing, D&A, capex and NWC as % of revenue | 19.0%, 6.5%, 2.2%, 2.5%, 14.0% |
| Assumptions!B27:B30 | Term loan balance, amortization, SOFR margin, cash | $300.0M, 5.0%, 2.75%, $46.0M |
| Assumptions!B33:F33 | Revenue growth FY2026E–FY2030E | 4.0%, 4.5%, 4.5%, 4.0%, 3.5% |
| DCF!B7:B9, B14, B16 | ERP, beta, size premium, target debt/capital, terminal growth | 5.00%, 1.15, 1.00%, 25.0%, 2.5% |
| P&L row 18, P&L row 20, DCF rows 28 and 30 (buried) | Unit conversions: 1,000,000 ($ to $M), 1,000 (bbl-eq), 365 (days per year) | n/a |
