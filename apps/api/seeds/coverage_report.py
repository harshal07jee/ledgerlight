"""
Coverage Report Generator (PRD Section 7.4 & Milestone M1 Cleanup).
Computes:
- Auto-extractable vs manual share across:
  - All questions
  - By Evidence Type / Extraction Method
  - By Industry
  - By Dimension
- Detailed mapping of every CONTRACT_CLAUSE question to CUAD categories
- Flags any category not belonging to the 41 official CUAD labels
- Adds explicit notice regarding design-time routing labels vs measured accuracy

Produces data/seeds/coverage_report.md.
"""
import os
import json
from collections import defaultdict
from typing import Dict, Any, List

# 41 Official CUAD Labels (The Atticus Project - CUAD v1)
OFFICIAL_CUAD_41 = {
    "document name",
    "parties",
    "agreement date",
    "effective date",
    "expiration date",
    "renewal term",
    "notice period to terminate renewal",
    "governing law",
    "most favored nation",
    "competitive restriction exception",
    "non-compete",
    "exclusivity",
    "no-solicit of customers",
    "no-solicit of employees",
    "non-disparagement",
    "termination for convenience",
    "rofr/rofo/rofn",
    "change of control",
    "anti-assignment",
    "revenue/profit sharing",
    "price restrictions",
    "minimum commitment",
    "volume restriction",
    "ip ownership assignment",
    "jointly owned property",
    "license grant",
    "non-transferable license",
    "affiliate license-licensor",
    "affiliate license-licensee",
    "unlimited/all-you-can-eat-license",
    "irrevocable or perpetual license",
    "source code escrow",
    "post-termination services",
    "audit rights",
    "uncapped liability",
    "cap on liability",
    "liquidated damages",
    "warranty duration",
    "insurance",
    "covenant not to sue",
    "third party beneficiary",
}


