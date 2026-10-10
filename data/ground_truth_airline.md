# Case study ground truth: airline

Workbook: `case_study_airline.xlsx` (assumptions set 2025-05-01, market inputs at close of 2025-04-30). Owner: Matthew.

Company: Northstar Airways, Inc. (fictional US network airline with a domestic hub network and transpacific routes to Japan; Japan tickets sold in JPY; 70% of fuel hedged with swaps). Tabs: `Cover`, `Assumptions`, `P&L`, `DCF`. As built, FY2025E EBITDA is $1,158.4M and enterprise value (NPV) is $9,193.1M.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` is meant to check the pipeline against this, but it is skipped until the pipeline is implemented, so these results are not checked yet.

## Planted market drivers

"Today" means the latest value available on 2026-10-10. Impacts are one at a time against the as-built model.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B14 | Jet fuel, US Gulf Coast kerosene-type, $/gal | $1.909 ([FRED DJFUELUSGULF](https://fred.stlouisfed.org/series/DJFUELUSGULF), 2025-04-30) | $4.342 ([FRED DJFUELUSGULF](https://fred.stlouisfed.org/series/DJFUELUSGULF), 2026-10-06) | Yes; +127.4%. Even with 70% hedged: EBITDA -$551.9M, EV -$6,956.4M |
| P&L!C14:G14 (buried: `=C13*1000/142.63`) | USD/JPY, ¥ per $ (Japan point-of-sale revenue) | 142.63 ([FRED DEXJPUS](https://fred.stlouisfed.org/series/DEXJPUS), 2025-04-30) | 157.81 ([FRED DEXJPUS](https://fred.stlouisfed.org/series/DEXJPUS), 2026-10-02) | Yes; +10.6% (weaker yen). EBITDA -$191.1M, EV -$2,294.5M |
| Assumptions!B33 | SOFR, the base rate on aircraft-secured floating-rate debt | 4.41% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2025-04-30) | 3.87% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-10-08) | Yes; -54bp. EBITDA unchanged, net income +$18.4M, EV +$239.4M (lower rates help) |
| DCF!B6 | Risk-free rate, 10-year US Treasury | 4.17% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2025-04-30) | 5.22% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-10-08) | Yes; +105bp. EV -$788.2M |

## Controls (should not be flagged)

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B15 | Federal excise tax on domestic passenger tickets | 7.5% | 7.5%, unchanged ([26 U.S.C. § 4261(a)](https://www.law.cornell.edu/uscode/text/26/4261)) | No (fresh control); 0.0% |
| Assumptions!B16 | US federal corporate income tax rate | 21.0% | 21.0%, unchanged ([26 U.S.C. § 11(b)](https://www.law.cornell.edu/uscode/text/26/11)) | No (fresh control); 0.0% |

## Other hardcoded inputs (not market drivers)

None of these should be flagged as stale. They are company plans, contract terms or house views. The swap price (B20) is a fixed hedge contract price, so it should not be compared to market jet fuel.

| Cell | Driver | Value in model |
|---|---|---|
| Assumptions!B5 | FY2024A operating revenue | $7,950.0M |
| Assumptions!B6:B9 | ASMs FY2025E, load factor, domestic RPM share, domestic gross yield | 62.0bn, 84.0%, 70.0%, 17.20¢ |
| Assumptions!B10:B11 | Transpacific sales in JPY FY2025E, cargo and other % of passenger revenue | ¥260.0bn, 9.0% |
| Assumptions!B19:B20 | Share of fuel hedged, weighted swap price | 70.0%, $2.100 |
| Assumptions!B23:B28 | ASMs per gallon, labor and other cost per ASM, D&A, capex and NWC as % of revenue | 82.0, 4.10¢, 5.00¢, 5.5%, 5.5%, -8.0% |
| Assumptions!B31:B32, B34:B35 | Debt balance, amortization, margin over SOFR, cash | $4,450.0M, 6.0%, 2.10%, $3,000.0M |
| Assumptions!B38:F38 | ASM growth FY2025E–FY2029E | 5.0%, 4.5%, 4.0%, 4.0%, 3.5% |
| DCF!B7:B9, B14, B16 | ERP, beta, size premium, target debt/capital, terminal growth | 5.00%, 1.40, 0.00%, 40.0%, 2.0% |
| P&L rows 10, 14, 20, 23, 24; DCF rows 5, 19, 28 and 30 (buried) | Unit conversions and dates: 10 (billions × cents to $M), 1,000 (¥bn and billions to millions), 365 (days per year), the valuation date and fiscal year-end dates | n/a |
