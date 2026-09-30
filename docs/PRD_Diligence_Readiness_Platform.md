# PRD — Diligence Readiness Platform (working name: **Ledgerlight**)

> **How to use this document (for the AI builder):** Read the whole PRD before writing code. Build in the milestone order in Section 15. Where this document says **MUST**, it is a hard requirement. Where it says **SHOULD**, use judgment. Where something is marked **[ASSUMPTION]**, ask the human before changing it. Never invent data, statistics, regulatory citations, or benchmark numbers. If a value is not in the seed files or this PRD, leave it configurable and flag it.

---

## 1. Product summary

A web platform where a company preparing for investment (VC round, growth financing, M&A, IPO prep) uploads its data room and receives:

1. An **explainable Readiness Score** (0–100) with per-dimension scores.
2. A **gap list** where every gap traces back to a specific question, rule, and source document passage.
3. A **30/60/90/180-day remediation roadmap** generated from the failed and unverified items.

The goal is for founders to find their deal-breakers *before* an investor does.

**Initial market:** United States. UK and other Western markets are later phases (the schema must already support a `geography` tag).

**What this product is not:**
- It does **not** predict the probability of raising capital, being acquired, or completing an IPO.
- It does **not** give investment advice, legal advice, or connect users to investors (no brokerage / matchmaking).
- It does **not** use a black-box model to produce the score. The score is deterministic and rules-based.

Every report and the footer MUST carry a disclaimer: *"This is a readiness assessment based on the information provided. It is not legal, financial, or investment advice and does not predict transaction outcomes."*

---

## 2. Research framing (drives several design choices)

This project also feeds an academic paper, so the system must be **measurable**. The core contribution being tested:

> **Confidence-gated, evidence-linked extraction with a deterministic scoring layer**: an extractive QA model fills a regulatory-grounded question bank; low-confidence or missing answers are routed to a human instead of being guessed; the final score is computed by transparent rules, and every point deducted is traceable to a question, a rule, and a source passage.

Therefore the system MUST log everything needed for evaluation (Section 12), including per-answer confidence, whether the user accepted/corrected the auto-fill, and the final ground-truth value. Do not skip this logging.

**Claims policy:** The UI, docs, and any generated text MUST NOT claim "zero hallucinations", "100% accurate", or "guaranteed". Use wording like "extractive answers are linked to source text and low-confidence answers are sent for human review."

---

## 3. Users and use cases

| Persona | Description | Main need |
|---|---|---|
| **Founder / CFO** (primary) | Startup or SME leader preparing for a raise | Know what an investor will flag; get a fix list |
| **Advisor / counsel** (secondary) | Lawyer or consultant helping a client | Review answers, evidence, and the trace |
| **Admin** (internal) | Team maintaining the question bank | Edit questions, weights, citations; monitor extraction quality |

**Core user journey:** Sign up → describe company → upload documents → review auto-filled answers → answer what's missing → get score, trace, and roadmap → export PDF → re-assess later and compare.

---

## 4. Scope

### In scope (MVP)
- Onboarding with company profile and industry/sub-sector selection.
- Question bank: Universal Core (11 dimensions) + 5 industry branches (Healthcare, FinTech, Software/SaaS, Manufacturing & Industrial, Energy & CleanTech), USA only.
- Conditional question gating (`depends_on`).
- Document upload and extraction with confidence gating.
- Manual answer entry with optional evidence upload.
- Deterministic scoring engine with transaction-type weighting.
- Score trace ("why this score") view.
- Roadmap generation (30/60/90/180).
- PDF export of the report.
- Admin console for the question bank and extraction-quality metrics.
- Security controls in Section 11.

### Out of scope (MVP)
- Investor matchmaking, growth/TAM roadmaps, valuation.
- Multi-country rulesets (schema-ready only).
- Third-party integrations (QuickBooks, Xero, CRM).
- Fine-tuning models (use pre-trained; training is a later research task).
- Real peer benchmarking (needs real anonymized data; see Section 9.5).

---

## 5. System architecture

```
┌────────────────────────┐        ┌──────────────────────────────────────┐
│  Next.js frontend      │  HTTPS │  API service (FastAPI)               │
│  (TypeScript, Tailwind,│◄──────►│  auth, questionnaire, scoring,       │
│   shadcn/ui, Motion)   │        │  roadmap, reports, admin             │
└────────────────────────┘        └───────────┬──────────────┬───────────┘
                                              │              │
                                   job queue  │              │ SQL
                                              ▼              ▼
                                  ┌────────────────┐   ┌────────────────┐
                                  │ Extraction     │   │ PostgreSQL     │
                                  │ worker         │   │ (encrypted)    │
                                  │ (Python, HF    │   └────────────────┘
                                  │ transformers)  │
                                  └────────────────┘
```

