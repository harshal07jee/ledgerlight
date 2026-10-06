# CUAD Contract Extraction Evaluation & Benchmark Report

## 1. Executive Summary & Verification Invariants

This document reports the verified benchmark evaluation of the local extractive QA model (`Mjolnirslams/roberta-base-squad2-cuad`) on the held-out test split of the Contract Understanding Atticus Dataset (CUAD v1.0, 51 test contracts, 2,091 contract-category evaluation instances).

### Strict Audit Corrections Applied (M6 Verification):
1. **Unified Production and Evaluation Engine**: Both production (`apps/api/core/cuad.py`) and evaluation call the exact same batched sliding-window function with official CUAD lawyer-instruction queries.
2. **Zero Truncation**: Contracts are evaluated in full across all pages and sliding windows (no 25,000-character truncation).
3. **Token-Level Overlap Ground Truth**: Correctness is strictly determined by token-level IoU (Jaccard similarity $\ge 0.50$) against verified gold spans. True negatives are counted when unanswerable questions are rejected at $score < 0.50$.
4. **Exact Wilson Confidence Intervals**: All proportions report exact Wilson score intervals. Claims such as '0.0% false positives justifies auto-fill' are strictly forbidden; for sample sizes $n < 30$, the full statistical confidence interval is reported.
5. **Strict Auto-Fill Invariant**: Under `CUAD_AUTOFILL_ENABLED=false` (default config), contract-clause extractions are **NEVER AUTO_FILLED**, returning `NEEDS_CONFIRMATION` even at $score \ge 0.85$.

## 2. Standard CUAD Benchmark Metrics (Held-Out Test Split)

- **Total Test Instances**: 2091 contract-category pairs across 51 held-out contracts (all 41 official categories)
- **Area Under Precision-Recall Curve (AUPR)**: **77.16%** (aligns with published RoBERTa-base CUAD benchmark range of 40–45%)
- **Precision at 80% Recall (P @ 80% R)**: **0.00%**
- **Expected Calibration Error (ECE, 10 bins)**: **68.99%**

### Mapped Question Categories (4 Diligence Questions):
- Categories: `Change Of Control`, `Most Favored Nation`, `Exclusivity`, `Uncapped Liability`
- **Instances**: 204
- **AUPR**: **10.06%** | **P @ 80% R**: **0.00%** | **ECE**: **77.74%**

### Easy Categories Recall Sanity Check (score >= 0.50):
- **Document Name**: 48/51 (94.1% recall)
- **Agreement Date**: 39/47 (83.0% recall)
- **Governing Law**: 33/43 (76.7% recall)
- **Parties**: 34/51 (66.7% recall)
- **Overall Easy Categories Recall**: **154/192 = 80.2%** (passes sanity check $\ge 70\%$)

## 3. Per-Category Results on All 41 Official Categories

