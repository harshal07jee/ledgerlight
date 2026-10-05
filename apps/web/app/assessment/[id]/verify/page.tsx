"use client";

/**
 * Extraction Verification Workspace (PRD Section 7.4 & FR-4).
 * 
 * Features:
 * - Evidence viewer highlighting source snippet (<= 500 chars) and page number.
 * - Explicit formula and inputs viewer for FINANCIAL_TABLE extractions.
 * - Strict labeling: says "Document found", NEVER "compliant" for certificates/policies.
 * - Interactive Confirm / Edit / Reject buttons.
 * - Bulk Confirm button for AUTO_FILLED / high confidence extractions.
 * - Honest extraction coverage metric banner (no rounding up).
 * 
 * Marked 21st.dev Slots:
 * <!-- 21ST_DEV_SLOT: sheet-drawer (https://21st.dev/s/sheet-drawer) -->
 * <!-- 21ST_DEV_SLOT: verification-card (https://21st.dev/s/card) -->
 * <!-- 21ST_DEV_SLOT: metric-badge (https://21st.dev/s/badge) -->
 */

import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavigationMenu } from "@/components/ui-21st/navigation-menu";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface ExtractionItem {
  id: string;
  question_id: string;
  document_id?: string;
  answer_value: any;
  confidence: number;
  status: "AUTO_FILLED" | "NEEDS_CONFIRMATION" | "MANUAL_REQUIRED";
  method: string;
  source_file?: string;
  page?: number;
  char_start?: number;
  char_end?: number;
  snippet?: string;
  formula?: string;
  formula_inputs?: Record<string, any>;
  user_action: "pending" | "confirmed" | "rejected";
  confirmed_value?: any;
  created_at: string;
  updated_at: string;
}

interface CoverageData {
  total_applicable_questions: number;
  total_scored_questions: number;
  auto_extractable_count: number;
  auto_extractable_pct: number;
  manual_required_count: number;
  manual_required_pct: number;
  breakdown_by_method: Record<string, number>;
  cuad_model_status: string;
}

