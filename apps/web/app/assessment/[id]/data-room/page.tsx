"use client";

/**
 * Data Room Upload & Processing Workspace (PRD Section 7.1 to 7.3 & FR-3).
 * 
 * Features:
 * - Multi-file and ZIP bundle dropzone.
 * - Real stage counts (Uploaded, Parsed, Classified, Extractions Proposed) - NO fake percentages.
 * - Document inventory with user classification override (PATCH /documents/{doc_id}).
 * - Document deletion (DELETE /documents/{doc_id}).
 * - Direct link to Verification Workspace.
 * 
 * Marked 21st.dev Slots:
 * <!-- 21ST_DEV_SLOT: file-dropzone (https://21st.dev/s/file-dropzone) -->
 * <!-- 21ST_DEV_SLOT: data-table (https://21st.dev/s/data-table) -->
 * <!-- 21ST_DEV_SLOT: badge (https://21st.dev/s/badge) -->
 */

import React, { useState, useEffect, useCallback, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { NavigationMenu } from "@/components/ui-21st/navigation-menu";

const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

const CLASSIFICATION_OPTIONS = [
  { value: "cap_table", label: "Cap Table / Equity Registry" },
  { value: "bank_statement", label: "Bank Account Statement" },
  { value: "financial_statement", label: "Financial Statement (P&L, Balance Sheet, Budget)" },
  { value: "certificate_or_report", label: "Audit Report / Certificate (SOC 2, ISO, PCI)" },
  { value: "policy", label: "Policy Document (BCP/DR, InfoSec, Privacy)" },
  { value: "customer_contract", label: "Customer Contract / MSA / SOW" },
  { value: "employment_ip_agreement", label: "Employment / IP Assignment (PIIA)" },
  { value: "board_minutes", label: "Board Minutes / Resolutions" },
  { value: "unclassified", label: "Unclassified (User Review Required)" },
];

interface DocumentItem {
  id: string;
  filename: string;
  file_type: string;
  file_size: number;
  sha256: string;
  mime_type: string;
  page_count: number;
  status: string;
  stage: string;
  error_message?: string;
  created_at: string;
}

export default function DataRoomUploadPage() {
  const params = useParams();
  const router = useRouter();
  const assessmentId = params?.id as string;

  const [documents, setDocuments] = useState<DocumentItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadSuccess, setUploadSuccess] = useState<string | null>(null);
  const [dragActive, setDragActive] = useState(false);

  // Real stage counts
  const [stageCounts, setStageCounts] = useState({
    uploaded: 0,
    parsed: 0,
    classified: 0,
    extractionsProposed: 0,
  });

  const fileInputRef = useRef<HTMLInputElement>(null);

  const getAuthHeaders = useCallback(() => {
    const token = typeof window !== "undefined" ? localStorage.getItem("ledgerlight_token") : null;
    return {
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    };
  }, []);

  const fetchDocuments = useCallback(async () => {
    try {
      setLoading(true);
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/documents`, {
        headers: getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        const data = await res.json();
        const docs: DocumentItem[] = data.documents || [];
        setDocuments(docs);

        // Fetch extractions count
        const extRes = await fetch(`${API_BASE}/assessments/${assessmentId}/extractions`, {
          headers: getAuthHeaders(),
          credentials: "include",
        });
        let extCount = 0;
        if (extRes.ok) {
          const extData = await extRes.json();
          extCount = extData.extractions?.length || 0;
        }

        // Compute real stage counts (no fake percentages)
        setStageCounts({
          uploaded: docs.length,
          parsed: docs.filter((d) => d.status === "processed").length,
          classified: docs.filter((d) => d.file_type !== "unclassified").length,
          extractionsProposed: extCount,
        });
      }
    } catch (err: any) {
      console.error("Failed to load documents", err);
    } finally {
      setLoading(false);
    }
  }, [assessmentId, getAuthHeaders]);

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleUploadFiles = async (files: FileList | File[]) => {
    if (!files || files.length === 0) return;

    setUploading(true);
    setUploadError(null);
    setUploadSuccess(null);

    const formData = new FormData();
    for (let i = 0; i < files.length; i++) {
      formData.append("files", files[i]);
    }

    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/documents/upload`, {
        method: "POST",
        headers: getAuthHeaders(),
        credentials: "include",
        body: formData,
      });

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}));
        throw new Error(errData.detail || `Upload failed with status ${res.status}`);
      }

      const result = await res.json();
      setUploadSuccess(
        `Successfully uploaded ${result.documents_uploaded} document(s). Generated ${result.extractions_found} proposed extraction(s).`
      );
      fetchDocuments();
    } catch (err: any) {
      setUploadError(err.message || "Failed to upload document(s).");
    } finally {
      setUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDrag = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    if (e.type === "dragenter" || e.type === "dragover") {
      setDragActive(true);
    } else if (e.type === "dragleave") {
      setDragActive(false);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setDragActive(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      handleUploadFiles(e.dataTransfer.files);
    }
  };

  const handleClassificationChange = async (docId: string, newType: string) => {
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/documents/${docId}`, {
        method: "PATCH",
        headers: {
          ...getAuthHeaders(),
          "Content-Type": "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ file_type: newType }),
      });
      if (res.ok) {
        setDocuments((prev) =>
          prev.map((d) => (d.id === docId ? { ...d, file_type: newType } : d))
        );
      }
    } catch (err) {
      console.error("Failed to update classification", err);
    }
  };

  const handleDeleteDocument = async (docId: string, filename: string) => {
    if (!confirm(`Are you sure you want to delete '${filename}' and its extracted data?`)) {
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/assessments/${assessmentId}/documents/${docId}`, {
        method: "DELETE",
        headers: getAuthHeaders(),
        credentials: "include",
      });
      if (res.ok) {
        fetchDocuments();
      }
    } catch (err) {
      console.error("Failed to delete document", err);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  };

  return (
    <div className="min-h-screen bg-[#F6F3EC] text-[#16181D]">
      <NavigationMenu
        rightElement={
          <div className="flex items-center gap-3">
            <Link
              href={`/assessment/${assessmentId}`}
              className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-3 py-1.5 font-mono text-xs font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
            >
              &larr; Questionnaire
            </Link>
            <Link
              href={`/assessment/${assessmentId}/verify`}
              className="rounded-lg bg-[#1F4D3F] px-3.5 py-1.5 font-mono text-xs font-semibold text-white hover:bg-[#17392F] transition-colors shadow-xs"
            >
              Verify Extractions &rarr;
            </Link>
          </div>
        }
      />

      {/* Sub-Header Navigation Tabs */}
      <div className="border-b border-[#E2DDD2] bg-[#FFFFFF]">
        <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6 lg:px-8">
          <div>
            <h1 className="font-serif text-lg font-semibold text-[#16181D]">
              Data Room & Document Ingestion
            </h1>
            <p className="text-xs text-[#5F6470]">
              Secure upload, format validation, and automated deterministic extraction.
            </p>
          </div>

          <div className="flex items-center gap-2">
            <Link
              href={`/assessment/${assessmentId}`}
              className="rounded-lg px-3 py-1.5 font-mono text-xs text-[#5F6470] hover:text-[#16181D]"
            >
              Questionnaire
            </Link>
            <span className="rounded-lg bg-[#1F4D3F]/10 px-3 py-1.5 font-mono text-xs font-semibold text-[#1F4D3F]">
              Data Room
            </span>
            <Link
              href={`/assessment/${assessmentId}/verify`}
              className="rounded-lg px-3 py-1.5 font-mono text-xs text-[#5F6470] hover:text-[#16181D]"
            >
              Verify Workspace
            </Link>
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
        {/* Real Stage Counts Bar (PRD 7.1 / FR-3: real counts, no fake percentages) */}
        <div className="mb-8 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-4 shadow-xs">
            <div className="font-mono text-xs font-medium uppercase tracking-wider text-[#5F6470]">
              1. Uploaded
            </div>
            <div className="mt-1 font-serif text-2xl font-bold text-[#16181D]">
              {stageCounts.uploaded}
            </div>
            <div className="mt-1 text-xs text-[#5F6470]">Primary documents</div>
          </div>

          <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-4 shadow-xs">
            <div className="font-mono text-xs font-medium uppercase tracking-wider text-[#5F6470]">
              2. Parsed & Text
            </div>
            <div className="mt-1 font-serif text-2xl font-bold text-[#1F4D3F]">
              {stageCounts.parsed}
            </div>
            <div className="mt-1 text-xs text-[#5F6470]">With page & char offsets</div>
          </div>

          <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-4 shadow-xs">
            <div className="font-mono text-xs font-medium uppercase tracking-wider text-[#5F6470]">
              3. Classified
            </div>
            <div className="mt-1 font-serif text-2xl font-bold text-[#16181D]">
              {stageCounts.classified}
            </div>
            <div className="mt-1 text-xs text-[#5F6470]">Heuristically typed</div>
          </div>

          <div className="rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-4 shadow-xs">
            <div className="font-mono text-xs font-medium uppercase tracking-wider text-[#5F6470]">
              4. Extractions
            </div>
            <div className="mt-1 font-serif text-2xl font-bold text-[#2F7D57]">
              {stageCounts.extractionsProposed}
            </div>
            <div className="mt-1 text-xs text-[#5F6470]">Formulas & snippet proposals</div>
          </div>
        </div>

        {/* Upload Alerts */}
        {uploadError && (
          <div className="mb-6 rounded-xl border border-[#B4382F]/30 bg-[#FDF2F1] p-4 text-sm text-[#B4382F]">
            <div className="font-semibold">Security / Validation Error:</div>
            <div>{uploadError}</div>
          </div>
        )}

        {uploadSuccess && (
          <div className="mb-6 rounded-xl border border-[#2F7D57]/30 bg-[#E8F0EC] p-4 text-sm text-[#1F4D3F]">
            <div className="font-semibold">Success:</div>
            <div>{uploadSuccess}</div>
          </div>
        )}

        {/* 21ST_DEV_SLOT: file-dropzone (https://21st.dev/s/file-dropzone) */}
        <div className="mb-10 rounded-2xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xs">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="font-serif text-base font-semibold text-[#16181D]">
                Data Room Dropzone
              </h2>
              <p className="text-xs text-[#5F6470]">
                Upload financial statements, cap table, contracts, audit reports, or a single ZIP archive.
              </p>
            </div>
            <span className="font-mono text-xs text-[#5F6470]">
              Max 50MB per file / 500MB ZIP
            </span>
          </div>

          <div
            onDragEnter={handleDrag}
            onDragLeave={handleDrag}
            onDragOver={handleDrag}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
            className={`relative flex min-h-[180px] cursor-pointer flex-col items-center justify-center rounded-xl border-2 border-dashed p-6 text-center transition-all ${
              dragActive
                ? "border-[#1F4D3F] bg-[#1F4D3F]/5 scale-[1.01]"
                : "border-[#E2DDD2] bg-[#F6F3EC]/40 hover:bg-[#F6F3EC]/80"
            }`}
          >
            <input
              ref={fileInputRef}
              type="file"
              multiple
              accept=".pdf,.docx,.xlsx,.csv,.txt,.zip"
              onChange={(e) => e.target.files && handleUploadFiles(e.target.files)}
              className="hidden"
            />

            <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-[#1F4D3F]/10 text-[#1F4D3F]">
              <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
                />
              </svg>
            </div>

            <div className="font-serif text-sm font-semibold text-[#16181D]">
              {uploading ? "Validating & Extracting..." : "Drag and drop data room files here, or click to browse"}
            </div>
            <p className="mt-1 text-xs text-[#5F6470]">
              Supported: PDF, DOCX, XLSX, CSV, TXT, ZIP
            </p>

            <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
              <span className="rounded-md border border-[#E2DDD2] bg-[#FFFFFF] px-2 py-0.5 font-mono text-[10px] text-[#5F6470]">
                MIME & Magic Bytes Verified
              </span>
              <span className="rounded-md border border-[#E2DDD2] bg-[#FFFFFF] px-2 py-0.5 font-mono text-[10px] text-[#5F6470]">
                No Raw File Retention
              </span>
              <span className="rounded-md border border-[#E2DDD2] bg-[#FFFFFF] px-2 py-0.5 font-mono text-[10px] text-[#5F6470]">
                Zip Bomb & Traversal Shield
              </span>
            </div>
          </div>
        </div>

        {/* 21ST_DEV_SLOT: data-table (https://21st.dev/s/data-table) */}
        <div className="rounded-2xl border border-[#E2DDD2] bg-[#FFFFFF] shadow-xs">
          <div className="flex items-center justify-between border-b border-[#E2DDD2] px-6 py-4">
            <div>
              <h3 className="font-serif text-base font-semibold text-[#16181D]">
                Document Inventory ({documents.length})
              </h3>
              <p className="text-xs text-[#5F6470]">
                Heuristic classification can be corrected manually if needed.
              </p>
            </div>

            <Link
              href={`/assessment/${assessmentId}/verify`}
              className="rounded-lg border border-[#1F4D3F] px-3.5 py-1.5 font-mono text-xs font-semibold text-[#1F4D3F] hover:bg-[#1F4D3F] hover:text-white transition-colors"
            >
              Open Verification Workspace &rarr;
            </Link>
          </div>

          {loading ? (
            <div className="p-8 text-center text-xs font-mono uppercase text-[#5F6470]">
              Loading document inventory...
            </div>
          ) : documents.length === 0 ? (
            <div className="p-12 text-center">
              <div className="font-serif text-sm font-semibold text-[#16181D]">
                No documents uploaded yet
              </div>
              <p className="mt-1 text-xs text-[#5F6470]">
                Upload files above to begin deterministic extraction.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse text-xs">
                <thead>
                  <tr className="border-b border-[#E2DDD2] bg-[#F6F3EC]/50 font-mono uppercase text-[11px] text-[#5F6470]">
                    <th className="py-3 px-4 font-semibold">Document Name</th>
                    <th className="py-3 px-4 font-semibold">Classification Type</th>
                    <th className="py-3 px-4 font-semibold">Size</th>
                    <th className="py-3 px-4 font-semibold">Pages</th>
                    <th className="py-3 px-4 font-semibold">SHA-256 Fingerprint</th>
                    <th className="py-3 px-4 font-semibold">Status</th>
                    <th className="py-3 px-4 font-semibold text-right">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-[#E2DDD2]/60">
                  {documents.map((doc) => (
                    <tr key={doc.id} className="hover:bg-[#F6F3EC]/30 transition-colors">
                      <td className="py-3.5 px-4 font-medium text-[#16181D]">
                        <div className="flex items-center gap-2">
                          <span className="font-mono text-xs font-semibold text-[#1F4D3F]">
                            {doc.filename.split(".").pop()?.toUpperCase()}
                          </span>
                          <span>{doc.filename}</span>
                        </div>
                      </td>

                      <td className="py-3.5 px-4">
                        <select
                          value={doc.file_type}
                          onChange={(e) => handleClassificationChange(doc.id, e.target.value)}
                          className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-2.5 py-1 text-xs text-[#16181D] focus:border-[#1F4D3F] focus:outline-hidden"
                        >
                          {CLASSIFICATION_OPTIONS.map((opt) => (
                            <option key={opt.value} value={opt.value}>
                              {opt.label}
                            </option>
                          ))}
                        </select>
                      </td>

                      <td className="py-3.5 px-4 font-mono text-[#5F6470]">
                        {formatFileSize(doc.file_size)}
                      </td>

                      <td className="py-3.5 px-4 font-mono text-[#5F6470]">
                        {doc.page_count}
                      </td>

                      <td className="py-3.5 px-4 font-mono text-[11px] text-[#5F6470]" title={doc.sha256}>
                        {doc.sha256.substring(0, 12)}...
                      </td>

                      <td className="py-3.5 px-4">
                        <span className="inline-flex items-center rounded-md bg-[#E8F0EC] px-2 py-0.5 font-mono text-[10px] font-semibold text-[#1F4D3F]">
                          {doc.status}
                        </span>
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleDeleteDocument(doc.id, doc.filename)}
                          className="rounded px-2 py-1 font-mono text-xs text-[#B4382F] hover:bg-[#FDF2F1] transition-colors"
                        >
                          Delete
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
