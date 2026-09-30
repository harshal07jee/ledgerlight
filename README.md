# Ledgerlight — Diligence Readiness Platform

> A confidence-gated, evidence-linked diligence readiness assessment and deterministic risk scoring platform for institutional transactions (Series A+, Growth Equity, M&A, Debt).

---

## 1. Quick Start (One Command Startup)

Run the entire platform (PostgreSQL, Redis, FastAPI, Next.js) using Docker Compose:

```bash
docker compose up --build
```

- **Frontend (Next.js):** [http://localhost:3000](http://localhost:3000)
- **Backend API (FastAPI):** [http://localhost:8000](http://localhost:8000)
- **Interactive OpenAPI Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)
- **Admin Question Bank Console:** [http://localhost:3000/admin](http://localhost:3000/admin)

---

## 2. Local Development (Without Docker)

### Backend API:
```bash
# 1. Install dependencies
pip install -r apps/api/requirements.txt

# 2. Seed SQLite database with question bank and demo accounts
python -m apps.api.seeds.db_seed

# 3. Run FastAPI dev server
uvicorn apps.api.main:app --reload --port 8000
```

### Frontend Web:
```bash
cd apps/web
npm install
npm run dev
```

---

## 3. Running Automated Tests

Run the complete test suite (20 tests covering dependency logic, chained dependencies, pass rule inference, seed normalization, and API endpoints):

```bash
pytest -v
```

---

## 4. Question Bank Pipeline (Milestone M1)

Seed normalization and generation scripts:

1. **Branch Normalization & Deduplication:**
   ```bash
   python -m apps.api.seeds.normalize
   ```
   *Outputs:*
   - `data/seeds/normalized_branch_questions.json` & `.csv` (121 branch questions)
   - `data/seeds/seed_merge_report.csv` (Detailed log of every duplicate merged and collision resolved)

2. **Universal Core Bank Generation:**
   ```bash
   python -m apps.api.seeds.extract_core
   ```
   *Outputs:*
   - `data/seeds/draft_universal_core.json` & `.csv` (32 candidate core questions, all marked `DRAFT` with exact NVCA/ILPA citations)

3. **Extraction Coverage Report:**
   ```bash
   python -m apps.api.seeds.coverage_report
   ```
   *Output:*
   - `data/seeds/coverage_report.md` (Detailed auto-extractable vs manual breakdown per dimension and industry)

---

## 5. Repository Layout

```
├── apps/
│   ├── api/             # FastAPI backend service (Python 3.12, SQLAlchemy 2.0)
│   │   ├── core/        # Dependencies and pass rule evaluation engines
│   │   ├── models/      # SQLAlchemy 2.0 ORM models
│   │   └── seeds/       # Normalization, extraction, and database seeding
│   ├── web/             # Next.js 14 frontend (TypeScript, Tailwind, Editorial Theme)
│   │   ├── app/         # App router (Landing page, Admin console, layout)
│   └── worker/          # Asynchronous extraction task worker
├── data/
│   ├── ASP/             # Original raw seed assets (CSVs, NVCA docx, checklists)
│   └── seeds/           # Processed question banks, merge report, coverage report
├── packages/
│   └── schema/          # Shared Pydantic v2 unified question models
├── tests/               # Pytest automated test suites
├── docker-compose.yml   # Multi-service composition (Postgres, Redis, API, Web)
└── pytest.ini           # Pytest root configuration
```

---

## 6. Regulatory Disclaimer

*This is a readiness assessment based on the information provided. It is not legal, financial, or investment advice and does not predict transaction outcomes.*
