# Case study ground truth: homebuilder

Workbook: `case_study_homebuilder.xlsx` (assumptions set 2025-11-01, market inputs at close of 2025-10-31). Owner: Matthew.

Company: Ridgeline Homes, Inc. (fictional US homebuilder that uses mortgage-rate buydowns as its main sales incentive). Tabs: `Cover`, `Assumptions`, `P&L`, `DCF`. As built, FY2025E EBITDA is $572.4M and enterprise value (NPV) is $5,958.5M.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` checks against this.

## Planted market drivers

"Today" means the latest value available on 2026-10-10. Impacts are one at a time against the as-built model.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B16 | 30-year fixed mortgage rate (drives the buydown incentive: P&L row 11 = (rate − 5.49% target) × 100 × 4.5% × 85% LTV) | 6.17% ([FRED MORTGAGE30US](https://fred.stlouisfed.org/series/MORTGAGE30US), week of 2025-10-30) | 7.40% ([FRED MORTGAGE30US](https://fred.stlouisfed.org/series/MORTGAGE30US), week of 2026-10-08) | Yes; +123bp. Incentive rises from 2.60% to 7.31% of revenue. EBITDA -$123.1M, EV -$1,293.8M |
| Assumptions!B18 | Conforming loan limit, one-unit baseline (feeds the eligibility check in P&L rows 28–29) | $806,500 (FHFA 2025 limit) | $832,750, the 2026 limit in force since 2026-01-01 ([FHFA](https://www.fhfa.gov/news/news-release/fhfa-announces-conforming-loan-limit-values-for-2026)) | Yes; +3.3%, but immaterial: EBITDA and EV unchanged, and the ASP check still reads "Yes" |
| P&L!C33:G33 (buried: `=Assumptions!$B$29*(0.0422+Assumptions!$B$30)`) | SOFR, the base rate on the revolving credit facility | 4.22% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2025-10-31) | 3.87% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-10-08) | Yes; -35bp. EBITDA unchanged, net income +$1.1M, EV +$11.4M |
| DCF!B6 | Risk-free rate, 10-year US Treasury | 4.11% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2025-10-31) | 5.22% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-10-08) | Yes; +111bp. EV -$541.3M |

## Controls (should not be flagged)

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B17 | Bank prime loan rate (base rate on A&D loans) | 7.00% ([FRED DPRIME](https://fred.stlouisfed.org/series/DPRIME), 2025-10-31) | 7.00% ([FRED DPRIME](https://fred.stlouisfed.org/series/DPRIME), 2026-10-02). It fell to 6.75% after later cuts and returned to 7.00% with the 2026-09-16 hike | No (fresh control); 0.0%. Same value, even though it moved in between |
| Assumptions!B19 | US federal corporate income tax rate | 21.0% | 21.0%, unchanged ([26 U.S.C. § 11(b)](https://www.law.cornell.edu/uscode/text/26/11)) | No (fresh control); 0.0% |

## Other hardcoded inputs (not market drivers)

None of these should be flagged as stale. They are company plans, contract terms or house views. The senior notes coupon (B32) is fixed by the indenture, so it should not be compared to market rates.

| Cell | Driver | Value in model |
|---|---|---|
| Assumptions!B5 | FY2024A home sales revenue | $2,760.0M |
| Assumptions!B6:B9 | Closings FY2025E, ASP, land % of ASP, direct cost per home | 6,050, $478.0k, 24.0%, $212.0k |
| Assumptions!B10:B13 | SG&A, D&A, capex and NWC as % of revenue | 9.5%, 0.8%, 0.7%, 70.0% |
| Assumptions!B22:B24 | Buydown target rate, cost of a 100bp buydown, average LTV | 5.49%, 4.50%, 85.0% |
| Assumptions!B27:B33 | A&D loans and margin, revolver and margin, senior notes and coupon, cash | $620.0M, 0.50%, $400.0M, 1.75%, $1,200.0M, 5.25%, $505.0M |
| Assumptions!B36:F37 | Closings growth and ASP growth FY2025E–FY2029E | 3.0–4.0%; 2.5% |
| DCF!B7:B9, B14, B16 | ERP, beta, size premium, target debt/capital, terminal growth | 5.00%, 1.60, 1.00%, 30.0%, 2.5% |
| P&L rows 10, 11, 17, 28; DCF rows 5, 19, 28 and 30 (buried) | Unit conversions and dates: 1,000 ($000 to $M), 100 (rate to 100bp steps), 365 (days per year), the valuation date and fiscal year-end dates | n/a |