**Recommended stack [ASSUMPTION — confirm with team]:**
- **Frontend:** Next.js (App Router) + TypeScript + Tailwind CSS + shadcn/ui + Motion (Framer Motion). Charts: visx or Recharts.
- **Backend API:** FastAPI (Python 3.11+), Pydantic v2, SQLAlchemy 2, Alembic migrations.
- **Worker:** Celery or RQ with Redis. Same Python codebase as the API for shared models.
- **DB:** PostgreSQL 15+. The knowledge graph is stored as relational tables (`graph_nodes`, `graph_edges`) and traversed with NetworkX in code. Do NOT add Neo4j in the MVP.
- **Auth:** email + magic link or OAuth via Auth.js (or an equivalent). Sessions in HTTP-only, secure cookies.
- **Document parsing:** `pymupdf` (PDF text + page/bbox), `python-docx`, `openpyxl`/`pandas` (spreadsheets), `pytesseract` OCR fallback for scanned PDFs.
- **Deployment:** Docker Compose for local; one-command startup.

**Repo layout:**
```
/apps/web            Next.js app
/apps/api            FastAPI app
/apps/worker         extraction tasks (may share /apps/api code)
/data/seeds          question bank CSVs + mapping tables
/packages/schema     shared types / OpenAPI-generated client
/docs                architecture, evaluation protocol
```

---

## 6. Question bank (the heart of the product)

### 6.1 Source files (provided by the team)
- `70% questions/` → Universal Core sources: NVCA model agreements (SPA, COI, IRA, Voting, ROFR/Co-Sale), Series A term sheet, ILPA DDQ 2.0, and the commercial/financial metrics in `questions.txt`.
- `30% questions/` → industry branch CSVs (7 files across 5 industries).
- `law firms reports/` → ~25 real diligence checklists used to **expand and cross-check** the core bank.

**Known gap (MUST be addressed in Milestone 1):** The Universal Core bank does not yet exist as a single file. Only ~14 financial/commercial questions exist in prose. The builder MUST NOT invent the rest. Instead, produce a **draft** core bank by extracting candidate questions from the NVCA SPA Section 2 representations, the ILPA DDQ, and the law-firm checklists, mark each row `review_status = DRAFT`, and cite the exact source. A human reviewer approves rows before they go live.

### 6.2 Unified schema (all seed files MUST be normalized to this)

The existing CSVs use two different layouts (healthcare has `sub_sector/geography/stage`; others have `sub_category`). Write a normalization script that merges everything into one table.

`questions`

| Column | Type | Notes |
|---|---|---|
| `question_id` | text PK | e.g. `CORE_IP_01`, `MED_DEV_03` |
| `scope` | enum | `CORE` or `BRANCH` |
| `industry` | text | `UNIVERSAL`, `HEALTHCARE`, `FINTECH`, `SOFTWARE`, `MANUFACTURING`, `ENERGY` |
| `sub_sector` | text | e.g. `MEDICAL_DEVICES`, `ALL` |
| `geography` | text[] | `{USA}`; `{UNIVERSAL}` reserved |
| `stage` | text[] | `Startup, Growth, Established, Mature` or `ALL` |
| `dimension` | text | one of the dimension codes in 6.3 |
| `sub_category` | text | free tag |
| `question_text` | text | plain English |
| `input_type` | enum | `BOOLEAN, MULTIPLE_CHOICE, TEXT, PERCENTAGE, NUMBER, CURRENCY, FILE` |
| `options` | jsonb | for MULTIPLE_CHOICE |
| `depends_on` | jsonb | see 6.4 |
| `risk_weight` | enum | `CRITICAL, HIGH, MEDIUM, LOW` |
| `pass_rule` | jsonb | machine-readable pass/fail rule, see 6.5 |
| `evidence_type` | enum | `CONTRACT_CLAUSE, FINANCIAL_TABLE, CERTIFICATE_OR_REPORT, POLICY_DOC, SELF_ATTESTED` |
| `extraction_hint` | jsonb | doc types to search, keywords, `cuad_category` if applicable |
| `remediation_action` | text | playbook text |
| `remediation_horizon_days` | int | 30, 60, 90, or 180 |
| `source_doc` | text | e.g. `NVCA_SPA_2025` |
| `source_ref` | text | e.g. `Section 2.8(h)` or `21 CFR 820` |
| `last_verified_on` | date | date a human confirmed the citation is current |
| `review_status` | enum | `DRAFT, APPROVED, DEPRECATED` |

Rules:
- Rows with `review_status != APPROVED` MUST NOT be shown to normal users (admins can toggle "include drafts" for testing).
- Regulatory deadlines and effective dates in question or remediation text (for example a rule "taking effect" in a given year) MUST have `last_verified_on` set by a human before approval. Seed rows that mention specific dates default to `DRAFT` until verified.
- Deduplicate: the three healthcare files overlap (e.g. `MED_DEV_01` appears in several). Merge on normalized question text + ID; keep the more complete row; log every merge in `seed_merge_report.csv`.

