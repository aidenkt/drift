# Case study ground truth: coffee roaster

Workbook: `case_study_coffee.xlsx` (assumptions set 2026-05-01, market inputs at close of 2026-04-30). Owner: Matthew.

Company: Bluestem Coffee Roasters, Inc. (fictional US coffee roaster; buys green arabica priced off the arabica benchmark, about half from its own sourcing and dry-mill operation in Brazil; runs its own diesel delivery fleet). Tabs: `Cover`, `Assumptions`, `P&L`, `DCF`. As built, FY2026E EBITDA is $97.9M and enterprise value (NPV) is $1,436.8M.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` is meant to check the pipeline against this, but it is skipped until the pipeline is implemented, so these results are not checked yet.

## Planted market drivers

"Today" means the latest value available on 2026-10-10. Impacts are one at a time against the as-built model.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B23 | Arabica coffee, other mild arabicas, ¢/lb | 334.11 (IMF monthly average for Mar-2026, the latest published on 2026-04-30; [FRED PCOFFOTMUSDM](https://fred.stlouisfed.org/series/PCOFFOTMUSDM)) | 359.16 (IMF monthly average for Jul-2026, latest published; [FRED PCOFFOTMUSDM](https://fred.stlouisfed.org/series/PCOFFOTMUSDM)). Spot futures have since fallen: ICE Coffee C Dec-2026 settled at 289.05 on 2026-10-08 ([Kirehalli market report](https://kirehalli.com/coffee-prices-karnataka-09-10-2026/)) | Yes either way. On FRED: +7.5%, EBITDA -$29.6M, EV -$382.7M. On spot futures: -13.5%, EBITDA +$53.2M, EV +$688.4M |
| P&L!C16:G16 (buried: `=C15/4.9792`) | USD/BRL, R$ per $ (Brazil sourcing and dry-mill costs) | 4.9792 ([FRED DEXBZUS](https://fred.stlouisfed.org/series/DEXBZUS), 2026-04-30) | 5.2222 ([FRED DEXBZUS](https://fred.stlouisfed.org/series/DEXBZUS), 2026-10-02) | Yes; +4.9% (weaker real). EBITDA +$2.0M, EV +$25.4M |
| Assumptions!B24 | Natural gas, Henry Hub spot, $/MMBtu (roasting energy) | $2.64 ([FRED DHHNGSP](https://fred.stlouisfed.org/series/DHHNGSP), 2026-04-30) | $3.03 ([FRED DHHNGSP](https://fred.stlouisfed.org/series/DHHNGSP), 2026-10-06) | Yes; +14.8%, but immaterial: EBITDA -$0.2M, EV -$2.1M |
| Assumptions!B25 | On-highway diesel, US average retail, $/gal (delivery fleet) | $5.351 ([FRED GASDESW](https://fred.stlouisfed.org/series/GASDESW), week of 2026-04-27) | $6.199 ([FRED GASDESW](https://fred.stlouisfed.org/series/GASDESW), week of 2026-10-05) | Yes; +15.8%. EBITDA -$5.8M, EV -$74.7M |
| Assumptions!B32 | SOFR, the base rate on the term loan | 3.66% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-04-30) | 3.87% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-10-08) | Yes; +21bp. EBITDA unchanged, net income -$0.6M, EV -$11.6M |
| DCF!B6 | Risk-free rate, 10-year US Treasury | 4.40% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-04-30) | 5.22% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-10-08) | Yes; +82bp. EV -$123.6M |

## Controls (should not be flagged)

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B26 | Additional US tariff on Brazilian green coffee | 0.0% (green coffee exempt from the Section 122 surcharge, Annex II; [Royal Coffee](https://royalcoffee.com/blogs/blog/green-coffee-is-exempt-from-the-new-tariffs-heres-what-roasters-need-to-know)) | 0.0%. The Section 122 surcharge has expired, and coffee is exempt from the Section 301 Brazil and forced-labor tariffs that replaced it ([NCA](https://www.ncausa.org/Newsroom/NCA-applauds-exemption-of-coffee-from-Section-301-tariffs-on-Brazil), [Honigman](https://www.honigman.com/alert-3462)) | No (fresh control); 0.0%. The legal basis changed, but the rate did not |
| Assumptions!B27 | US federal corporate income tax rate | 21.0% | 21.0%, unchanged ([26 U.S.C. § 11(b)](https://www.law.cornell.edu/uscode/text/26/11)) | No (fresh control); 0.0% |

## Other hardcoded inputs (not market drivers)

None of these should be flagged as stale. They are company plans, contract terms or house views. The contract differential (B9) and utility delivery charge (B13) are negotiated terms, not market prices.

| Cell | Driver | Value in model |
|---|---|---|
| Assumptions!B5 | FY2025A net revenue | $920.0M |
| Assumptions!B6:B10 | Green coffee volume FY2026E, roast shrink, net price per lb, contract differential, Brazil share | 118.0M lbs, 16.0%, $9.75, 38.0¢, 55.0% |
| Assumptions!B11:B14 | Brazil costs (R$), gas use, utility delivery charge, fleet diesel gallons | R$210.0M, 420k MMBtu, $4.50, 6.8M gal |
| Assumptions!B15:B20 | Packaging, plant labor, SG&A, D&A, capex and NWC as % of revenue | 7.0%, 11.0%, 18.0%, 2.5%, 3.0%, 16.0% |
| Assumptions!B30:B31, B33:B34 | Term loan, amortization, margin over SOFR, cash | $380.0M, 5.0%, 3.00%, $58.0M |
| Assumptions!B37:F38 | Volume growth and price growth FY2026E–FY2030E | 4.0–4.5%; 2.5–3.0% |
| DCF!B7:B9, B14, B16 | ERP, beta, size premium, target debt/capital, terminal growth | 5.00%, 0.95, 1.50%, 30.0%, 2.5% |
| P&L rows 13, 18; DCF rows 5, 19, 28 and 30 (buried) | Unit conversions and dates: 100 (¢ to $), 1,000 (000 MMBtu to $M), 365 (days per year), the valuation date and fiscal year-end dates | n/a |
