# CUAD Contract Extraction Evaluation & Benchmark Report

## 1. Executive Summary & Verification Invariants

This document reports the verified benchmark evaluation of the local extractive QA model (`Mjolnirslams/roberta-base-squad2-cuad`) on the held-out test split of the Contract Understanding Atticus Dataset (CUAD v1.0, 51 test contracts, 510 genuine contract-category evaluation pairs across 10 diligence categories).

### Strict Audit Corrections Applied (M6 Verification):
1. **Quarantine and Removal of Fabricated Fallbacks**: All 1,581 synthetic fallback rows (which previously inserted constant scores 0.6500 for positives and 0.1500 for negatives) have been removed from `docs/cuad_predictions.csv` and evaluation metrics. All reported statistics derive strictly from genuine model inference.
2. **Official Per-Category CUAD Logic**: Metrics are computed per category following the official Atticus Project `evaluate.py` logic (`metrics.auc` on monotonically adjusted precision curves across confidence thresholds), rather than pooled across unrelated categories.
3. **Root Cause Analysis of Truncation & Low Recall**: In `scripts/threshold_study.py`, contracts were truncated to 25,000 characters (`eval_text = c_text[:25000]`). Because 32 of 51 test contracts are longer than 25,000 characters (mean length 36,000 characters; max 225,000 characters), 85% of gold clause spans were located beyond character 25,000 and physically omitted from the model context. This caused real model recall to cap at 6%–29% per category, producing a macro-average AUPR of 5.96% compared to the published benchmark of 42.6% on un-truncated contracts.
4. **Exact Wilson Confidence Intervals**: All proportions report exact Wilson score confidence intervals. With sample size $n < 30$, claims of 0.0% error are prohibited; the full statistical interval is reported.
5. **Strict Auto-Fill Invariant**: Under `CUAD_AUTOFILL_ENABLED=false` (default configuration), contract-clause questions are **NEVER AUTO_FILLED**, returning `NEEDS_CONFIRMATION` even at score $\ge 0.85$.

## 2. Standard CUAD Benchmark Metrics vs Published Baselines

- **Evaluated Instances**: 510 genuine predictions across 51 held-out test contracts (10 diligence categories)
- **Macro-Average AUPR (Official CUAD Script Logic)**: **5.96%**
- **Published CUAD Paper Baseline (RoBERTa-base, Hendrycks et al. Table 2)**: **42.6% AUPR**
- **Benchmark Gap**: **36.64 percentage points** (attributable to 25,000-character input truncation dropping >80% of target contract clauses)
- **Precision at 80% Recall (P @ 80% R)**: **0.00%** (0.00% because truncation prevented recall from ever reaching the 80% threshold; maximum observed recall was 29.41% on Renewal Term)
- **Expected Calibration Error (ECE, 10 equal-width bins)**: **67.81%**

### Diligence Question Categories (4 Mapped Question Categories):
- Categories: `Change Of Control`, `Most Favored Nation`, `Exclusivity`, `Uncapped Liability`
- **Test Instances**: 204 (46 ground truth clauses across 51 contracts)
- **Macro-Average AUPR**: **3.74%** | **P @ 80% R**: **0.00%** | **ECE**: **77.74%**

## 3. Per-Category Results (Official Atticus Evaluation Logic)

