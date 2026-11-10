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
  Shield,
  Info,
  Sparkles,
  Lock,
  Briefcase,
  GraduationCap,
  Award,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import { ResumeUploadDropzone } from "@/components/candidate/ResumeUploadDropzone";
import type { CandidateResume, ResumeExtractionResponse } from "@/types/candidate";

export default function CandidateResumesPage() {
  const [resumes, setResumes] = useState<CandidateResume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Skill & structured extraction review modal state
  const [reviewResume, setReviewResume] = useState<CandidateResume | null>(null);
  const [extractionData, setExtractionData] = useState<ResumeExtractionResponse | null>(null);
  const [loadingExtraction, setLoadingExtraction] = useState(false);
  const [editSkills, setEditSkills] = useState<string[]>([]);
  const [newSkillInput, setNewSkillInput] = useState("");
  const [savingSkills, setSavingSkills] = useState(false);
  const [syncingProfile, setSyncingProfile] = useState(false);
  const [syncSuccess, setSyncSuccess] = useState(false);

  // Extracted snippet preview modal
  const [previewResume, setPreviewResume] = useState<CandidateResume | null>(null);

  // Defensibility retention info modal
  const [retentionResume, setRetentionResume] = useState<CandidateResume | null>(null);

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

  const handleDelete = async (resume: CandidateResume) => {
    if (resume.has_active_applications) {
      setRetentionResume(resume);
      return;
    }

    if (!confirm(`Are you sure you want to delete ${resume.file_name}? This action cannot be undone.`)) {
      return;
    }
    try {
      await candidateApi.deleteResume(resume.id);
      setResumes((prev) => prev.filter((r) => r.id !== resume.id));
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

  const handleOpenReview = async (resume: CandidateResume) => {
    setReviewResume(resume);
    setEditSkills([...(resume.extracted_skills || [])]);
    setSyncSuccess(false);
    setLoadingExtraction(true);
    try {
      const extraction = await candidateApi.getResumeExtraction(resume.id);
      setExtractionData(extraction);
      if (extraction.skills_extracted && extraction.skills_extracted.length > 0) {
        setEditSkills(extraction.skills_extracted);
      }
    } catch {
      // Fallback to local resume fields if extraction endpoint fails
      setExtractionData(null);
    } finally {
      setLoadingExtraction(false);
    }
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
    if (!reviewResume) return;
    setSavingSkills(true);
    try {
      const updated = await candidateApi.updateResumeSkills(reviewResume.id, editSkills);
      setResumes((prev) =>
        prev.map((r) => (r.id === updated.id ? { ...r, extracted_skills: editSkills } : r))
      );
      setReviewResume(null);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update extracted skills");
    } finally {
      setSavingSkills(false);
    }
  };

  const handleSyncToProfile = async () => {
    if (!reviewResume) return;
    setSyncingProfile(true);
    try {
      await candidateApi.syncResumeSkillsToProfile(reviewResume.id);
      setSyncSuccess(true);
      setTimeout(() => setSyncSuccess(false), 3000);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to synchronize skills to profile");
    } finally {
      setSyncingProfile(false);
    }
  };

  const formatFileSize = (bytes: number) => {
    if (bytes < 1024) return `${bytes} B`;
    if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
    return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  };

  return (
    <div className="space-y-8">
      {/* Page Title & Breadcrumbs */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Resume Documents & Versioning
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Upload and manage candidate resumes in PDF and Word DOCX formats. Each document is securely hashed with SHA-256 deduplication and retained for audit defensibility.
        </p>
      </div>

      {/* Accurate Capability & Processing Status Notice (Step 4.1.4 Requirement 5) */}
      <div className="flex items-start gap-3 p-4 bg-sky-50 dark:bg-sky-950/40 border border-sky-200 dark:border-sky-800 rounded-2xl text-xs text-sky-900 dark:text-sky-200">
        <Info className="w-4 h-4 shrink-0 text-sky-600 dark:text-sky-400 mt-0.5" />
        <div className="space-y-1">
          <p className="font-semibold">Processing Pipeline Status & Capabilities</p>
          <p className="text-sky-700 dark:text-sky-300">
            Direct digital text extraction is fully active for native PDF and Word (.docx) documents. Scanned image OCR is currently unconfigured in this deployment; image-only resumes will require text-layer documents. File validation conforms to private S3 object isolation and fail-closed malware checking.
          </p>
        </div>
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
          <span className="text-xs text-slate-500 font-medium">
            SHA-256 Deduplicated & Defensible
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
                      {resume.has_active_applications && (
                        <span className="inline-flex items-center gap-1 px-2 py-0.5 text-[10px] font-bold rounded-md bg-purple-50 dark:bg-purple-950/50 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800">
                          <Lock className="w-3 h-3" /> Application Retained
                        </span>
                      )}
                    </div>
                    <p className="text-xs text-slate-500 dark:text-slate-400">
                      {formatFileSize(resume.file_size_bytes)} &bull; Uploaded on {new Date(resume.uploaded_at).toLocaleDateString()} &bull; Digest: {resume.sha256_hash.substring(0, 10)}...
                    </p>

                    {/* Extracted skills snippet */}
                    {resume.extracted_skills && resume.extracted_skills.length > 0 && (
                      <div className="pt-1.5 flex flex-wrap items-center gap-1.5">
                        <span className="text-[11px] font-medium text-slate-500">Extracted Skills ({resume.extracted_skills.length}):</span>
                        {resume.extracted_skills.slice(0, 6).map((skill, i) => (
                          <span
                            key={i}
                            className="text-[10px] px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded font-medium"
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
                    onClick={() => handleOpenReview(resume)}
                    className="inline-flex items-center gap-1 px-3 py-1.5 text-xs font-semibold text-primary-700 dark:text-primary-300 hover:bg-primary-50 dark:hover:bg-primary-950/40 rounded-lg transition-colors"
                    title="Review Extracted Skills and Profile Data"
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
                    onClick={() => handleDelete(resume)}
                    className={`p-1.5 rounded-lg transition-colors ${
                      resume.has_active_applications
                        ? "text-slate-300 dark:text-slate-600 hover:text-amber-600 hover:bg-amber-50 dark:hover:bg-amber-950/30"
                        : "text-slate-400 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                    }`}
                    title={resume.has_active_applications ? "Protected by Application Retention" : "Delete Resume"}
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Extracted Skills & Structured Review Modal */}
      {reviewResume && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-2xl w-full p-6 space-y-4 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                  <Sparkles className="w-5 h-5 text-primary-600" />
                  Candidate Extraction Review & Verification
                </h3>
                <p className="text-xs text-slate-500">
                  {reviewResume.file_name} (v{reviewResume.version_number}) &bull; SHA-256 Verified
                </p>
              </div>
              <button
                onClick={() => setReviewResume(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {loadingExtraction ? (
              <div className="py-8 flex flex-col items-center justify-center space-y-2">
                <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
                <p className="text-xs text-slate-500">Parsing structured resume fields...</p>
              </div>
            ) : (
              <div className="space-y-4">
                {/* Structured contact & summary preview if extracted */}
                {extractionData?.extracted_data && (
                  <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-2 border border-slate-100 dark:border-slate-800 text-xs">
                    <div className="font-semibold text-slate-700 dark:text-slate-300">
                      Extracted Candidate Information:
                    </div>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-slate-600 dark:text-slate-400">
                      {extractionData.extracted_data.name && (
                        <div>
                          <span className="font-medium text-slate-500">Name:</span> {extractionData.extracted_data.name}
                        </div>
                      )}
                      {extractionData.extracted_data.email && (
                        <div>
                          <span className="font-medium text-slate-500">Email:</span> {extractionData.extracted_data.email}
                        </div>
                      )}
                      {extractionData.extracted_data.phone && (
                        <div>
                          <span className="font-medium text-slate-500">Phone:</span> {extractionData.extracted_data.phone}
                        </div>
                      )}
                    </div>
                    {extractionData.extracted_data.summary && (
                      <p className="text-slate-600 dark:text-slate-400 italic pt-1 border-t border-slate-200 dark:border-slate-700">
                        &quot;{extractionData.extracted_data.summary}&quot;
                      </p>
                    )}
                  </div>
                )}

                {/* Skills Verification Section */}
                <div className="space-y-2">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-bold text-slate-800 dark:text-slate-200">
                      Skills Extracted & Verified ({editSkills.length})
                    </label>
                    <span className="text-[10px] text-slate-400">
                      Add missing skills or remove false positives
                    </span>
                  </div>

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
                      placeholder="Add verified skill (e.g., Python, Docker, Kubernetes)..."
                      className="flex-1 px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:outline-none focus:ring-1 focus:ring-primary-500"
                    />
                    <button
                      type="button"
                      onClick={handleAddSkillToResume}
                      className="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 text-xs font-semibold rounded-lg hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                    >
                      <Plus className="w-4 h-4" />
                    </button>
                  </div>

                  <div className="flex flex-wrap gap-1.5 max-h-40 overflow-y-auto p-2.5 border border-slate-200 dark:border-slate-800 rounded-xl bg-slate-50/50 dark:bg-slate-900/50">
                    {editSkills.map((skill) => (
                      <span
                        key={skill}
                        className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs font-medium bg-primary-50 dark:bg-primary-950/50 text-primary-700 dark:text-primary-300 border border-primary-200/50 rounded-md"
                      >
                        <span>{skill}</span>
                        <span className="text-[9px] px-1 py-0.2 bg-primary-100 dark:bg-primary-900/60 rounded text-primary-800 dark:text-primary-200 font-mono">
                          Verified
                        </span>
                        <button
                          type="button"
                          onClick={() => handleRemoveSkillFromResume(skill)}
                          className="hover:text-red-500 ml-0.5"
                          title={`Remove ${skill}`}
                        >
                          <X className="w-3 h-3" />
                        </button>
                      </span>
                    ))}
                    {editSkills.length === 0 && (
                      <span className="text-xs text-slate-400 italic">No skills currently listed in this resume.</span>
                    )}
                  </div>
                </div>

                {/* Additional Sections Accordion / Preview */}
                {extractionData?.extracted_data && (
                  <div className="space-y-2 pt-2 border-t border-slate-100 dark:border-slate-800">
                    <p className="text-xs font-bold text-slate-700 dark:text-slate-300">
                      Additional Extracted Portfolio Sections:
                    </p>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-2 text-xs">
                      <div className="p-2.5 bg-slate-50 dark:bg-slate-800/40 rounded-lg flex items-center gap-2">
                        <Briefcase className="w-4 h-4 text-slate-500 shrink-0" />
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-slate-200">
                            {extractionData.extracted_data.experience.length} Experience
                          </p>
                          <p className="text-[10px] text-slate-400">Position records</p>
                        </div>
                      </div>
                      <div className="p-2.5 bg-slate-50 dark:bg-slate-800/40 rounded-lg flex items-center gap-2">
                        <GraduationCap className="w-4 h-4 text-slate-500 shrink-0" />
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-slate-200">
                            {extractionData.extracted_data.education.length} Education
                          </p>
                          <p className="text-[10px] text-slate-400">Degrees & institutions</p>
                        </div>
                      </div>
                      <div className="p-2.5 bg-slate-50 dark:bg-slate-800/40 rounded-lg flex items-center gap-2">
                        <Award className="w-4 h-4 text-slate-500 shrink-0" />
                        <div>
                          <p className="font-semibold text-slate-800 dark:text-slate-200">
                            {extractionData.extracted_data.certifications.length} Certifications
                          </p>
                          <p className="text-[10px] text-slate-400">Verified credentials</p>
                        </div>
                      </div>
                    </div>
                  </div>
                )}

                {syncSuccess && (
                  <div className="p-3 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 rounded-xl text-xs text-emerald-800 dark:text-emerald-300 flex items-center gap-2">
                    <CheckCircle className="w-4 h-4 text-emerald-600" />
                    <span>Skills successfully synchronized to your permanent candidate profile!</span>
                  </div>
                )}
              </div>
            )}

            <div className="flex flex-col sm:flex-row items-center justify-between gap-3 pt-3 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                disabled={syncingProfile || editSkills.length === 0}
                onClick={handleSyncToProfile}
                className="w-full sm:w-auto px-3 py-2 text-xs font-semibold text-primary-700 dark:text-primary-300 bg-primary-50 dark:bg-primary-950/40 hover:bg-primary-100 rounded-lg transition-colors flex items-center justify-center gap-1.5 disabled:opacity-50"
              >
                {syncingProfile ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <Sparkles className="w-3.5 h-3.5" />}
                Apply to Verified Profile
              </button>

              <div className="flex items-center gap-2 w-full sm:w-auto justify-end">
                <button
                  type="button"
                  onClick={() => setReviewResume(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 dark:text-slate-400 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={savingSkills}
                  onClick={handleSaveSkills}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5 transition-colors"
                >
                  {savingSkills ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : <CheckCircle className="w-3.5 h-3.5" />}
                  Save Resume Skills
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Extracted Text Snippet Preview Modal */}
      {previewResume && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Extracted Document Text
                </h3>
                <p className="text-xs text-slate-500">{previewResume.file_name} (v{previewResume.version_number})</p>
              </div>
              <button
                onClick={() => setPreviewResume(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl text-xs font-mono text-slate-700 dark:text-slate-300 max-h-72 overflow-y-auto whitespace-pre-wrap leading-relaxed">
              {previewResume.extracted_text_snippet || "No preview snippet available."}
            </div>

            <div className="flex justify-between items-center pt-2">
              <span className="text-[11px] text-slate-400">
                SHA-256: {previewResume.sha256_hash.substring(0, 16)}...
              </span>
              <button
                type="button"
                onClick={() => setPreviewResume(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-semibold rounded-lg transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Defensibility Retention Info Modal */}
      {retentionResume && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center gap-3 text-amber-600 dark:text-amber-400">
              <Shield className="w-6 h-6 shrink-0" />
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Application Retention Protection
              </h3>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Resume <span className="font-semibold text-slate-800 dark:text-slate-200">{retentionResume.file_name} (v{retentionResume.version_number})</span> is associated with active or submitted job applications. Under compliance, audit defensibility, and record retention requirements, historical resume snapshots cannot be deleted while linked applications exist.
            </p>

            <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl text-xs text-slate-500 space-y-1">
              <p className="font-medium text-slate-700 dark:text-slate-300">Defensibility Guarantees:</p>
              <ul className="list-disc pl-4 space-y-0.5 text-[11px]">
                <li>Preserves cryptographic SHA-256 evidence of submission.</li>
                <li>You may upload newer resume versions at any time.</li>
                <li>You can set another resume as your active default.</li>
              </ul>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="button"
                onClick={() => setRetentionResume(null)}
                className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-lg transition-colors"
              >
                Understood
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
