"""
PDF Generation Engine for Diligence Readiness Platform (PRD Section 9.4).
Produces an editorial, multi-page diligence report containing:
1. Cover page with audit metadata & PRD Section 1 disclaimer
2. Executive Summary with Readiness Score, Best/Worst bounds, & Completeness
3. Critical-Items Alert Banner (if applicable)
4. Dimension Readiness Score Table
5. Explanatory Score Trace Table ("Why this score")
6. Remediation Roadmap across 30/60/90/180-day horizon buckets
7. Methodology & Audit Governance page (weights, config version, question bank version, legal disclaimer)
"""
from io import BytesIO
from datetime import datetime
from typing import Dict, Any, List, Optional

from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
    PageBreak,
    KeepTogether,
    HRFlowable
)
from reportlab.pdfgen import canvas

# Design tokens matching PRD Section 13.2
COLOR_PAPER = colors.HexColor("#F6F3EC")
COLOR_SURFACE = colors.HexColor("#FFFFFF")
COLOR_BORDER = colors.HexColor("#E2DDD2")
COLOR_INK = colors.HexColor("#16181D")
COLOR_MUTED = colors.HexColor("#5F6470")
COLOR_ACCENT = colors.HexColor("#1F4D3F")
COLOR_PASS = colors.HexColor("#2F7D57")
COLOR_PARTIAL = colors.HexColor("#B7791F")
COLOR_FAIL = colors.HexColor("#B4382F")

DISCLAIMER_TEXT = (
    "This is a readiness assessment based on the information provided. "
    "It is not legal, financial, or investment advice and does not predict transaction outcomes."
)


