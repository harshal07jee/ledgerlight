"use client";

import React, { useEffect, useState, useMemo } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavigationMenu } from "@/components/ui-21st/navigation-menu";
import { NumberTicker } from "@/components/ui-21st/number-ticker";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const DIMENSION_NAMES: Record<string, string> = {
  GOVERNANCE: "Governance & Corporate Structure",
  FIN_CONTROLS: "Financial Controls & Reporting",
  LEGAL_IP_REG: "Legal, IP & Regulatory",
  OPS_TECH_CYBER: "Operations, Technology & Cyber",
  HUMAN_CAPITAL: "Human Capital / HR",
  TXN_READINESS: "Transaction & Investor Readiness",
  FIN_PERFORMANCE: "Financial Performance & Growth",
  PROFIT_CASHFLOW: "Profitability & Cash Flow",
  REVENUE_QUALITY: "Revenue Quality & Concentration",
  MGMT_DEPTH: "Management Team Depth",
  CUSTOMER_MARKET: "Customer & Market Position",
  INDUSTRY_REG: "Industry Regulatory & Technical Branch",
};

interface TraceRow {
  id?: string;
  question_id: string;
  question_text: string;
  dimension: string;
  risk_weight: string;
  weight_value: number;
  answer_state: string;
  user_answer: any;
  expected_rule: string;
  points_lost: number;
  source_doc?: string;
  source_ref?: string;
  evidence_snippet?: string;
  answer_origin: string;
  notes?: string;
  is_critical_fail: boolean;
}

interface DimensionScore {
  dimension: string;
  score: number | null;
  answered_count: number;
  total_applicable: number;
  earned_weight: number;
  total_weight: number;
  transaction_weight: number;
}

interface FailedCriticalItem {
  question_id: string;
  question_text: string;
  dimension: string;
  risk_weight: string;
  points_lost: number;
  source_doc?: string;
  source_ref?: string;
}

interface ScoreReportData {
  assessment_id: string;
  score_run_id?: string;
  overall_score: number;
  unconstrained_score: number;
  best_case_score?: number;
  worst_case_score?: number;
  critical_cap_applied: boolean;
  critical_fail_cap?: number;
  failed_critical_count: number;
  failed_critical_items: FailedCriticalItem[];
  completeness: {
    completeness_pct: number;
    is_provisional: boolean;
    total_applicable?: number;
    answered_count?: number;
    unanswered_count?: number;
  };
  dimension_scores: Record<string, DimensionScore>;
  trace_rows: TraceRow[];
  total_deductions: number;
  total_points_lost: number;
  scored_question_review_status?: {
    AI_PRE_REVIEWED: number;
    UNREVIEWED_SEED: number;
    APPROVED: number;
    total_scored?: number;
  };
  transaction_type: string;
  config_version: string;
  question_bank_version: string;
  created_at?: string;
}

interface RoadmapTask {
  id: string;
  assessment_id: string;
  question_id: string;
  title: string;
  description: string;
  dimension: string;
  sub_category: string;
  horizon_days: number;
  risk_weight: string;
  weight_value: number;
  points_recoverable: number;
  priority_score: number;
  source_doc?: string;
  source_ref?: string;
  status: "todo" | "in_progress" | "done";
  assignee?: string | null;
  comments: Array<{
    id: string;
    author: string;
    text: string;
    created_at: string;
  }>;
}

interface RoadmapGroup {
  group_key: string;
  dimension: string;
  sub_category: string;
  tasks: RoadmapTask[];
  total_points_recoverable: number;
  task_count: number;
}

interface RoadmapData {
  assessment_id: string;
  buckets: Record<string | number, RoadmapTask[]>;
  groups: RoadmapGroup[];
  summary: {
    total_tasks: number;
    total_points_recoverable: number;
    critical_tasks_count: number;
    by_horizon: Record<string, number>;
  };
}

interface DeltaData {
  is_initial_assessment: boolean;
  overall_score_delta: number;
  unconstrained_score_delta: number;
  completeness_delta: number;
  critical_cap_status: {
    previous_capped: boolean;
    current_capped: boolean;
    cap_lifted: boolean;
    cap_imposed: boolean;
  };
  dimension_deltas: Array<{
    dimension: string;
    current_score: number | null;
    previous_score: number | null;
    delta: number;
  }>;
  flipped_items: Array<{
    question_id: string;
    question_text: string;
    dimension: string;
    previous_state: string;
    current_state: string;
    flipped_to_pass: boolean;
    flipped_to_fail: boolean;
    points_recovered: number;
    source_doc?: string;
    source_ref?: string;
  }>;
  total_flipped_to_pass: number;
  current_run_id?: string;
  previous_run_id?: string;
}

type TabType = "score_trace" | "roadmap" | "delta";
type SortField = "points_lost" | "weight_value" | "question_id" | "dimension";
type SortDirection = "asc" | "desc";

