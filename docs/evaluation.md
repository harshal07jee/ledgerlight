# CUAD Extractive QA Gating Evaluation on Held-Out Test Split

**Evaluation Scope:** Complete held-out test split of 51 commercial contracts (510 contract-category evaluation instances) across target diligence categories.  
**Calibration Split Protocol:** Platt scaling parameters ($A=4.2049, B=-1.0237$) fitted on the 51 validation split contracts (510 instances) and evaluated on the 51 test contracts.  
**Air-Gap Guarantee:** 100% local CPU execution. Zero document text leaves the machine.  
**Scope Notice:** *This evaluation was conducted on commercial contracts only; employment agreements, PIIAs, and SAFE financing documents are untested in the CUAD dataset.*

---

## 1. Executive Summary & Gating Metrics

All confidence intervals are exact Wilson score intervals. Sample size $n$ is explicitly stated for every figure:

| Metric | Measured Value | 95% Wilson Confidence Interval | Sample Size ($n$) | Operational Definition |
|---|:---:|:---:|:---:|---|
| **Coverage at $T_{high} = 0.85$** | **0.8%** | [0.3%, 2.0%] | $n=510$ | Fraction of contract-category pairs qualifying for high confidence |
| **Error Rate at $T_{high} = 0.85$** | **0.0%** | [0.0%, 49.0%] | $n=4$ accepted | False positives among accepted proposals at $T_{high}$ |
| **Coverage at $T_{low} = 0.50$** | **2.9%** | [1.8%, 4.8%] | $n=510$ | Fraction qualifying for human review queue (`NEEDS_CONFIRMATION`) |
| **Error Rate at $T_{low} = 0.50$** | **20.0%** | [7.0%, 45.2%] | $n=15$ accepted | False positives among surfaced proposals at $T_{low}$ |
| **Expected Calibration Error (Raw)** | **0.2855** | — | $n=510$ | 10-bin calibration gap before scaling |
| **Expected Calibration Error (Calibrated)** | **0.0314** | — | $n=510$ | 10-bin calibration gap after Platt scaling on validation split |

---

## 2. Per-Category Performance Breakdown

Measured at $T_{low} = 0.50$ across all 51 test contracts ($n=51$ per category). Intervals are exact Wilson score 95% intervals:

| Category | Gold Positives ($n$) | Surfaced ($n$) | Coverage (%) | Precision (%) | Recall (%) |
|---|:---:|:---:|:---:|:---:|:---:|
| **Change Of Control** | 15 | 2 | 3.9% [1.1%, 13.2%] | 100.0% [34.2%, 100.0%] | 13.3% [3.7%, 37.9%] |
| **Most Favored Nation** | 3 | 0 | 0.0% [0.0%, 7.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 56.1%] |
| **Exclusivity** | 18 | 0 | 0.0% [0.0%, 7.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 17.6%] |
| **Uncapped Liability** | 10 | 0 | 0.0% [0.0%, 7.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 27.8%] |
| **Cap On Liability** | 30 | 0 | 0.0% [0.0%, 7.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 11.3%] |
| **Ip Ownership Assignment** | 14 | 0 | 0.0% [0.0%, 7.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 21.5%] |
| **Renewal Term** | 17 | 8 | 15.7% [8.2%, 28.0%] | 75.0% [40.9%, 92.8%] | 35.3% [17.3%, 58.7%] |
| **Non-Compete** | 9 | 0 | 0.0% [0.0%, 7.0%] | 0.0% [0.0%, 0.0%] | 0.0% [0.0%, 29.9%] |
| **Termination For Convenience** | 11 | 1 | 2.0% [0.4%, 10.3%] | 0.0% [0.0%, 79.3%] | 0.0% [0.0%, 25.9%] |
| **Anti-Assignment** | 33 | 4 | 7.8% [3.1%, 18.5%] | 100.0% [51.0%, 100.0%] | 12.1% [4.8%, 27.3%] |

---

## 3. Comparative Baseline Evaluation

| Baseline / System | Description | Coverage (%) | Error Rate (%) [95% Wilson CI] | Sample Size ($n$) | Outcome |
|---|---|:---:|:---:|:---:|---|
| **1. Always Accept Top Prediction** | Selects candidate span regardless of score | 100.0% | 68.6% [64.5%, 72.5%] | $n=510$ | Rejected (Severe false positives) |
| **2. Keyword-Only Search** | Matches lexical token presence in text | 15.1% | 51.9% [41.0%, 62.7%] | $n=77$ | Rejected (Fails contractual semantics) |
| **3. Fixed Baseline ($T = 0.50$)** | Uncalibrated score cutoff at 0.50 | 2.9% | 20.0% [7.0%, 45.2%] | $n=15$ | Used for `NEEDS_CONFIRMATION` queue |
| **4. Calibrated Dual-Gated CUAD** | $T_{high}=0.85$, $T_{low}=0.50$, Platt scaled | **0.8%** | **0.0%** [0.0%, 49.0%] | $n=4$ | Active Gating Framework |

---

## 4. Threshold Sweep Table (Excerpt from docs/threshold_study_results.csv)

| Threshold ($T$) | Coverage (%) [95% CI] | Error Rate (%) [95% CI] | Accepted ($n$) | Total ($n$) |
|:---:|:---:|:---:|:---:|:---:|
| **0.30** | 3.5% [2.2%, 5.5%] | 22.2% [9.0%, 45.2%] | 18 | 510 |
| **0.50 ($T_{low}$)** | 2.9% [1.8%, 4.8%] | 20.0% [7.0%, 45.2%] | 15 | 510 |
| **0.70** | 1.2% | 16.7% | 6 | 510 |
| **0.85 ($T_{high}$)** | 0.8% [0.3%, 2.0%] | 0.0% [0.0%, 49.0%] | 4 | 510 |
| **0.95** | 0.2% | 0.0% | 1 | 510 |

---

## 5. What the Results Mean in Plain Words

1. **Commercial Contracts Only:**
   This evaluation was conducted exclusively on commercial contracts from SEC EDGAR filings (supply, licensing, distributor, and vendor agreements). **Employment agreements, PIIAs, and SAFE financing documents are untested in CUAD** and must remain strictly human-verified.
2. **Clause Span as Evidence, Not Verdict:**
   Extracting an agreement clause proves that a legal provision exists at that specific page and offset. It does not determine whether the company complied with the clause. Therefore, for qualitative compliance questions, the system proposes "Clause found" with `NEEDS_CONFIRMATION`; human auditors retain final review authority.
3. **Company-Level vs. Contract-Level Evidence:**
   For questions asking whether "any active agreements contain X", surfacing an extracted clause above $T_{low}$ proposes "Yes" for verification. Crucially, **not finding a clause never auto-fills "No"**; failing to find a clause in a sample document does not prove absence across the company's entire historical portfolio.
4. **Air-Gap Invariant:**
   Model execution operates on CPU locally. Zero contract text, snippets, or confidential company figures leave the environment.
