"use client";

import React, { useEffect, useState, useRef, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavigationMenu } from "@/components/ui-21st/navigation-menu";
import { NumberTicker } from "@/components/ui-21st/number-ticker";
import { FileDropzone } from "@/components/ui-21st/file-dropzone";
import { AlertDialog } from "@/components/ui-21st/alert-dialog";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface QuestionItem {
  question_id: string;
  scope: string;
  industry: string;
  sub_sector: string;
  dimension: string;
  sub_category?: string;
  question_text: string;
  input_type: string;
  options?: string[];
  risk_weight: string;
  remediation_horizon_days: number;
  evidence_type: string;
  extraction_hint?: {
    standard?: string;
    cuad_category?: string;
    doc_types?: string[];
    table_type?: string;
  };
  remediation_action?: string;
  source_doc?: string;
  source_ref?: string;
  current_answer?: any;
  notes?: string;
  updated_at?: string;
  review_status?: string;
}

interface DimensionGroup {
  dimension: string;
  dimension_name: string;
  total: number;
  answered: number;
  questions: QuestionItem[];
}

interface AssessmentProgress {
  total_applicable: number;
  answered_count: number;
  completeness_pct: number;
  is_provisional: boolean;
  hidden_not_applicable_count: number;
}

interface AssessmentData {
  id: string;
  name: string;
  industry: string;
  sub_sector: string;
  stage: string;
  transaction_type: string;
}

