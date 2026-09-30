"use client";

/**
 * Component: AlertDialog
 * Author / Library: shadcn/ui (adapted from 21st.dev /s/alert-dialog)
 * Source URL: https://21st.dev/s/alert-dialog
 *
 * Re-themed to Ledgerlight design tokens:
 * - Surface: #FFFFFF
 * - Border: #E2DDD2
 * - Warning/Fail: #B4382F
 * - Accessible focus rings and keyboard escape
 */

import React, { useEffect } from "react";

interface AlertDialogProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  isDestructive?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export function AlertDialog({
  isOpen,
  title,
  description,
  confirmLabel = "Continue",
  cancelLabel = "Cancel",
  isDestructive = false,
  onConfirm,
  onCancel,
}: AlertDialogProps) {
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        onCancel();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onCancel]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-[#16181D]/40 backdrop-blur-xs transition-opacity"
        onClick={onCancel}
      />

      {/* Modal Dialog */}
      <div className="relative w-full max-w-lg rounded-xl border border-[#E2DDD2] bg-[#FFFFFF] p-6 shadow-xl transition-all">
        <div className="flex items-start gap-4">
          <div
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-full ${
              isDestructive ? "bg-[#B4382F]/10 text-[#B4382F]" : "bg-[#1F4D3F]/10 text-[#1F4D3F]"
            }`}
          >
            <svg
              className="h-5 w-5"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
              />
            </svg>
          </div>

          <div className="flex-1">
            <h3 className="font-serif text-lg font-semibold text-[#16181D]">
              {title}
            </h3>
            <p className="mt-2 text-sm text-[#5F6470] leading-relaxed">
              {description}
            </p>
          </div>
        </div>

        <div className="mt-6 flex items-center justify-end gap-3">
          <button
            type="button"
            onClick={onCancel}
            className="rounded-lg border border-[#E2DDD2] bg-[#FFFFFF] px-4 py-2 text-sm font-medium text-[#16181D] hover:bg-[#F6F3EC] transition-colors"
          >
            {cancelLabel}
          </button>
          <button
            type="button"
            onClick={onConfirm}
            className={`rounded-lg px-4 py-2 text-sm font-medium text-white transition-colors ${
              isDestructive
                ? "bg-[#B4382F] hover:bg-[#922D26]"
                : "bg-[#1F4D3F] hover:bg-[#17392F]"
            }`}
          >
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
