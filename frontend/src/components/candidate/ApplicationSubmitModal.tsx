"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  X,
  FileText,
  CheckCircle2,
  AlertCircle,
  Loader2,
  ChevronRight,
  ChevronLeft,
  Building2,
  MapPin,
  DollarSign,
  ShieldCheck,
  Send,
  Clock,
  ExternalLink,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type {
  JobDetail,
  CandidateResume,
  ApplicationSubmitResponse,
} from "@/types/candidate";

interface ApplicationSubmitModalProps {
  job: JobDetail | null;
  onClose: () => void;
  onSuccess?: () => void;
}

export function ApplicationSubmitModal({
  job,
  onClose,
  onSuccess,
}: ApplicationSubmitModalProps) {
  const [step, setStep] = useState<number>(1);
  const [resumes, setResumes] = useState<CandidateResume[]>([]);
  const [loadingResumes, setLoadingResumes] = useState(true);

  // Form states
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [coverLetter, setCoverLetter] = useState<string>("");
  const [workAuth, setWorkAuth] = useState<string>("authorized");
  const [sponsorshipRequired, setSponsorshipRequired] = useState<string>("no");
  const [earliestStartDate, setEarliestStartDate] = useState<string>("Immediately");
  const [additionalNotes, setAdditionalNotes] = useState<string>("");

  // Consents
  const [dataConsent, setDataConsent] = useState<boolean>(false);
  const [accuracyCertified, setAccuracyCertified] = useState<boolean>(false);

  // Submission state
  const [submitting, setSubmitting] = useState<boolean>(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [submitResult, setSubmitResult] = useState<ApplicationSubmitResponse | null>(null);
  const [idempotencyKey] = useState<string>(() => {
    if (typeof crypto !== "undefined" && crypto.randomUUID) {
      return crypto.randomUUID();
    }
    return `idemp_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`;
  });

  useEffect(() => {
    async function loadResumes() {
      try {
        setLoadingResumes(true);
        const list = await candidateApi.getResumes();
        setResumes(list);
        if (list.length > 0) {
          const def = list.find((r) => r.is_default);
          setSelectedResumeId(def ? def.id : list[0].id);
        }
      } catch {
        // Non-blocking
      } finally {
        setLoadingResumes(false);
      }
    }
    loadResumes();
  }, []);

  if (!job) return null;

  const selectedResume = resumes.find((r) => r.id === selectedResumeId);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!job) return;

    if (!selectedResumeId) {
      setSubmitError("A valid resume version must be selected prior to application submission.");
      return;
    }

    if (!dataConsent || !accuracyCertified) {
      setSubmitError("Please confirm all required statutory consent and accuracy acknowledgments.");
      return;
    }

    setSubmitting(true);
    setSubmitError(null);

    const answersPayload = {
      work_authorization: workAuth,
      visa_sponsorship_required: sponsorshipRequired === "yes",
      earliest_start_date: earliestStartDate,
      additional_notes: additionalNotes.trim() || undefined,
    };

    const consentPayload = {
      data_processing_consent: dataConsent,
      accuracy_certified: accuracyCertified,
      consented_at: new Date().toISOString(),
    };

    try {
      const response = await candidateApi.applyJob(job.id, {
        resume_id: selectedResumeId,
        cover_letter: coverLetter.trim() || undefined,
        answers: answersPayload,
        consent_records: consentPayload,
        idempotency_key: idempotencyKey,
      });

      setSubmitResult(response);
      setStep(5); // Confirmation screen
      if (onSuccess) {
        onSuccess();
      }
    } catch (err: unknown) {
      setSubmitError(
        err instanceof Error
          ? err.message
          : "Failed to submit application. Please check your network and try again."
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-3 sm:p-4 overflow-y-auto">
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-2xl w-full shadow-2xl flex flex-col my-auto max-h-[92vh] overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between bg-slate-50/50 dark:bg-slate-800/30">
          <div>
            <h3 className="text-base sm:text-lg font-bold text-slate-900 dark:text-white">
              Apply for {job.title}
            </h3>
            <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
              {job.organization_name && (
                <span className="font-semibold text-slate-700 dark:text-slate-300">
                  {job.organization_name}
                </span>
              )}
              {job.location && <span>&bull; {job.location}</span>}
              <span className="capitalize">&bull; {job.remote_type}</span>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
            aria-label="Close modal"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Progress Stepper (Hidden on completion) */}
        {step < 5 && (
          <div className="px-6 py-3 border-b border-slate-100 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between text-xs font-semibold text-slate-500 overflow-x-auto">
            <div
              className={`flex items-center gap-1.5 ${
                step >= 1 ? "text-primary-600 dark:text-primary-400" : ""
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${
                  step >= 1
                    ? "bg-primary-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500"
                }`}
              >
                1
              </span>
              <span>Overview</span>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 dark:text-slate-700" />

            <div
              className={`flex items-center gap-1.5 ${
                step >= 2 ? "text-primary-600 dark:text-primary-400" : ""
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${
                  step >= 2
                    ? "bg-primary-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500"
                }`}
              >
                2
              </span>
              <span>Resume</span>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 dark:text-slate-700" />

            <div
              className={`flex items-center gap-1.5 ${
                step >= 3 ? "text-primary-600 dark:text-primary-400" : ""
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${
                  step >= 3
                    ? "bg-primary-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500"
                }`}
              >
                3
              </span>
              <span>Questions</span>
            </div>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 dark:text-slate-700" />

            <div
              className={`flex items-center gap-1.5 ${
                step >= 4 ? "text-primary-600 dark:text-primary-400" : ""
              }`}
            >
              <span
                className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] ${
                  step >= 4
                    ? "bg-primary-600 text-white"
                    : "bg-slate-100 dark:bg-slate-800 text-slate-500"
                }`}
              >
                4
              </span>
              <span>Review & Sign</span>
            </div>
          </div>
        )}

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-4 flex-1">
          {submitError && (
            <div
              role="alert"
              className="flex items-start gap-2.5 p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl text-xs text-red-700 dark:text-red-300"
            >
              <AlertCircle className="w-4 h-4 shrink-0 mt-0.5" />
              <div>{submitError}</div>
            </div>
          )}

          {/* STEP 1: Requisition Overview */}
          {step === 1 && (
            <div className="space-y-4">
              <div className="p-4 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-xl space-y-3 text-xs">
                <div className="font-semibold text-slate-800 dark:text-slate-200 text-sm">
                  Requisition Summary
                </div>
                <div className="grid grid-cols-2 gap-3 text-slate-600 dark:text-slate-300">
                  <div>
                    <span className="text-slate-400 block font-medium">Department</span>
                    <span>{job.department || "General"}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block font-medium">Arrangement</span>
                    <span className="capitalize">{job.remote_type}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block font-medium">Employment Type</span>
                    <span className="capitalize">{job.employment_type.replace("_", " ")}</span>
                  </div>
                  <div>
                    <span className="text-slate-400 block font-medium">Compensation</span>
                    <span>
                      {job.salary_min || job.salary_max
                        ? `$${job.salary_min?.toLocaleString() || "0"} - $${job.salary_max?.toLocaleString() || "0"} ${job.salary_currency || "USD"}`
                        : "Competitive / Market"}
                    </span>
                  </div>
                </div>
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Role Overview
                </label>
                <div className="p-3.5 bg-slate-50/70 dark:bg-slate-800/30 rounded-xl text-xs text-slate-600 dark:text-slate-400 leading-relaxed max-h-36 overflow-y-auto">
                  {job.description}
                </div>
              </div>

              {job.required_skills && job.required_skills.length > 0 && (
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Required Core Skills
                  </label>
                  <div className="flex flex-wrap gap-1.5">
                    {job.required_skills.map((s, idx) => (
                      <span
                        key={idx}
                        className="px-2.5 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-md text-[11px] font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 2: Resume Selection */}
          {step === 2 && (
            <div className="space-y-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                  Select Resume Version
                </h4>
                <p className="text-xs text-slate-500">
                  Choose the resume version you wish to submit. An immutable cryptographic SHA-256 seal of this document will be recorded in compliance with enterprise audit requirements.
                </p>
              </div>

              {loadingResumes ? (
                <div className="py-8 flex flex-col items-center justify-center space-y-2">
                  <Loader2 className="w-6 h-6 animate-spin text-primary-600" />
                  <p className="text-xs text-slate-500">Loading your verified resumes...</p>
                </div>
              ) : resumes.length === 0 ? (
                <div className="p-6 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl text-center space-y-2">
                  <FileText className="w-8 h-8 text-amber-600 mx-auto" />
                  <p className="text-xs font-semibold text-amber-800 dark:text-amber-200">
                    No Resumes Available
                  </p>
                  <p className="text-xs text-amber-700 dark:text-amber-300 max-w-sm mx-auto">
                    You must upload at least one verified resume in your profile before applying.
                  </p>
                  <div className="pt-2">
                    <Link
                      href="/candidate/resumes"
                      className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-amber-700 hover:bg-amber-800 text-white text-xs font-semibold rounded-lg shadow-sm"
                    >
                      <span>Upload Resume Now</span>
                      <ExternalLink className="w-3 h-3" />
                    </Link>
                  </div>
                </div>
              ) : (
                <div className="space-y-2.5 max-h-60 overflow-y-auto">
                  {resumes.map((r) => {
                    const isSelected = r.id === selectedResumeId;
                    return (
                      <label
                        key={r.id}
                        className={`flex items-start gap-3 p-3.5 border rounded-xl cursor-pointer transition-all ${
                          isSelected
                            ? "bg-primary-50/50 dark:bg-primary-950/30 border-primary-500 dark:border-primary-600 ring-1 ring-primary-500"
                            : "border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800/40"
                        }`}
                      >
                        <input
                          type="radio"
                          name="selected_resume"
                          value={r.id}
                          checked={isSelected}
                          onChange={() => setSelectedResumeId(r.id)}
                          className="mt-1 text-primary-600 focus:ring-primary-500"
                        />
                        <div className="flex-1 space-y-1">
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold text-slate-900 dark:text-white">
                              {r.file_name}
                            </span>
                            <span className="text-[10px] font-semibold px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded">
                              v{r.version_number}
                            </span>
                          </div>
                          <div className="flex items-center gap-2 text-[11px] text-slate-500">
                            <span>
                              Uploaded{" "}
                              {new Date(r.uploaded_at || Date.now()).toLocaleDateString()}
                            </span>
                            {r.is_default && (
                              <span className="text-primary-600 font-semibold">&bull; Default</span>
                            )}
                          </div>
                          {r.extracted_skills && r.extracted_skills.length > 0 && (
                            <div className="flex flex-wrap gap-1 pt-1">
                              {r.extracted_skills.slice(0, 4).map((s: string, idx: number) => (
                                <span
                                  key={idx}
                                  className="text-[10px] px-1.5 py-0.5 bg-white dark:bg-slate-800 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 rounded"
                                >
                                  {s}
                                </span>
                              ))}
                            </div>
                          )}
                        </div>
                      </label>
                    );
                  })}
                </div>
              )}

              <div className="flex items-center gap-2 p-3 bg-blue-50 dark:bg-blue-950/30 border border-blue-100 dark:border-blue-900 rounded-xl text-xs text-blue-800 dark:text-blue-300">
                <ShieldCheck className="w-4 h-4 text-blue-600 shrink-0" />
                <span>
                  Your submitted resume cannot be retroactively altered by the hiring organization.
                </span>
              </div>
            </div>
          )}

          {/* STEP 3: Questions & Cover Letter */}
          {step === 3 && (
            <div className="space-y-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                  Application Questionnaire
                </h4>
                <p className="text-xs text-slate-500">
                  Please provide statutory eligibility and availability details for this requisition.
                </p>
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                <div>
                  <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                    Work Authorization *
                  </label>
                  <select
                    value={workAuth}
                    onChange={(e) => setWorkAuth(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                  >
                    <option value="authorized">Legally authorized to work</option>
                    <option value="authorized_needs_sponsorship">Authorized, require sponsorship</option>
                    <option value="not_authorized">Not currently authorized</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                    Visa Sponsorship Needed *
                  </label>
                  <select
                    value={sponsorshipRequired}
                    onChange={(e) => setSponsorshipRequired(e.target.value)}
                    className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                  >
                    <option value="no">No, will not require sponsorship</option>
                    <option value="yes">Yes, will require sponsorship</option>
                  </select>
                </div>
              </div>

              <div className="text-xs">
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  Earliest Available Start Date
                </label>
                <input
                  type="text"
                  value={earliestStartDate}
                  onChange={(e) => setEarliestStartDate(e.target.value)}
                  placeholder="e.g. Immediately, 2 weeks notice, Jan 15"
                  className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>

              <div className="text-xs">
                <label className="block text-slate-700 dark:text-slate-300 font-semibold mb-1">
                  Cover Letter / Note to Hiring Team (Optional)
                </label>
                <textarea
                  rows={4}
                  value={coverLetter}
                  onChange={(e) => setCoverLetter(e.target.value)}
                  placeholder="Highlight your relevant experience, project achievements, or reasons for applying..."
                  className="w-full px-3 py-2 border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>
            </div>
          )}

          {/* STEP 4: Review & Legal Consents */}
          {step === 4 && (
            <div className="space-y-4">
              <div className="space-y-1">
                <h4 className="text-sm font-bold text-slate-900 dark:text-white">
                  Review & Confirm Submission
                </h4>
                <p className="text-xs text-slate-500">
                  Please verify your submission details and complete the mandatory statutory declarations.
                </p>
              </div>

              <div className="p-4 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2 text-xs">
                <div className="flex justify-between py-1 border-b border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-slate-400">Position</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                    {job.title}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-slate-400">Organization</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                    {job.organization_name || "Verified Enterprise"}
                  </span>
                </div>
                <div className="flex justify-between py-1 border-b border-slate-200/60 dark:border-slate-700/60">
                  <span className="text-slate-400">Selected Resume</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                    {selectedResume ? `${selectedResume.file_name} (v${selectedResume.version_number})` : "None"}
                  </span>
                </div>
                <div className="flex justify-between py-1">
                  <span className="text-slate-400">Work Authorization</span>
                  <span className="font-semibold capitalize text-slate-800 dark:text-slate-200">
                    {workAuth.replace("_", " ")}
                  </span>
                </div>
              </div>

              {/* Statutory Declarations & Consents */}
              <div className="space-y-3 pt-1">
                <label className="flex items-start gap-2.5 cursor-pointer text-xs">
                  <input
                    type="checkbox"
                    checked={dataConsent}
                    onChange={(e) => setDataConsent(e.target.checked)}
                    className="mt-0.5 rounded text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-slate-600 dark:text-slate-300 leading-relaxed">
                    <strong>Data Processing Consent:</strong> I consent to the collection, processing, and retention of my application, profile data, and resume by the hiring organization and AI HR Intelligence Platform strictly for recruitment and compliance recordkeeping under applicable data privacy frameworks (EEOC / OFCCP / GDPR).
                  </span>
                </label>

                <label className="flex items-start gap-2.5 cursor-pointer text-xs">
                  <input
                    type="checkbox"
                    checked={accuracyCertified}
                    onChange={(e) => setAccuracyCertified(e.target.checked)}
                    className="mt-0.5 rounded text-primary-600 focus:ring-primary-500"
                  />
                  <span className="text-slate-600 dark:text-slate-300 leading-relaxed">
                    <strong>Accuracy Certification:</strong> I hereby certify that all information submitted in this application and accompanying resume is true, accurate, and complete to the best of my knowledge.
                  </span>
                </label>
              </div>
            </div>
          )}

          {/* STEP 5: Submission Success Confirmation */}
          {step === 5 && submitResult && (
            <div className="py-8 text-center space-y-4">
              <div className="w-14 h-14 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto shadow-sm">
                <CheckCircle2 className="w-8 h-8" />
              </div>

              <div className="space-y-1">
                <h4 className="text-lg font-bold text-slate-900 dark:text-white">
                  Application Submitted Successfully!
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Your application has been sealed and securely delivered to the {job.organization_name || "hiring"} recruitment team.
                </p>
              </div>

              <div className="max-w-md mx-auto p-4 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-xl text-left text-xs space-y-2">
                <div className="flex justify-between">
                  <span className="text-slate-400">Application Reference</span>
                  <span className="font-mono text-slate-700 dark:text-slate-300">
                    {submitResult.id.substring(0, 18)}...
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Submission Date</span>
                  <span className="font-semibold text-slate-700 dark:text-slate-300">
                    {new Date(submitResult.applied_at).toLocaleString()}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Status</span>
                  <span className="px-2 py-0.5 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 rounded font-semibold text-[11px] capitalize">
                    {submitResult.candidate_status}
                  </span>
                </div>
              </div>

              <div className="pt-3 flex flex-col sm:flex-row items-center justify-center gap-2.5">
                <Link
                  href="/candidate/applications"
                  className="w-full sm:w-auto px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors text-center"
                >
                  Track in My Applications
                </Link>
                <button
                  type="button"
                  onClick={onClose}
                  className="w-full sm:w-auto px-5 py-2.5 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 text-xs font-semibold rounded-xl transition-colors"
                >
                  Explore More Jobs
                </button>
              </div>
            </div>
          )}
        </div>

        {/* Modal Footer Controls (Hidden on confirmation step) */}
        {step < 5 && (
          <div className="px-6 py-3.5 border-t border-slate-100 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/20 flex items-center justify-between">
            {step > 1 ? (
              <button
                type="button"
                onClick={() => setStep(step - 1)}
                className="inline-flex items-center gap-1 px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
              >
                <ChevronLeft className="w-3.5 h-3.5" />
                <span>Previous</span>
              </button>
            ) : (
              <button
                type="button"
                onClick={onClose}
                className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
              >
                Cancel
              </button>
            )}

            {step < 4 ? (
              <button
                type="button"
                onClick={() => {
                  if (step === 2 && !selectedResumeId) {
                    setSubmitError("Please select a resume version to continue.");
                    return;
                  }
                  setSubmitError(null);
                  setStep(step + 1);
                }}
                disabled={step === 2 && resumes.length === 0}
                className="inline-flex items-center gap-1 px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
              >
                <span>Continue</span>
                <ChevronRight className="w-3.5 h-3.5" />
              </button>
            ) : (
              <button
                type="button"
                onClick={handleSubmit}
                disabled={submitting || !dataConsent || !accuracyCertified}
                className="inline-flex items-center gap-1.5 px-6 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
              >
                {submitting ? (
                  <Loader2 className="w-3.5 h-3.5 animate-spin" />
                ) : (
                  <Send className="w-3.5 h-3.5" />
                )}
                <span>Confirm & Submit Application</span>
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