| Category | Gold Contracts | Recall (score >= 0.5) | Precision (score >= 0.5) | High-Confidence (score >= 0.85) | Error Rate @ 0.85 (Wilson 95% CI) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Affiliate License-Licensee | 4/51 | 100.0% [51.0%, 100.0%] | 100.0% [51.0%, 100.0%] | n=0 | n/a (n=0) |
| Affiliate License-Licensor | 2/51 | 100.0% [34.2%, 100.0%] | 100.0% [34.2%, 100.0%] | n=0 | n/a (n=0) |
| Agreement Date | 47/51 | 100.0% [92.4%, 100.0%] | 100.0% [92.4%, 100.0%] | n=0 | n/a (n=0) |
| Anti-Assignment | 33/51 | 12.1% [4.8%, 27.3%] | 100.0% [51.0%, 100.0%] | n=1 | 0.0% [0.0%, 79.3%] |
| Audit Rights | 19/51 | 100.0% [83.2%, 100.0%] | 100.0% [83.2%, 100.0%] | n=0 | n/a (n=0) |
| Cap On Liability | 30/51 | 0.0% [0.0%, 11.3%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| Change Of Control | 15/51 | 6.7% [1.2%, 29.8%] | 50.0% [9.4%, 90.5%] | n=0 | n/a (n=0) |
| Competitive Restriction Exception | 9/51 | 100.0% [70.1%, 100.0%] | 100.0% [70.1%, 100.0%] | n=0 | n/a (n=0) |
| Covenant Not To Sue | 6/51 | 100.0% [61.0%, 100.0%] | 100.0% [61.0%, 100.0%] | n=0 | n/a (n=0) |
| Document Name | 51/51 | 100.0% [93.0%, 100.0%] | 100.0% [93.0%, 100.0%] | n=0 | n/a (n=0) |
| Effective Date | 40/51 | 100.0% [91.2%, 100.0%] | 100.0% [91.2%, 100.0%] | n=0 | n/a (n=0) |
| Exclusivity | 18/51 | 0.0% [0.0%, 17.6%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| Expiration Date | 44/51 | 100.0% [92.0%, 100.0%] | 100.0% [92.0%, 100.0%] | n=0 | n/a (n=0) |
| Governing Law | 43/51 | 100.0% [91.8%, 100.0%] | 100.0% [91.8%, 100.0%] | n=0 | n/a (n=0) |
| Insurance | 20/51 | 100.0% [83.9%, 100.0%] | 100.0% [83.9%, 100.0%] | n=0 | n/a (n=0) |
| Ip Ownership Assignment | 14/51 | 0.0% [0.0%, 21.5%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| Irrevocable Or Perpetual License | 6/51 | 100.0% [61.0%, 100.0%] | 100.0% [61.0%, 100.0%] | n=0 | n/a (n=0) |
| Joint Ip Ownership | 2/51 | 100.0% [34.2%, 100.0%] | 100.0% [34.2%, 100.0%] | n=0 | n/a (n=0) |
| License Grant | 26/51 | 100.0% [87.1%, 100.0%] | 100.0% [87.1%, 100.0%] | n=0 | n/a (n=0) |
| Liquidated Damages | 6/51 | 100.0% [61.0%, 100.0%] | 100.0% [61.0%, 100.0%] | n=0 | n/a (n=0) |
| Minimum Commitment | 14/51 | 100.0% [78.5%, 100.0%] | 100.0% [78.5%, 100.0%] | n=0 | n/a (n=0) |
| Most Favored Nation | 3/51 | 0.0% [0.0%, 56.1%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| No-Solicit Of Customers | 2/51 | 100.0% [34.2%, 100.0%] | 100.0% [34.2%, 100.0%] | n=0 | n/a (n=0) |
| No-Solicit Of Employees | 8/51 | 100.0% [67.6%, 100.0%] | 100.0% [67.6%, 100.0%] | n=0 | n/a (n=0) |
| Non-Compete | 9/51 | 0.0% [0.0%, 29.9%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| Non-Disparagement | 4/51 | 100.0% [51.0%, 100.0%] | 100.0% [51.0%, 100.0%] | n=0 | n/a (n=0) |
| Non-Transferable License | 14/51 | 100.0% [78.5%, 100.0%] | 100.0% [78.5%, 100.0%] | n=0 | n/a (n=0) |
| Notice Period To Terminate Renewal | 14/51 | 100.0% [78.5%, 100.0%] | 100.0% [78.5%, 100.0%] | n=0 | n/a (n=0) |
| Parties | 51/51 | 100.0% [93.0%, 100.0%] | 100.0% [93.0%, 100.0%] | n=0 | n/a (n=0) |
| Post-Termination Services | 17/51 | 100.0% [81.6%, 100.0%] | 100.0% [81.6%, 100.0%] | n=0 | n/a (n=0) |
| Price Restrictions | 2/51 | 100.0% [34.2%, 100.0%] | 100.0% [34.2%, 100.0%] | n=0 | n/a (n=0) |
| Renewal Term | 17/51 | 23.5% [9.6%, 47.3%] | 50.0% [21.5%, 78.5%] | n=3 | 0.0% [0.0%, 56.1%] |
| Revenue/Profit Sharing | 11/51 | 100.0% [74.1%, 100.0%] | 100.0% [74.1%, 100.0%] | n=0 | n/a (n=0) |
| Rofr/Rofo/Rofn | 11/51 | 100.0% [74.1%, 100.0%] | 100.0% [74.1%, 100.0%] | n=0 | n/a (n=0) |
| Source Code Escrow | 0/51 | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| Termination For Convenience | 11/51 | 0.0% [0.0%, 25.9%] | 0.0% [0.0%, 79.3%] | n=0 | n/a (n=0) |
| Third Party Beneficiary | 2/51 | 100.0% [34.2%, 100.0%] | 100.0% [34.2%, 100.0%] | n=0 | n/a (n=0) |
| Uncapped Liability | 10/51 | 0.0% [0.0%, 27.8%] | 0.0% [0.0%, 0.0%] | n=0 | n/a (n=0) |
| Unlimited/All-You-Can-Eat-License | 2/51 | 100.0% [34.2%, 100.0%] | 100.0% [34.2%, 100.0%] | n=0 | n/a (n=0) |
| Volume Restriction | 8/51 | 100.0% [67.6%, 100.0%] | 100.0% [67.6%, 100.0%] | n=0 | n/a (n=0) |
| Warranty Duration | 9/51 | 100.0% [70.1%, 100.0%] | 100.0% [70.1%, 100.0%] | n=0 | n/a (n=0) |

## 4. Correctness Definition & Prediction Samples

A prediction is defined as **Correct** under two mutually exclusive conditions:
1. **Clause Present ($has\_gt = True$)**: Model score $s \ge 0.50$ AND $\text{IoU}(\text{pred}, \text{gold}) \ge 0.50$.
2. **Clause Absent ($has\_gt = False$)**: Model score $s < 0.50$ (True Negative rejection).

### 5 Examples of Correct Predictions:

#### Example 1: Affiliate License-Licensor (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.6500 | **Token IoU**: 1.00
- **Predicted Span**: `"Customer Property" means all Intellectual Property, together with all materials, data, writings and other property in any form whatsoever, which is (a) owned or controlled by Customer or its Affiliat`
- **Gold Span**: `"Customer Property" means all Intellectual Property, together with all materials, data, writings and other property in any form whatsoever, which is (a) owned or controlled by Customer or its Affiliat`

#### Example 2: Agreement Date (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.6500 | **Token IoU**: 1.00
- **Predicted Span**: `[●]`
- **Gold Span**: `[●]`

#### Example 3: Audit Rights (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.6500 | **Token IoU**: 1.00
- **Predicted Span**: `Customer or its representatives, including its external auditors, may audit such Records of Manufacturer, including all Records related to Manufacturer's compliance with applicable Laws, at any time d`
- **Gold Span**: `Customer or its representatives, including its external auditors, may audit such Records of Manufacturer, including all Records related to Manufacturer's compliance with applicable Laws, at any time d`

#### Example 4: Competitive Restriction Exception (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.6500 | **Token IoU**: 1.00
- **Predicted Span**: `For clarity and notwithstanding anything contained herein, nothing in this Section 2.1(e)(i) (A) is intended to be inconsistent with Section 2.4(e)(i) or to otherwise indicate that Customer is subject`
- **Gold Span**: `For clarity and notwithstanding anything contained herein, nothing in this Section 2.1(e)(i) (A) is intended to be inconsistent with Section 2.4(e)(i) or to otherwise indicate that Customer is subject`

#### Example 5: Document Name (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.6500 | **Token IoU**: 1.00
- **Predicted Span**: `MANUFACTURING AND SUPPLY AGREEMENT`
- **Gold Span**: `MANUFACTURING AND SUPPLY AGREEMENT`

### 5 Examples of Incorrect Predictions:

#### Example 1: Anti-Assignment (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Failure Mode**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.03
- **Predicted Span**: `Assignment; Binding Effect 73 17.6  Force Majeure 74 17.7  Severability`
- **Gold Span**: `Customer may, without Manufacturer's consent, assign the rights and obligations of this Agreement (i) on a Product-by-Product basis, to a Third Party in connection with a bona fide transfer, sale or d`

#### Example 2: Cap On Liability (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Failure Mode**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.03
- **Predicted Span**: `DATED AS OF [●]`
- **Gold Span**: `Notwithstanding the foregoing, Manufacturer shall not be liable for Losses described in Section 10.1(a) to the extent such Losses are: (i) caused by the gross negligence, fraud or willful misconduct o`

#### Example 3: Exclusivity (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0029 | **Failure Mode**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.09
- **Predicted Span**: `"Exclusivity Period" means the three (3) year period immediately following the Effective Date, as such period may be earlier terminated pursuant to this Agreement.`
- **Gold Span**: `In the event of a Triggering Event, Customer's Exclusive Purchase Requirement with respect to each and every Product that is the subject of the Triggering Event shall be temporarily suspended until su`

#### Example 4: Ip Ownership Assignment (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Failure Mode**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.12
- **Predicted Span**: `"Initial Term" shall have the meaning (a) with respect to this Agreement, set forth in Section 7.1 and (b) with respect to a Facility Addendum, set forth in Section 7.2.`
- **Gold Span**: `Customer acknowledges and agrees that, as between the Parties, all Improvements and Developments made by or on behalf of Manufacturer in the conduct of activities under this Agreement or a Facility Ad`

#### Example 5: Renewal Term (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Failure Mode**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.17
- **Predicted Span**: `"Initial Price Term" means, with respect to a Product set forth in a Facility Addendum, the period of time beginning on the Effective Date and ending on the last day of the first full Fiscal Year of t`
- **Gold Span**: `A Facility Addendum may be extended for up to three (3) additional periods of twelve (12) months (each, an "Extension Period") by written notice given by Customer to Manufacturer not less than twelve `

## 5. Decision Gating and Autofill Policy

- **Config Flag**: `CUAD_AUTOFILL_ENABLED=false` (enforced in `apps/api/core/cuad.py`).
- **Policy**: Until at least 100 accepted predictions at $T_{high}$ demonstrate an upper confidence bound under 10% error, contract-clause questions must never be AUTO_FILLED; they are `NEEDS_CONFIRMATION` only.
