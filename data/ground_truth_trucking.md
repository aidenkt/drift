# Case study ground truth: trucking

Workbook: `case_study_trucking.xlsx` (assumptions set 2026-03-01, market inputs at close of 2026-02-27). Owner: Matthew.

Company: Keystone Freight Lines, Inc. (fictional US truckload carrier with cross-border lanes into Canada, billed in CAD, and a Mexico terminal network paid in MXN). Tabs: `Cover`, `Assumptions`, `P&L`, `DCF`. As built, FY2026E EBITDA is $683.6M and enterprise value (NPV) is $6,700.9M.

This case buries three of its five drivers inside formulas, including the risk-free rate in the cost of equity.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` is meant to check the pipeline against this, but it is skipped until the pipeline is implemented, so these results are not checked yet.

## Planted market drivers

"Today" means the latest value available on 2026-10-10. Impacts are one at a time against the as-built model.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B24 | On-highway diesel, US average retail, $/gal | $3.809 ([FRED GASDESW](https://fred.stlouisfed.org/series/GASDESW), week of 2026-02-23) | $6.199 ([FRED GASDESW](https://fred.stlouisfed.org/series/GASDESW), week of 2026-10-05) | Yes; +62.7%. Mostly passed through by the fuel surcharge (P&L row 12): EBITDA -$7.6M, EV -$125.9M |
| Assumptions!B25 | USD/CAD, C$ per $ (Canada cross-border revenue) | 1.3632 ([FRED DEXCAUS](https://fred.stlouisfed.org/series/DEXCAUS), 2026-02-27) | 1.4253 ([FRED DEXCAUS](https://fred.stlouisfed.org/series/DEXCAUS), 2026-10-02) | Yes; +4.6% (weaker Canadian dollar). EBITDA -$11.5M, EV -$131.1M |
| P&L!C27:G27 (buried: `=C26/17.2207`) | USD/MXN, MXN per $ (Mexico terminal and drayage costs) | 17.2207 ([FRED DEXMXUS](https://fred.stlouisfed.org/series/DEXMXUS), 2026-02-27) | 18.1920 ([FRED DEXMXUS](https://fred.stlouisfed.org/series/DEXMXUS), 2026-10-02) | Yes; +5.6% (weaker peso). EBITDA +$9.8M, EV +$129.1M |
| P&L!C38:G38 (buried: `=0.0368+Assumptions!$B$32`) | SOFR, the base rate on floating-rate equipment notes | 3.68% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-02-27) | 3.87% ([FRED SOFR](https://fred.stlouisfed.org/series/SOFR), 2026-10-08) | Yes; +19bp. EBITDA unchanged, net income -$1.6M, EV -$58.8M |
| DCF!B9 (buried: `=0.0397+B7*B6+B8`) | Risk-free rate, 10-year US Treasury, inside the cost of equity | 3.97% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-02-27) | 5.22% ([FRED DGS10](https://fred.stlouisfed.org/series/DGS10), 2026-10-08) | Yes; +125bp. EV -$809.5M |

## Controls (should not be flagged)

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Assumptions!B26 | Federal heavy vehicle use tax, per tractor over 75,000 lbs | $550/year | $550/year, unchanged ([26 U.S.C. § 4481](https://www.law.cornell.edu/uscode/text/26/4481)) | No (fresh control); 0.0% |
| Assumptions!B27 | US federal corporate income tax rate | 21.0% | 21.0%, unchanged ([26 U.S.C. § 11(b)](https://www.law.cornell.edu/uscode/text/26/11)) | No (fresh control); 0.0% |

## Other hardcoded inputs (not market drivers)

None of these should be flagged as stale. They are company plans, contract terms or house views. The fuel surcharge peg price (B8) is a contract term, not a diesel price, so it should not be compared to market diesel.

| Cell | Driver | Value in model |
|---|---|---|
| Assumptions!B5 | FY2025A operating revenue | $3,050.0M |
| Assumptions!B6:B10 | Miles FY2026E, linehaul rate per mile, fuel surcharge peg, surcharge mpg, surcharge coverage | 980.0M, $2.45, $1.25, 6.0, 85.0% |
| Assumptions!B11:B14 | Canada revenue (C$), Mexico costs (MXN), fleet mpg, tractors | C$420.0M, MXN 3,150.0M, 6.9, 6,500 |
| Assumptions!B15:B21 | Driver wages, maintenance, insurance per mile; other opex, D&A, capex, NWC as % of revenue | $0.95, $0.21, $0.14, 14.0%, 9.0%, 11.0%, 6.0% |
| Assumptions!B30:B33 | Equipment debt, amortization, margin over SOFR, cash | $1,100.0M, 10.0%, 1.85%, $140.0M |
| Assumptions!B36:F37 | Miles growth and rate per mile growth FY2026E–FY2030E | 3.0–3.5%; 2.0–2.5% |
| DCF!B6:B8, B13, B15 | ERP, beta, size premium, target debt/capital, terminal growth | 5.00%, 1.20, 1.00%, 35.0%, 2.5% |
| P&L row 25; DCF rows 5, 18, 27 and 29 (buried) | Unit conversions and dates: 1,000,000 ($ to $M), 365 (days per year), the valuation date and fiscal year-end dates | n/a |
