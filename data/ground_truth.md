# Case study ground truth

Workbook: `Drift_Hertz_Mock_Fleet_Model.xlsx` (assumptions set Dec 2023). Owner: Matthew.

List every constant we planted and what the pipeline should conclude. `engine/tests/test_case_study.py` checks against this.

| Cell | Driver | Value in model | Expected live (source, date) | Should be stale? |
|---|---|---|---|---|
| Inputs!B11 | Residual value of a 2-3 year old EV at disposal (as % of cost) | 72.00% | 49.97% (Manheim / Cox Automotive used EV values; iSeeCars used EV price studies, 2023-12) | Yes; -30.6%, EBITDA -182M |
| Inputs!B12 | Residual value of a 2 year old gas car at disposal (as % of cost) | 82.00% | 80.03% (Manheim Used Vehicle Value Index, 2023-12) | Yes; -2.4%, EBITDA -157M |
| Inputs!B16 | Blended cost of fleet debt (floating-rate ABS, partly hedged) | 3.40% | 5.63% (1M Term SOFR (FRED) plus peer-reported fleet interest per unit, 2023-Q4) | Yes; +65.5%, EBITDA -237M |
| Fleet_Model!B11 (buried constant 1.2) | EV collision repair cost relative to a gas car | 1.20x | 1.56x (CCC Intelligent Solutions crash-course / repair cost reports, 2022 data) | Yes; +30.0%, EBITDA -21M |
| Fleet_Model!B13, C13 (buried constant 0.015) | Remarketing / auction fee as % of sale proceeds | 1.50% | 1.50% (Auction house fee schedules (Manheim, ADESA), 2023) | No (fresh control); +0.0%, EBITDA +0M |
| Inputs!B8 | Rental revenue per day | $61.00 | $58.09 reference only (Reference only: peer-reported RPD, 2023-Q4) | No: label only, management lever; EBITDA -456M if moved |
| Inputs!B9 | EV acquisition cost per car | $42,000 | n/a | No: not a market driver |
| Inputs!B10 | ICE acquisition cost per car | $33,000 | n/a | No: not a market driver |
| Inputs!B13 | EV holding period | 36 | n/a | No: not a market driver |
| Inputs!B14 | ICE holding period | 24 | n/a | No: not a market driver |
| Inputs!B7 | Fleet utilization | 78.00% | n/a | No: not a market driver |
| Inputs!B5 | EV fleet size | 60,000 | n/a | No: not a market driver |
| Inputs!B6 | ICE fleet size | 490,000 | n/a | No: not a market driver |
| Inputs!B15 | Average debt per car | $19,400 | n/a | No: not a market driver |
| Inputs!B17 | ICE collision cost per day | $3.40 | n/a | No: not a market driver |
| Inputs!B18 | Other direct operating cost per day | $27.00 | n/a | No: not a market driver |
| Inputs!B19 | SG&A | $1,600M | n/a | No: not a market driver |
| Fleet_Model!B6, C6 (buried) | Days per year (365) | 365 | n/a | No: not a market driver |
| Fleet_Model rows 9, 13 (buried) | Months per year (12) | 12 | n/a | No: not a market driver |
| Fleet_Model rows 7-13 (buried) | Dollars to $M scaling (1,000,000) | 1,000,000 | n/a | No: not a market driver |

Source: `Drift_Hertz_Mock_Fleet_Model.xlsx`, sheet `Driver_Map` (model built 2022-12-15, refreshed 2023-12-04). Mock company calibrated to Hertz's Q4 2023 EV write-down. Market_Data monthly series are synthetic; dollar impacts are one-at-a-time vs an as-built EBITDA of $1,018M. NOTE: the workbook named in the header above (`case_study_aug2026.xlsx`, set 2026-08-01) is a different file; reconcile the name and date before running `test_case_study.py`.
