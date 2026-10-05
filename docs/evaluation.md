# CUAD Extractive QA Gating Evaluation & Threshold Study

**Model:** `Mjolnirslams/roberta-base-squad2-cuad`  
**Base Architecture:** `deepset/roberta-base-squad2` fine-tuned on the Atticus CUAD Dataset  
**License:** CC-BY-4.0  
**Download Size:** ~473.26 MB (496,250,208 bytes, 124M parameters)  
**Evaluation Scope:** 41 Official CUAD Contract Clause Categories  
**Air-Gap Guarantee:** 100% Local CPU Execution. Zero document text leaves the machine.

---

## 1. Executive Summary & Gating Metrics

| Metric | Measured Value | Standard Target | Interpretation |
|---|:---:|:---:|---|
| **Coverage at $T_{high} = 0.85$** | **4.0%** | 15–25% | Fraction of contract clauses passing strict auto-fill gating |
| **Error Rate at $T_{high} = 0.85$** | **33.3%** | $\le 5.0\%$ | Strict safety invariant: minimal false positives at auto-fill |
| **Coverage at $T_{low} = 0.50$** | **10.7%** | 30–50% | Proposals surfaced to user in confirmation queue |
| **Expected Calibration Error (Raw)** | **0.0437** | $\le 0.15$ | Calibration alignment before temperature scaling |
| **Expected Calibration Error (Calibrated)** | **0.0437** | $\le 0.10$ | Calibration alignment after scaling |

---

## 2. Comparative Baseline Evaluation

| System / Baseline | Description | Coverage (%) | Error Rate (%) | Status in Platform |
|---|---|:---:|:---:|---|
| **1. Always Accept Top Prediction** | Naive maximum span selection without threshold gating | 100.0% | 90.7% | **REJECTED** (High false positive rate) |
| **2. Keyword-Only Search** | Lexical string matching across contract text | 49.3% | 81.1% | **REJECTED** (Fails context & semantics) |
| **3. Fixed Baseline ($T = 0.50$)** | Low threshold without dual-tier presence gating | 10.7% | 25.0% | Used for `NEEDS_CONFIRMATION` queue |
| **4. Calibrated Dual-Gated CUAD (Ledgerlight)** | $T_{high} = 0.85$, $T_{low} = 0.50$, pure presence only for auto-fill | **4.0%** | **33.3%** | **PRODUCTION STANDARD (M6)** |

---

## 3. Threshold Sweep Table (Excerpt)

| Threshold | Coverage (%) | Error Rate (%) | Action in Platform |
|:---:|:---:|:---:|---|
| **0.30** | 10.7% | 25.0% | Rejected (Below $T_{low}$) |
| **0.50 ($T_{low}$)** | 10.7% | 25.0% | Proposes Evidence (`NEEDS_CONFIRMATION`) |
| **0.70** | 8.0% | 16.7% | Verified Evidence (`NEEDS_CONFIRMATION`) |
| **0.85 ($T_{high}$)** | 4.0% | 33.3% | `AUTO_FILLED` (Pure presence only) |
| **0.95** | 1.3% | 0.0% | High-certainty presence |

---

## 4. Operational Gating Rules (PRD 7.5 & 12.1)
1. **Clause Span as Evidence, Not Verdict:**
   When a clause span is extracted, it highlights the exact passage and page. For qualitative / compliance clauses, it proposes `"Clause found"` with status `NEEDS_CONFIRMATION`; human auditors decide compliance.
2. **Pure Presence Restrictions:**
   Only pure presence questions (e.g. poison pills, MFN, anti-assignment) may ever achieve `AUTO_FILLED` above $T_{high}$.
3. **Structured Audit Logging (PRD 12.1):**
   Every extraction logs `model_name`, `raw_score`, `calibrated_score`, `status`, `user_action`, and `latency_ms`. **Zero document text is stored in the audit logs.**
