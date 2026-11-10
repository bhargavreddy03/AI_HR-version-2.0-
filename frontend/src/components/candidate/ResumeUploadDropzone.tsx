"use client";

import React, { useState, useRef } from "react";
import { UploadCloud, FileText, CheckCircle2, AlertCircle, Loader2 } from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type { CandidateResume } from "@/types/candidate";

interface ResumeUploadDropzoneProps {
  onUploadSuccess?: (resume: CandidateResume) => void;
  className?: string;
}

export function ResumeUploadDropzone({
  onUploadSuccess,
  className = "",
}: ResumeUploadDropzoneProps) {
  const [isDragging, setIsDragging] = useState(false);
  const [isUploading, setIsUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [successResume, setSuccessResume] = useState<CandidateResume | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const allowedTypes = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"];
  const maxSizeBytes = 15 * 1024 * 1024; // 15 MB

  const validateAndUpload = async (file: File) => {
    setError(null);
    setSuccessResume(null);

    if (!allowedTypes.includes(file.type) && !file.name.toLowerCase().endsWith(".pdf") && !file.name.toLowerCase().endsWith(".docx")) {
      setError("Only PDF and DOCX files are supported.");
      return;
    }

    if (file.size > maxSizeBytes) {
      setError("File exceeds maximum allowed size (15 MB).");
      return;
    }

    setIsUploading(true);
    try {
      const resume = await candidateApi.uploadResume(file);
      setSuccessResume(resume);
      if (onUploadSuccess) {
        onUploadSuccess(resume);
      }
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : "Failed to upload resume";
      setError(message);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) {
        fileInputRef.current.value = "";
      }
    }
  };

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      validateAndUpload(e.dataTransfer.files[0]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      validateAndUpload(e.target.files[0]);
    }
  };

  return (
    <div className={`space-y-4 ${className}`}>
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        onClick={() => !isUploading && fileInputRef.current?.click()}
        className={`relative flex flex-col items-center justify-center p-8 border-2 border-dashed rounded-xl cursor-pointer transition-all ${
          isDragging
            ? "border-primary-500 bg-primary-50/50 dark:bg-primary-950/20"
            : "border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 hover:border-slate-400 dark:hover:border-slate-600"
        } ${isUploading ? "opacity-60 pointer-events-none" : ""}`}
        role="button"
        tabIndex={0}
        aria-label="Upload Resume File"
      >
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.docx,application/pdf"
          className="hidden"
          onChange={handleFileChange}
          disabled={isUploading}
        />

        <div className="flex flex-col items-center text-center space-y-2">
          {isUploading ? (
            <div className="p-3 bg-primary-50 dark:bg-primary-900/30 rounded-full text-primary-600 dark:text-primary-400 animate-spin">
              <Loader2 className="w-8 h-8" />
            </div>
          ) : (
            <div className="p-3 bg-slate-100 dark:bg-slate-800 rounded-full text-slate-600 dark:text-slate-400">
              <UploadCloud className="w-8 h-8" />
            </div>
          )}

          <div className="text-sm font-semibold text-slate-800 dark:text-slate-200">
            {isUploading ? "Extracting & Ingesting Resume..." : "Click or drag resume here to upload"}
          </div>

          <p className="text-xs text-slate-500 dark:text-slate-400">
            Supports PDF or DOCX up to 15MB. Ingested securely with Step 3.10 pipeline.
          </p>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3 text-xs text-red-700 bg-red-50 dark:bg-red-950/40 dark:text-red-300 border border-red-200 dark:border-red-800 rounded-lg"
        >
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {successResume && (
        <div className="p-4 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl space-y-2">
          <div className="flex items-center gap-2 text-xs font-semibold text-emerald-800 dark:text-emerald-300">
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600 dark:text-emerald-400" />
            <span>Resume ingested successfully (v{successResume.version_number}): {successResume.file_name}</span>
          </div>

          {successResume.extracted_skills && successResume.extracted_skills.length > 0 && (
            <div className="pt-2 border-t border-emerald-100 dark:border-emerald-900/60">
              <p className="text-xs font-medium text-emerald-900 dark:text-emerald-200 mb-1.5">
                Automatically Extracted Skills ({successResume.extracted_skills.length}):
              </p>
              <div className="flex flex-wrap gap-1.5">
                {successResume.extracted_skills.map((skill, idx) => (
                  <span
                    key={idx}
                    className="inline-flex items-center px-2 py-0.5 text-xs font-medium bg-emerald-100 dark:bg-emerald-900 text-emerald-800 dark:text-emerald-200 rounded-md"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
