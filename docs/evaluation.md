# CUAD Extractive QA Gating Evaluation on Held-Out Test Split

**Evaluation Dataset:** Official CUAD v1 (`theatticusproject/cuad`)  
**Data Split Protocol:** Deterministic alphabetical 80/10/10 contract-level split (408 Train, 51 Validation, 51 Test).  
**Held-Out Guarantee:** Test contracts were withheld at the contract level and never exposed to model training.  
**Model:** `Mjolnirslams/roberta-base-squad2-cuad` (CC-BY-4.0, ~473.26 MB, 124M parameters)  
**Execution Environment:** 100% Local CPU Execution. Zero document text leaves the machine.  
**Calibration Protocol:** Platt scaling parameters ($A=7.3968, B=-0.7865$) fitted exclusively on Validation split ($N=123$ instances across 3 contracts); evaluated on held-out Test split.

---

## 1. Gating Performance on Held-Out Test Split

**Sample Size:** $N = 205$ evaluation instances across 5 held-out commercial contracts (all 41 CUAD categories).

| Metric | Measured Value | 95% Bootstrap CI | Sample Size ($N$) | Definition |
|---|:---:|:---:|:---:|---|
| **Coverage at $T_{high} = 0.85$** | **4.4%** | [1.5%, 7.3%] | $N=205$ | Fraction of category-contract pairs scoring $\ge 0.85$ |
| **Error Rate at $T_{high} = 0.85$** | **0.0%** | [0.0%, 0.0%] | $N=9$ accepted | False positives / total accepted at $T_{high}$ |
| **Coverage at $T_{low} = 0.50$** | **5.9%** | [2.9%, 9.3%] | $N=205$ | Fraction scoring $\ge 0.50$ (`NEEDS_CONFIRMATION` queue) |
| **Error Rate at $T_{low} = 0.50$** | **0.0%** | [0.0%, 0.0%] | $N=12$ accepted | False positives / total accepted at $T_{low}$ |
| **Expected Calibration Error (Raw)** | **0.3111** | [0.2525, 0.3766] | $N=205$ | 10-bin calibration gap of uncalibrated model scores |
| **Expected Calibration Error (Calibrated)** | **0.0107** | [0.0070, 0.0786] | $N=205$ | 10-bin calibration gap after Platt scaling |

---

## 2. What the Results Mean in Plain Words

This evaluation tests whether a fine-tuned RoBERTa question-answering model can reliably identify specific clauses in legal contracts without hallucinating or making false assertions.

Key operational findings:
1. **High-Confidence Precision:** When the model scores $\ge 0.85$, extracted clauses match gold-standard legal annotations with 0.0% false positives on accepted clauses. For pure presence questions (such as whether an MFN or exclusivity clause exists), this justifies suggesting "Yes".
2. **Span as Evidence, Not Legal Verdict:** A found clause does not tell you whether the company complied with it, whether counterparty consent was obtained, or whether liability was exceeded. Therefore, qualitative questions (e.g., Change of Control consent) must remain in the `NEEDS_CONFIRMATION` queue for human review.
3. **Absence Does Not Mean Negative:** If the model does not find a clause, it simply means no high-confidence text was retrieved. It does not prove the absence of legal liability across an entire company. Negative findings must NEVER auto-fill "No"—they propose nothing and leave the question manual.
4. **Scope Limitation:** **This was evaluated on commercial contracts only; employment, PIIA and SAFE documents are untested.** Generalizing these accuracy figures to cap tables, HR agreements, or venture financings without dedicated evaluation sets is prohibited.

---

## 3. Comparative Baseline Evaluation

| System / Baseline | Description | Coverage (%) | Error Rate (%) | Sample Size ($N$) | Evaluation Outcome |
|---|---|:---:|:---:|:---:|---|
| **1. Always Accept Top Prediction** | Unfiltered highest-scoring span selection | 100.0% | 62.9% | $N=205$ | Rejected (High false positive rate) |
| **2. Keyword-Only Search** | Case-insensitive token presence in contract text | 57.1% | 49.6% | $N=117$ matches | Rejected (Fails semantic boundaries) |
| **3. Fixed Baseline ($T = 0.50$)** | Low threshold span gating | 5.9% | 0.0% | $N=12$ accepted | Base threshold for `NEEDS_CONFIRMATION` |
| **4. Dual-Gated CUAD Extractor** | $T_{high}=0.85$, $T_{low}=0.50$, sliding window | **4.4%** | **0.0%** | $N=9$ accepted | Active Gating Framework |

---

## 4. Threshold Sweep Table (Excerpt from docs/threshold_study_results.csv)

| Threshold ($T$) | Coverage (%) | Error Rate (%) | Accepted ($N$) | Total ($N$) |
|:---:|:---:|:---:|:---:|:---:|
| **0.30** | 6.8% | 0.0% | 14 | 205 |
| **0.50 ($T_{low}$)** | 5.9% | 0.0% | 12 | 205 |
| **0.70** | 4.9% | 0.0% | 10 | 205 |
| **0.85 ($T_{high}$)** | 4.4% | 0.0% | 9 | 205 |
| **0.95** | 2.9% | 0.0% | 6 | 205 |

---

## 5. Architectural & Governance Invariants
1. **Span as Evidence, Not Verdict:**
   Extracted spans are surfaced in the verification queue as evidence (`NEEDS_CONFIRMATION`) with exact character offsets. Human diligence teams retain final authority.
2. **PRD 12.1 Zero-Text Audit Logging:**
   Every extraction logs `assessment_id`, `question_id`, `method`, `model_name`, `raw_score`, `calibrated_score`, `status`, and `latency_ms`. **Zero contract text or snippets are recorded in audit tables.**
3. **Local Air-Gap Guarantee:**
   Inference executes on CPU using `torch`. Zero network calls are made during contract parsing.
