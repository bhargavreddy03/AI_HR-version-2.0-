"use client";

import React, { useState, useEffect } from "react";
import {
  FileText,
  Download,
  Trash2,
  CheckCircle,
  Star,
  Edit2,
  Eye,
  Loader2,
  AlertCircle,
  X,
  Plus,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import { ResumeUploadDropzone } from "@/components/candidate/ResumeUploadDropzone";
import type { CandidateResume } from "@/types/candidate";

export default function CandidateResumesPage() {
  const [resumes, setResumes] = useState<CandidateResume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Skill correction modal state
  const [editingResume, setEditingResume] = useState<CandidateResume | null>(null);
  const [editSkills, setEditSkills] = useState<string[]>([]);
  const [newSkillInput, setNewSkillInput] = useState("");
  const [savingSkills, setSavingSkills] = useState(false);

  // Extracted snippet preview modal
  const [previewResume, setPreviewResume] = useState<CandidateResume | null>(null);

  const loadResumes = async () => {
    try {
      setLoading(true);
      const data = await candidateApi.getResumes();
      setResumes(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load resumes");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadResumes();
  }, []);

  const handleSetDefault = async (id: string) => {
    try {
      await candidateApi.setDefaultResume(id);
      setResumes((prev) =>
        prev.map((r) => ({
          ...r,
          is_default: r.id === id,
        }))
      );
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to set default resume");
    }
  };

  const handleDelete = async (id: string) => {
    if (!confirm("Are you sure you want to delete this resume? Active job applications using this resume will retain their snapshot.")) {
      return;
    }
    try {
      await candidateApi.deleteResume(id);
      setResumes((prev) => prev.filter((r) => r.id !== id));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete resume");
    }
  };

  const handleDownload = async (id: string) => {
    try {
      const res = await candidateApi.getResumeDownloadUrl(id);
      if (res.download_url) {
        window.open(res.download_url, "_blank", "noopener,noreferrer");
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to generate download URL");
    }
  };

  const handleOpenEditSkills = (resume: CandidateResume) => {
    setEditingResume(resume);
    setEditSkills([...(resume.extracted_skills || [])]);
  };

  const handleAddSkillToResume = () => {
    const trimmed = newSkillInput.trim();
    if (trimmed && !editSkills.includes(trimmed)) {
      setEditSkills([...editSkills, trimmed]);
      setNewSkillInput("");
    }
  };

  const handleRemoveSkillFromResume = (skillToRemove: string) => {
    setEditSkills(editSkills.filter((s) => s !== skillToRemove));
  };

  const handleSaveSkills = async () => {
    if (!editingResume) return;
    setSavingSkills(true);
    try {
      const updated = await candidateApi.updateResumeSkills(editingResume.id, editSkills);
      setResumes((prev) =>
        prev.map((r) => (r.id === updated.id ? updated : r))
      );
      setEditingResume(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update extracted skills");
    } finally {
      setSavingSkills(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-8">
      {/* Page Title */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Resume Documents & Versioning
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Upload and manage versioned resume documents. Each resume is securely parsed, scanned for malware, and hashed with SHA-256 deduplication.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Note: Connect your session to sync live resumes ({error})</span>
        </div>
      )}

      {/* Upload Dropzone */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <h2 className="text-base font-bold text-slate-900 dark:text-white">
          Upload New Resume Version
        </h2>
        <ResumeUploadDropzone onUploadSuccess={() => loadResumes()} />
      </div>

      {/* Resumes List */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            Your Uploaded Resumes ({resumes.length})
          </h2>
          <span className="text-xs text-slate-500">
            SHA-256 Deduplicated
          </span>
        </div>

        {loading ? (
          <div className="py-12 flex flex-col items-center justify-center space-y-2">
            <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
            <p className="text-xs text-slate-500">Loading your resumes...</p>
          </div>
        ) : resumes.length === 0 ? (
          <div className="py-12 text-center text-slate-400 text-sm">
            No resume uploaded yet. Upload your PDF or DOCX resume above.
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {resumes.map((resume) => (
              <div
                key={resume.id}
                className="py-4 flex flex-col lg:flex-row lg:items-center justify-between gap-4"
              >
                <div className="flex items-start gap-3">
                  <div className="p-2.5 bg-primary-50 dark:bg-primary-950/40 text-primary-600 dark:text-primary-400 rounded-xl shrink-0 mt-0.5">
                    <FileText className="w-6 h-6" />
                  </div>
                  <div className="space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <p className="text-sm font-bold text-slate-900 dark:text-white">
                        {resume.file_name}
                      </p>
                      <span className="px-2 py-0.5 text-[10px] font-bold uppercase rounded-md bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                        v{resume.version_number}
                      </span>
                      {resume.is_default && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-md bg-emerald-50 dark:bg-emerald-950/50 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                          <CheckCircle className="w-3 h-3" /> Default
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {formatFileSize(resume.file_size_bytes)} &bull; Uploaded on {new Date(resume.uploaded_at).toLocaleDateString()} &bull; Hash: {resume.sha256_hash.substring(0, 10)}...
                    </p>

                    {/* Extracted skills snippet */}
                    {resume.extracted_skills && resume.extracted_skills.length > 0 && (
                      <div className="pt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] font-medium text-slate-500">Skills ({resume.extracted_skills.length}):</span>
                        {resume.extracted_skills.slice(0, 6).map((skill, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded"
                          >
                            {skill}
                          </span>
                        ))}
                        {resume.extracted_skills.length > 6 && (
                          <span className="text-[10px] text-slate-400">
                            +{resume.extracted_skills.length - 6} more
                          </span>
                        )}
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex items-center gap-2 self-end lg:self-center">
                  {!resume.is_default && (
                    <button
                      type="button"
                      onClick={() => handleSetDefault(resume.id)}
                      className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                      title="Set as Default Resume"
                    >
                      <Star className="w-3.5 h-3.5" /> Make Default
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => handleOpenEditSkills(resume)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-primary-700 dark:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-950/40 rounded-lg transition-colors"
                    title="Review & Correct Extracted Skills"
                  >
                    <Edit2 className="w-3.5 h-3.5" /> Review Skills
                  </button>

                  {resume.extracted_text_snippet && (
                    <button
                      type="button"
                      onClick={() => setPreviewResume(resume)}
                      className="p-1.5 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                      title="Preview Extracted Text"
                    >
                      <Eye className="w-4 h-4" />
                    </button>
                  )}

                  <button
                    type="button"
                    onClick={() => handleDownload(resume.id)}
                    className="p-1.5 text-slate-500 hover:text-slate-700 dark:hover:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
                    title="Download Original Resume"
                  >
                    <Download className="w-4 h-4" />
                  </button>

                  <button
                    type="button"
                    onClick={() => handleDelete(resume.id)}
                    className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30 rounded-lg transition-colors"
                    title="Delete Resume"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Extracted Skills Correction Modal */}
      {editingResume && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Review & Correct Extracted Skills
                </h3>
                <p className="text-xs text-slate-500">
                  {editingResume.file_name} (v{editingResume.version_number})
                </p>
              </div>
              <button
                onClick={() => setEditingResume(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400">
              Our AI parser extracts skills from your resume. You can add missing skills or remove false positives before applying to positions.
            </p>

            <div className="flex gap-2">
              <input
                type="text"
                value={newSkillInput}
                onChange={(e) => setNewSkillInput(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    e.preventDefault();
                    handleAddSkillToResume();
                  }
                }}
                placeholder="Add missing skill..."
                className="flex-1 px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
              />
              <button
                type="button"
                onClick={handleAddSkillToResume}
                className="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 text-xs font-semibold rounded-lg hover:bg-slate-200"
              >
                <Plus className="w-4 h-4" />
              </button>
            </div>

            <div className="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto p-2 border border-slate-100 dark:border-slate-800 rounded-xl">
              {editSkills.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-1 px-2.5 py-1 text-xs font-medium bg-primary-50 dark:bg-primary-950/50 text-primary-700 dark:text-primary-300 rounded-md"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => handleRemoveSkillFromResume(skill)}
                    className="hover:text-red-500"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
              {editSkills.length === 0 && (
                <span className="text-xs text-slate-400 italic">No skills in this resume.</span>
              )}
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setEditingResume(null)}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={savingSkills}
                onClick={handleSaveSkills}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5"
              >
                {savingSkills ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                Save Corrections
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Extracted Text Snippet Preview Modal */}
      {previewResume && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Extracted Document Text
                </h3>
                <p className="text-xs text-slate-500">{previewResume.file_name}</p>
              </div>
              <button
                onClick={() => setPreviewResume(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl text-xs font-mono text-slate-700 dark:text-slate-300 max-h-72 overflow-y-auto whitespace-pre-wrap leading-relaxed">
              {previewResume.extracted_text_snippet || "No preview snippet available."}
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setPreviewResume(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-semibold rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
