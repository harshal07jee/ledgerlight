"use client";

import React from "react";

export default function LandingPage() {
  const dimensions = [
    { code: "GOVERNANCE", title: "Governance & Corporate Structure", desc: "Corporate records, capitalization table integrity, stock ledger, board consent ratification, and subsidiary chain of title." },
    { code: "FIN_CONTROLS", title: "Financial Controls & Reporting", desc: "US GAAP compliance, accrual accounting, unrecorded liabilities, sales tax nexus, and timely federal/state returns." },
    { code: "LEGAL_IP_REG", title: "Legal, IP & Regulatory", desc: "PIIA founder invention assignments, clean patent/trademark chains, open-source copyleft scans, and material contract terms." },
    { code: "OPS_TECH_CYBER", title: "Operations, Technology & Cyber", desc: "Independent SOC 2 Type II audits, Written Information Security Policy (WISP), DR/BCP testing, and active D&O/cyber insurance." },
    { code: "HUMAN_CAPITAL", title: "Human Capital / HR", desc: "FLSA exempt/non-exempt classifications, independent contractor 1099 compliance, wage-and-hour audits, and benefit plans." },
    { code: "TXN_READINESS", title: "Transaction & Investor Readiness", desc: "Preferential side letters, MFN terms, change-of-control third-party consents, and NVCA-standard class voting rights." },
    { code: "FIN_PERFORMANCE", title: "Financial Performance & Growth", desc: "Trailing 12-month budget vs. actual variance (< 15%), non-recurring EBITDA add-back audit (< 10%), and unit economics." },
    { code: "PROFIT_CASHFLOW", title: "Profitability & Cash Flow", desc: "Net monthly cash burn, verified cash runway months (flagged if < 6–9 months), and burdened gross margin structure." },
    { code: "REVENUE_QUALITY", title: "Revenue Quality & Concentration", desc: "Single customer revenue concentration (flagged if > 20%), contractually recurring share, and historical cohort NRR." },
    { code: "MGMT_DEPTH", title: "Management Team Depth", desc: "Executive second-in-command coverage, key-person dependency, and operational standard operating procedures." },
    { code: "CUSTOMER_MARKET", title: "Customer & Market Position", desc: "Enterprise SLA liability caps, customer contract duration, churn benchmarks, and counterparty credit risks." },
  ];

  const standards = [
    "NVCA Model SPA 2025",
    "NVCA Model IRA & COI",
    "ILPA Due Diligence Questionnaire 2.0",
    "AICPA SOC 2 Trust Criteria",
    "FDA QMSR / 21 CFR 820",
    "HIPAA / HITECH Security Rule",
    "SEC Item 1.05 Cybersecurity Rules",
    "CFPB Section 1033",
    "EPA TSCA PFAS Lookback",
    "FERC Order 2023 Interconnection"
  ];

  return (
    <div className="space-y-24 py-12">
      {/* 1. Hero Section */}
      <section className="max-w-6xl mx-auto px-6">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-12 items-center">
          {/* Left Column: Headline and Copy */}
          <div className="lg:col-span-7 space-y-6">
            <div className="inline-flex items-center space-x-2 px-3 py-1 rounded-sm bg-accent-light text-accent text-xs font-mono font-medium border border-accent/20">
              <span>●</span>
              <span>Diligence Readiness Engine for US Transactions</span>
            </div>

            <h1 className="font-serif text-4xl sm:text-5xl lg:text-6xl font-normal tracking-tight text-ink leading-[1.12]">
              Find your deal-breakers before an investor does.
            </h1>

            <p className="text-lg text-ink-muted leading-relaxed max-w-xl">
              An explainable, deterministic readiness assessment for companies preparing for Series A+, growth equity, M&A, or debt financing. Grounded in NVCA model agreements and audited against 11 institutional dimensions.
            </p>

            <div className="flex flex-col sm:flex-row gap-4 pt-2">
              <a
                href="/onboarding"
                className="inline-flex justify-center items-center px-6 py-3 rounded-md bg-accent text-white font-medium hover:bg-accent-hover transition-colors text-sm shadow-sm"
              >
                Start Free Diligence Assessment
              </a>
              <a
                href="/admin"
                className="inline-flex justify-center items-center px-6 py-3 rounded-md border border-border bg-surface text-ink font-medium hover:border-ink transition-colors text-sm"
              >
                Admin Question Console
              </a>
            </div>

            <p className="text-xs text-ink-muted/80 font-mono">
              Deterministic scoring • Evidence-linked passages • Zero hallucinations
            </p>
          </div>

          {/* Right Column: Real Product Excerpt (Cropped Report & Score Card) */}
          <div className="lg:col-span-5">
            <div className="bg-surface border border-border rounded-md shadow-sm p-6 space-y-6">
              {/* Score Header */}
              <div className="flex justify-between items-start border-b border-border pb-5">
                <div>
                  <div className="text-xs font-mono uppercase tracking-wider text-ink-muted">Readiness Score</div>
                  <div className="flex items-baseline space-x-2 mt-1">
                    <span className="font-serif text-5xl font-bold tabular-nums text-ink">58</span>
                    <span className="text-sm font-mono text-ink-muted">/ 100</span>
                  </div>
                </div>

                <div className="text-right">
                  <span className="inline-block px-2.5 py-1 rounded-sm text-xs font-mono font-semibold bg-status-fail/10 text-status-fail border border-status-fail/20">
                    CAPPED AT 60 (CRITICAL FAIL)
                  </span>
                  <div className="text-xs text-ink-muted mt-1 font-mono">Completeness: 88%</div>
                </div>
              </div>

              {/* Sample Trace Item (Explainability excerpt) */}
              <div className="space-y-3">
                <div className="text-xs font-mono uppercase tracking-wider text-ink-muted">Audit Score Trace (Excerpt)</div>
                
                <div className="p-3.5 bg-paper rounded-sm border border-border space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="font-mono font-semibold text-status-fail">CORE_IP_02 • FAIL</span>
                    <span className="font-mono text-ink-muted">-8.0 pts (CRITICAL)</span>
                  </div>
                  <p className="font-medium text-ink">
                    Missing PIIA invention assignment for 1 founder.
                  </p>
                  <div className="text-ink-muted text-[11px] space-y-1">
                    <div><strong>Rule:</strong> Pass when 100% of founders/contractors executed PIIA.</div>
                    <div><strong>Source:</strong> NVCA SPA 2025 Section 2.8(h) (PIIA and Invention Assignment)</div>
                    <div className="font-mono text-accent truncate"><strong>Matched:</strong> "Founder John Doe - No executed assignment discovered"</div>
                  </div>
                </div>

                <div className="p-3.5 bg-paper rounded-sm border border-border space-y-2 text-xs">
                  <div className="flex justify-between items-center">
                    <span className="font-mono font-semibold text-status-pass">CORE_CASH_FLOW_01 • PASS</span>
                    <span className="font-mono text-ink-muted">Full Credit (100%)</span>
                  </div>
                  <p className="font-medium text-ink">
                    Cash runway is 14.2 months (Threshold: ≥ 9 mo).
                  </p>
                  <div className="text-ink-muted text-[11px]">
                    <strong>Source:</strong> Trailing 6-Month Cash Burn & Bank Balance Schedule
                  </div>
                </div>
              </div>

              {/* Remediation Preview */}
              <div className="pt-2 border-t border-border flex justify-between items-center text-xs font-mono text-ink-muted">
                <span>Remediation Roadmap: 4 Tasks</span>
                <span className="text-accent underline cursor-pointer">View 30-Day Fixes →</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* 2. Regulatory & Diligence Sources Strip */}
      <section id="sources" className="border-y border-border bg-surface py-8">
        <div className="max-w-6xl mx-auto px-6 space-y-4">
          <p className="text-xs font-mono uppercase tracking-widest text-ink-muted text-center">
            Standard Diligence Sources & Regulatory Grounding
          </p>
          <div className="flex flex-wrap justify-center gap-x-8 gap-y-3 text-xs font-mono text-ink">
            {standards.map((s, idx) => (
              <span key={idx} className="flex items-center space-x-2">
                <span className="text-ink-muted/50">•</span>
                <span>{s}</span>
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* 3. Three-Step Workflow */}
      <section id="workflow" className="max-w-6xl mx-auto px-6 space-y-12">
        <div className="max-w-xl space-y-3">
          <div className="text-xs font-mono uppercase tracking-widest text-accent font-semibold">Audit Methodology</div>
          <h2 className="font-serif text-3xl font-normal text-ink">
            A transparent 3-step diligence pipeline.
          </h2>
          <p className="text-sm text-ink-muted leading-relaxed">
            No black-box guesses. Extractive models propose answers directly from your contracts and financial statements, requiring your confirmation before anything affects your score.
          </p>
        </div>

        <div className="grid grid-cols-1 md:grid-cols-3 gap-8">
          <div className="p-6 bg-surface border border-border rounded-md space-y-4">
            <span className="font-mono text-xl font-bold text-accent">01</span>
            <h3 className="font-serif text-xl font-medium text-ink">Ground & Ingest</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Upload your data room (financial models, cap table, customer contracts, policies). Files are processed in memory and deleted immediately after parsing.
            </p>
          </div>

          <div className="p-6 bg-surface border border-border rounded-md space-y-4">
            <span className="font-mono text-xl font-bold text-accent">02</span>
            <h3 className="font-serif text-xl font-medium text-ink">Verify & Gating</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              High-confidence items ($\ge 0.85$) auto-fill with exact highlighted source snippets. Ambiguous items route to human confirmation; unanswerable items route to manual entry.
            </p>
          </div>

          <div className="p-6 bg-surface border border-border rounded-md space-y-4">
            <span className="font-mono text-xl font-bold text-accent">03</span>
            <h3 className="font-serif text-xl font-medium text-ink">Score, Trace & Fix</h3>
            <p className="text-xs text-ink-muted leading-relaxed">
              Receive a deterministic 0–100 Readiness Score with per-dimension points, full audit trace for every deduction, and a 30/60/90/180-day remediation roadmap.
            </p>
          </div>
        </div>
      </section>

      {/* 4. What We Check (11 Dimensions Compact Ruled List) */}
      <section id="dimensions" className="max-w-6xl mx-auto px-6 space-y-8">
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b border-border pb-6">
          <div>
            <div className="text-xs font-mono uppercase tracking-widest text-accent font-semibold">Scope of Review</div>
            <h2 className="font-serif text-3xl font-normal text-ink mt-2">
              The 11 Universal Diligence Dimensions
            </h2>
          </div>
          <p className="text-xs font-mono text-ink-muted max-w-md">
            All institutional transaction categories weighted by deal type (VC Growth, M&A Sell-Side, IPO Prep, Debt).
          </p>
        </div>

        <div className="divide-y divide-border border-y border-border">
          {dimensions.map((dim, idx) => (
            <div key={idx} className="py-4 grid grid-cols-1 md:grid-cols-12 gap-4 items-baseline hover:bg-surface/50 transition-colors px-2">
              <div className="md:col-span-1 font-mono text-xs text-ink-muted">
                {String(idx + 1).padStart(2, "0")}
              </div>
              <div className="md:col-span-4 font-serif text-base font-medium text-ink">
                {dim.title}
              </div>
              <div className="md:col-span-5 text-xs text-ink-muted leading-relaxed">
                {dim.desc}
              </div>
              <div className="md:col-span-2 text-right">
                <span className="font-mono text-[11px] text-ink-muted uppercase tracking-wider bg-paper px-2 py-0.5 border border-border rounded-sm">
                  {dim.code}
                </span>
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* 5. Start Assessment Call to Action */}
      <section id="get-started" className="max-w-6xl mx-auto px-6">
        <div className="bg-surface border border-border rounded-md p-10 text-center space-y-6 max-w-3xl mx-auto shadow-sm">
          <div className="inline-block font-mono text-xs uppercase tracking-widest text-accent font-semibold">
            Confidential & Ephemeral
          </div>
          <h2 className="font-serif text-3xl sm:text-4xl text-ink font-normal">
            Ready to audit your data room?
          </h2>
          <p className="text-sm text-ink-muted leading-relaxed max-w-lg mx-auto">
            Uploaded raw files are processed in an encrypted temporary environment and deleted immediately. Only evidence citations and verified answers are retained.
          </p>
          <div className="pt-2">
            <button
              onClick={() => alert("Assessment flow begins in Milestone M2. Seed Question Bank and Admin review are live in M1.")}
              className="px-8 py-3.5 rounded-md bg-accent text-white font-medium hover:bg-accent-hover transition-colors text-sm shadow-sm"
            >
              Begin Company Onboarding
            </button>
          </div>
          <p className="text-xs text-ink-muted font-mono">
            Compliant with standard US venture, growth equity, and M&A requirements.
          </p>
        </div>
      </section>
    </div>
  );
}