### 6.3 Dimensions (11 core + branch dimensions)

Core dimensions (each gets a weight per transaction type):

1. `GOVERNANCE` — Governance & Corporate Structure
2. `FIN_CONTROLS` — Financial Controls & Reporting
3. `LEGAL_IP_REG` — Legal, IP & Regulatory
4. `OPS_TECH_CYBER` — Operations, Technology & Cyber
5. `HUMAN_CAPITAL` — Human Capital / HR
6. `TXN_READINESS` — Transaction & Investor Readiness
7. `FIN_PERFORMANCE` — Financial Performance & Growth
8. `PROFIT_CASHFLOW` — Profitability & Cash Flow
9. `REVENUE_QUALITY` — Revenue Quality & Concentration
10. `MGMT_DEPTH` — Management Team Depth
11. `CUSTOMER_MARKET` — Customer & Market Position

Branch questions map into these same dimensions (existing seed values like `Legal_IP_Regulatory`, `Operations_Tech`, `Healthcare_Regulatory` MUST be mapped to the codes above). `Healthcare_Regulatory` and similar industry-only dimensions become an additional **12th dimension** `INDUSTRY_REG` shown only when a branch is active.

### 6.4 Conditional logic (`depends_on`)

Seed files use strings like `MED_DEV_01:Class II` and `MED_DEV_CYBER_01:Yes`. Convert to JSON:

```json
{ "all": [ { "question_id": "MED_DEV_01", "op": "eq", "value": "Class II" } ] }
```

Supported ops: `eq, neq, in, gte, lte, answered`. Support `all` / `any` nesting and **chained** dependencies (a question depending on a question that is itself conditional). A question is **applicable** only if its dependency is satisfied *and* its parent is itself applicable. Non-applicable questions are excluded from scoring (not counted as pass or fail).

Also support company-level gating from the profile: `industry`, `sub_sector`, `stage`, `geography`.

### 6.5 Pass rules

Each question needs a deterministic `pass_rule`. Examples:

```json
{ "type": "bool", "pass_when": true }
{ "type": "threshold", "field": "runway_months", "op": "gte", "value": 9,
  "partial": { "op": "gte", "value": 6 } }
{ "type": "threshold", "field": "top1_customer_pct", "op": "lte", "value": 20 }
{ "type": "choice", "pass_values": ["Yes"], "fail_values": ["No"] }
```

Some source questions phrase the ideal answer as "No" (e.g., "Do any arrangements factor in referral volume?" → pass when *No*). The normalization step MUST set the correct `pass_when`; add a unit test that checks every BOOLEAN question has an explicit rule.