class NumberedCanvas(canvas.Canvas):
    """Canvas that performs a two-pass render to display total page count and disclaimer footer."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont("Helvetica", 7)
        self.setFillColor(COLOR_MUTED)

        # Header on later pages (not on cover)
        if self._pageNumber > 1:
            self.drawString(54, 750, "LEDGERLIGHT DILIGENCE READINESS REPORT")
            self.drawRightString(letter[0] - 54, 750, f"Page {self._pageNumber} of {page_count}")
            self.setStrokeColor(COLOR_BORDER)
            self.setLineWidth(0.5)
            self.line(54, 742, letter[0] - 54, 742)

        # Mandatory running footer disclaimer on ALL pages
        self.setStrokeColor(COLOR_BORDER)
        self.setLineWidth(0.5)
        self.line(54, 45, letter[0] - 54, 45)
        self.drawString(54, 32, DISCLAIMER_TEXT)
        self.drawRightString(letter[0] - 54, 32, "CONFIDENTIAL & PROPRIETARY")

        self.restoreState()


def generate_assessment_pdf(
    assessment_data: Dict[str, Any],
    score_data: Dict[str, Any],
    trace_rows: List[Dict[str, Any]],
    roadmap_data: Dict[str, Any]
) -> bytes:
    """
    Renders complete branded PDF document as bytes.
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54
    )

    styles = getSampleStyleSheet()

    # Custom editorial typography styles
    style_cover_brand = ParagraphStyle(
        "CoverBrand",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=10,
        leading=12,
        textColor=COLOR_ACCENT,
        textTransform="uppercase",
        spaceAfter=15
    )
    style_cover_title = ParagraphStyle(
        "CoverTitle",
        parent=styles["Title"],
        fontName="Times-Bold",
        fontSize=28,
        leading=34,
        textColor=COLOR_INK,
        alignment=0,
        spaceAfter=10
    )
    style_cover_sub = ParagraphStyle(
        "CoverSub",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=12,
        leading=16,
        textColor=COLOR_MUTED,
        spaceAfter=25
    )
    style_h1 = ParagraphStyle(
        "Heading1_Custom",
        parent=styles["Heading1"],
        fontName="Times-Bold",
        fontSize=18,
        leading=22,
        textColor=COLOR_INK,
        spaceAfter=12
    )
    style_h2 = ParagraphStyle(
        "Heading2_Custom",
        parent=styles["Heading2"],
        fontName="Times-Bold",
        fontSize=13,
        leading=16,
        textColor=COLOR_INK,
        spaceBefore=10,
        spaceAfter=8
    )
    style_body = ParagraphStyle(
        "Body_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=9,
        leading=13,
        textColor=COLOR_INK
    )
    style_muted = ParagraphStyle(
        "Muted_Custom",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
        textColor=COLOR_MUTED
    )
    style_mono = ParagraphStyle(
        "Mono_Custom",
        parent=styles["Normal"],
        fontName="Courier",
        fontSize=8,
        leading=10,
        textColor=COLOR_INK
    )

    story = []

    # =========================================================================
    # 1. COVER PAGE
    # =========================================================================
    story.append(Spacer(1, 40))
    story.append(Paragraph("LEDGERLIGHT DILIGENCE PLATFORM &bull; READINESS AUDIT", style_cover_brand))
    story.append(Paragraph("Diligence Readiness Assessment", style_cover_title))
    
    company_name = assessment_data.get("name", "Target Company Assessment")
    industry = assessment_data.get("industry", "UNIVERSAL")
    txn_type = (assessment_data.get("transaction_type") or "VC_GROWTH_FINANCING").replace("_", " ")
    stage = assessment_data.get("stage", "Growth")
    
    story.append(Paragraph(f"Prepared for: <b>{company_name}</b>", style_cover_sub))
    story.append(Spacer(1, 20))

    meta_table_data = [
        [Paragraph("<b>Target Transaction:</b>", style_body), Paragraph(txn_type, style_body)],
        [Paragraph("<b>Industry & Sub-Sector:</b>", style_body), Paragraph(f"{industry} &bull; {assessment_data.get('sub_sector', 'ALL')}", style_body)],
        [Paragraph("<b>Company Stage:</b>", style_body), Paragraph(stage, style_body)],
        [Paragraph("<b>Assessment ID:</b>", style_body), Paragraph(assessment_data.get("id", ""), style_mono)],
        [Paragraph("<b>Assessment Date:</b>", style_body), Paragraph(datetime.utcnow().strftime("%B %d, %Y"), style_body)],
        [Paragraph("<b>Scoring Configuration:</b>", style_body), Paragraph(f"Version {score_data.get('config_version', '1.0.0')}", style_body)],
        [Paragraph("<b>Question Bank Version:</b>", style_body), Paragraph(f"Version {score_data.get('question_bank_version', '1.0.0')}", style_body)],
    ]
    t_meta = Table(meta_table_data, colWidths=[150, 350])
    t_meta.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PAPER),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
    ]))
    story.append(t_meta)

    story.append(Spacer(1, 100))

    cover_disclaimer_p = Paragraph(
        f"<b>IMPORTANT NOTICE:</b><br/>{DISCLAIMER_TEXT}<br/>"
        "This document contains proprietary audit analysis generated deterministically from provided materials. "
        "Unauthorized distribution or duplication is strictly prohibited.",
        style_muted
    )
    story.append(cover_disclaimer_p)

    story.append(PageBreak())

    # =========================================================================
    # 2. EXECUTIVE SUMMARY & CRITICAL ITEMS
    # =========================================================================
    story.append(Paragraph("1. Executive Summary", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=15))

    overall_score = score_data.get("overall_score", 0.0)
    unconstrained = score_data.get("unconstrained_score", 0.0)
    best_case = score_data.get("best_case_score", overall_score)
    worst_case = score_data.get("worst_case_score", overall_score)
    completeness = score_data.get("completeness", {})
    comp_pct = completeness.get("completeness_pct", 0.0)
    is_provisional = completeness.get("is_provisional", False)
    crit_capped = score_data.get("critical_cap_applied", False)

    summary_cards_data = [
        [
            Paragraph("<b>Overall Readiness Score</b>", style_body),
            Paragraph("<b>Evidence Completeness</b>", style_body),
            Paragraph("<b>Unverified Sensitivity Range</b>", style_body)
        ],
        [
            Paragraph(f"<font size='26' color='#16181D'><b>{overall_score}</b></font><font size='12' color='#5F6470'> / 100</font>", style_body),
            Paragraph(f"<font size='26' color='#1F4D3F'><b>{comp_pct}%</b></font><br/><font size='8' color='#5F6470'>{'PROVISIONAL (<60%)' if is_provisional else 'VERIFIED STATUS'}</font>", style_body),
            Paragraph(f"Worst: <b>{worst_case}</b><br/>Best: <b>{best_case}</b><br/><font size='7' color='#5F6470'>Unverified items as Fail vs Pass</font>", style_body)
        ]
    ]
    t_summary = Table(summary_cards_data, colWidths=[160, 160, 180])
    t_summary.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PAPER),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("PADDING", (0, 0), (-1, -1), 10),
        ("ALIGN", (0, 1), (-1, 1), "CENTER"),
    ]))
    story.append(t_summary)

    # Scored weight origin breakdown (PRD Section 8 & Pre-M5 requirement)
    origin_share = score_data.get("weight_origin_share") or {}
    ev_pct = origin_share.get("evidence_backed_share_pct", origin_share.get("evidence_backed_pct", 0.0))
    sa_pct = origin_share.get("self_attested_share_pct", origin_share.get("self_attested_pct", 0.0))
    ev_wt = origin_share.get("evidence_backed_weight", 0.0)
    sa_wt = origin_share.get("self_attested_weight", 0.0)

    t_origin = Table([
        [
            Paragraph(
                f"<b>Scored Weight Origin:</b> Evidence-Backed <b>{ev_pct}%</b> ({ev_wt} pts) &bull; "
                f"Self-Attested <b>{sa_pct}%</b> ({sa_wt} pts)",
                style_muted
            )
        ]
    ], colWidths=[500])
    t_origin.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), COLOR_PAPER),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("PADDING", (0, 0), (-1, -1), 6),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
    ]))
    story.append(Spacer(1, 6))
    story.append(t_origin)

    story.append(Spacer(1, 15))

    # Critical alert banner
    if crit_capped:
        crit_msg = (
            f"<b>CRITICAL RISK CAP APPLIED:</b> Overall readiness score has been capped at <b>60.0</b> "
            f"(unconstrained raw score was <b>{unconstrained}</b>) due to failed deal-breaker items. "
            "Investors will flag these issues as fatal barriers to closing."
        )
        t_alert = Table([[Paragraph(crit_msg, style_body)]], colWidths=[500])
        t_alert.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#FDF2F2")),
            ("BOX", (0, 0), (-1, -1), 1, COLOR_FAIL),
            ("PADDING", (0, 0), (-1, -1), 8),
        ]))
        story.append(t_alert)
        story.append(Spacer(1, 10))

        failed_crit = score_data.get("failed_critical_items", [])
        if failed_crit:
            crit_rows = [["ID", "Failed Critical Requirement", "Source Citation", "Deduction"]]
            for item in failed_crit:
                crit_rows.append([
                    item.get("question_id", ""),
                    Paragraph(item.get("question_text", ""), style_body),
                    f"{item.get('source_doc', '')} {item.get('source_ref', '')}",
                    f"-{item.get('points_lost', 0)} pts"
                ])
            t_crit_table = Table(crit_rows, colWidths=[70, 260, 110, 60])
            t_crit_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#F9D5D3")),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 8),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_FAIL),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#F5B7B1")),
                ("PADDING", (0, 0), (-1, -1), 4),
            ]))
            story.append(t_crit_table)
            story.append(Spacer(1, 15))

    story.append(PageBreak())

    # =========================================================================
    # 3. DIMENSION SCORES BREAKDOWN
    # =========================================================================
    story.append(Paragraph("2. Dimension Readiness Scores", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=15))

    dim_headers = ["Code", "Dimension Name", "Score", "Weight", "Answered", "Status"]
    dim_rows = [dim_headers]

    dim_scores = score_data.get("dimension_scores", {})
    for dcode, ddata in dim_scores.items():
        score_val = ddata.get("score")
        score_str = f"{score_val}%" if score_val is not None else "—"
        ans_count = f"{ddata.get('answered_count', 0)} / {ddata.get('total_applicable', 0)}"
        txn_wt = f"{ddata.get('transaction_weight', 10)}%"

        if score_val is None:
            status_str = "Unassessed"
        elif score_val >= 80:
            status_str = "Strong"
        elif score_val >= 50:
            status_str = "Moderate"
        else:
            status_str = "At Risk"

        dim_rows.append([
            dcode,
            Paragraph(dcode.replace("_", " ").title(), style_body),
            score_str,
            txn_wt,
            ans_count,
            status_str
        ])

    t_dims = Table(dim_rows, colWidths=[90, 180, 50, 50, 65, 65])
    t_dims.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PAPER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("PADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (2, 0), (4, -1), "CENTER"),
    ]))
    story.append(t_dims)

    story.append(PageBreak())

    # =========================================================================
    # 4. SCORE DEDUCTION TRACE TABLE ("Why this score")
    # =========================================================================
    story.append(Paragraph("3. Diligence Deduction Trace", style_h1))
    story.append(Paragraph("Every point deducted is traced back to a specific requirement, rule, and citation.", style_muted))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=15))

    trace_headers = ["ID", "Audit Requirement", "Answer", "Expected Rule", "Loss", "Origin & Citation"]
    trace_table_data = [trace_headers]

    for r in trace_rows[:40]:  # Cap at top 40 deductions for PDF readability
        origin_label = r.get("origin", "self-attested")
        trace_table_data.append([
            r.get("question_id", ""),
            Paragraph(r.get("question_text", ""), style_body),
            str(r.get("user_answer", "No")),
            Paragraph(r.get("expected_rule", "Pass"), style_muted),
            f"-{r.get('points_lost', 0)}",
            Paragraph(f"<b>[{origin_label}]</b><br/>{r.get('source_doc', '')} {r.get('source_ref', '')}", style_muted)
        ])

    if len(trace_table_data) == 1:
        trace_table_data.append(["—", Paragraph("No deductions recorded. All applicable questions passed.", style_body), "—", "—", "0", "—"])

    t_trace = Table(trace_table_data, colWidths=[65, 175, 45, 95, 40, 80])
    t_trace.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PAPER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 7),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("PADDING", (0, 0), (-1, -1), 3),
        ("ALIGN", (4, 0), (4, -1), "RIGHT"),
    ]))
    story.append(t_trace)

    # =========================================================================
    # 5. UNSCORED DISCLOSURES (PRD Section 8 & Pre-M5 Requirement)
    # =========================================================================
    unscored_disclosures = score_data.get("unscored_disclosures") or []
    if unscored_disclosures:
        story.append(PageBreak())
        story.append(Paragraph("4. Unscored Disclosures", style_h1))
        story.append(Paragraph("Recorded qualitative and operational disclosures for transactional diligence. Excluded from quantitative scoring.", style_muted))
        story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=15))

        disc_headers = ["ID", "Audit Item", "Dimension", "Disclosed Response"]
        disc_rows = [disc_headers]
        for d in unscored_disclosures:
            disc_rows.append([
                d.get("question_id", ""),
                Paragraph(d.get("question_text", ""), style_body),
                d.get("dimension", ""),
                Paragraph(f"<b>{d.get('value', '—')}</b><br/><font color='#5F6470'>{d.get('notes', '')}</font>", style_body)
            ])

        t_disc = Table(disc_rows, colWidths=[70, 210, 80, 140])
        t_disc.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), COLOR_PAPER),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 7),
            ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
            ("PADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(t_disc)

    story.append(PageBreak())

    # =========================================================================
    # 6. REMEDIATION ROADMAP (30/60/90/180-DAY HORIZONS)
    # =========================================================================
    story.append(Paragraph("5. Diligence Remediation Roadmap", style_h1))
    story.append(Paragraph("Actionable remediation tasks organized by execution horizon and priority score (weight &times; points lost).", style_muted))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=15))

    buckets = roadmap_data.get("buckets", {})
    for horizon in [30, 60, 90, 180]:
        tasks = buckets.get(horizon, [])
        story.append(Paragraph(f"<b>{horizon}-Day Execution Horizon ({len(tasks)} Tasks)</b>", style_h2))

        if tasks:
            h_rows = [["ID", "Action Plan / Playbook", "Dimension", "Recoverable", "Citation"]]
            for t in tasks[:15]:  # Top 15 per bucket
                h_rows.append([
                    t.get("question_id", ""),
                    Paragraph(f"<b>{t.get('title', '')}</b><br/>{t.get('description', '')}", style_body),
                    t.get("dimension", ""),
                    f"+{t.get('points_recoverable', 0)} pts",
                    f"{t.get('source_doc', '')} {t.get('source_ref', '')}"
                ])
            t_h = Table(h_rows, colWidths=[65, 235, 75, 55, 70])
            t_h.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), COLOR_PAPER),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 7),
                ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
                ("PADDING", (0, 0), (-1, -1), 3),
            ]))
            story.append(t_h)
        else:
            story.append(Paragraph("<i>No tasks scheduled in this horizon.</i>", style_muted))

        story.append(Spacer(1, 10))

    story.append(PageBreak())

    # =========================================================================
    # 7. METHODOLOGY & AUDIT GOVERNANCE PAGE
    # =========================================================================
    story.append(Paragraph("6. Methodology & Audit Governance", style_h1))
    story.append(HRFlowable(width="100%", thickness=1, color=COLOR_ACCENT, spaceAfter=15))

    methodology_p = (
        "<b>Deterministic Scoring Layer:</b><br/>"
        "The Diligence Readiness Platform score is strictly rules-based and deterministic. "
        "Points are allocated according to explicit pass rules and severity weights: "
        "CRITICAL (8), HIGH (5), MEDIUM (3), and LOW (1). Partial pass conditions award 50% points. "
        "Unverified and unanswered questions are excluded from dimension scores and counted in evidence completeness. "
        "Scores with less than 60% evidence completeness are flagged as Provisional."
    )
    story.append(Paragraph(methodology_p, style_body))
    story.append(Spacer(1, 15))

    version_table_data = [
        ["Parameter", "Version / Rule Value"],
        ["Scoring Engine Config Version", f"v{score_data.get('config_version', '1.0.0')}"],
        ["Question Bank Version", f"v{score_data.get('question_bank_version', '1.0.0')}"],
        ["Critical-Fail Cap Ceiling", "60.0 points"],
        ["Provisional Completeness Threshold", "60.0%"],
        ["Severity Weights", "CRITICAL=8, HIGH=5, MEDIUM=3, LOW=1"],
        ["Partial Compliance Multiplier", "0.5 (50%)"],
        ["Scored Weight Origin Share", f"Evidence-Backed: {ev_pct}% | Self-Attested: {sa_pct}%"],
        ["Transaction Weight Matrix Status", "[ASSUMPTION] UNVALIDATED"]
    ]
    t_ver = Table(version_table_data, colWidths=[200, 300])
    t_ver.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), COLOR_PAPER),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BOX", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("INNERGRID", (0, 0), (-1, -1), 0.5, COLOR_BORDER),
        ("PADDING", (0, 0), (-1, -1), 4),
    ]))
    story.append(t_ver)

    story.append(Spacer(1, 25))

    story.append(Paragraph("<b>Statutory Legal Disclaimer:</b>", style_h2))
    story.append(Paragraph(
        f"<i>&ldquo;{DISCLAIMER_TEXT}&rdquo;</i><br/><br/>"
        "The assessment scores, remediation timelines, and risk categorizations presented in this document are "
        "analytical indicators for transactional preparation only. They do not constitute formal legal opinions, "
        "fairness opinions, audited representations, or warranty enforceability covenants.",
        style_body
    ))

    # Build PDF with NumberedCanvas
    doc.build(story, canvasmaker=NumberedCanvas)
    return buffer.getvalue()