| Category | Gold Clauses (n) | Max Recall | Official AUPR | P @ 80% R | Recall @ 0.50 (Wilson 95% CI) | Precision @ 0.50 (Wilson 95% CI) | High-Conf (>=0.85) | Error Rate @ 0.85 (Wilson 95% CI) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| Anti-Assignment | 33 / 51 | 15.2% | 12.63% | 0.00% | 12.1% [4.8%, 27.3%] | 100.0% [51.0%, 100.0%] | n=1 | 0.0% [0.0%, 79.3%] |
| Cap On Liability | 30 / 51 | 0.0% | 0.00% | 0.00% | 0.0% [0.0%, 11.3%] | n/a (n=0) | n=0 | n/a (n=0) |
| Change Of Control | 15 / 51 | 6.7% | 3.33% | 0.00% | 6.7% [1.2%, 29.8%] | 50.0% [9.4%, 90.5%] | n=0 | n/a (n=0) |
| Exclusivity | 18 / 51 | 16.7% | 11.64% | 0.00% | 0.0% [0.0%, 17.6%] | n/a (n=0) | n=0 | n/a (n=0) |
| Ip Ownership Assignment | 14 / 51 | 7.1% | 3.57% | 0.00% | 0.0% [0.0%, 21.5%] | n/a (n=0) | n=0 | n/a (n=0) |
| Most Favored Nation | 3 / 51 | 0.0% | 0.00% | 0.00% | 0.0% [0.0%, 56.1%] | n/a (n=0) | n=0 | n/a (n=0) |
| Non-Compete | 9 / 51 | 11.1% | 2.78% | 0.00% | 0.0% [0.0%, 29.9%] | n/a (n=0) | n=0 | n/a (n=0) |
| Renewal Term | 17 / 51 | 29.4% | 25.62% | 0.00% | 23.5% [9.6%, 47.3%] | 50.0% [21.5%, 78.5%] | n=3 | 0.0% [0.0%, 56.1%] |
| Termination For Convenience | 11 / 51 | 0.0% | 0.00% | 0.00% | 0.0% [0.0%, 25.9%] | 0.0% [0.0%, 79.3%] | n=0 | n/a (n=0) |
| Uncapped Liability | 10 / 51 | 0.0% | 0.00% | 0.00% | 0.0% [0.0%, 27.8%] | n/a (n=0) | n=0 | n/a (n=0) |

## 4. Correctness Definition & Prediction Samples

A prediction is defined as **Correct** under two mutually exclusive conditions:
1. **Clause Present ($has\_gt = True$)**: Model score $s \ge 0.50$ AND $\text{IoU}(\text{pred}, \text{gold}) \ge 0.50$.
2. **Clause Absent ($has\_gt = False$)**: Model score $s < 0.50$ (True Negative rejection).

### 5 Examples of Correct Predictions (Genuine Model Output):

#### Example 1: Anti-Assignment (UsioInc_20040428_SB-2_EX-10.11_1723988_EX-10.11_Affiliate Agreement 2)
- **Score**: 0.7555 | **Token IoU**: 1.00
- **Predicted Span**: `This  agreement  may  not  be assigned or delegated by Affiliate without  prior  written  consent  from  Network  1.`
- **Gold Span**: `This  agreement  may  not  be assigned or delegated by Affiliate without  prior  written  consent  from  Network  1.`

#### Example 2: Anti-Assignment (VNUE,INC_07_10_2015-EX-10.1-SPONSORSHIP AGREEMENT)
- **Score**: 0.6614 | **Token IoU**: 1.00
- **Predicted Span**: `This Agreement is personal to each of the parties, and neither party may assign or delegate any of its rights or obligations under this Agreement without first obtaining the other party's written cons`
- **Gold Span**: `This Agreement is personal to each of the parties, and neither party may assign or delegate any of its rights or obligations under this Agreement without first obtaining the other party's written cons`

#### Example 3: Change Of Control (VertexEnergyInc_20200113_8-K_EX-10.1_11943624_EX-10.1_Marketing Agreement)
- **Score**: 0.5355 | **Token IoU**: 1.00
- **Predicted Span**: `A Party may terminate the JSMA immediately upon the delivery of written notice to the other Party if there has been a Change in Control.`
- **Gold Span**: `A Party may terminate the JSMA immediately upon the delivery of written notice to the other Party if there has been a Change in Control.`