Thresholds already stated in the seed material (use as defaults, editable in admin): runway < 6 months = critical fail, 6–9 = partial; any single customer > 20% of revenue = high-risk gap; NRR < 100% = flagged; budget variance > 15% = flagged; EBITDA add-backs > 10% = critical. Do not add new thresholds without a cited source; leave `pass_rule` empty and mark the question `SELF_ATTESTED` scoring (pass/fail on the user's yes/no) instead.

---

## 7. Extraction pipeline

### 7.1 Principle
Extraction **proposes**; the user **confirms**. Nothing extracted goes into the score until it is either high-confidence-and-not-rejected or user-confirmed (see 7.5).

### 7.2 Step 1 — Ingest
- Accept PDF, DOCX, XLSX, CSV, TXT, and ZIP of those (max sizes configurable; default 50 MB per file, 500 MB per ZIP). Validate MIME type and magic bytes, not just extension. Reject executables. Scan archives for path traversal and zip bombs.
- Process in memory or in an encrypted temp directory with a hard TTL (default: deleted immediately after processing completes or fails; a scheduled sweeper deletes anything older than 1 hour).
- Extract text with page numbers and character offsets (`pymupdf`); OCR only if a page has no text layer.

### 7.3 Step 2 — Classify documents
Classify each file into a document type (cap table, financial statement, bank statement, customer contract, employment/IP agreement, board minutes, policy, certificate/audit report, other). Use filename + keyword heuristics first; an optional lightweight zero-shot classifier may be added. Store the type; low-confidence classification → mark "unclassified" (do not guess).

### 7.4 Step 3 — Route each question by `evidence_type`

**Important design constraint:** the CUAD-finetuned model only understands *contract clause* categories (e.g. Governing Law, Change of Control, IP Ownership Assignment, Termination for Convenience, Anti-Assignment, Cap on Liability, Renewal Term). It cannot answer "what is your cash runway?" or "do you hold SOC 2?". So questions are routed:

| `evidence_type` | Method | Notes |
|---|---|---|
| `CONTRACT_CLAUSE` | CUAD extractive QA model | Only when `extraction_hint.cuad_category` is set. Model: a CUAD-finetuned RoBERTa/DeBERTa (the team identified `roberta-base-squad2-cuad`). **Verify the exact Hugging Face repo id, license, and that it loads before building on it.** |
| `FINANCIAL_TABLE` | Deterministic parsing | Parse XLSX/CSV/PDF tables; compute burn, runway, gross margin, customer concentration, etc. with explicit formulas. Show the formula and inputs to the user. |
| `CERTIFICATE_OR_REPORT` | Keyword/regex + document-type match | e.g. SOC 2 Type II report, ISO 9001 certificate, FDA 510(k) letter. Look for issuer, standard name, dates; show the matched snippet. |
| `POLICY_DOC` | Keyword + section detection | Detect presence of a policy (incident response, DR/BCP, GenAI usage). Presence ≠ adequacy; label result "document found" not "compliant". |
| `SELF_ATTESTED` | No extraction | Ask the user directly. |

Every question gets a `mapping status` in the seed data: which method applies. The builder MUST generate a coverage report: how many questions are auto-extractable vs manual. Expect the manual share to be large in the MVP; that is acceptable and must be shown honestly to the team.

### 7.5 Step 4 — Confidence gating (the research feature)
For each proposed answer, store: `answer_value`, `confidence` (0–1), `source_file`, `page`, `char_start`, `char_end`, `snippet`, `method`.

- `confidence ≥ T_high` (default **0.85**, configurable, see 12.3): status **AUTO_FILLED** — shown with a green mark and clickable citation; the user can still edit.
- `T_low ≤ confidence < T_high` (default T_low **0.50**): status **NEEDS_CONFIRMATION** — shown as a suggestion the user must accept or reject.
- `confidence < T_low` or nothing found: status **MANUAL_REQUIRED** — the user answers directly; the UI says "We couldn't find this in your documents."

Calibration: raw QA-model scores are not calibrated probabilities. The system MUST support a calibration step (temperature scaling or isotonic regression) fitted on a labeled validation set once available. Until then, label the value "model score", not "probability".

Deterministic methods (financial tables) set confidence = 1.0 only when all required input cells were found; otherwise treat as NEEDS_CONFIRMATION.

### 7.6 Step 5 — Contradiction checks (lightweight knowledge graph)
Build a graph per assessment from extracted entities (parties, founders, IP assets, contracts, equity holders, financial line items) and relations (assigned_to, signed_by, party_to, depends_on_revenue_from). Use it for:
1. **Trace/explanation** — link each failed question to entities and documents.
2. **Cross-document consistency rules** (deterministic), e.g.: cap table total ≠ sum of holders; revenue in P&L ≠ revenue in board deck (tolerance configurable); contract counterparty absent from AR aging; founder listed with no IP-assignment agreement found.

Contradictions produce a **Consistency Flag** (never auto-fail): shown to the user for resolution. Do not use a GNN or any learned scoring in the MVP.

---

## 8. Scoring engine (deterministic, transparent)

### 8.1 Inputs
Company profile (industry, sub-sector, stage, transaction type) + final answer per applicable question.

### 8.2 Answer states
Each applicable question resolves to one state:
`PASS (1.0)`, `PARTIAL (0.5, configurable)`, `FAIL (0.0)`, or `UNVERIFIED` (unanswered / manual required not completed).

### 8.3 Formulas

Severity weights (defaults, admin-editable): `CRITICAL = 8`, `HIGH = 5`, `MEDIUM = 3`, `LOW = 1`.

Dimension score:

```
DimScore_d = 100 × Σ(w_q × s_q) / Σ(w_q)     over answered applicable questions q in d
```

Overall score:

```
Overall = Σ( W[txn_type][d] × DimScore_d ) / Σ W[txn_type][d]     over dimensions with ≥ 1 answered question
```

- `W[txn_type][d]` is the **transaction-type weighting matrix** (transaction types: `VC_GROWTH_FINANCING`, `M&A_SELL_SIDE`, `IPO_PREP`, `DEBT_FINANCING`). Ship a default matrix as a config file; values are **[ASSUMPTION]** and must be reviewed by the team and cited in the paper's methodology. Do not present them as industry-standard numbers.

### 8.4 Critical-fail cap
If any `CRITICAL` question is `FAIL`, cap the overall score at a configurable ceiling (default **60**) and show a banner naming the failed critical items. Document this rule in the trace.

### 8.5 Unverified handling — report two numbers
Never treat `UNVERIFIED` as PASS. Show:
- **Readiness Score** — computed over answered questions.
- **Evidence Completeness** — `answered_applicable / total_applicable` (as a %).

A score with completeness < 60% MUST display a "Provisional" badge. (Threshold configurable.)

### 8.6 Score trace (explainability)
For every deduction the trace stores: `question_id`, question text, answer, expected (from `pass_rule`), weight, points lost `= w_q × (1 − s_q)`, source citation (`source_doc`, `source_ref`), evidence snippet + file + page, and how the answer was obtained (auto / confirmed / manual). The UI renders this as a sortable "Why this score" table, and the PDF includes it.

### 8.7 Determinism requirement
Same inputs + same config version → same score, always. Store `config_version` and `question_bank_version` with every assessment. Include a unit-test suite with golden cases (e.g., all pass = 100; one critical fail caps at 60; unanswered questions excluded from score but reduce completeness).

---

## 9. Roadmap and value features

### 9.1 Roadmap generation
For each FAIL/PARTIAL item (and each critical UNVERIFIED item), create a task from `remediation_action` in the bucket `remediation_horizon_days` (30/60/90/180). Order within a bucket by `weight × points lost` descending. Group tasks that share a root cause (same dimension + same `sub_category`). No LLM generation of remediation text in the MVP: playbook text comes from the reviewed question bank only.

### 9.2 Consistency flags
Show the flags from 7.6 in a separate "Needs your attention" list.

### 9.3 Re-assessment
Users can re-run after fixing items; show score delta per dimension and which items flipped.

### 9.4 PDF export
Branded report: cover, summary, dimension scores, critical items, trace table, roadmap, methodology page (weights, config version, question bank version), disclaimer.

### 9.5 Peer benchmarking — **not in MVP**
Do NOT display invented "average for your peer group" numbers or claims like "investors will cut your valuation by X%". A benchmark is allowed only when it is (a) a threshold with a cited source already in the question bank, or (b) an aggregate of real anonymized assessments with at least **N ≥ 30** companies in the peer cell (N configurable). Until then, the "how do you compare" area shows *rule thresholds* ("Most investor checklists flag a single customer above 20% of revenue — you are at 34%").

---

## 10. Functional requirements by module

**FR-1 Auth & accounts.** Sign up with name, work email, company name; email verification; org workspace with roles (Owner, Editor, Viewer, Advisor-guest). Admin role separate.

**FR-2 Company profile.** Industry, sub-sector (dependent dropdown), stage, headcount band, incorporation state, transaction type. Changing industry re-computes applicable questions and warns about discarded answers.

**FR-3 Data room upload.** Drag-and-drop, multi-file + ZIP, per-file progress, virus/type validation, list with detected document types (user can correct a type).

**FR-4 Processing view.** Live status per file and stage (parsing → classifying → extracting → checking consistency) via SSE/WebSocket. Failures show a plain-language reason and a retry.

**FR-5 Verification workspace.** Questionnaire grouped by dimension; status chips (Auto-filled, Needs confirmation, Manual required, Answered, Not applicable). Side panel shows the source document snippet with the matched text highlighted and page number. Bulk-confirm high-confidence items. Progress bar = evidence completeness. Autosave.

**FR-6 Manual entry.** Input controls per `input_type`; optional evidence upload per question; notes field.

**FR-7 Report.** Score, completeness, dimension bars, critical-items banner, trace table, consistency flags, roadmap, export.

**FR-8 Roadmap board.** Four columns (30/60/90/180). Tasks can be marked done, assigned to a teammate, and commented. Marking done does not change the score until the user re-assesses with evidence.

**FR-9 Admin console.** CRUD on questions with versioning and review status; import/export CSV; weight and threshold editor; dashboard of extraction metrics (12.2); audit log of edits.

**FR-10 Audit log.** Immutable log of logins, uploads, deletions, answer changes, report exports, admin edits.

---

## 11. Security and privacy requirements

These are hard requirements because the platform handles confidential company documents.

1. **Encryption:** TLS 1.2+ everywhere; database and backups encrypted at rest (AES-256); field-level encryption for extracted snippets and free-text answers (envelope keys, KMS-style key management; keys never in the repo).
2. **Document handling:** raw files are processed then deleted (7.2). Only the extracted snippet (≤ 500 chars), file name, page, and a SHA-256 hash are retained. Provide a per-assessment "Delete all my data" action that hard-deletes within 24 hours and logs the deletion.
3. **Access control:** tenant isolation enforced at the query layer (every query scoped by `org_id`) with automated tests attempting cross-tenant access; RBAC per role; admin actions require re-authentication.
4. **Auth hardening:** rate limiting and lockout, secure cookies (HttpOnly, Secure, SameSite), CSRF protection, optional TOTP 2FA.
5. **Input safety:** strict upload validation, size limits, parsing in a sandboxed worker with no outbound network, no execution of document content, output escaping to prevent XSS from extracted text.
6. **Secrets and config:** environment-based secrets; no secrets in logs; dependency scanning in CI.
7. **No training on customer data:** uploaded content is never used to train or fine-tune any model unless a user explicitly opts in (opt-in flag off by default, and out of scope for MVP).
8. **Third-party calls:** the MVP extraction runs entirely on infrastructure the team controls. No document text is sent to external LLM APIs.
9. **Privacy notice & consent:** show at signup and before first upload what is stored, for how long, and how to delete it.
10. **Logging:** logs MUST NOT contain document text or answers; use IDs only.

---

## 12. Evaluation and research instrumentation

### 12.1 What to log per proposed answer
`assessment_id, question_id, method, model_name+version, raw_score, calibrated_score (nullable), status_assigned, user_action (accepted/edited/rejected/none), final_value, time_to_confirm_ms`.

### 12.2 Admin metrics
- Auto-fill coverage (% of applicable questions auto-filled), by industry/dimension.
- Acceptance rate and edit rate of auto-filled answers.
- Precision of auto-filled answers = accepted / (accepted + edited + rejected).
- Manual-required rate.
- Time to complete an assessment.

### 12.3 Threshold study (for the paper)
Provide an offline script that, given a labeled set (contracts with known clause answers, e.g. the CUAD test split, plus internally labeled sample data rooms), sweeps the confidence threshold from 0.30 to 0.99 and outputs the **coverage-vs-error curve** (fraction auto-filled vs error rate among auto-filled), with the default `T_high` marked. Also compute expected calibration error before and after calibration. Baselines to compare against: (a) always-accept top prediction, (b) fixed-threshold with no calibration, (c) keyword-only search.

Scoring-layer evaluation: sensitivity analysis of the weight matrix (how much does the score move if weights change ±20%), and rank-stability across transaction types.

---

## 13. Frontend design specification

### 13.1 Design intent
Feel like a **serious, calm, editorial audit tool** — closer to a well-made financial document than a generic SaaS dashboard. It must not look like a default AI-generated template.

**Anti-"AI look" rules (MUST follow):**
- No purple/blue-to-pink gradient hero, no default shadcn zinc look left untouched, no glowing gradient orbs, no stock 3-icon-cards "features" row, no emoji as icons, no lorem ipsum, no fake logos or fake testimonials.
- One accent color used sparingly; status colors reserved for status.
- Real, specific copy throughout (use the copy guidance in 13.6).
- Restrained motion: purposeful transitions only (page-in, number count-up, progress). Respect `prefers-reduced-motion`.
- Consistent radius (pick one scale), consistent spacing scale, tabular numerals for all figures.
- Dense-but-legible data tables; do not hide the trace behind excess whitespace.

### 13.2 Design tokens (starting point — [ASSUMPTION], team may change)
```
Background (paper)   #F6F3EC      Surface        #FFFFFF     Border  #E2DDD2
Ink (text)           #16181D      Muted text     #5F6470
Accent (primary)     #1F4D3F   (deep green)      Accent hover  #17392F
Status: pass #2F7D57 · partial #B7791F · fail #B4382F · unverified #6B7280
Dark mode: ink-black background #0F1113, same accents lightened for contrast (WCAG AA)
```
Typography: display **Fraunces** or **Instrument Serif** (headlines only); UI **Geist** or **Inter Tight**; data/IDs **Geist Mono** or **JetBrains Mono**. Use tabular figures for scores. Radius scale: 6 / 10 / 14 px. Score numeral is large serif; question IDs are mono.

Implement tokens as CSS variables consumed by Tailwind + shadcn theme so components sourced from 21st.dev inherit them.

### 13.3 Using 21st.dev
21st.dev is a registry of React + Tailwind components built to shadcn conventions. Components are copied into the repo (not installed as a dependency) via the "Copy prompt" flow or the shadcn CLI install command, then adapted. **Do not clone any whole site or template.** Pick a small number of components, restyle them with the tokens above, and combine them with custom layout so the result is distinct.

Rules for the builder:
1. Put pulled components in `apps/web/components/ui-21st/`, one file each, with a header comment: component name, author/library, source URL.
2. Immediately re-theme each component to the tokens in 13.2 (colors, radius, fonts). Remove any built-in gradients/glows that clash with the design intent.
3. Check each component's license/terms on its page. Some templates are paid; use only free components or ones the team has access to.
4. Keep components accessible: keyboard navigation, focus rings, ARIA labels, contrast AA.
5. **The human team pulls the components** (the site limits free copies per day). The builder should scaffold each screen with shadcn/ui primitives first, leave a clearly marked slot, and list which 21st component goes in it. Do not hallucinate 21st component names or URLs; if unsure, use the search category link below and describe the intended component.

### 13.4 Component shopping list (search these categories on 21st.dev)

| Screen / element | What to look for | Where to search on 21st.dev |
|---|---|---|
| Landing hero | A quiet animated hero with a single strong headline; avoid shader-heavy or neon options | `community/components/s/hero`, `/s/animated-hero` |
| Landing background | Subtle grid, paper-texture, or faint gradient; not glowing | `/s/background`, `/s/gradient` |
| Sign-in / sign-up | Clean split-screen or centered card sign-in | `/s/sign-in` |
| Top navigation | Simple navigation menu with a mobile drawer | `/s/navigation-menu` |
| Buttons | One primary, one secondary, one ghost style; subtle hover | `/s/button` |
| Score numerals | Number ticker / count-up for the readiness score | search "number ticker" (Magic UI has one) |
| Cards & summary grids | Bento-style but restrained summary cards for dimension scores | `/s/card` |
| Upload area | Drag-and-drop file dropzone with progress rows | search "file upload" / "dropzone" |
| Processing state | Stepper / progress list with staged status text | search "stepper", "progress" |
| Verification table | Data table with row status chips, filters, expandable rows (shadcn data table pattern) | search "data table" |
| Charts | Dimension bars and score delta; keep monochrome + status colors | visx / Recharts (21st lists a visx library) |
| Footer | Minimal footer with disclaimer and links | `/s/footer` |
| Optional assistant panel | Chat-style side panel for "explain this question" — only if the answers come from the question bank (no free-form LLM claims) | `/s/ai-chat` |

Libraries on 21st that fit this aesthetic and are worth browsing first: shadcn/ui, Origin UI, Magic UI (for restrained micro-interactions such as number ticker), Motion Primitives, Kokonut UI, Tailark (marketing blocks), Efferd, ReUI, and visx (charts). Avoid loud shader/liquid-metal categories for the product UI.

### 13.5 Screens (with layout guidance)

1. **Landing.** Headline focused on the outcome ("Find your deal-breakers before an investor does."). Left: headline + sub + primary CTA. Right: a *real-looking* product excerpt (a cropped score report with a trace row), not an abstract illustration. Below: "How it works" as three numbered steps with mono step labels; a "What we check" section listing the 11 dimensions as a compact ruled list (not icon cards); sources strip listing the actual standards used (NVCA, ILPA, SOC 2, HIPAA, FDA QMSR, etc.) as text. No fabricated customer logos or testimonials. Footer disclaimer.
2. **Sign-up / onboarding gateway.** Step 1: name, work email, company name. Step 2: industry → sub-sector → stage → transaction type. Progress indicator; one question group per step. Explain *why* each is asked ("Industry decides which regulatory questions apply").
3. **Data room.** Large dropzone; below it a table of files with detected type (editable), size, status. Right rail: "Documents that help most" checklist (cap table, last 2 years financials, customer contracts, IP assignment agreements, policies).
4. **Processing.** Per-file rows with a stage stepper, plus a plain-language log line ("Reading page 14 of 32 — Master Services Agreement"). Never show a fake percentage; use real stage counts.
5. **Verification workspace (most important screen).** Three-pane layout: left = dimension list with completeness per dimension; center = question list; right = evidence viewer showing the source snippet and page with the highlight. Status chips as in FR-5. A sticky footer shows overall completeness and a "Generate report" button, enabled at any completeness but labeled "Provisional" below the threshold.
6. **Report.** Top: large serif score numeral, completeness meter, and Provisional badge if applicable; critical-items banner in status red; dimension bars; tabs: *Why this score* (trace table), *Needs attention* (consistency flags), *Roadmap*. Every row in the trace links back to the verification workspace item.
7. **Roadmap board.** Four horizontal lanes (30/60/90/180 days) with task cards showing dimension, points recoverable, and source. Card detail drawer shows the remediation playbook text and citation.
8. **Re-assessment compare.** Two-column delta view.
9. **Admin.** Question table with filters and inline edit; version history; extraction metrics dashboard; weights editor.
10. **Settings / data controls.** Export, delete data, members, retention explanation.

States to design for every screen: empty, loading (skeletons), error, partial, and success. Responsive: desktop-first, usable on tablet; mobile limited to viewing reports.

### 13.6 Copy guidance
Plain, specific, calm. Examples:
- Empty upload: "Drop your cap table, last two years of financials, and any signed customer contracts. We read them here and delete the files when we're done."
- Manual required: "We couldn't find a signed IP-assignment agreement for this founder in your documents. Upload it or answer below."
- Provisional badge tooltip: "Only 48% of applicable questions have answers, so this score may change a lot."
Never use hype ("supercharge", "revolutionize", "AI-powered magic").

### 13.7 Accessibility and quality bar
WCAG 2.1 AA, keyboard-only completion of the full flow, screen-reader labels for status chips (don't rely on color alone — include icon + text), Lighthouse accessibility ≥ 95 on core screens.

---

## 14. API surface (indicative — generate an OpenAPI spec)

```
POST   /auth/signup | /auth/login | /auth/logout
GET    /me
POST   /orgs/{org}/assessments
GET    /assessments/{id}
PATCH  /assessments/{id}/profile
POST   /assessments/{id}/files            (multipart; returns file_id)
GET    /assessments/{id}/files
GET    /assessments/{id}/events            (SSE processing stream)
GET    /assessments/{id}/questions         (applicable questions + current answer state)
PUT    /assessments/{id}/answers/{qid}     (confirm / edit / reject / manual)
POST   /assessments/{id}/score             (compute; returns score, completeness, trace)
GET    /assessments/{id}/trace
GET    /assessments/{id}/roadmap
GET    /assessments/{id}/report.pdf
DELETE /assessments/{id}                   (hard delete flow)
# admin
GET/POST/PUT /admin/questions ; POST /admin/questions/import ; GET /admin/metrics
GET/PUT /admin/config/weights
```

Core tables: `orgs, users, memberships, assessments, files, doc_classifications, extraction_candidates, answers, graph_nodes, graph_edges, consistency_flags, score_runs, score_trace_rows, roadmap_tasks, questions, question_versions, config_versions, audit_log`.

---

## 15. Milestones (build in this order; each must be runnable and tested)

**M0 — Foundations.** Repo, Docker Compose, CI, DB + migrations, auth, design tokens + shadcn theme, empty app shell, landing page.
**M1 — Question bank.** Normalization + merge script for all seed CSVs (with `seed_merge_report.csv`), `depends_on` converter, pass-rule authoring for existing rows, draft Universal Core bank extracted from NVCA/ILPA/law-firm sources (all `DRAFT`), admin CRUD and review workflow, coverage report (auto vs manual method per question). **Acceptance:** every APPROVED row has a `pass_rule`, citation, and horizon; tests for chained dependencies pass.
**M2 — Questionnaire without AI.** Onboarding → applicable questions → manual answering → autosave → progress/completeness.
**M3 — Scoring & trace.** Scoring engine per Section 8 with golden-case unit tests, trace table UI, critical cap, provisional logic, config versioning.
**M4 — Roadmap & report.** Roadmap generation, board UI, PDF export, re-assessment delta.
**M5 — Upload & deterministic extraction.** Secure upload, parsing, classification, financial-table calculators, certificate/policy detectors, evidence viewer with highlights.
**M6 — CUAD extraction & gating.** Model integration for `CONTRACT_CLAUSE` questions, confidence statuses, verification workspace states, logging per 12.1.
**M7 — Consistency checks & graph.** Entity extraction, graph tables, deterministic contradiction rules, flags UI.
**M8 — Evaluation & hardening.** Threshold-study script, calibration, metrics dashboard, security test suite (tenant isolation, upload abuse), deletion flow verification, accessibility pass.

---

## 16. Acceptance criteria (release gate for MVP)

1. A user can complete signup → assessment → report → PDF export for each of the 5 industries with only manual answers (no AI).
2. With uploads, contract-clause questions with a mapped CUAD category are proposed with citation, page, and confidence; low-confidence items are never silently accepted.
3. Scoring is deterministic: re-running with the same inputs and config version yields identical output (tested).
4. Every point deducted appears in the trace with question, rule, source citation, and evidence (or "manual answer").
5. Unanswered questions never count as pass; completeness and Provisional badge behave as specified.
6. No document text appears in logs; raw files are gone after processing (verified by test).
7. Cross-tenant access attempts fail in automated tests.
8. No invented statistics, fake logos, or "guaranteed accuracy" language anywhere in the UI or PDF.
9. Lighthouse accessibility ≥ 95 on landing, verification workspace, and report.
10. The admin metrics page shows coverage, acceptance rate, and manual-required rate.

---

## 17. Risks and open decisions for the human team

| # | Item | Why it matters |
|---|---|---|
| 1 | **Universal Core bank is not finished** | Highest project risk; needs human legal/finance review. |
| 2 | **CUAD covers only contract clauses** | Auto-fill coverage will be well below the total question count; be honest in the paper. |
| 3 | **Weight matrix values** | Currently assumptions; need justification (literature, expert survey, or sensitivity analysis). |
| 4 | **Regulatory dates in seed rows** | Several rows cite effective dates/deadlines that must be checked against primary sources before approval. |
| 5 | **Labeled data for calibration/evaluation** | Need a small hand-labeled set of contracts and data rooms; plan labeling time. |
| 6 | **Legal exposure of compliance wording** | Keep wording as "readiness indicators", keep disclaimers, get advisor/faculty sign-off before any real-user pilot. |
| 7 | **Hosting and compliance claims** | Do not claim SOC 2/HIPAA compliance for the platform itself. |
| 8 | **Novelty positioning** | Knowledge graphs alone are not novel; the defensible contribution is the measured, calibrated confidence-gating + deterministic explainable scoring pipeline with evaluation results. |

---

## 18. Definition of done for the AI builder
- All milestones implemented in order with passing tests.
- README with one-command local run, environment variables, and how to load seed data.
- `docs/evaluation.md` describing how to reproduce the threshold study.
- A short `docs/known_limitations.md` listing which questions are auto-extractable vs manual, generated from the coverage report.
- Screenshots of each screen in light and dark mode.