export default function VerificationWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = params?.id as string;

  const [extractions, setExtractions] = useState<ExtractionItem[]>([]);
  const [coverage, setCoverage] = useState<CoverageData | null>(null);
  const [loading, setLoading] = useState(true);
  const [filterStatus, setFilterStatus] = useState<string>("ALL");
  const [editingValues, setEditingValues] = useState<Record<string, any>>({});
  const [activeEvidenceExt, setActiveEvidenceExt] = useState<ExtractionItem | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  const getAuthHeaders = useCallback(() => {
    const token = typeof window !== "undefined" ? (localStorage.getItem("ledgerlight_token") || "demo-token-founder") : "demo-token-founder";
    return {
      "Content-Type": "application/json",
      Authorization: `Bearer ${token}`,
    };
  }, []);

  const fetchData = useCallback(async () => {
    try {
      setLoading(true);

      // Fetch extractions
      const extRes = await fetch(`${API_BASE}/assessments/${assessmentId}/extractions`, {
        headers: getAuthHeaders(),
        credentials: "include",
      });
      if (extRes.ok) {
        const extData = await extRes.json();
        const items: ExtractionItem[] = extData.extractions || [];
        setExtractions(items);

        // Initialize editing values
        const initialEditVals: Record<string, any> = {};
        items.forEach((item) => {
          initialEditVals[item.id] =
            item.confirmed_value !== null && item.confirmed_value !== undefined
              ? item.confirmed_value
              : item.answer_value;
        });
        setEditingValues(initialEditVals);
      }

      // Fetch honest coverage report
      const covRes = await fetch(`${API_BASE}/assessments/${assessmentId}/extraction-coverage`, {
        headers: getAuthHeaders(),
        credentials: "include",
      });
      if (covRes.ok) {
        const covData = await covRes.json();
        setCoverage(covData.coverage || null);
      }
    } catch (err) {
      console.error("Failed to load verification data", err);
    } finally {
      setLoading(false);
    }
  }, [assessmentId, getAuthHeaders]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  const handleConfirmExtraction = async (extId: string) => {
    try {
      const val = editingValues[extId];
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/extractions/${extId}/confirm`, {
        method: "POST",
        headers: getAuthHeaders(),
        credentials: "include",
        body: JSON.stringify({ confirmed_value: val }),
      });
      if (res.ok) {
        setExtractions((prev) =>
          prev.map((e) =>
            e.id === extId ? { ...e, user_action: "confirmed", confirmed_value: val } : e
          )
        );
        setActionMessage(`Confirmed answer for ${extractions.find((e) => e.id === extId)?.question_id}`);
        setTimeout(() => setActionMessage(null), 3000);
      }
    } catch (err) {
      console.error("Failed to confirm extraction", err);
    }
  };

  const handleRejectExtraction = async (extId: string) => {
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/extractions/${extId}/reject`, {
        method: "POST",
        headers: getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        setExtractions((prev) =>
          prev.map((e) => (e.id === extId ? { ...e, user_action: "rejected" } : e))
        );
        setActionMessage(`Rejected extraction for ${extractions.find((e) => e.id === extId)?.question_id}`);
        setTimeout(() => setActionMessage(null), 3000);
      }
    } catch (err) {
      console.error("Failed to reject extraction", err);
    }
  };

  const handleBulkConfirm = async () => {
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/extractions/bulk-confirm`, {
        method: "POST",
        headers: getAuthHeaders(),
        credentials: "include",
        body: JSON.stringify({ min_confidence: 0.85 }),
      });
      if (res.ok) {
        const result = await res.json();
        setActionMessage(`Bulk confirmed ${result.confirmed_count} high-confidence extraction(s).`);
        setTimeout(() => setActionMessage(null), 4000);
        fetchData();
      }
    } catch (err) {
      console.error("Failed to bulk confirm", err);
    }
  };

  const filteredExtractions = extractions.filter((ext) => {
    if (filterStatus === "NEEDS_CONFIRMATION") return ext.status === "NEEDS_CONFIRMATION";
    if (filterStatus === "AUTO_FILLED") return ext.status === "AUTO_FILLED";
    if (filterStatus === "CONFIRMED") return ext.user_action === "confirmed";
    if (filterStatus === "REJECTED") return ext.user_action === "rejected";
    return true;
  });

  const pendingCount = extractions.filter((e) => e.user_action === "pending").length;
  const highConfPendingCount = extractions.filter(
    (e) => e.user_action === "pending" && e.confidence >= 0.85
  ).length;

  return (
    <div className="min-h-screen bg-[#F6F3EC] text-[#16181D]">
      <NavigationMenu
        rightElement={
          <div className="flex items-center gap-3">
            <Link
              href={`/assessment/${assessmentId}/data-room`}
              className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
            >
              &larr; Data Room
            </Link>
            <Link
              href={`/assessment/${assessmentId}/report`}
              className="rounded-lg bg-[#1F4D3F] px-3.5 py-1.5 font-mono text-xs font-semibold text-white hover:bg-[#17392F] transition-colors shadow-xs"
            >
              View Report &rarr;
            </Link>
          </div>
        }
      />

      {/* Sub-Header Navigation Tabs */}
      <div className="border-b border-[#E2DDD2] bg-[#FFFFFF]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
          <div>
            <h1 className="font-serif text-lg font-semibold text-[#16181D]">
              Verification Workspace
            </h1>
            <p className="text-xs text-[#5F6470]">
              Review deterministic formulas, inspect evidence snippets, and confirm answers.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href={`/assessment/${assessmentId}`}
              className="rounded-lg px-3 py-1.5 font-mono text-xs text-[#5F6470] hover:text-[#16181D]"
            >
              Questionnaire
            </Link>
            <Link
              href={`/assessment/${assessmentId}/data-room`}
              className="rounded-lg px-3 py-1.5 font-mono text-xs text-[#5F6470] hover:text-[#16181D]"
            >
              Data Room
            </Link>
            <span className="rounded-lg bg-[#1F4D3F]/10 px-3 py-1.5 font-mono text-xs font-semibold text-[#1F4D3F]">
              Verify Workspace
            </span>
            <Link
              href={`/assessment/${assessmentId}/report`}
              className="rounded-lg px-3 py-1.5 font-mono text-xs text-[#5F6470] hover:text-[#16181D]"
            >
              Readiness Report
            </Link>
          </div>
        </div>
      </div>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {/* Honest Coverage Report Banner */}
        {coverage && (
          <div className="mb-8 rounded-2xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div>
                <span className="font-mono text-[11px] font-semibold uppercase tracking-wider text-[#1F4D3F]">
                  Diligence Automation Coverage (M5)
                </span>
                <h2 className="mt-1 font-serif text-base font-semibold text-[#16181D]">
                  {coverage.auto_extractable_count} of {coverage.total_scored_questions} Scored Questions are Auto-Extractable ({coverage.auto_extractable_pct.toFixed(2)}%)
                </h2>
                <p className="mt-1 text-xs text-[#5F6470]">
                  State it honestly; do not round up. {coverage.manual_required_count} questions ({coverage.manual_required_pct.toFixed(2)}%) require manual completion or attestations.
                </p>
              </div>

              <div className="flex items-center gap-3">
                {highConfPendingCount > 0 && (
                  <button
                    type="button"
                    onClick={handleBulkConfirm}
                    className="rounded-lg bg-[#1F4D3F] px-4 py-2 font-mono text-xs font-semibold text-white shadow-xs hover:bg-[#17392F] transition-all"
                  >
                    Bulk Confirm ({highConfPendingCount}) High-Confidence &rarr;
                  </button>
                )}
              </div>
            </div>

            {/* Method Breakdown Chips */}
            <div className="mt-4 flex flex-wrap items-center gap-2 border-t border-[#E2DDD2] pt-4">
              <span className="font-mono text-xs font-medium text-[#5F6470]">Coverage by Method:</span>
              <span className="rounded-md bg-[#F6F3EC] px-2.5 py-1 font-mono text-xs text-[#16181D]">
                Financial Tables: {coverage.breakdown_by_method.FINANCIAL_TABLE || 0}
              </span>
              <span className="rounded-md bg-[#F6F3EC] px-2.5 py-1 font-mono text-xs text-[#16181D]">
                Certificates / Reports: {coverage.breakdown_by_method.CERTIFICATE_OR_REPORT || 0}
              </span>
              <span className="rounded-md bg-[#F6F3EC] px-2.5 py-1 font-mono text-xs text-[#16181D]">
                Policy Documents: {coverage.breakdown_by_method.POLICY_DOC || 0}
              </span>
              <span className="rounded-md bg-[#F6F3EC] px-2.5 py-1 font-mono text-xs text-[#5F6470]">
                Contracts (CUAD Pending): {coverage.breakdown_by_method.CONTRACT_CLAUSE || 0}
              </span>
              <span className="rounded-md bg-[#F6F3EC] px-2.5 py-1 font-mono text-xs text-[#5F6470]">
                Self-Attested: {coverage.breakdown_by_method.SELF_ATTESTED || 0}
              </span>
            </div>
          </div>
        )}

        {actionMessage && (
          <div className="mb-6 rounded-xl border border-[#2F7D57]/30 bg-[#E8F0EC] p-3 text-sm text-[#1F4D3F] transition-all">
            {actionMessage}
          </div>
        )}

        {/* Filter Tabs */}
        <div className="mb-6 flex flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-1.5 rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-1 shadow-xs">
            {["ALL", "NEEDS_CONFIRMATION", "AUTO_FILLED", "CONFIRMED", "REJECTED"].map((tab) => (
              <button
                key={tab}
                type="button"
                onClick={() => setFilterStatus(tab)}
                className={`rounded-lg px-3 py-1.5 font-mono text-xs transition-all ${
                  filterStatus === tab
                    ? "bg-[#1F4D3F] text-white font-semibold shadow-xs"
                    : "text-[#5F6470] hover:text-[#16181D]"
                }`}
              >
                {tab.replace("_", " ")}
              </button>
            ))}
          </div>

          <div className="font-mono text-xs text-[#5F6470]">
            Showing {filteredExtractions.length} of {extractions.length} proposed extraction(s)
          </div>
        </div>

        {/* 21ST_DEV_SLOT: verification-card (https://21st.dev/s/card) */}
        {loading ? (
          <div className="p-12 text-center font-mono text-xs uppercase text-[#5F6470]">
            Loading extraction verification queue...
          </div>
        ) : filteredExtractions.length === 0 ? (
          <div className="rounded-2xl border border-[#E2DDD2] bg-[#FFFFFF] p-12 text-center shadow-xs">
            <div className="font-serif text-sm font-semibold text-[#16181D]">
              No extractions match the selected filter
            </div>
            <p className="mt-1 text-xs text-[#5F6470]">
              Upload more documents in the Data Room to populate extraction proposals.
            </p>
          </div>
        ) : (
          <div className="space-y-4">
            {filteredExtractions.map((ext) => (
              <div
                key={ext.id}
                className={`rounded-2xl border bg-[#FFFFFF] p-6 shadow-xs transition-all ${
                  ext.user_action === "confirmed"
                    ? "border-[#2F7D57]/40 bg-[#FFFFFF]"
                    : ext.user_action === "rejected"
                    ? "border-[#B4382F]/30 opacity-75"
                    : "border-[#E2DDD2]"
                }`}
              >
                <div className="flex flex-wrap items-start justify-between gap-4">
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-[#1F4D3F]">
                        {ext.question_id}
                      </span>

                      {/* 21ST_DEV_SLOT: metric-badge (https://21st.dev/s/badge) */}
                      <span
                        className={`rounded-md px-2 py-0.5 font-mono text-[10px] font-semibold uppercase ${
                          ext.status === "AUTO_FILLED"
                            ? "bg-[#E8F0EC] text-[#1F4D3F]"
                            : ext.status === "NEEDS_CONFIRMATION"
                            ? "bg-[#FEF3D6] text-[#B7791F]"
                            : "bg-[#F6F3EC] text-[#5F6470]"
                        }`}
                      >
                        {ext.status.replace("_", " ")}
                      </span>

                      <span className="rounded-md border border-[#E2DDD2] px-2 py-0.5 font-mono text-[10px] text-[#5F6470]">
                        Method: {ext.method}
                      </span>

                      {ext.user_action === "confirmed" && (
                        <span className="rounded-md bg-[#2F7D57] text-white px-2 py-0.5 font-mono text-[10px] font-bold">
                          CONFIRMED
                        </span>
                      )}

                      {ext.user_action === "rejected" && (
                        <span className="rounded-md bg-[#B4382F] text-white px-2 py-0.5 font-mono text-[10px] font-bold">
                          REJECTED
                        </span>
                      )}
                    </div>

                    <div className="font-serif text-sm font-medium text-[#16181D]">
                      Source Document: {ext.source_file || "Uploaded document"}{" "}
                      {ext.page ? `(Page ${ext.page})` : ""}
                    </div>
                  </div>

                  {/* Confidence meter */}
                  <div className="text-right">
                    <div className="font-mono text-xs text-[#5F6470]">
                      Confidence:{" "}
                      <span
                        className={`font-bold ${
                          ext.confidence >= 0.85
                            ? "text-[#1F4D3F]"
                            : ext.confidence >= 0.5
                            ? "text-[#B7791F]"
                            : "text-[#B4382F]"
                        }`}
                      >
                        {(ext.confidence * 100).toFixed(0)}%
                      </span>
                    </div>
                    <div className="mt-1 text-[11px] text-[#5F6470]">
                      {ext.confidence === 1.0
                        ? "All formula cells verified"
                        : "Requires human verification"}
                    </div>
                  </div>
                </div>

                {/* Mathematical Formula (Financial Tables) */}
                {ext.formula && (
                  <div className="mt-4 rounded-xl border border-[#1F4D3F]/20 bg-[#1F4D3F]/5 p-3.5 text-xs">
                    <div className="font-mono text-[11px] font-semibold uppercase text-[#1F4D3F]">
                      Deterministic Formula:
                    </div>
                    <div className="mt-1 font-mono text-xs font-bold text-[#16181D]">
                      {ext.formula}
                    </div>
                    {ext.formula_inputs && (
                      <div className="mt-2 flex flex-wrap gap-3 font-mono text-[11px] text-[#5F6470]">
                        {Object.entries(ext.formula_inputs).map(([k, v]) => (
                          <span key={k} className="rounded bg-[#FFFFFF] px-2 py-0.5 border border-[#E2DDD2]">
                            {k}: <span className="font-semibold text-[#16181D]">{v !== null ? v : "Not found"}</span>
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                )}

                {/* Evidence Snippet Viewer */}
                {ext.snippet && (
                  <div className="mt-4 rounded-xl border border-[#E2DDD2] bg-[#F6F3EC]/60 p-3.5 text-xs">
                    <div className="flex items-center justify-between">
                      <div className="font-mono text-[11px] font-semibold text-[#5F6470] uppercase">
                        Source Evidence Snippet (Max 500 chars):
                      </div>
                      <button
                        type="button"
                        onClick={() => setActiveEvidenceExt(ext)}
                        className="font-mono text-[11px] text-[#1F4D3F] hover:underline"
                      >
                        Inspect Drawer &rarr;
                      </button>
                    </div>
                    <p className="mt-1.5 text-xs text-[#16181D] leading-relaxed italic">
                      &ldquo;{ext.snippet}&rdquo;
                    </p>
                  </div>
                )}

                {/* Editable Value and Action Controls */}
                <div className="mt-5 flex flex-wrap items-center justify-between gap-4 border-t border-[#E2DDD2] pt-4">
                  <div className="flex items-center gap-3">
                    <label className="font-mono text-xs text-[#5F6470]">
                      Proposed Answer Value:
                    </label>
                    <input
                      type="text"
                      value={editingValues[ext.id] ?? ""}
                      onChange={(e) =>
                        setEditingValues((prev) => ({
                          ...prev,
                          [ext.id]: e.target.value,
                        }))
                      }
                      className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs font-semibold text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden"
                    />
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => handleRejectExtraction(ext.id)}
                      disabled={ext.user_action === "rejected"}
                      className={`rounded-lg border px-3.5 py-1.5 font-mono text-xs transition-colors ${
                        ext.user_action === "rejected"
                          ? "border-[#B4382F] bg-[#B4382F] text-white"
                          : "border-[#E2DDD2] bg-[#FFFFFF] text-[#B4382F] hover:bg-[#FDF2F1]"
                      }`}
                    >
                      Reject
                    </button>

                    <button
                      type="button"
                      onClick={() => handleConfirmExtraction(ext.id)}
                      className={`rounded-lg px-4 py-1.5 font-mono text-xs font-semibold transition-all shadow-xs ${
                        ext.user_action === "confirmed"
                          ? "bg-[#2F7D57] text-white"
                          : "bg-[#1F4D3F] text-white hover:bg-[#17392F]"
                      }`}
                    >
                      {ext.user_action === "confirmed" ? "Confirmed ✓" : "Confirm Answer"}
                    </button>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        {/* 21ST_DEV_SLOT: sheet-drawer (https://21st.dev/s/sheet-drawer) */}
        {activeEvidenceExt && (
          <div className="fixed inset-0 z-50 flex items-center justify-end bg-black/40 p-4 transition-all">
            <div className="h-full w-full max-w-lg rounded-2xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-2xl overflow-y-auto">
              <div className="flex items-center justify-between border-b border-[#E2DDD2] pb-4">
                <div>
                  <h3 className="font-serif text-base font-semibold text-[#16181D]">
                    Evidence Inspector
                  </h3>
                  <p className="font-mono text-xs text-[#5F6470]">
                    Question: {activeEvidenceExt.question_id}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => setActiveEvidenceExt(null)}
                  className="rounded-lg p-1.5 text-[#5F6470] hover:bg-[#F6F3EC]"
                >
                  ✕
                </button>
              </div>

              <div className="mt-6 space-y-4">
                <div>
                  <div className="font-mono text-xs font-semibold text-[#5F6470] uppercase">
                    Source File:
                  </div>
                  <div className="mt-1 font-serif text-sm font-medium text-[#16181D]">
                    {activeEvidenceExt.source_file || "Unknown"}
                  </div>
                </div>

                <div>
                  <div className="font-mono text-xs font-semibold text-[#5F6470] uppercase">
                    Page Location:
                  </div>
                  <div className="mt-1 font-mono text-xs text-[#16181D]">
                    Page {activeEvidenceExt.page || 1}
                  </div>
                </div>

                <div>
                  <div className="font-mono text-xs font-semibold text-[#5F6470] uppercase">
                    Detection Status:
                  </div>
                  <div className="mt-1 text-xs text-[#16181D]">
                    {/* Strictly says "Document found", never "compliant" */}
                    Document found in uploaded data room.
                  </div>
                </div>

                <div>
                  <div className="font-mono text-xs font-semibold text-[#5F6470] uppercase">
                    Exact Snippet:
                  </div>
                  <div className="mt-1 rounded-xl border border-[#E2DDD2] bg-[#F6F3EC] p-4 font-mono text-xs text-[#16181D] leading-relaxed">
                    {activeEvidenceExt.snippet}
                  </div>
                </div>

                {activeEvidenceExt.formula && (
                  <div>
                    <div className="font-mono text-xs font-semibold text-[#5F6470] uppercase">
                      Formula & Inputs:
                    </div>
                    <div className="mt-1 rounded-xl border border-[#1F4D3F]/20 bg-[#1F4D3F]/5 p-4 font-mono text-xs text-[#1F4D3F]">
                      <div>{activeEvidenceExt.formula}</div>
                      <div className="mt-2 text-[#5F6470]">
                        {JSON.stringify(activeEvidenceExt.formula_inputs, null, 2)}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              <div className="mt-8 flex items-center justify-end gap-3 border-t border-[#E2DDD2] pt-4">
                <button
                  type="button"
                  onClick={() => setActiveEvidenceExt(null)}
                  className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-4 py-2 font-mono text-xs text-[#16181D] hover:bg-[#F6F3EC]"
                >
                  Close
                </button>
              </div>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