#### Example 4: Renewal Term (VnueInc_20150914_8-K_EX-10.1_9259571_EX-10.1_Promotion Agreement)
- **Score**: 0.9933 | **Token IoU**: 1.00
- **Predicted Span**: `At any time prior to the end of the Term, the Parties may agree in writing to extend the Agreement for successive One (1) Year periods (the "Renewal Terms") under the same conditions set forth herein.`
- **Gold Span**: `At any time prior to the end of the Term, the Parties may agree in writing to extend the Agreement for successive One (1) Year periods (the "Renewal Terms") under the same conditions set forth herein.`

#### Example 5: Renewal Term (WOMENSGOLFUNLIMITEDINC_03_29_2000-EX-10.13-ENDORSEMENT AGREEMENT)
- **Score**: 0.9242 | **Token IoU**: 1.00
- **Predicted Span**: `The Company may renew this Agreement on the same terms and conditions for one (1) additional five year period that shall begin on January 1, 2005 and end on December 31, 2009, by providing a written n`
- **Gold Span**: `The Company may renew this Agreement on the same terms and conditions for one (1) additional five year period that shall begin on January 1, 2005 and end on December 31, 2009, by providing a written n`

### 5 Examples of Incorrect Predictions (Genuine Model Output):

#### Example 1: Exclusivity (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0029 | **Decision**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.10
- **Predicted Span**: `"Exclusivity Period" means the three (3) year period immediately following the Effective Date, as such period may be earlier terminated pursuant to this Agreement.`
- **Gold Span**: `In the event of a Triggering Event, Customer's Exclusive Purchase Requirement with respect to each and every Product that is the subject of the Triggering Event shall be temporarily suspended until su`

#### Example 2: Uncapped Liability (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Decision**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.12
- **Predicted Span**: `"Initial Term" shall have the meaning (a) with respect to this Agreement, set forth in Section 7.1 and (b) with respect to a Facility Addendum, set forth in Section 7.2.`
- **Gold Span**: `Except in the event of (i) Third Party Claims subject to a Party's indemnification obligations pursuant to Section 10.1, (ii) Third Party Claims subject to a Party's indemnification obligations pursua`

#### Example 3: Cap On Liability (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Decision**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.03
- **Predicted Span**: `DATED AS OF [●]`
- **Gold Span**: `Notwithstanding the foregoing, Manufacturer shall not be liable for Losses described in Section 10.1(a) to the extent such Losses are: (i) caused by the gross negligence, fraud or willful misconduct o`

#### Example 4: Ip Ownership Assignment (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Decision**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.17
- **Predicted Span**: `"Initial Term" shall have the meaning (a) with respect to this Agreement, set forth in Section 7.1 and (b) with respect to a Facility Addendum, set forth in Section 7.2.`
- **Gold Span**: `Customer acknowledges and agrees that, as between the Parties, all Improvements and Developments made by or on behalf of Manufacturer in the conduct of activities under this Agreement or a Facility Ad`

#### Example 5: Renewal Term (UpjohnInc_20200121_10-12G_EX-2.6_11948692_EX-2.6_Manufacturing Agreement_ Supply Agreement)
- **Score**: 0.0000 | **Decision**: `FALSE_NEGATIVE_MISSED` | **Token IoU**: 0.18
- **Predicted Span**: `"Initial Price Term" means, with respect to a Product set forth in a Facility Addendum, the period of time beginning on the Effective Date and ending on the last day of the first full Fiscal Year of t`
- **Gold Span**: `A Facility Addendum may be extended for up to three (3) additional periods of twelve (12) months (each, an "Extension Period") by written notice given by Customer to Manufacturer not less than twelve `

## 5. Autofill Policy and Safety Gating

- **Config Flag**: `CUAD_AUTOFILL_ENABLED=false` (enforced in `apps/api/core/cuad.py`).
- **Safety Invariant**: Until at least 100 accepted predictions at $T_{high}$ demonstrate an upper confidence bound under 10% error, contract-clause questions must never be AUTO_FILLED; they are `NEEDS_CONFIRMATION` only.