export default function AssessmentWorkspacePage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = params?.id as string;

  const [assessment, setAssessment] = useState<AssessmentData | null>(null);
  const [progress, setProgress] = useState<AssessmentProgress | null>(null);
  const [byDimension, setByDimension] = useState<DimensionGroup[]>([]);
  const [activeDimension, setActiveDimension] = useState<string>("GOVERNANCE");
  const [loading, setLoading] = useState(true);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved">("idle");
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  // Expanded remediation accordion IDs
  const [expandedPlaybooks, setExpandedPlaybooks] = useState<Record<string, boolean>>({});

  // Industry switch modal state
  const [isSwitchModalOpen, setIsSwitchModalOpen] = useState(false);
  const [targetIndustry, setTargetIndustry] = useState<string>("");
  const [switchWarningText, setSwitchWarningText] = useState<string>("");

  const debounceTimers = useRef<Record<string, NodeJS.Timeout>>({});

  const getAuthHeaders = useCallback(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("ledgerlight_token") : null;
    return {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  // Fetch assessment questions and progress
  const fetchQuestions = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/questions`, {
        headers: getAuthHeaders(),
        credentials: "include",
      });
      if (!res.ok) throw new Error("Failed to load diligence questionnaire.");
      const data = await res.json();
      setAssessment(data.assessment);
      setProgress(data.progress);
      setByDimension(data.by_dimension);

      if (data.by_dimension.length > 0 && !activeDimension) {
        setActiveDimension(data.by_dimension[0].dimension);
      }
    } catch (err: any) {
      setErrorMsg(err.message || "Failed to connect to Diligence API.");
    } finally {
      setLoading(false);
    }
  }, [assessmentId, activeDimension, getAuthHeaders]);

  useEffect(() => {
    if (assessmentId) {
      fetchQuestions();
    }
  }, [assessmentId, fetchQuestions]);

  // Autosave handler
  const saveAnswer = async (questionId: string, value: any, notes?: string) => {
    setSaveStatus("saving");
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/answers/${questionId}`, {
        method: "PUT",
        headers: getAuthHeaders(),
        credentials: "include",
        body: JSON.stringify({ value, notes }),
      });

      if (!res.ok) throw new Error("Failed to save answer.");
      const resData = await res.json();

      // Update progress metrics
      if (resData.progress) {
        setProgress(resData.progress);
      }

      // Update local question state
      setByDimension((prev) =>
        prev.map((group) => {
          const updatedQs = group.questions.map((q) =>
            q.question_id === questionId ? { ...q, current_answer: value, notes: notes ?? q.notes } : q
          );
          const answered = updatedQs.filter((q) => q.current_answer !== null && q.current_answer !== undefined).length;
          return { ...group, questions: updatedQs, answered };
        })
      );

      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2500);
    } catch (err) {
      console.error(err);
      setSaveStatus("idle");
    }
  };

  // Immediate save for boolean or choice pills
  const handleImmediateChange = (questionId: string, val: any) => {
    saveAnswer(questionId, val);
  };

  // Debounced save for text, numbers, percentages
  const handleDebouncedChange = (questionId: string, val: any) => {
    // Update local state immediately for snappy input
    setByDimension((prev) =>
      prev.map((group) => ({
        ...group,
        questions: group.questions.map((q) =>
          q.question_id === questionId ? { ...q, current_answer: val } : q
        ),
      }))
    );

    if (debounceTimers.current[questionId]) {
      clearTimeout(debounceTimers.current[questionId]);
    }
    setSaveStatus("saving");
    debounceTimers.current[questionId] = setTimeout(() => {
      saveAnswer(questionId, val);
    }, 600);
  };

  const togglePlaybook = (qid: string) => {
    setExpandedPlaybooks((prev) => ({ ...prev, [qid]: !prev[qid] }));
  };

  // Initiate industry switch check
  const handleInitiateIndustrySwitch = async (newInd: string) => {
    setTargetIndustry(newInd);
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/profile`, {
        method: "PATCH",
        headers: getAuthHeaders(),
        credentials: "include",
        body: JSON.stringify({ industry: newInd, confirm_discard_answers: false }),
      });

      if (res.status === 409) {
        const conflictData = await res.json();
        setSwitchWarningText(conflictData.detail.warning);
        setIsSwitchModalOpen(true);
      } else if (res.ok) {
        // Updated without conflict
        fetchQuestions();
      }
    } catch (err: any) {
      console.error(err);
    }
  };

  const handleConfirmIndustrySwitch = async () => {
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/profile`, {
        method: "PATCH",
        headers: getAuthHeaders(),
        credentials: "include",
        body: JSON.stringify({ industry: targetIndustry, confirm_discard_answers: true }),
      });
      if (res.ok) {
        setIsSwitchModalOpen(false);
        fetchQuestions();
      }
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-[#F6F3EC]">
        <div className="text-center">
          <div className="mx-auto h-8 w-8 animate-spin rounded-full border-2 border-[#1F4D3F] border-t-transparent" />
          <p className="mt-4 font-mono text-xs uppercase tracking-wider text-[#5F6470]">
            Loading Diligence Questionnaire...
          </p>
        </div>
      </div>
    );
  }

  const currentGroup = byDimension.find((d) => d.dimension === activeDimension) || byDimension[0];

  return (
    <div className="min-h-screen bg-[#F6F3EC] text-[#16181D]">
      {/* 21st.dev Slot: @shadcn/navigation-menu - Clean editorial header */}
      <NavigationMenu
        rightElement={
          <div className="flex items-center gap-4">
            {/* Autosave status indicator */}
            <div className="flex items-center gap-2">
              <span
                className={`h-2 w-2 rounded-full transition-colors ${
                  saveStatus === "saving"
                    ? "bg-[#B7791F] animate-pulse"
                    : saveStatus === "saved"
                    ? "bg-[#2F7D57]"
                    : "bg-[#5F6470]/30"
                }`}
              />
              <span className="font-mono text-xs text-[#5F6470]">
                {saveStatus === "saving"
                  ? "Saving..."
                  : saveStatus === "saved"
                  ? "All changes saved"
                  : "Autosave active"}
              </span>
            </div>

            <Link
              href={`/assessment/${assessmentId}/data-room`}
              className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
            >
              Data Room
            </Link>

            <Link
              href={`/assessment/${assessmentId}/verify`}
              className="rounded-lg border border-[#1F4D3F] bg-[#E8F0EC] px-3 py-1.5 font-mono text-xs font-semibold text-[#1F4D3F] hover:bg-[#1F4D3F] hover:text-white transition-colors"
            >
              Verify Extractions
            </Link>

            <Link
              href={`/assessment/${assessmentId}/report`}
              className="rounded-lg bg-[#1F4D3F] px-3.5 py-1.5 font-mono text-xs font-semibold text-white hover:bg-[#17392F] transition-colors shadow-xs flex items-center gap-1.5"
            >
              <span>View Readiness Report</span>
              <span>&rarr;</span>
            </Link>

            <Link
              href="/admin"
              className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
            >
              Admin Console
            </Link>
          </div>
        }
      />

      {/* Diligence Context Sub-Header */}
      <div className="border-b border-[#E2DDD2] bg-[#FFFFFF]">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4 px-4 py-3 sm:px-6 lg:px-8">
          <div className="flex flex-wrap items-center gap-3">
            <h1 className="font-serif text-lg font-semibold text-[#16181D]">
              {assessment?.name || "Diligence Assessment"}
            </h1>
            <span className="rounded bg-[#E8F0EC] px-2 py-0.5 font-mono text-xs font-semibold text-[#1F4D3F]">
              {assessment?.industry}
            </span>
            <span className="rounded border border-[#E2DDD2] px-2 py-0.5 font-mono text-xs text-[#5F6470]">
              {assessment?.sub_sector}
            </span>
            <span className="rounded border border-[#E2DDD2] px-2 py-0.5 font-mono text-xs text-[#5F6470]">
              {assessment?.stage}
            </span>
            <button
              onClick={() => {
                const nextInd = assessment?.industry === "SOFTWARE" ? "HEALTHCARE" : "SOFTWARE";
                handleInitiateIndustrySwitch(nextInd);
              }}
              className="text-xs text-[#1F4D3F] hover:underline"
            >
              Change Industry
            </button>
          </div>

          {/* Pruned questions badge */}
          {progress && progress.hidden_not_applicable_count > 0 && (
            <div className="font-mono text-xs text-[#5F6470]">
              <span className="font-semibold text-[#16181D]">
                {progress.hidden_not_applicable_count}
              </span>{" "}
              non-applicable questions hidden
            </div>
          )}
        </div>

        {/* Evidence-Completeness Progress Bar */}
        {progress && (
          <div className="border-t border-[#E2DDD2]/60 bg-[#F6F3EC]/40 px-4 py-2.5 sm:px-6 lg:px-8">
            <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
              <div className="flex items-center gap-3">
                <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                  Evidence Completeness:
                </span>
                {/* 21st.dev Slot: @magicui/number-ticker - Monospace completeness ticker */}
                <span className="font-serif text-base font-semibold text-[#1F4D3F]">
                  <NumberTicker value={progress.completeness_pct} decimals={1} />%
                </span>
                <span className="font-mono text-xs text-[#5F6470]">
                  ({progress.answered_count} / {progress.total_applicable} applicable questions answered)
                </span>
              </div>

              {progress.is_provisional && (
                <div className="flex items-center gap-2 rounded bg-[#B7791F]/10 px-2 py-1 text-[11px] text-[#B7791F]">
                  <span className="h-1.5 w-1.5 rounded-full bg-[#B7791F]" />
                  <span>
                    Provisional status: Score calibrates once completeness reaches ≥ 60%.
                  </span>
                </div>
              )}
            </div>

            {/* Visual Progress Track */}
            <div className="mx-auto mt-2 h-1.5 max-w-7xl overflow-hidden rounded-full bg-[#E2DDD2]">
              <div
                className="h-full bg-[#1F4D3F] transition-all duration-500 ease-out"
                style={{ width: `${progress.completeness_pct}%` }}
              />
            </div>
          </div>
        )}
      </div>

      {/* Main Workspace Layout */}
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-12">
          {/* Dimension Sidebar */}
          <aside className="lg:col-span-4 xl:col-span-3">
            <div className="sticky top-24 rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-4 shadow-xs">
              <h2 className="font-mono text-xs font-semibold uppercase tracking-wider text-[#5F6470]">
                Audit Dimensions ({byDimension.length})
              </h2>

              <nav className="mt-3 space-y-1">
                {byDimension.map((group) => {
                  const isActive = group.dimension === activeDimension;
                  const isComplete = group.answered === group.total && group.total > 0;

                  return (
                    <button
                      key={group.dimension}
                      onClick={() => setActiveDimension(group.dimension)}
                      className={`flex w-full items-center justify-between rounded-lg px-3 py-2 text-left text-xs transition-colors ${
                        isActive
                          ? "bg-[#1F4D3F] font-semibold text-white shadow-xs"
                          : "text-[#16181D] hover:bg-[#F6F3EC]"
                      }`}
                    >
                      <span className="truncate pr-2">{group.dimension_name}</span>
                      <span
                        className={`font-mono text-[11px] shrink-0 rounded px-1.5 py-0.5 ${
                          isActive
                            ? "bg-white/20 text-white"
                            : isComplete
                            ? "bg-[#2F7D57]/10 text-[#2F7D57] font-semibold"
                            : "bg-[#F6F3EC] text-[#5F6470]"
                        }`}
                      >
                        {group.answered}/{group.total}
                      </span>
                    </button>
                  );
                })}
              </nav>
            </div>
          </aside>

          {/* Questionnaire Main Column */}
          <main className="lg:col-span-8 xl:col-span-9">
            {currentGroup ? (
              <div className="space-y-6">
                {/* Dimension Section Header */}
                <div className="border-b border-[#E2DDD2] pb-4">
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-xs font-semibold uppercase tracking-wider text-[#1F4D3F]">
                      Section: {currentGroup.dimension}
                    </span>
                    <span className="font-mono text-xs text-[#5F6470]">
                      {currentGroup.answered} of {currentGroup.total} completed
                    </span>
                  </div>
                  <h2 className="mt-1 font-serif text-2xl font-semibold text-[#16181D]">
                    {currentGroup.dimension_name}
                  </h2>
                </div>

                {/* Question Cards */}
                <div className="space-y-4">
                  {currentGroup.questions.map((q) => {
                    const isAnswered = q.current_answer !== null && q.current_answer !== undefined;
                    const isOpen = expandedPlaybooks[q.question_id] || false;

                    return (
                      <div
                        key={q.question_id}
                        className={`rounded-xl border bg-[#FFFFFF] p-6 transition-all ${
                          isAnswered ? "border-[#E2DDD2]" : "border-[#E2DDD2] shadow-xs"
                        }`}
                      >
                        {/* Question Metadata Header */}
                        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-[#E2DDD2]/60 pb-3">
                          <div className="flex items-center gap-2">
                            <span className="font-mono text-xs font-bold text-[#16181D]">
                              {q.question_id}
                            </span>
                            <span
                              className={`rounded px-1.5 py-0.5 font-mono text-[10px] font-semibold ${
                                q.risk_weight === "CRITICAL"
                                  ? "bg-[#B4382F]/10 text-[#B4382F]"
                                  : q.risk_weight === "HIGH"
                                  ? "bg-[#B7791F]/10 text-[#B7791F]"
                                  : "bg-[#5F6470]/10 text-[#5F6470]"
                              }`}
                            >
                              {q.risk_weight}
                            </span>
                            <span className="rounded bg-[#F6F3EC] px-1.5 py-0.5 font-mono text-[10px] text-[#5F6470]">
                              Horizon: {q.remediation_horizon_days}d
                            </span>
                            {q.review_status === "UNREVIEWED_SEED" && (
                              <span className="rounded bg-amber-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-amber-700 border border-amber-500/20">
                                Seed Data (Unreviewed)
                              </span>
                            )}
                            {q.review_status === "AI_PRE_REVIEWED" && (
                              <span className="rounded bg-purple-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-purple-700 border border-purple-500/20">
                                AI pre-reviewed, not human-verified
                              </span>
                            )}
                            {q.review_status === "APPROVED" && (
                              <span className="rounded bg-emerald-500/10 px-1.5 py-0.5 font-mono text-[10px] font-semibold text-emerald-700 border border-emerald-500/20">
                                Verified
                              </span>
                            )}
                          </div>

                          <span className="font-mono text-[10px] text-[#5F6470]">
                            Method: {q.evidence_type}
                          </span>
                        </div>

                        {/* Question Text */}
                        <p className="mt-4 text-sm font-medium text-[#16181D] leading-relaxed">
                          {q.question_text}
                        </p>

                        {/* Input Controls per input_type */}
                        <div className="mt-5">
                          {/* 1. BOOLEAN */}
                          {q.input_type === "BOOLEAN" && (
                            <div className="flex items-center gap-3">
                              <button
                                type="button"
                                onClick={() => handleImmediateChange(q.question_id, true)}
                                className={`flex-1 rounded-lg border py-2 text-xs font-semibold transition-all ${
                                  q.current_answer === true
                                    ? "border-[#1F4D3F] bg-[#1F4D3F] text-white shadow-xs"
                                    : "border-[#E2DDD2] bg-[#FFFFFF] text-[#16181D] hover:bg-[#F6F3EC]"
                                }`}
                              >
                                Yes
                              </button>
                              <button
                                type="button"
                                onClick={() => handleImmediateChange(q.question_id, false)}
                                className={`flex-1 rounded-lg border py-2 text-xs font-semibold transition-all ${
                                  q.current_answer === false
                                    ? "border-[#B4382F] bg-[#B4382F] text-white shadow-xs"
                                    : "border-[#E2DDD2] bg-[#FFFFFF] text-[#16181D] hover:bg-[#F6F3EC]"
                                }`}
                              >
                                No
                              </button>
                            </div>
                          )}

                          {/* 2. MULTIPLE_CHOICE */}
                          {q.input_type === "MULTIPLE_CHOICE" && q.options && (
                            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
                              {q.options.map((opt) => (
                                <button
                                  key={opt}
                                  type="button"
                                  onClick={() => handleImmediateChange(q.question_id, opt)}
                                  className={`rounded-lg border px-3 py-2 text-left text-xs font-medium transition-colors ${
                                    q.current_answer === opt
                                      ? "border-[#1F4D3F] bg-[#E8F0EC] text-[#1F4D3F] font-semibold"
                                      : "border-[#E2DDD2] bg-[#FFFFFF] text-[#16181D] hover:bg-[#F6F3EC]"
                                  }`}
                                >
                                  {opt}
                                </button>
                              ))}
                            </div>
                          )}

                          {/* 3. PERCENTAGE */}
                          {q.input_type === "PERCENTAGE" && (
                            <div className="flex max-w-xs items-center rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30">
                              <input
                                type="number"
                                min="0"
                                max="100"
                                step="0.1"
                                value={q.current_answer ?? ""}
                                onChange={(e) =>
                                  handleDebouncedChange(
                                    q.question_id,
                                    e.target.value === "" ? null : parseFloat(e.target.value)
                                  )
                                }
                                placeholder="0.0"
                                className="w-full bg-transparent px-3 py-2 text-sm text-[#16181D] focus:outline-hidden tabular-nums"
                              />
                              <span className="pr-3 font-mono text-xs font-semibold text-[#5F6470]">%</span>
                            </div>
                          )}

                          {/* 4. CURRENCY */}
                          {q.input_type === "CURRENCY" && (
                            <div className="flex max-w-xs items-center rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30">
                              <span className="pl-3 font-mono text-xs font-semibold text-[#5F6470]">$</span>
                              <input
                                type="number"
                                step="1000"
                                value={q.current_answer ?? ""}
                                onChange={(e) =>
                                  handleDebouncedChange(
                                    q.question_id,
                                    e.target.value === "" ? null : parseFloat(e.target.value)
                                  )
                                }
                                placeholder="0"
                                className="w-full bg-transparent px-3 py-2 text-sm text-[#16181D] focus:outline-hidden tabular-nums"
                              />
                            </div>
                          )}

                          {/* 5. NUMBER */}
                          {q.input_type === "NUMBER" && (
                            <input
                              type="number"
                              value={q.current_answer ?? ""}
                              onChange={(e) =>
                                handleDebouncedChange(
                                  q.question_id,
                                  e.target.value === "" ? null : parseFloat(e.target.value)
                                )
                              }
                              placeholder="e.g. 18"
                              className="max-w-xs rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3 py-2 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden tabular-nums"
                            />
                          )}

                          {/* 6. TEXT */}
                          {q.input_type === "TEXT" && (
                            <textarea
                              rows={2}
                              value={q.current_answer ?? ""}
                              onChange={(e) => handleDebouncedChange(q.question_id, e.target.value)}
                              placeholder="Enter specific factual response or citation details..."
                              className="block w-full rounded-lg border border-[#E2DDD2] bg-[#F6F3EC]/30 px-3 py-2 text-sm text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden"
                            />
                          )}

                          {/* 7. FILE */}
                          {q.input_type === "FILE" && (
                            /* 21st.dev Slot: @shadcn/file-dropzone - Restricted drag-and-drop document dropzone */
                            <FileDropzone
                              hint={`Attach ${q.extraction_hint?.cuad_category || "relevant agreement or certificate"}`}
                              docTypes={q.extraction_hint?.doc_types || ["PDF", "DOCX"]}
                            />
                          )}
                        </div>

                        {/* Auditor Notes Field */}
                        <div className="mt-4">
                          <input
                            type="text"
                            value={q.notes ?? ""}
                            onChange={(e) =>
                              handleDebouncedChange(q.question_id, q.current_answer)
                            }
                            placeholder="Add auditor notes or reference clause..."
                            className="block w-full rounded-md border border-transparent bg-transparent px-2 py-1 text-xs text-[#5F6470] hover:border-[#E2DDD2] focus:border-[#1F4D3F] focus:bg-[#FFFFFF] focus:outline-hidden"
                          />
                        </div>

                        {/* Remediation Playbook Accordion */}
                        {q.remediation_action && (
                          <div className="mt-4 border-t border-[#E2DDD2]/40 pt-3">
                            <button
                              type="button"
                              onClick={() => togglePlaybook(q.question_id)}
                              className="flex items-center gap-1.5 text-xs font-medium text-[#1F4D3F] hover:underline"
                            >
                              <svg
                                className={`h-3.5 w-3.5 transition-transform ${isOpen ? "rotate-90" : ""}`}
                                fill="none"
                                stroke="currentColor"
                                viewBox="0 0 24 24"
                              >
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 5l7 7-7 7" />
                              </svg>
                              <span>Investor Rationale & Remediation Playbook</span>
                            </button>

                            {isOpen && (
                              <div className="mt-2 rounded-lg bg-[#F6F3EC]/70 p-3 text-xs text-[#5F6470] space-y-1.5">
                                <p>
                                  <strong className="text-[#16181D]">Remediation Action:</strong>{" "}
                                  {q.remediation_action}
                                </p>
                                {q.source_doc && (
                                  <p className="font-mono text-[10px] text-[#5F6470]/80">
                                    Citation: {q.source_doc} &bull; {q.source_ref}
                                  </p>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            ) : (
              <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-8 text-center">
                <p className="text-sm text-[#5F6470]">No applicable questions in this dimension.</p>
              </div>
            )}
          </main>
        </div>
      </div>

      {/* Sticky Bottom Progress & Report Trigger Footer (PRD 13.5 Screen 5) */}
      <div className="sticky bottom-0 z-30 border-t border-[#E2DDD2] bg-[#FFFFFF]/95 backdrop-blur-xs px-4 py-3 shadow-lg">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-4">
          <div className="flex items-center gap-3">
            <span className="font-mono text-xs text-[#5F6470]">Overall Progress:</span>
            <span className="font-serif text-sm font-bold text-[#1F4D3F]">
              {progress?.completeness_pct ?? 0}%
            </span>
            <span className="font-mono text-xs text-[#5F6470]">
              ({progress?.answered_count ?? 0} of {progress?.total_applicable ?? 0} answered)
            </span>
            {progress?.is_provisional && (
              <span className="rounded bg-[#B7791F]/10 px-2 py-0.5 text-[11px] font-semibold text-[#B7791F]">
                Provisional (&lt;60%)
              </span>
            )}
          </div>

          <Link
            href={`/assessment/${assessmentId}/report`}
            className="flex items-center gap-2 rounded-lg bg-[#1F4D3F] px-4 py-2 font-mono text-xs font-semibold text-white hover:bg-[#17392F] transition-all shadow-xs"
          >
            <span>Generate Readiness Report</span>
            {progress?.is_provisional && (
              <span className="rounded bg-[#B7791F] px-1.5 py-0.2 text-[10px] text-white">
                Provisional
              </span>
            )}
            <span>&rarr;</span>
          </Link>
        </div>
      </div>

      {/* 21st.dev Slot: @shadcn/alert-dialog - Industry switch confirmation modal */}
      <AlertDialog
        isOpen={isSwitchModalOpen}
        title="Discard Industry Branch Answers?"
        description={switchWarningText}
        confirmLabel="Confirm & Discard Branch Answers"
        cancelLabel="Keep Current Industry"
        isDestructive={true}
        onConfirm={handleConfirmIndustrySwitch}
        onCancel={() => setIsSwitchModalOpen(false)}
      />
    </div>
  );
}
