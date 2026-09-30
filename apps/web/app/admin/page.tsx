"use client";

import React, { useState, useEffect } from "react";

interface QuestionSummary {
  question_id: string;
  scope: string;
  industry: string;
  sub_sector: string;
  dimension: string;
  question_text: string;
  input_type: string;
  risk_weight: string;
  evidence_type: string;
  review_status: string;
  source_doc: string;
  source_ref: string;
  remediation_horizon_days: number;
  last_verified_on: string | null;
}

interface CoverageMetrics {
  total_questions: number;
  approved: number;
  draft: number;
  auto_extractable: number;
  auto_extractable_pct: number;
  manual_required: number;
  manual_required_pct: number;
  by_evidence_type: Record<string, number>;
}

export default function AdminPage() {
  const [questions, setQuestions] = useState<QuestionSummary[]>([]);
  const [metrics, setMetrics] = useState<CoverageMetrics | null>(null);
  const [selectedStatus, setSelectedStatus] = useState<string>("ALL");
  const [selectedIndustry, setSelectedIndustry] = useState<string>("ALL");
  const [search, setSearch] = useState<string>("");
  const [loading, setLoading] = useState<boolean>(true);
  const [approvingId, setApprovingId] = useState<string | null>(null);

  const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

  const fetchQuestions = async () => {
    try {
      setLoading(true);
      const params = new URLSearchParams();
      if (selectedStatus !== "ALL") params.append("review_status", selectedStatus);
      if (selectedIndustry !== "ALL") params.append("industry", selectedIndustry);
      if (search) params.append("search", search);
      params.append("limit", "150");

      const res = await fetch(`${API_URL}/admin/questions?${params.toString()}`, {
        headers: {
          "Authorization": "Bearer demo-token-admin"
        }
      });
      if (res.ok) {
        const data = await res.json();
        setQuestions(data.items);
      }
    } catch (err) {
      console.error("Failed to fetch questions:", err);
    } finally {
      setLoading(false);
    }
  };

  const fetchMetrics = async () => {
    try {
      const res = await fetch(`${API_URL}/admin/metrics/coverage`, {
        headers: {
          "Authorization": "Bearer demo-token-admin"
        }
      });
      if (res.ok) {
        const data = await res.json();
        setMetrics(data);
      }
    } catch (err) {
      console.error("Failed to fetch coverage metrics:", err);
    }
  };

  useEffect(() => {
    fetchQuestions();
    fetchMetrics();
  }, [selectedStatus, selectedIndustry]);

  const handleApprove = async (qid: string) => {
    try {
      setApprovingId(qid);
      const today = new Date().toISOString().split("T")[0];
      const res = await fetch(`${API_URL}/admin/questions/${qid}/approve`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "Authorization": "Bearer demo-token-admin"
        },
        body: JSON.stringify({
          reviewer_name: "Lead Diligence Counsel",
          last_verified_on: today,
          verification_notes: "Approved citation, pass rule, and horizon in M1 Admin Console"
        })
      });
      if (res.ok) {
        await fetchQuestions();
        await fetchMetrics();
      } else {
        const errorData = await res.json();
        alert(`Approval failed: ${errorData.detail}`);
      }
    } catch (err) {
      console.error(err);
      alert("Network error approving question.");
    } finally {
      setApprovingId(null);
    }
  };

  return (
    <div className="max-w-6xl mx-auto px-6 py-10 space-y-8">
      {/* Header */}
      <div className="border-b border-border pb-6 flex flex-col md:flex-row justify-between items-start md:items-end gap-4">
        <div>
          <div className="text-xs font-mono uppercase tracking-widest text-accent font-semibold">
            Question Bank Administration (Milestone M1)
          </div>
          <h1 className="font-serif text-3xl font-normal text-ink mt-1">
            Question Inventory & Review Console
          </h1>
        </div>
        <div className="text-xs font-mono text-ink-muted">
          All changes version-controlled in <code className="bg-paper px-1.5 py-0.5 border border-border rounded-sm">question_versions</code>
        </div>
      </div>

      {/* Metrics Row */}
      {metrics && (
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="p-4 bg-surface border border-border rounded-md">
            <div className="text-xs font-mono uppercase text-ink-muted">Total Questions</div>
            <div className="text-2xl font-serif font-bold text-ink mt-1">{metrics.total_questions}</div>
            <div className="text-[11px] font-mono text-ink-muted mt-1">11 Core + 5 Branches</div>
          </div>
          <div className="p-4 bg-surface border border-border rounded-md">
            <div className="text-xs font-mono uppercase text-ink-muted">Approved Status</div>
            <div className="text-2xl font-serif font-bold text-status-pass mt-1">{metrics.approved}</div>
            <div className="text-[11px] font-mono text-ink-muted mt-1">Live in Assessments</div>
          </div>
          <div className="p-4 bg-surface border border-border rounded-md">
            <div className="text-xs font-mono uppercase text-ink-muted">Draft Candidates</div>
            <div className="text-2xl font-serif font-bold text-status-partial mt-1">{metrics.draft}</div>
            <div className="text-[11px] font-mono text-ink-muted mt-1">Pending Human Review</div>
          </div>
          <div className="p-4 bg-surface border border-border rounded-md">
            <div className="text-xs font-mono uppercase text-ink-muted">Auto-Extractable Share</div>
            <div className="text-2xl font-serif font-bold text-accent mt-1">{metrics.auto_extractable_pct}%</div>
            <div className="text-[11px] font-mono text-ink-muted mt-1">{metrics.auto_extractable} Auto / {metrics.manual_required} Manual</div>
          </div>
        </div>
      )}

      {/* Filters and Search */}
      <div className="p-4 bg-surface border border-border rounded-md flex flex-wrap items-center justify-between gap-4">
        <div className="flex flex-wrap items-center gap-3">
          <div className="text-xs font-mono font-medium text-ink-muted">Review Status:</div>
          {["ALL", "APPROVED", "UNREVIEWED_SEED", "DRAFT"].map((st) => (
            <button
              key={st}
              onClick={() => setSelectedStatus(st)}
              className={`px-2.5 py-1 text-xs font-mono rounded-sm border transition-colors ${
                selectedStatus === st
                  ? "bg-accent text-white border-accent"
                  : "bg-paper text-ink border-border hover:border-ink"
              }`}
            >
              {st}
            </button>
          ))}

          <span className="text-border mx-1">|</span>

          <div className="text-xs font-mono font-medium text-ink-muted">Industry:</div>
          {["ALL", "UNIVERSAL", "HEALTHCARE", "FINTECH", "SOFTWARE", "MANUFACTURING", "ENERGY"].map((ind) => (
            <button
              key={ind}
              onClick={() => setSelectedIndustry(ind)}
              className={`px-2 py-1 text-[11px] font-mono rounded-sm border transition-colors ${
                selectedIndustry === ind
                  ? "bg-ink text-white border-ink"
                  : "bg-paper text-ink border-border hover:border-ink"
              }`}
            >
              {ind}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <input
            type="text"
            placeholder="Search question text or ID..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && fetchQuestions()}
            className="px-3 py-1.5 text-xs bg-paper border border-border rounded-sm text-ink placeholder:text-ink-muted focus:outline-none focus:border-accent w-64 font-mono"
          />
          <button
            onClick={fetchQuestions}
            className="px-3 py-1.5 text-xs font-mono bg-accent text-white rounded-sm hover:bg-accent-hover"
          >
            Filter
          </button>
        </div>
      </div>

      {/* Questions Data Table */}
      <div className="bg-surface border border-border rounded-md overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-paper border-b border-border font-mono text-[11px] text-ink-muted uppercase">
              <tr>
                <th className="py-3 px-4">ID</th>
                <th className="py-3 px-4">Industry / Dim</th>
                <th className="py-3 px-4">Question Text</th>
                <th className="py-3 px-4">Evidence</th>
                <th className="py-3 px-4">Risk</th>
                <th className="py-3 px-4">Source Citation</th>
                <th className="py-3 px-4">Status</th>
                <th className="py-3 px-4 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border font-sans">
              {loading ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-ink-muted font-mono">
                    Loading question inventory...
                  </td>
                </tr>
              ) : questions.length === 0 ? (
                <tr>
                  <td colSpan={8} className="py-8 text-center text-ink-muted font-mono">
                    No questions match the selected filters.
                  </td>
                </tr>
              ) : (
                questions.map((q) => (
                  <tr key={q.question_id} className="hover:bg-paper/40 transition-colors">
                    <td className="py-3 px-4 font-mono text-xs font-semibold text-ink whitespace-nowrap">
                      {q.question_id}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <div className="font-mono text-[11px] text-ink">{q.industry}</div>
                      <div className="text-[10px] text-ink-muted font-mono">{q.dimension}</div>
                    </td>
                    <td className="py-3 px-4 max-w-md text-ink leading-relaxed">
                      {q.question_text}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className="font-mono text-[10px] px-1.5 py-0.5 rounded-sm bg-paper border border-border text-ink-muted">
                        {q.evidence_type}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className={`font-mono text-[10px] font-semibold ${
                        q.risk_weight === "CRITICAL" ? "text-status-fail" :
                        q.risk_weight === "HIGH" ? "text-status-partial" : "text-ink-muted"
                      }`}>
                        {q.risk_weight}
                      </span>
                    </td>
                    <td className="py-3 px-4 max-w-xs truncate text-[11px] font-mono text-ink-muted" title={`${q.source_doc} ${q.source_ref}`}>
                      {q.source_doc || "—"} {q.source_ref ? `(${q.source_ref})` : ""}
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap">
                      <span className={`font-mono text-[10px] font-semibold px-2 py-0.5 rounded-sm border ${
                        q.review_status === "APPROVED"
                          ? "bg-status-pass/10 text-status-pass border-status-pass/20"
                          : q.review_status === "UNREVIEWED_SEED"
                          ? "bg-amber-500/10 text-amber-600 border-amber-500/20"
                          : "bg-status-partial/10 text-status-partial border-status-partial/20"
                      }`}>
                        {q.review_status}
                      </span>
                    </td>
                    <td className="py-3 px-4 whitespace-nowrap text-right">
                      {q.review_status === "APPROVED" ? (
                        <div className="flex flex-col items-end">
                          <span className="text-[10px] font-mono text-status-pass font-semibold">Verified</span>
                          {q.reviewer_name && (
                            <span className="text-[9px] font-mono text-ink-muted">by {q.reviewer_name}</span>
                          )}
                        </div>
                      ) : (
                        <button
                          disabled={approvingId === q.question_id}
                          onClick={() => handleApprove(q.question_id)}
                          className="px-2.5 py-1 text-[11px] font-mono bg-accent text-white rounded-sm hover:bg-accent-hover disabled:opacity-50 transition-colors"
                        >
                          {approvingId === q.question_id ? "Approving..." : "Approve"}
                        </button>
                      )}
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
