# Case study ground truth (Aug 2025 model)

Workbook: `case_study_aug2025.xlsx` (assumptions set 2025-08-01, market inputs at close of 2025-07-31). Owner: Matthew.

Same company as `case_study_aug2026.xlsx` (Calder & Finch Home, Inc.), modeled a year earlier. Tabs: `Cover`, `Assumptions`, `P&L`, `DCF`. This version has no EU sourcing, so there is no EUR/USD input. As built, FY2025E EBITDA is $125.3M and enterprise value (NPV) is $1,160.0M.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` checks against this.

## Planted market drivers

"Today" means the latest value available on 2026-10-10. Impacts are one at a time against the as-built model.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| P&L!C33:G33 (buried: `=0.0439+Assumptions!$B$28`) | SOFR, the floating base rate on the term loan | 4.39% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2025-07-31) | 3.87% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-10-08). The Fed target's upper bound went from 4.50% to 4.00% after cuts and a 2026-09-16 hike ([FRED DFEDTARU](https://fred.stlouisfed.org/series/DFEDTARU)) | Yes; -52bp. EBITDA unchanged, net income +$1.3M, EV +$16.8M |
| DCF!B6 | Risk-free rate, 10-year US Treasury | 4.37% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2025-07-31) | 5.22% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-10-08) | Yes; +85bp. EV -$94.4M |
| Assumptions!B19 | Brent crude, $/bbl (drives foam, poly, packaging and diesel cost) | $73.43 ([FRED DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU), 2025-07-31) | $125.44 EIA spot ([FRED DCOILBRENTEU](https://fred.stlouisfed.org/series/DCOILBRENTEU), 2026-10-06). The front-month future is lower, $104.72 on 2026-10-09 ([Investing.com](https://www.investing.com/commodities/brent-oil-historical-data)) | Yes; +70.8% on spot. EBITDA -$21.1M, EV -$247.3M (-$12.7M and -$148.8M on the future) |
| P&L!C16:G16 (buried: `=C15*2632/1000000`) | Ocean freight per 40ft container, Asia to US West Coast (Drewry WCI Shanghai–Los Angeles) | $2,632 (Drewry WCI, 2025-07-31 assessment, via [MTS Insights](https://www.mtsinsights.com/summaries/1070/)) | $7,624 (Drewry WCI, 2026-10-08 assessment, via [Daily Cargo News](https://thedcn.com.au/news/world-container-index-8-october-2026)) | Yes; +189.7%. EBITDA -$46.9M, EV -$550.8M |
| Assumptions!B21 | Additional US tariff on Vietnam-origin goods | 20.0% (IEEPA reciprocal rate set by the [2025-07-31 executive order](https://www.whitehouse.gov/presidential-actions/2025/07/further-modifying-the-reciprocal-tariff-rates/), effective 2025-08-07) | 12.5% Section 301 forced-labor duty, in force 2026-07-24 ([C.H. Robinson](https://www.chrobinson.com/en-us/resources/insights-and-advisories/client-advisories/2026q3/07-24-26-client-advisory-new-section-301-forced-labor-tariffs-now-in-effect/)). The Supreme Court struck down the IEEPA tariffs on 2026-02-20 ([Learning Resources v. Trump](https://supreme.justia.com/cases/federal/us/607/24-1287/)) | Yes; -7.5pp. EBITDA +$13.1M, EV +$154.2M (a lower tariff helps) |
| Assumptions!B22 | US tariff on Canada-origin furniture | 0.0% (USMCA-qualifying goods were exempt from the 35% IEEPA Canada duty that took effect 2025-08-01; [KPMG](https://kpmg.com/us/en/taxnewsflash/news/2025/08/white-house-35-percent-tariff-canadian-imports.html)) | 50% Section 338 duty, in force 2026-08-22; seating and furniture were added to the covered list 2026-09-15 ([CBP CSMS #69606660](https://content.govdelivery.com/accounts/USDHSCBP/bulletins/4261d04), [Zonos summary](https://zonos.com/docs/guides/country-guides/united-states/section-338-canada-tariffs)) | Yes; +50pp. EBITDA -$58.4M, EV -$685.2M |

## Controls (should not be flagged)

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B20 | MFN (column 1 general) duty on wooden furniture, HTS 9403.60.80 | 0.0% (Free) | 0.0% (Free), unchanged ([USITC HTS search](https://hts.usitc.gov/search?query=9403.60.80)) | No (fresh control); 0.0% |
| Assumptions!B23 | US federal corporate income tax rate | 21.0% | 21.0%, unchanged ([26 U.S.C. § 11(b)](https://www.law.cornell.edu/uscode/text/26/11)) | No (fresh control); 0.0% |

## Other hardcoded inputs (not market drivers)

None of these should be flagged as stale. They are company plans, contract terms or house views.

| Cell | Driver | Value in model |
|---|---|---|
| Assumptions!B5 | FY2024A net revenue | $781.0M |
| Assumptions!B6:B8 | Product purchases as % of revenue; Vietnam and Canada shares | 48.0%; 45.0%; 30.0% |
| Assumptions!B10 | Containers imported from Asia, FY2025E | 9,400 FEU |
| Assumptions!B11 | Oil-linked consumption, FY2025E | 405k bbl-equivalent |
| Assumptions!B12:B16 | SG&A, warehousing, D&A, capex and NWC as % of revenue | 19.0%, 6.5%, 2.2%, 2.5%, 14.0% |
| Assumptions!B26:B29 | Term loan balance, amortization, SOFR margin, cash | $315.0M, 5.0%, 2.75%, $41.0M |
| Assumptions!B32:F32 | Revenue growth FY2025E–FY2029E | 3.8%, 4.0%, 4.5%, 4.5%, 4.0% |
| DCF!B7:B9, B14, B16 | ERP, beta, size premium, target debt/capital, terminal growth | 5.00%, 1.15, 1.00%, 25.0%, 2.5% |
| P&L row 16, P&L row 18, DCF rows 28 and 30 (buried) | Unit conversions: 1,000,000 ($ to $M), 1,000 (bbl-eq), 365 (days per year) | n/a |