def generate_coverage_report(
    seeds_dir: str = "data/seeds",
    output_path: str = "data/seeds/coverage_report.md"
) -> str:
    """Reads normalized branch questions and core bank questions, then writes coverage_report.md."""
    branch_json = os.path.join(seeds_dir, "normalized_branch_questions.json")
    core_json = os.path.join(seeds_dir, "draft_universal_core.json")

    branch_questions = []
    core_questions = []

    if os.path.exists(branch_json):
        with open(branch_json, "r", encoding="utf-8") as f:
            branch_questions = json.load(f)
    if os.path.exists(core_json):
        with open(core_json, "r", encoding="utf-8") as f:
            core_questions = json.load(f)

    all_questions = branch_questions + core_questions
    total = len(all_questions)
    if total == 0:
        return "No questions found."

    by_method: Dict[str, int] = defaultdict(int)
    by_industry: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))
    by_dimension: Dict[str, Dict[str, int]] = defaultdict(lambda: defaultdict(int))

    auto_extractable_count = 0
    manual_count = 0
    contract_clause_questions = []

    for q in all_questions:
        ev = q.get("evidence_type", "SELF_ATTESTED")
        ind = q.get("industry", "UNIVERSAL")
        dim = q.get("dimension", "OTHER")

        by_method[ev] += 1
        by_industry[ind][ev] += 1
        by_dimension[dim][ev] += 1

        if ev in ("CONTRACT_CLAUSE", "FINANCIAL_TABLE", "CERTIFICATE_OR_REPORT", "POLICY_DOC"):
            auto_extractable_count += 1
        else:
            manual_count += 1

        if ev == "CONTRACT_CLAUSE":
            contract_clause_questions.append(q)

    auto_pct = (auto_extractable_count / total) * 100
    manual_pct = (manual_count / total) * 100

    lines = [
        "# Diligence Question Bank Extraction Coverage & CUAD Routing Report",
        "",
        f"> **Generated for:** Ledgerlight Diligence Readiness Platform (PRD Section 7.4 & M1 Cleanup)",
        f"> **Total Questions Analyzed:** {total} (Branch: {len(branch_questions)}, Core: {len(core_questions)})",
        "",
        "> [!NOTE]",
        "> **Important Disclaimer on CUAD Category Mapping:**",
        "> The CUAD categories assigned below are **design-time routing labels** used to direct extracted document clauses to specialized extractive QA models. They represent intended pipeline targets, **NOT** empirically measured model extraction accuracy or benchmark performance.",
        "",
        "## 1. Executive Summary",
        "",
        f"- **Auto-Extractable Proposals:** **{auto_extractable_count}** questions (**{auto_pct:.1f}%**)",
        f"- **Manual Entry / Self-Attested Required:** **{manual_count}** questions (**{manual_pct:.1f}%**)",
        "",
        "> Per PRD Section 7.4, the manual share in MVP is an intentional architectural design: extractive QA proposes answers only when authoritative contract clauses or formal certificates exist, and routes unverified items to human review rather than hallucinating.",
        "",
        "## 2. Breakdown by Extraction Method",
        "",
        "| Extraction Method | Category Description | Question Count | Share (%) |",
        "|---|---|---|---|",
        f"| `CONTRACT_CLAUSE` | Extractive QA (CUAD Model for MSAs, IP agreements, SLAs) | {by_method['CONTRACT_CLAUSE']} | {(by_method['CONTRACT_CLAUSE']/total)*100:.1f}% |",
        f"| `FINANCIAL_TABLE` | Deterministic parsing (Formulas on P&L, burn, cap tables, concentration) | {by_method['FINANCIAL_TABLE']} | {(by_method['FINANCIAL_TABLE']/total)*100:.1f}% |",
        f"| `CERTIFICATE_OR_REPORT` | Regex / Keyword detector (SOC 2, ISO, FDA 510(k), Good Standing) | {by_method['CERTIFICATE_OR_REPORT']} | {(by_method['CERTIFICATE_OR_REPORT']/total)*100:.1f}% |",
        f"| `POLICY_DOC` | Pattern & presence detector (WISP, BCP/DR, incident response) | {by_method['POLICY_DOC']} | {(by_method['POLICY_DOC']/total)*100:.1f}% |",
        f"| `SELF_ATTESTED` | Manual response required (governance questions, unmapped rules) | {by_method['SELF_ATTESTED']} | {(by_method['SELF_ATTESTED']/total)*100:.1f}% |",
        f"| **Total** | | **{total}** | **100.0%** |",
        "",
        "## 3. Breakdown by Industry",
        "",
        "| Industry | Total | Auto-Extractable | Manual Required | Auto Coverage % |",
        "|---|---|---|---|---|"
    ]

    for ind in sorted(by_industry.keys()):
        counts = by_industry[ind]
        ind_total = sum(counts.values())
        ind_auto = (
            counts.get("CONTRACT_CLAUSE", 0) +
            counts.get("FINANCIAL_TABLE", 0) +
            counts.get("CERTIFICATE_OR_REPORT", 0) +
            counts.get("POLICY_DOC", 0)
        )
        ind_manual = counts.get("SELF_ATTESTED", 0)
        pct = (ind_auto / ind_total * 100) if ind_total > 0 else 0
        lines.append(f"| `{ind}` | {ind_total} | {ind_auto} | {ind_manual} | {pct:.1f}% |")

    lines.extend([
        "",
        "## 4. Breakdown by Dimension",
        "",
        "| Dimension | Total | Contract QA | Financial Formula | Cert / Regex | Policy Detect | Manual |",
        "|---|---|---|---|---|---|---|"
    ])

    for dim in sorted(by_dimension.keys()):
        counts = by_dimension[dim]
        dim_total = sum(counts.values())
        lines.append(
            f"| `{dim}` | {dim_total} | "
            f"{counts.get('CONTRACT_CLAUSE', 0)} | "
            f"{counts.get('FINANCIAL_TABLE', 0)} | "
            f"{counts.get('CERTIFICATE_OR_REPORT', 0)} | "
            f"{counts.get('POLICY_DOC', 0)} | "
            f"{counts.get('SELF_ATTESTED', 0)} |"
        )

    lines.extend([
        "",
        "## 5. Contract Clause Routing & CUAD Taxonomy Validation",
        "",
        "Each question below utilizes `CONTRACT_CLAUSE` extraction. Its design-time category is validated against the **41 official CUAD labels** established by The Atticus Project.",
        "",
        "| Question ID | Question Text (Summary) | Mapped CUAD Category | CUAD Validation Status | Target Document Types |",
        "|---|---|---|---|---|"
    ])

    unofficial_count = 0
    for q in contract_clause_questions:
        hint = q.get("extraction_hint") or {}
        cuad_cat = hint.get("cuad_category", "UNMAPPED")
        doc_types = ", ".join(hint.get("doc_types", []))

        # Check official 41
        if cuad_cat.lower() in OFFICIAL_CUAD_41:
            status_tag = "VALID (Official CUAD Label)"
        else:
            status_tag = "**[FLAG: UNOFFICIAL CUAD LABEL]**"
            unofficial_count += 1

        # Truncate text for clean table rendering
        txt = q.get("question_text", "")
        if len(txt) > 75:
            txt_disp = txt[:72] + "..."
        else:
            txt_disp = txt
        # Escape pipe symbols in markdown table
        txt_disp = txt_disp.replace("|", "/")

        lines.append(f"| `{q['question_id']}` | {txt_disp} | `{cuad_cat}` | {status_tag} | `{doc_types}` |")

    lines.extend([
        "",
        f"**CUAD Validation Summary:** {len(contract_clause_questions)} total contract clause questions evaluated. "
        f"**{len(contract_clause_questions) - unofficial_count}** match official CUAD labels, **{unofficial_count}** flagged as unofficial.",
        "",
        "---",
        "*Report generated automatically by `apps/api/seeds/coverage_report.py`.*"
    ])

    report_text = "\n".join(lines)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(report_text)

    print(f"Generated coverage report at {output_path} ({len(contract_clause_questions)} clauses evaluated, {unofficial_count} unofficial).")
    return report_text


if __name__ == "__main__":
    generate_coverage_report()