export default function ReadinessReportPage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = params?.id as string;

  const [activeTab, setActiveTab] = useState<TabType>("score_trace");
  const [report, setReport] = useState<ScoreReportData | null>(null);
  const [roadmap, setRoadmap] = useState<RoadmapData | null>(null);
  const [delta, setDelta] = useState<DeltaData | null>(null);

  const [loading, setLoading] = useState(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [downloadingPdf, setDownloadingPdf] = useState(false);
  const [recalculating, setRecalculating] = useState(false);

  // Trace table filters & sort
  const [searchQuery, setSearchQuery] = useState("");
  const [dimensionFilter, setDimensionFilter] = useState<string>("ALL");
  const [sortField, setSortField] = useState<SortField>("points_lost");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  // Roadmap Detail Drawer & State
  const [activeDrawerTask, setActiveDrawerTask] = useState<RoadmapTask | null>(null);
  const [roadmapViewMode, setRoadmapViewMode] = useState<"lanes" | "clusters">("lanes");
  const [commentInput, setCommentInput] = useState("");
  const [assigneeInput, setAssigneeInput] = useState("");
  const [updatingTask, setUpdatingTask] = useState(false);

  // Fetch all report data
  const loadAllData = async (triggerScoreCalculation = false) => {
    try {
      if (triggerScoreCalculation) {
        setRecalculating(true);
      } else {
        setLoading(true);
      }
      setErrorMsg(null);

      const token = typeof window !== "undefined" ? localStorage.getItem("ledgerlight_token") : null;
      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
      };

      // 1. Fetch score & trace
      let scoreRes: Response;
      if (triggerScoreCalculation) {
        scoreRes = await fetch(`${API_BASE}/assessments/${assessmentId}/score`, {
          method: "POST",
          headers,
          credentials: "include",
        });
      } else {
        scoreRes = await fetch(`${API_BASE}/assessments/${assessmentId}/trace`, {
          headers,
          credentials: "include",
        });
        if (!scoreRes.ok) {
          scoreRes = await fetch(`${API_BASE}/assessments/${assessmentId}/score`, {
            method: "POST",
            headers,
            credentials: "include",
          });
        }
      }

      if (!scoreRes.ok) {
        throw new Error(`Failed to load assessment score (Status: ${scoreRes.status})`);
      }
      const scoreData: ScoreReportData = await scoreRes.json();
      setReport(scoreData);

      // 2. Fetch roadmap data
      const roadmapRes = await fetch(`${API_BASE}/assessments/${assessmentId}/roadmap`, {
        headers,
        credentials: "include",
      });
      if (roadmapRes.ok) {
        const roadmapData: RoadmapData = await roadmapRes.json();
        setRoadmap(roadmapData);
      }

      // 3. Fetch delta data
      const deltaRes = await fetch(`${API_BASE}/assessments/${assessmentId}/delta`, {
        headers,
        credentials: "include",
      });
      if (deltaRes.ok) {
        const deltaData: DeltaData = await deltaRes.json();
        setDelta(deltaData);
      }
    } catch (err: any) {
      console.error("Report load error:", err);
      setErrorMsg(err.message || "Failed to load diligence readiness report.");
    } finally {
      setLoading(false);
      setRecalculating(false);
    }
  };

  useEffect(() => {
    if (assessmentId) {
      loadAllData(false);
    }
  }, [assessmentId]);

  // Handle PDF Export
  const handleDownloadPdf = async () => {
    try {
      setDownloadingPdf(true);
      const token = typeof window !== "undefined" ? localStorage.getItem("ledgerlight_token") : null;
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/report.pdf`, {
        headers: {
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
      });
      if (!res.ok) {
        throw new Error(`Failed to generate PDF (Status: ${res.status})`);
      }
      const blob = await res.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `ledgerlight_report_${assessmentId.slice(0, 8)}.pdf`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
    } catch (err: any) {
      alert(err.message || "Failed to download PDF report");
    } finally {
      setDownloadingPdf(false);
    }
  };

  // Update Roadmap Task (Done, Assignee, Comment)
  const handleUpdateTask = async (
    taskId: string,
    updates: { status?: "todo" | "in_progress" | "done"; assignee?: string; comment?: string }
  ) => {
    try {
      setUpdatingTask(true);
      const token = typeof window !== "undefined" ? localStorage.getItem("ledgerlight_token") : null;
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/roadmap/tasks/${taskId}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        credentials: "include",
        body: JSON.stringify(updates),
      });

      if (!res.ok) {
        throw new Error("Failed to update task");
      }

      const updatedTask: RoadmapTask = await res.json();

      // Synchronize in local roadmap state
      setRoadmap((prev) => {
        if (!prev) return null;
        const newBuckets: Record<string | number, RoadmapTask[]> = { ...prev.buckets };
        for (const h of [30, 60, 90, 180]) {
          const lane = newBuckets[h] || newBuckets[String(h)] || [];
          const updatedLane = lane.map((t) => (t.id === taskId ? updatedTask : t));
          newBuckets[h] = updatedLane;
          newBuckets[String(h)] = updatedLane;
        }

        const newGroups = prev.groups.map((g) => ({
          ...g,
          tasks: g.tasks.map((t) => (t.id === taskId ? updatedTask : t)),
        }));

        return { ...prev, buckets: newBuckets, groups: newGroups };
      });

      if (activeDrawerTask && activeDrawerTask.id === taskId) {
        setActiveDrawerTask(updatedTask);
      }
      setCommentInput("");
    } catch (err: any) {
      alert(err.message || "Failed to update task");
    } finally {
      setUpdatingTask(false);
    }
  };

  // Sort and filter trace rows
  const filteredAndSortedTrace = useMemo(() => {
    if (!report?.trace_rows) return [];

    let rows = [...report.trace_rows];

    if (dimensionFilter !== "ALL") {
      rows = rows.filter((r) => r.dimension === dimensionFilter);
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      rows = rows.filter(
        (r) =>
          r.question_id.toLowerCase().includes(q) ||
          r.question_text.toLowerCase().includes(q) ||
          (r.source_doc && r.source_doc.toLowerCase().includes(q))
      );
    }

    rows.sort((a, b) => {
      let valA: any = a[sortField];
      let valB: any = b[sortField];

      if (sortField === "question_id" || sortField === "dimension") {
        return sortDirection === "asc"
          ? String(valA).localeCompare(String(valB))
          : String(valB).localeCompare(String(valA));
      }

      const numA = Number(valA) || 0;
      const numB = Number(valB) || 0;
      return sortDirection === "asc" ? numA - numB : numB - numA;
    });

    return rows;
  }, [report?.trace_rows, dimensionFilter, searchQuery, sortField, sortDirection]);

  const handleSort = (field: SortField) => {
    if (sortField === field) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortField(field);
      setSortDirection("desc");
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F6F3EC]">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-[#1F4D3F] border-t-transparent" />
          <p className="mt-4 font-mono text-xs uppercase tracking-wider text-[#5F6470]">
            Computing Deterministic Readiness Score, Trace & Roadmap...
          </p>
        </div>
      </div>
    );
  }

  if (errorMsg || !report) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[#F6F3EC] px-4">
        <div className="max-w-md rounded-xl border border-[#B4382F]/30 bg-[#FFFFFF] p-6 text-center shadow-xs">
          <div className="mx-auto mb-3 flex h-10 w-10 items-center justify-center rounded-full bg-[#B4382F]/10 text-[#B4382F]">
            <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
            </svg>
          </div>
          <h2 className="font-serif text-lg font-semibold text-[#16181D]">Report Unavailable</h2>
          <p className="mt-2 text-xs text-[#5F6470]">{errorMsg}</p>
          <div className="mt-6 flex justify-center gap-3">
            <Link
              href={`/assessment/${assessmentId}`}
              className="rounded-lg bg-[#1F4D3F] px-4 py-2 font-mono text-xs font-medium text-white hover:bg-[#17392F]"
            >
              Return to Questionnaire
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const txnFormatted = report.transaction_type.replace(/_/g, " ");

  return (
    <div className="min-h-screen bg-[#F6F3EC] text-[#16181D]">
      {/* Editorial Navigation Bar */}
      <NavigationMenu
        rightElement={
          <div className="flex items-center gap-3">
            <button
              onClick={handleDownloadPdf}
              disabled={downloadingPdf}
              className="inline-flex items-center gap-2 rounded-lg bg-[#1F4D3F] px-3.5 py-1.5 font-mono text-xs font-medium text-white hover:bg-[#17392F] transition-colors shadow-xs disabled:opacity-50"
            >
              <svg className="h-4 w-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
              </svg>
              {downloadingPdf ? "Generating PDF..." : "Export PDF Report"}
            </button>
            <Link
              href={`/assessment/${assessmentId}`}
              className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
            >
              &larr; Workspace
            </Link>
          </div>
        }
      />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8 space-y-6">
        {/* Top Header Breadcrumb & Version Tags */}
        <div className="flex flex-wrap items-center justify-between gap-4 border-b border-[#E2DDD2] pb-5">
          <div>
            <div className="flex items-center gap-2 font-mono text-xs text-[#5F6470]">
              <span>DILIGENCE READINESS AUDIT</span>
              <span>&bull;</span>
              <span className="font-semibold text-[#1F4D3F]">{txnFormatted}</span>
            </div>
            <h1 className="mt-1 font-serif text-2xl sm:text-3xl font-bold tracking-tight text-[#16181D]">
              Assessment & Remediation Platform
            </h1>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <span className="rounded-md border border-[#E2DDD2] bg-[#FFFFFF] px-2.5 py-1 font-mono text-[11px] text-[#5F6470]">
              Config v{report.config_version}
            </span>
            <span className="rounded-md border border-[#E2DDD2] bg-[#FFFFFF] px-2.5 py-1 font-mono text-[11px] text-[#5F6470]">
              QB v{report.question_bank_version}
            </span>
            <button
              onClick={() => loadAllData(true)}
              disabled={recalculating}
              className="inline-flex items-center gap-1.5 rounded-md border border-[#E2DDD2] bg-[#FFFFFF] px-2.5 py-1 font-mono text-[11px] font-medium text-[#1F4D3F] hover:bg-[#F6F3EC] transition-colors disabled:opacity-50"
            >
              <svg className={`h-3 w-3 ${recalculating ? "animate-spin" : ""}`} fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              {recalculating ? "Calculating..." : "Re-assess"}
            </button>
          </div>
        </div>

        {/* M4 Tab Switcher */}
        <div className="flex border-b border-[#E2DDD2]">
          <button
            onClick={() => setActiveTab("score_trace")}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 font-mono text-xs font-semibold transition-all ${
              activeTab === "score_trace"
                ? "border-[#1F4D3F] text-[#1F4D3F] bg-[#FFFFFF]/60"
                : "border-transparent text-[#5F6470] hover:text-[#16181D]"
            }`}
          >
            <span>1. Executive Score & Trace</span>
            <span className="rounded-full bg-[#1F4D3F]/10 px-2 py-0.5 text-[10px] text-[#1F4D3F]">
              {report.overall_score} pts
            </span>
          </button>

          <button
            onClick={() => setActiveTab("roadmap")}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 font-mono text-xs font-semibold transition-all ${
              activeTab === "roadmap"
                ? "border-[#1F4D3F] text-[#1F4D3F] bg-[#FFFFFF]/60"
                : "border-transparent text-[#5F6470] hover:text-[#16181D]"
            }`}
          >
            <span>2. Remediation Roadmap Board</span>
            {roadmap?.summary?.total_tasks ? (
              <span className="rounded-full bg-[#B7791F]/10 px-2 py-0.5 text-[10px] text-[#B7791F]">
                {roadmap.summary.total_tasks} tasks
              </span>
            ) : null}
          </button>

          <button
            onClick={() => setActiveTab("delta")}
            className={`flex items-center gap-2 border-b-2 px-5 py-3 font-mono text-xs font-semibold transition-all ${
              activeTab === "delta"
                ? "border-[#1F4D3F] text-[#1F4D3F] bg-[#FFFFFF]/60"
                : "border-transparent text-[#5F6470] hover:text-[#16181D]"
            }`}
          >
            <span>3. Re-assessment Delta</span>
            {delta && !delta.is_initial_assessment ? (
              <span
                className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${
                  delta.overall_score_delta >= 0
                    ? "bg-[#2F7D57]/10 text-[#2F7D57]"
                    : "bg-[#B4382F]/10 text-[#B4382F]"
                }`}
              >
                {delta.overall_score_delta >= 0 ? `+${delta.overall_score_delta}` : delta.overall_score_delta}
              </span>
            ) : (
              <span className="rounded-full bg-[#5F6470]/10 px-2 py-0.5 text-[10px] text-[#5F6470]">Initial</span>
            )}
          </button>
        </div>

        {/* ========================================================================= */}
        {/* TAB 1: EXECUTIVE SCORE & TRACE (Milestone M3 Core)                         */}
        {/* ========================================================================= */}
        {activeTab === "score_trace" && (
          <div className="space-y-8 animate-fadeIn">
            {/* Critical Fail Cap Alert Banner */}
            {report.critical_cap_applied && (
              <div className="rounded-xl border border-[#B4382F]/40 bg-[#B4382F]/5 p-5 shadow-xs">
                <div className="flex items-start gap-3">
                  <div className="mt-0.5 rounded-full bg-[#B4382F]/10 p-1.5 text-[#B4382F]">
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
                    </svg>
                  </div>
                  <div className="flex-1">
                    <h3 className="font-serif text-base font-semibold text-[#B4382F]">
                      Critical Risk Cap Applied &mdash; Overall Score Capped at 60
                    </h3>
                    <p className="mt-1 text-xs text-[#5F6470]">
                      Per PRD Section 8.4, one or more <strong className="text-[#16181D]">CRITICAL</strong> risk items failed verification.
                      The unconstrained weighted readiness score was{" "}
                      <strong className="text-[#16181D]">{report.unconstrained_score}</strong>, but has been capped at{" "}
                      <strong className="text-[#B4382F]">60.0</strong> until these fatal diligence blockers are remediated.
                    </p>

                    <div className="mt-3 divide-y divide-[#B4382F]/15 rounded-lg border border-[#B4382F]/20 bg-[#FFFFFF]">
                      {report.failed_critical_items.map((item) => (
                        <div key={item.question_id} className="flex flex-wrap items-center justify-between gap-2 p-3 text-xs">
                          <div>
                            <span className="font-mono text-[11px] font-bold text-[#B4382F]">
                              [{item.question_id}]
                            </span>{" "}
                            <span className="font-medium text-[#16181D]">{item.question_text}</span>
                            {item.source_doc && (
                              <span className="block font-mono text-[10px] text-[#5F6470]">
                                Source: {item.source_doc} {item.source_ref ? `• ${item.source_ref}` : ""}
                              </span>
                            )}
                          </div>
                          <span className="rounded bg-[#B4382F]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#B4382F]">
                            -{item.points_lost} pts
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Executive Summary Cards */}
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-5">
              {/* Overall Score */}
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                    Readiness Score
                  </span>
                  <span
                    className={`rounded px-2 py-0.5 font-mono text-[10px] font-bold uppercase ${
                      report.overall_score >= 80
                        ? "bg-[#2F7D57]/10 text-[#2F7D57]"
                        : report.overall_score >= 60
                        ? "bg-[#B7791F]/10 text-[#B7791F]"
                        : "bg-[#B4382F]/10 text-[#B4382F]"
                    }`}
                  >
                    {report.overall_score >= 80 ? "Audit Ready" : report.overall_score >= 60 ? "Moderate" : "High Risk"}
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="font-serif text-4xl font-bold tracking-tight text-[#16181D]">
                    <NumberTicker value={report.overall_score} decimals={1} />
                  </span>
                  <span className="font-mono text-sm text-[#5F6470]">/ 100</span>
                </div>
                {report.critical_cap_applied && (
                  <p className="mt-2 font-mono text-[11px] text-[#B4382F]">
                    Raw unconstrained: {report.unconstrained_score}
                  </p>
                )}
              </div>

              {/* Best/Worst Bounds */}
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                    Unverified Bounds
                  </span>
                  <span className="rounded bg-[#5F6470]/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-[#5F6470]">
                    Range
                  </span>
                </div>
                <div className="mt-3 flex items-center justify-between gap-4">
                  <div>
                    <span className="block font-mono text-[10px] text-[#5F6470]">Worst-Case (Fail)</span>
                    <span className="font-serif text-xl font-bold text-[#B4382F]">
                      {report.worst_case_score ?? report.overall_score}
                    </span>
                  </div>
                  <div className="h-8 w-px bg-[#E2DDD2]" />
                  <div>
                    <span className="block font-mono text-[10px] text-[#5F6470]">Best-Case (Pass)</span>
                    <span className="font-serif text-xl font-bold text-[#2F7D57]">
                      {report.best_case_score ?? report.overall_score}
                    </span>
                  </div>
                </div>
                <p className="mt-2 font-mono text-[10px] text-[#5F6470]">
                  Assuming unverified answers flip to all-fail vs all-pass
                </p>
              </div>

              {/* Completeness */}
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                    Completeness
                  </span>
                  {report.completeness.is_provisional ? (
                    <span className="rounded bg-[#B7791F]/10 px-2 py-0.5 font-mono text-[10px] font-bold text-[#B7791F] uppercase">
                      Provisional
                    </span>
                  ) : (
                    <span className="rounded bg-[#2F7D57]/10 px-2 py-0.5 font-mono text-[10px] font-bold text-[#2F7D57] uppercase">
                      Verified
                    </span>
                  )}
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="font-serif text-4xl font-bold tracking-tight text-[#16181D]">
                    <NumberTicker value={report.completeness.completeness_pct} decimals={1} />
                  </span>
                  <span className="font-mono text-sm text-[#5F6470]">%</span>
                </div>
                <p className="mt-2 text-[11px] text-[#5F6470]">
                  {report.completeness.is_provisional
                    ? "< 60% threshold — score marked provisional"
                    : "Sufficient data density for diligence audit"}
                </p>
              </div>

              {/* Deductions Lost */}
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                    Diligence Gaps
                  </span>
                  <span className="rounded bg-[#B4382F]/10 px-2 py-0.5 font-mono text-[10px] font-bold text-[#B4382F]">
                    {report.total_deductions} Deductions
                  </span>
                </div>
                <div className="mt-3 flex items-baseline gap-2">
                  <span className="font-serif text-4xl font-bold tracking-tight text-[#B4382F]">
                    -{report.total_points_lost}
                  </span>
                  <span className="font-mono text-sm text-[#5F6470]">pts</span>
                </div>
                <p className="mt-2 text-[11px] text-[#5F6470]">
                  Recoverable via remediation tasks
                </p>
              </div>

              {/* Scored Questions Review Status Breakdown */}
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
                <div className="flex items-center justify-between">
                  <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                    Question Review Audit
                  </span>
                  <span className="rounded bg-purple-500/10 px-2 py-0.5 font-mono text-[10px] font-semibold text-purple-700">
                    Audit Status
                  </span>
                </div>
                <div className="mt-3 space-y-1.5 font-mono text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-[#5F6470] flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-purple-500" />
                      AI Pre-reviewed:
                    </span>
                    <span className="font-bold text-[#16181D]">
                      {report.scored_question_review_status?.AI_PRE_REVIEWED ?? 0}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[#5F6470] flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-amber-500" />
                      Unreviewed Seed:
                    </span>
                    <span className="font-bold text-[#16181D]">
                      {report.scored_question_review_status?.UNREVIEWED_SEED ?? 0}
                    </span>
                  </div>
                  <div className="flex items-center justify-between">
                    <span className="text-[#5F6470] flex items-center gap-1.5">
                      <span className="h-2 w-2 rounded-full bg-emerald-500" />
                      Human Approved:
                    </span>
                    <span className="font-bold text-[#16181D]">
                      {report.scored_question_review_status?.APPROVED ?? 0}
                    </span>
                  </div>
                </div>
                <p className="mt-2 text-[10px] font-mono text-[#5F6470]">
                  Scored questions contributing to readiness
                </p>
              </div>
            </div>

            {/* Dimension Breakdown Table */}
            <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
              <h2 className="font-serif text-lg font-bold text-[#16181D]">
                Dimension Readiness Scores & Transaction Weighting
              </h2>
              <p className="mt-1 text-xs text-[#5F6470]">
                Calculated according to the transaction matrix for <strong className="text-[#16181D]">{txnFormatted}</strong>.
              </p>

              <div className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {Object.entries(report.dimension_scores).map(([dcode, ddata]) => {
                  const name = DIMENSION_NAMES[dcode] || dcode;
                  const score = ddata.score;
                  return (
                    <div key={dcode} className="rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 p-4 transition-all hover:bg-[#F6F3EC]/70">
                      <div className="flex items-start justify-between gap-2">
                        <div>
                          <span className="font-mono text-[10px] text-[#5F6470]">{dcode}</span>
                          <h4 className="font-serif text-xs font-bold text-[#16181D] line-clamp-1">{name}</h4>
                        </div>
                        <span className="rounded bg-[#FFFFFF] border border-[#E2DDD2] px-1.5 py-0.5 font-mono text-[10px] text-[#5F6470]">
                          Wt: {ddata.transaction_weight}%
                        </span>
                      </div>

                      <div className="mt-3 flex items-baseline justify-between">
                        <span className="font-serif text-2xl font-bold text-[#16181D]">
                          {score !== null ? `${score}%` : "—"}
                        </span>
                        <span className="font-mono text-[11px] text-[#5F6470]">
                          {ddata.answered_count} / {ddata.total_applicable} answered
                        </span>
                      </div>

                      <div className="mt-2 h-1.5 w-full rounded-full bg-[#E2DDD2] overflow-hidden">
                        <div
                          className={`h-full rounded-full transition-all duration-500 ${
                            score === null
                              ? "w-0"
                              : score >= 80
                              ? "bg-[#2F7D57]"
                              : score >= 50
                              ? "bg-[#B7791F]"
                              : "bg-[#B4382F]"
                          }`}
                          style={{ width: `${score ?? 0}%` }}
                        />
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Explanatory Trace Table */}
            <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] shadow-xs overflow-hidden">
              <div className="p-6 border-b border-[#E2DDD2]">
                <div className="flex flex-wrap items-center justify-between gap-4">
                  <div>
                    <h2 className="font-serif text-lg font-bold text-[#16181D]">
                      Explanatory Score Trace (&ldquo;Why this score&rdquo;)
                    </h2>
                    <p className="mt-1 text-xs text-[#5F6470]">
                      Every point deducted is deterministically tied to a specific rule, finding, and citation.
                    </p>
                  </div>

                  <div className="flex flex-wrap items-center gap-3">
                    <input
                      type="text"
                      placeholder="Search questions or citations..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs text-[#16181D] placeholder-[#5F6470] focus:border-[#1F4D3F] focus:outline-hidden"
                    />

                    <select
                      value={dimensionFilter}
                      onChange={(e) => setDimensionFilter(e.target.value)}
                      className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden"
                    >
                      <option value="ALL">All Dimensions</option>
                      {Object.keys(report.dimension_scores).map((d) => (
                        <option key={d} value={d}>
                          {d}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="overflow-x-auto">
                <table className="w-full text-left font-sans text-xs">
                  <thead className="border-b border-[#E2DDD2] bg-[#F6F3EC] font-mono text-[11px] text-[#5F6470] uppercase">
                    <tr>
                      <th
                        className="cursor-pointer px-3 py-2.5 font-semibold hover:text-[#16181D]"
                        onClick={() => handleSort("question_id")}
                      >
                        ID {sortField === "question_id" && (sortDirection === "asc" ? "▲" : "▼")}
                      </th>
                      <th
                        className="cursor-pointer px-3 py-2.5 font-semibold hover:text-[#16181D]"
                        onClick={() => handleSort("dimension")}
                      >
                        Dimension {sortField === "dimension" && (sortDirection === "asc" ? "▲" : "▼")}
                      </th>
                      <th className="px-3 py-2.5 font-semibold">Audit Requirement</th>
                      <th className="px-3 py-2.5 font-semibold">Answer</th>
                      <th className="px-3 py-2.5 font-semibold">Expected Rule</th>
                      <th
                        className="cursor-pointer px-3 py-2.5 font-semibold hover:text-[#16181D]"
                        onClick={() => handleSort("weight_value")}
                      >
                        Risk Wt {sortField === "weight_value" && (sortDirection === "asc" ? "▲" : "▼")}
                      </th>
                      <th
                        className="cursor-pointer px-3 py-2.5 font-semibold text-right hover:text-[#16181D]"
                        onClick={() => handleSort("points_lost")}
                      >
                        Points Lost {sortField === "points_lost" && (sortDirection === "asc" ? "▲" : "▼")}
                      </th>
                      <th className="px-3 py-2.5 font-semibold">Citation & Source</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2DDD2]">
                    {filteredAndSortedTrace.length > 0 ? (
                      filteredAndSortedTrace.map((row) => (
                        <tr
                          key={row.question_id}
                          className={`hover:bg-[#F6F3EC]/40 transition-colors ${
                            row.is_critical_fail ? "bg-[#B4382F]/5" : ""
                          }`}
                        >
                          <td className="px-3 py-3 font-mono font-bold text-[#16181D] whitespace-nowrap">
                            {row.question_id}
                            {row.is_critical_fail && (
                              <span className="ml-1.5 rounded bg-[#B4382F] px-1 py-0.2 text-[9px] font-bold text-white uppercase">
                                Fatal
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-3 font-mono text-[11px] text-[#5F6470] whitespace-nowrap">
                            {row.dimension}
                          </td>
                          <td className="px-3 py-3 text-[#16181D] max-w-xs sm:max-w-sm">
                            <span className="line-clamp-2">{row.question_text}</span>
                          </td>
                          <td className="px-3 py-3 font-mono text-[#B4382F] font-semibold whitespace-nowrap">
                            {String(row.user_answer ?? "No")}
                          </td>
                          <td className="px-3 py-3 text-[#5F6470] max-w-xs">
                            <span className="font-mono text-[11px]">{row.expected_rule}</span>
                          </td>
                          <td className="px-3 py-3 whitespace-nowrap">
                            <span
                              className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                                row.risk_weight === "CRITICAL"
                                  ? "bg-[#B4382F]/10 text-[#B4382F]"
                                  : row.risk_weight === "HIGH"
                                  ? "bg-[#B7791F]/10 text-[#B7791F]"
                                  : "bg-[#5F6470]/10 text-[#5F6470]"
                              }`}
                            >
                              {row.risk_weight} ({row.weight_value})
                            </span>
                          </td>
                          <td className="px-3 py-3 text-right font-mono font-bold text-[#B4382F] whitespace-nowrap">
                            -{row.points_lost}
                          </td>
                          <td className="px-3 py-3 font-mono text-[10px] text-[#5F6470] whitespace-nowrap">
                            {row.source_doc ? (
                              <div>
                                <span className="font-semibold text-[#16181D]">{row.source_doc}</span>
                                {row.source_ref && <span> &bull; {row.source_ref}</span>}
                              </div>
                            ) : (
                              <span className="italic">Self-attested</span>
                            )}
                          </td>
                        </tr>
                      ))
                    ) : (
                      <tr>
                        <td colSpan={8} className="py-8 text-center text-xs text-[#5F6470]">
                          {report.trace_rows.length === 0
                            ? "No deductions found — all evaluated questions passed with zero points lost!"
                            : "No deductions matching current filters."}
                        </td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 2: REMEDIATION ROADMAP BOARD (PRD 9.1 & FR-8)                          */}
        {/* ========================================================================= */}
        {activeTab === "roadmap" && (
          <div className="space-y-6 animate-fadeIn">
            {/* Roadmap Header Summary */}
            <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-5 shadow-xs">
              <div>
                <h2 className="font-serif text-lg font-bold text-[#16181D]">
                  Diligence Remediation Roadmap
                </h2>
                <p className="mt-1 text-xs text-[#5F6470]">
                  Ordered within execution horizon buckets by{" "}
                  <strong className="text-[#16181D]">priority score (weight &times; points lost)</strong>. Playbook actions derived strictly from vetted question bank.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-4">
                <div className="flex items-center gap-2 border-r border-[#E2DDD2] pr-4">
                  <span className="font-mono text-xs text-[#5F6470]">Total Tasks:</span>
                  <span className="font-mono text-sm font-bold text-[#16181D]">
                    {roadmap?.summary?.total_tasks ?? 0}
                  </span>
                </div>
                <div className="flex items-center gap-2 border-r border-[#E2DDD2] pr-4">
                  <span className="font-mono text-xs text-[#5F6470]">Recoverable Points:</span>
                  <span className="font-mono text-sm font-bold text-[#2F7D57]">
                    +{roadmap?.summary?.total_points_recoverable ?? 0} pts
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-xs text-[#5F6470]">View:</span>
                  <button
                    onClick={() => setRoadmapViewMode("lanes")}
                    className={`rounded px-2.5 py-1 font-mono text-xs font-semibold ${
                      roadmapViewMode === "lanes"
                        ? "bg-[#1F4D3F] text-white"
                        : "bg-[#F6F3EC] text-[#5F6470]"
                    }`}
                  >
                    4 Horizon Lanes
                  </button>
                  <button
                    onClick={() => setRoadmapViewMode("clusters")}
                    className={`rounded px-2.5 py-1 font-mono text-xs font-semibold ${
                      roadmapViewMode === "clusters"
                        ? "bg-[#1F4D3F] text-white"
                        : "bg-[#F6F3EC] text-[#5F6470]"
                    }`}
                  >
                    Root-Cause Clusters
                  </button>
                </div>
              </div>
            </div>

            {/* VIEW 1: 4 HORIZON LANES KANBAN BOARD */}
            {roadmapViewMode === "lanes" && (
              <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-4">
                {[
                  { days: 30, title: "30-Day Immediate", subtitle: "Blockers & Fast Fixes", color: "#B4382F" },
                  { days: 60, title: "60-Day Near-Term", subtitle: "Operational Policies", color: "#B7791F" },
                  { days: 90, title: "90-Day Medium-Term", subtitle: "Governance & Cadence", color: "#1F4D3F" },
                  { days: 180, title: "180-Day Structural", subtitle: "Architecture & Audits", color: "#5F6470" },
                ].map(({ days, title, subtitle, color }) => {
                  const tasks = roadmap?.buckets[days] || roadmap?.buckets[String(days)] || [];
                  const recoverablePts = tasks.reduce((sum, t) => sum + (t.points_recoverable || 0), 0);

                  return (
                    <div
                      key={days}
                      className="flex flex-col rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] shadow-xs overflow-hidden"
                    >
                      {/* Lane Header */}
                      <div className="border-b border-[#E2DDD2] bg-[#F6F3EC] p-4">
                        <div className="flex items-center justify-between">
                          <span
                            className="font-mono text-xs font-bold uppercase tracking-wider"
                            style={{ color }}
                          >
                            {title}
                          </span>
                          <span className="rounded-full bg-[#FFFFFF] border border-[#E2DDD2] px-2 py-0.5 font-mono text-[11px] font-semibold text-[#16181D]">
                            {tasks.length}
                          </span>
                        </div>
                        <div className="mt-1 flex items-center justify-between text-[11px] text-[#5F6470]">
                          <span>{subtitle}</span>
                          <span className="font-mono font-medium text-[#2F7D57]">
                            +{recoverablePts.toFixed(1)} pts
                          </span>
                        </div>
                      </div>

                      {/* Lane Task Cards */}
                      <div className="flex-1 space-y-3 p-3 overflow-y-auto max-h-[700px] bg-[#F6F3EC]/20">
                        {tasks.length > 0 ? (
                          tasks.map((task) => {
                            const isDone = task.status === "done";
                            return (
                              <div
                                key={task.id}
                                onClick={() => {
                                  setActiveDrawerTask(task);
                                  setAssigneeInput(task.assignee || "");
                                }}
                                className={`cursor-pointer rounded-lg border p-3.5 transition-all hover:shadow-md hover:border-[#1F4D3F] bg-[#FFFFFF] ${
                                  isDone
                                    ? "border-[#2F7D57]/40 bg-[#2F7D57]/5 opacity-80"
                                    : "border-[#E2DDD2]"
                                }`}
                              >
                                <div className="flex items-start justify-between gap-2">
                                  <span className="font-mono text-[10px] font-bold text-[#5F6470]">
                                    [{task.question_id}]
                                  </span>
                                  <div className="flex items-center gap-1.5">
                                    <span
                                      className={`rounded px-1.5 py-0.5 font-mono text-[9px] font-bold uppercase ${
                                        task.risk_weight === "CRITICAL"
                                          ? "bg-[#B4382F]/10 text-[#B4382F]"
                                          : task.risk_weight === "HIGH"
                                          ? "bg-[#B7791F]/10 text-[#B7791F]"
                                          : "bg-[#5F6470]/10 text-[#5F6470]"
                                      }`}
                                    >
                                      {task.risk_weight}
                                    </span>
                                    <span className="rounded bg-[#2F7D57]/10 px-1.5 py-0.5 font-mono text-[10px] font-bold text-[#2F7D57]">
                                      +{task.points_recoverable} pts
                                    </span>
                                  </div>
                                </div>

                                <h4
                                  className={`mt-2 font-serif text-xs font-semibold leading-snug text-[#16181D] ${
                                    isDone ? "line-through text-[#5F6470]" : ""
                                  }`}
                                >
                                  {task.title}
                                </h4>

                                <p className="mt-1 text-[11px] text-[#5F6470] line-clamp-2 leading-relaxed">
                                  {task.description}
                                </p>

                                <div className="mt-3 pt-2.5 border-t border-[#E2DDD2]/60 flex items-center justify-between text-[10px] font-mono text-[#5F6470]">
                                  <span className="rounded bg-[#F6F3EC] px-1.5 py-0.5">
                                    {task.dimension}
                                  </span>

                                  <div className="flex items-center gap-2">
                                    {task.assignee && (
                                      <span className="font-sans font-medium text-[#1F4D3F] line-clamp-1 max-w-[80px]">
                                        👤 {task.assignee}
                                      </span>
                                    )}
                                    {task.comments && task.comments.length > 0 && (
                                      <span>💬 {task.comments.length}</span>
                                    )}
                                    {isDone ? (
                                      <span className="rounded bg-[#2F7D57] px-1.5 py-0.2 text-[9px] font-bold text-white uppercase">
                                        Done
                                      </span>
                                    ) : (
                                      <span className="rounded bg-[#E2DDD2] px-1.5 py-0.2 text-[9px] font-semibold text-[#16181D]">
                                        Todo
                                      </span>
                                    )}
                                  </div>
                                </div>
                              </div>
                            );
                          })
                        ) : (
                          <div className="p-8 text-center text-xs text-[#5F6470] italic">
                            No tasks scheduled in this horizon.
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}

            {/* VIEW 2: ROOT-CAUSE CLUSTERS */}
            {roadmapViewMode === "clusters" && (
              <div className="space-y-4">
                {roadmap?.groups && roadmap.groups.length > 0 ? (
                  roadmap.groups.map((group) => (
                    <div
                      key={group.group_key}
                      className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-5 shadow-xs"
                    >
                      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-[#E2DDD2] pb-3">
                        <div>
                          <span className="font-mono text-xs text-[#1F4D3F] font-bold uppercase tracking-wider">
                            {group.dimension}
                          </span>
                          <h3 className="font-serif text-base font-bold text-[#16181D]">
                            Root Cause: {group.sub_category}
                          </h3>
                        </div>
                        <div className="flex items-center gap-3 font-mono text-xs">
                          <span className="rounded-md bg-[#F6F3EC] px-2.5 py-1 text-[#5F6470]">
                            {group.task_count} linked tasks
                          </span>
                          <span className="rounded-md bg-[#2F7D57]/10 px-2.5 py-1 font-bold text-[#2F7D57]">
                            +{group.total_points_recoverable} pts recoverable
                          </span>
                        </div>
                      </div>

                      <div className="mt-4 grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
                        {group.tasks.map((task) => (
                          <div
                            key={task.id}
                            onClick={() => {
                              setActiveDrawerTask(task);
                              setAssigneeInput(task.assignee || "");
                            }}
                            className="cursor-pointer rounded-lg border border-[#E2DDD2] p-3 hover:border-[#1F4D3F] transition-all bg-[#F6F3EC]/30"
                          >
                            <div className="flex items-center justify-between text-[10px] font-mono">
                              <span className="font-bold text-[#16181D]">[{task.question_id}]</span>
                              <span className="font-bold text-[#2F7D57]">+{task.points_recoverable} pts</span>
                            </div>
                            <h5 className="mt-1 font-serif text-xs font-semibold text-[#16181D] line-clamp-1">
                              {task.title}
                            </h5>
                            <p className="mt-1 text-[11px] text-[#5F6470] line-clamp-2">
                              {task.description}
                            </p>
                            <div className="mt-2 flex items-center justify-between text-[10px] font-mono text-[#5F6470]">
                              <span>{task.horizon_days}d Horizon</span>
                              <span>{task.status.toUpperCase()}</span>
                            </div>
                          </div>
                        ))}
                      </div>
                    </div>
                  ))
                ) : (
                  <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-8 text-center text-xs text-[#5F6470]">
                    No root-cause clusters available.
                  </div>
                )}
              </div>
            )}
          </div>
        )}

        {/* ========================================================================= */}
        {/* TAB 3: RE-ASSESSMENT DELTA VIEW (PRD 9.3)                                  */}
        {/* ========================================================================= */}
        {activeTab === "delta" && (
          <div className="space-y-6 animate-fadeIn">
            {delta?.is_initial_assessment ? (
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-8 text-center shadow-xs">
                <div className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-[#1F4D3F]/10 text-[#1F4D3F]">
                  <svg className="h-6 w-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
                  </svg>
                </div>
                <h3 className="mt-4 font-serif text-lg font-bold text-[#16181D]">
                  Initial Score Run Recorded
                </h3>
                <p className="mx-auto mt-2 max-w-lg text-xs text-[#5F6470]">
                  This assessment represents the baseline audit benchmark. As you resolve roadmap items and provide verified materials in the questionnaire workspace, trigger a re-assessment to compare historical score movements, dimension shifts, and resolved risk items.
                </p>
                <div className="mt-6">
                  <button
                    onClick={() => loadAllData(true)}
                    disabled={recalculating}
                    className="inline-flex items-center gap-2 rounded-lg bg-[#1F4D3F] px-4 py-2 font-mono text-xs font-medium text-white hover:bg-[#17392F]"
                  >
                    Snapshot Re-assessment Run
                  </button>
                </div>
              </div>
            ) : delta ? (
              <div className="space-y-6">
                {/* Movement Metrics Cards */}
                <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
                  <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-5 shadow-xs">
                    <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                      Score Delta
                    </span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span
                        className={`font-serif text-3xl font-bold ${
                          delta.overall_score_delta > 0
                            ? "text-[#2F7D57]"
                            : delta.overall_score_delta < 0
                            ? "text-[#B4382F]"
                            : "text-[#16181D]"
                        }`}
                      >
                        {delta.overall_score_delta > 0 ? `+${delta.overall_score_delta}` : delta.overall_score_delta}
                      </span>
                      <span className="font-mono text-xs text-[#5F6470]">pts movement</span>
                    </div>
                  </div>

                  <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-5 shadow-xs">
                    <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                      Unconstrained Delta
                    </span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="font-serif text-3xl font-bold text-[#16181D]">
                        {delta.unconstrained_score_delta > 0
                          ? `+${delta.unconstrained_score_delta}`
                          : delta.unconstrained_score_delta}
                      </span>
                      <span className="font-mono text-xs text-[#5F6470]">raw shift</span>
                    </div>
                  </div>

                  <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-5 shadow-xs">
                    <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                      Completeness Delta
                    </span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="font-serif text-3xl font-bold text-[#1F4D3F]">
                        {delta.completeness_delta > 0 ? `+${delta.completeness_delta}` : delta.completeness_delta}%
                      </span>
                      <span className="font-mono text-xs text-[#5F6470]">evidence coverage</span>
                    </div>
                  </div>

                  <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-5 shadow-xs">
                    <span className="font-mono text-[11px] uppercase tracking-wider text-[#5F6470]">
                      Resolved to Pass
                    </span>
                    <div className="mt-2 flex items-baseline gap-2">
                      <span className="font-serif text-3xl font-bold text-[#2F7D57]">
                        {delta.total_flipped_to_pass}
                      </span>
                      <span className="font-mono text-xs text-[#5F6470]">items fixed</span>
                    </div>
                  </div>
                </div>

                {/* Critical Cap Status Callout */}
                {delta.critical_cap_status.cap_lifted && (
                  <div className="rounded-xl border border-[#2F7D57]/40 bg-[#2F7D57]/5 p-4 text-xs text-[#2F7D57]">
                    <strong>FATAL RISK CAP LIFTED:</strong> The critical deal-breaker cap has been successfully removed in this score run!
                  </div>
                )}

                {/* Dimension Comparison Table */}
                <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] shadow-xs overflow-hidden">
                  <div className="p-5 border-b border-[#E2DDD2]">
                    <h3 className="font-serif text-base font-bold text-[#16181D]">
                      Per-Dimension Movement
                    </h3>
                    <p className="mt-1 text-xs text-[#5F6470]">
                      Score deltas across individual diligence dimensions between consecutive runs.
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-sans text-xs">
                      <thead className="border-b border-[#E2DDD2] bg-[#F6F3EC] font-mono text-[11px] text-[#5F6470] uppercase">
                        <tr>
                          <th className="px-4 py-2.5">Dimension</th>
                          <th className="px-4 py-2.5">Previous Run</th>
                          <th className="px-4 py-2.5">Current Run</th>
                          <th className="px-4 py-2.5 text-right">Movement</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#E2DDD2]">
                        {delta.dimension_deltas.map((dim) => (
                          <tr key={dim.dimension} className="hover:bg-[#F6F3EC]/30">
                            <td className="px-4 py-3 font-medium text-[#16181D]">
                              {DIMENSION_NAMES[dim.dimension] || dim.dimension}
                            </td>
                            <td className="px-4 py-3 font-mono text-[#5F6470]">
                              {dim.previous_score !== null ? `${dim.previous_score}%` : "—"}
                            </td>
                            <td className="px-4 py-3 font-mono font-bold text-[#16181D]">
                              {dim.current_score !== null ? `${dim.current_score}%` : "—"}
                            </td>
                            <td className="px-4 py-3 text-right font-mono font-bold">
                              <span
                                className={`rounded px-2 py-0.5 ${
                                  dim.delta > 0
                                    ? "bg-[#2F7D57]/10 text-[#2F7D57]"
                                    : dim.delta < 0
                                    ? "bg-[#B4382F]/10 text-[#B4382F]"
                                    : "text-[#5F6470]"
                                }`}
                              >
                                {dim.delta > 0 ? `+${dim.delta}%` : `${dim.delta}%`}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>

                {/* Items Flipped from FAIL/PARTIAL to PASS Table */}
                <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] shadow-xs overflow-hidden">
                  <div className="p-5 border-b border-[#E2DDD2]">
                    <h3 className="font-serif text-base font-bold text-[#2F7D57]">
                      Items Flipped to PASS ({delta.total_flipped_to_pass})
                    </h3>
                    <p className="mt-1 text-xs text-[#5F6470]">
                      Questions where evidence was remediated, resolving previous diligence deductions.
                    </p>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left font-sans text-xs">
                      <thead className="border-b border-[#E2DDD2] bg-[#F6F3EC] font-mono text-[11px] text-[#5F6470] uppercase">
                        <tr>
                          <th className="px-4 py-2.5">ID</th>
                          <th className="px-4 py-2.5">Dimension</th>
                          <th className="px-4 py-2.5">Requirement</th>
                          <th className="px-4 py-2.5">State Transition</th>
                          <th className="px-4 py-2.5 text-right">Points Recovered</th>
                          <th className="px-4 py-2.5">Source</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-[#E2DDD2]">
                        {delta.flipped_items.length > 0 ? (
                          delta.flipped_items.map((item) => (
                            <tr key={item.question_id} className="hover:bg-[#F6F3EC]/30">
                              <td className="px-4 py-3 font-mono font-bold text-[#16181D]">
                                {item.question_id}
                              </td>
                              <td className="px-4 py-3 font-mono text-[11px] text-[#5F6470]">
                                {item.dimension}
                              </td>
                              <td className="px-4 py-3 text-[#16181D] max-w-sm">
                                {item.question_text}
                              </td>
                              <td className="px-4 py-3 font-mono text-xs">
                                <span className="text-[#B4382F]">{item.previous_state}</span>
                                <span className="text-[#5F6470]"> &rarr; </span>
                                <span className="font-bold text-[#2F7D57]">{item.current_state}</span>
                              </td>
                              <td className="px-4 py-3 text-right font-mono font-bold text-[#2F7D57]">
                                +{item.points_recovered} pts
                              </td>
                              <td className="px-4 py-3 font-mono text-[10px] text-[#5F6470]">
                                {item.source_doc ? `${item.source_doc} ${item.source_ref || ""}` : "Attested"}
                              </td>
                            </tr>
                          ))
                        ) : (
                          <tr>
                            <td colSpan={6} className="py-6 text-center text-xs text-[#5F6470] italic">
                              No items flipped between these two score runs.
                            </td>
                          </tr>
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              </div>
            ) : null}
          </div>
        )}

        {/* ========================================================================= */}
        {/* ROADMAP TASK DETAIL DRAWER (Overlay Modal / Slide-over)                    */}
        {/* ========================================================================= */}
        {activeDrawerTask && (
          <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/40 backdrop-blur-xs">
            <div className="h-full w-full max-w-lg bg-[#FFFFFF] border-l border-[#E2DDD2] p-6 shadow-2xl overflow-y-auto flex flex-col justify-between">
              <div>
                {/* Drawer Header */}
                <div className="flex items-start justify-between border-b border-[#E2DDD2] pb-4">
                  <div>
                    <span className="font-mono text-xs font-bold text-[#1F4D3F]">
                      [{activeDrawerTask.question_id}] &bull; {activeDrawerTask.horizon_days}-Day Horizon
                    </span>
                    <h3 className="mt-1 font-serif text-lg font-bold text-[#16181D]">
                      {activeDrawerTask.title}
                    </h3>
                  </div>
                  <button
                    onClick={() => setActiveDrawerTask(null)}
                    className="rounded-lg p-1.5 text-[#5F6470] hover:bg-[#F6F3EC] hover:text-[#16181D]"
                  >
                    <svg className="h-5 w-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>

                {/* Score Independence Warning */}
                <div className="mt-4 rounded-lg border border-[#B7791F]/30 bg-[#B7791F]/5 p-3 text-[11px] text-[#B7791F]">
                  <strong>Operational Progress Only:</strong> Marking tasks as done tracks team execution. Per PRD Section 9.1, task status does <em>not</em> modify readiness scores until supporting evidence is updated in the workspace and re-assessed.
                </div>

                {/* Status Toggle & Points */}
                <div className="mt-4 flex items-center justify-between rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/40 p-3">
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id="taskDoneToggle"
                      checked={activeDrawerTask.status === "done"}
                      onChange={(e) =>
                        handleUpdateTask(activeDrawerTask.id, {
                          status: e.target.checked ? "done" : "todo",
                        })
                      }
                      className="h-4 w-4 rounded border-[#E2DDD2] text-[#2F7D57] focus:ring-[#1F4D3F]"
                    />
                    <label htmlFor="taskDoneToggle" className="cursor-pointer font-mono text-xs font-semibold text-[#16181D]">
                      {activeDrawerTask.status === "done" ? "Status: Completed (Done)" : "Status: In Progress / Todo"}
                    </label>
                  </div>
                  <span className="rounded bg-[#2F7D57]/10 px-2 py-0.5 font-mono text-xs font-bold text-[#2F7D57]">
                    +{activeDrawerTask.points_recoverable} pts
                  </span>
                </div>

                {/* Metadata Chips */}
                <div className="mt-4 flex flex-wrap gap-2 font-mono text-[10px]">
                  <span className="rounded bg-[#F6F3EC] px-2 py-1 text-[#5F6470]">
                    Dimension: {activeDrawerTask.dimension}
                  </span>
                  <span className="rounded bg-[#F6F3EC] px-2 py-1 text-[#5F6470]">
                    Root Cause: {activeDrawerTask.sub_category}
                  </span>
                  <span className="rounded bg-[#F6F3EC] px-2 py-1 text-[#5F6470]">
                    Severity: {activeDrawerTask.risk_weight}
                  </span>
                </div>

                {/* Playbook Text */}
                <div className="mt-5">
                  <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-[#1F4D3F]">
                    Playbook Remediation Action
                  </h4>
                  <div className="mt-2 rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 p-3.5 text-xs text-[#16181D] leading-relaxed">
                    {activeDrawerTask.description}
                  </div>
                </div>

                {/* Source Citation */}
                <div className="mt-4">
                  <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-[#5F6470]">
                    Audit Citation & Authority
                  </h4>
                  <p className="mt-1 font-mono text-xs text-[#16181D]">
                    {activeDrawerTask.source_doc ? (
                      <>
                        <strong className="text-[#1F4D3F]">{activeDrawerTask.source_doc}</strong>
                        {activeDrawerTask.source_ref && <span> &bull; {activeDrawerTask.source_ref}</span>}
                      </>
                    ) : (
                      "Universal diligence benchmark requirement"
                    )}
                  </p>
                </div>

                {/* Assignee Input */}
                <div className="mt-5 border-t border-[#E2DDD2] pt-4">
                  <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-[#16181D]">
                    Assign Ownership
                  </h4>
                  <div className="mt-2 flex gap-2">
                    <input
                      type="text"
                      placeholder="e.g. Legal Lead (alice@company.com)"
                      value={assigneeInput}
                      onChange={(e) => setAssigneeInput(e.target.value)}
                      className="flex-1 rounded-lg border border-[#E2DDD2] px-3 py-1.5 font-mono text-xs text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden"
                    />
                    <button
                      onClick={() => handleUpdateTask(activeDrawerTask.id, { assignee: assigneeInput })}
                      disabled={updatingTask}
                      className="rounded-lg bg-[#1F4D3F] px-3 py-1.5 font-mono text-xs font-medium text-white hover:bg-[#17392F]"
                    >
                      Save
                    </button>
                  </div>
                </div>

                {/* Comments Thread */}
                <div className="mt-5 border-t border-[#E2DDD2] pt-4">
                  <h4 className="font-mono text-xs font-bold uppercase tracking-wider text-[#16181D]">
                    Activity & Audit Notes ({activeDrawerTask.comments?.length || 0})
                  </h4>

                  <div className="mt-3 space-y-2.5 max-h-48 overflow-y-auto">
                    {activeDrawerTask.comments && activeDrawerTask.comments.length > 0 ? (
                      activeDrawerTask.comments.map((c) => (
                        <div key={c.id} className="rounded-lg bg-[#F6F3EC]/50 p-2.5 text-xs">
                          <div className="flex items-center justify-between text-[10px] font-mono text-[#5F6470]">
                            <span className="font-bold text-[#16181D]">{c.author}</span>
                            <span>{new Date(c.created_at).toLocaleDateString()}</span>
                          </div>
                          <p className="mt-1 text-[#16181D]">{c.text}</p>
                        </div>
                      ))
                    ) : (
                      <p className="text-[11px] text-[#5F6470] italic">No notes posted yet.</p>
                    )}
                  </div>

                  <div className="mt-3 flex gap-2">
                    <input
                      type="text"
                      placeholder="Add an operational note or status update..."
                      value={commentInput}
                      onChange={(e) => setCommentInput(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter" && commentInput.trim()) {
                          handleUpdateTask(activeDrawerTask.id, { comment: commentInput });
                        }
                      }}
                      className="flex-1 rounded-lg border border-[#E2DDD2] px-3 py-1.5 font-mono text-xs text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden"
                    />
                    <button
                      onClick={() => handleUpdateTask(activeDrawerTask.id, { comment: commentInput })}
                      disabled={updatingTask || !commentInput.trim()}
                      className="rounded-lg bg-[#16181D] px-3 py-1.5 font-mono text-xs font-medium text-white hover:bg-black disabled:opacity-50"
                    >
                      Post
                    </button>
                  </div>
                </div>
              </div>

              {/* Close Drawer Button */}
              <div className="mt-6 pt-4 border-t border-[#E2DDD2]">
                <button
                  onClick={() => setActiveDrawerTask(null)}
                  className="w-full rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] py-2 font-mono text-xs font-semibold text-[#16181D] hover:bg-[#F6F3EC]"
                >
                  Close Drawer
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Statutory Legal Disclaimer (PRD Section 1) */}
        <footer className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-4 text-center text-xs text-[#5F6470]">
          <p>
            <em>
              &ldquo;This is a readiness assessment based on the information provided. It is not legal, financial, or investment advice and does not predict transaction outcomes.&rdquo;
            </em>
          </p>
        </footer>
      </main>
    </div>
  );
}
