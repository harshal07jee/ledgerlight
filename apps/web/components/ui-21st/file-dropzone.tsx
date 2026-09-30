"use client";

/**
 * Component: FileDropzone
 * Author / Library: shadcn/ui Dropzone (adapted from 21st.dev search "file upload" / "dropzone")
 * Source URL: https://21st.dev/s/file-dropzone
 *
 * Restrained editorial dropzone:
 * - Dotted warm border: #E2DDD2
 * - Calm copy: "Drop your cap table, signed contracts, or certification reports"
 * - Clear target hints without neon highlights
 */

import React, { useState } from "react";

interface FileDropzoneProps {
  hint?: string;
  docTypes?: string[];
  onFileSelect?: (file: File) => void;
  disabled?: boolean;
}

export function FileDropzone({
  hint = "Upload primary evidence document (PDF, DOCX, XLSX)",
  docTypes = ["PDF", "DOCX", "XLSX"],
  onFileSelect,
  disabled = false,
}: FileDropzoneProps) {
  const [dragActive, setDragActive] = useState(false);
  const [fileName, setFileName] = useState<string | null>(null);

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
    if (disabled) return;

    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      const file = e.dataTransfer.files[0];
      setFileName(file.name);
      onFileSelect?.(file);
    }
  };

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    e.preventDefault();
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setFileName(file.name);
      onFileSelect?.(file);
    }
  };

  return (
    <div
      onDragEnter={handleDrag}
      onDragLeave={handleDrag}
      onDragOver={handleDrag}
      onDrop={handleDrop}
      className={`relative flex flex-col items-center justify-center rounded-lg border border-dashed px-4 py-3 transition-colors ${
        dragActive
          ? "border-[#1F4D3F] bg-[#E8F0EC]/50"
          : "border-[#E2DDD2] bg-[#F6F3EC]/40 hover:bg-[#F6F3EC]/80"
      } ${disabled ? "opacity-60 cursor-not-allowed" : "cursor-pointer"}`}
    >
      <input
        type="file"
        disabled={disabled}
        onChange={handleChange}
        className="absolute inset-0 w-full h-full opacity-0 cursor-pointer disabled:cursor-not-allowed"
      />
      <div className="flex items-center gap-2 text-xs text-[#5F6470]">
        <svg
          className="h-4 w-4 text-[#1F4D3F]"
          fill="none"
          stroke="currentColor"
          viewBox="0 0 24 24"
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth="2"
            d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12"
          />
        </svg>
        {fileName ? (
          <span className="font-mono font-medium text-[#16181D]">
            Selected: {fileName}
          </span>
        ) : (
          <span>
            <strong className="font-medium text-[#16181D]">Click to upload</strong> or drag & drop.{" "}
            {hint}
          </span>
        )}
      </div>
      {docTypes.length > 0 && !fileName && (
        <span className="mt-1 font-mono text-[10px] text-[#5F6470]/80">
          Target types: {docTypes.join(", ")}
        </span>
      )}
    </div>
  );
}
