"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Building2,
  MapPin,
  Bookmark,
  DollarSign,
  Calendar,
  Clock,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  Briefcase,
  Share2,
  Sparkles,
  ExternalLink,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type { JobDetail } from "@/types/candidate";

export default function CandidateJobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = params?.id as string;

  const [job, setJob] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isSaved, setIsSaved] = useState(false);
  const [savingAction, setSavingAction] = useState(false);
  const [copiedLink, setCopiedLink] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    async function loadJob() {
      try {
        setLoading(true);
        setError(null);

        // Fetch job detail & saved jobs list in parallel to verify saved status
        const [jobRes, savedList] = await Promise.allSettled([
          candidateApi.getJob(jobId),
          candidateApi.getSavedJobs(),
        ]);

        if (jobRes.status === "fulfilled") {
          setJob(jobRes.value);
          // If job object carries is_saved flag
          if (typeof jobRes.value.is_saved === "boolean") {
            setIsSaved(jobRes.value.is_saved);
          }
        } else {
          setError(
            jobRes.reason instanceof Error
              ? jobRes.reason.message
              : "Unable to load job opportunity details"
          );
        }

        if (savedList.status === "fulfilled" && Array.isArray(savedList.value)) {
          const found = savedList.value.some((s) => s.job_id === jobId);
          if (found) setIsSaved(true);
        }
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load job requisition");
      } finally {
        setLoading(false);
      }
    }

    loadJob();
  }, [jobId]);

  const handleToggleSave = async () => {
    if (!jobId || savingAction) return;
    try {
      setSavingAction(true);
      if (isSaved) {
        await candidateApi.unsaveJob(jobId);
        setIsSaved(false);
      } else {
        await candidateApi.saveJob(jobId);
        setIsSaved(true);
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update saved job");
    } finally {
      setSavingAction(false);
    }
  };

  const handleShare = async () => {
    try {
      if (typeof window !== "undefined") {
        await navigator.clipboard.writeText(window.location.href);
        setCopiedLink(true);
        setTimeout(() => setCopiedLink(false), 2500);
      }
    } catch {
      // ignore clipboard error
    }
  };

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center space-y-3 max-w-4xl mx-auto">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        <p className="text-xs text-slate-500 font-medium">Loading position requisition...</p>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="max-w-3xl mx-auto py-16 space-y-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 text-center space-y-3 shadow-sm">
          <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Position Not Found or Unavailable
          </h2>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            {error ||
              "The requested position could not be found or may have been unlisted by the hiring organization."}
          </p>
          <div className="pt-2">
            <Link
              href="/candidate/jobs"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to Job Search</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const skillsList = job.required_skills || job.skills_required || [];
  const isExpired = Boolean(job.is_expired);
  const hasApplied = Boolean(job.has_applied);

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Navigation Breadcrumb */}
      <div className="flex items-center justify-between">
        <Link
          href="/candidate/jobs"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to Open Positions</span>
        </Link>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleShare}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-slate-200 dark:border-slate-800 text-xs font-medium text-slate-700 dark:text-slate-300 rounded-lg hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
          >
            <Share2 className="w-3.5 h-3.5" />
            <span>{copiedLink ? "Link Copied!" : "Share"}</span>
          </button>

          <button
            type="button"
            onClick={handleToggleSave}
            disabled={savingAction}
            className={`inline-flex items-center gap-1.5 px-3.5 py-1.5 border rounded-lg text-xs font-semibold transition-colors ${
              isSaved
                ? "bg-amber-50 dark:bg-amber-950/40 border-amber-200 dark:border-amber-800 text-amber-700 dark:text-amber-300"
                : "border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
            }`}
          >
            <Bookmark className={`w-3.5 h-3.5 ${isSaved ? "fill-current" : ""}`} />
            <span>{isSaved ? "Saved" : "Save Job"}</span>
          </button>
        </div>
      </div>

      {/* Expired or Closed Banner */}
      {isExpired && (
        <div className="flex items-center gap-2.5 p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-2xl text-xs text-amber-800 dark:text-amber-300">
          <Clock className="w-4 h-4 text-amber-600 shrink-0" />
          <div>
            <strong>Position Closed:</strong> The application deadline for this position has passed. It is preserved for reference but is no longer accepting new submissions.
          </div>
        </div>
      )}

      {/* Applied Banner */}
      {hasApplied && (
        <div className="flex items-center justify-between p-4 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-800 rounded-2xl text-xs text-blue-900 dark:text-blue-200">
          <div className="flex items-center gap-2">
            <CheckCircle2 className="w-4 h-4 text-blue-600 shrink-0" />
            <span>
              You have already submitted an application for this position.
            </span>
          </div>
          <Link
            href="/candidate/applications"
            className="font-semibold underline hover:text-blue-700 dark:hover:text-blue-100 flex items-center gap-1"
          >
            <span>Track Application</span>
            <ExternalLink className="w-3 h-3" />
          </Link>
        </div>
      )}

      {/* Header Requisition Card */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 sm:p-8 shadow-sm space-y-5">
        <div className="space-y-3">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div>
              <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
                {job.title}
              </h1>

              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs sm:text-sm text-slate-500 mt-2">
                {job.organization_name && (
                  <span className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                    <Building2 className="w-4 h-4 text-primary-600" />
                    {job.organization_name}
                  </span>
                )}
                {job.department && (
                  <span>Department: {job.department}</span>
                )}
                {job.location && (
                  <span className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                    <MapPin className="w-4 h-4 text-slate-400" />
                    {job.location}
                  </span>
                )}
              </div>
            </div>

            {/* Quick action buttons */}
            <div className="flex items-center gap-3">
              {hasApplied ? (
                <Link
                  href="/candidate/applications"
                  className="px-5 py-2.5 bg-blue-600 hover:bg-blue-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors inline-flex items-center gap-1.5"
                >
                  <CheckCircle2 className="w-3.5 h-3.5" />
                  View Application
                </Link>
              ) : isExpired ? (
                <button
                  type="button"
                  disabled
                  className="px-5 py-2.5 bg-slate-200 dark:bg-slate-800 text-slate-400 text-xs font-semibold rounded-xl cursor-not-allowed"
                >
                  Applications Closed
                </button>
              ) : (
                <button
                  type="button"
                  onClick={() => {
                    // Navigate to Find Jobs with modal trigger or preserve seamless apply
                    router.push(`/candidate/jobs?apply_job=${job.id}`);
                  }}
                  className="px-6 py-2.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                >
                  Apply for Position
                </button>
              )}
            </div>
          </div>

          {/* Badges */}
          <div className="flex flex-wrap gap-2 text-xs pt-1">
            <span className="px-2.5 py-1 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 rounded-lg font-medium capitalize">
              {job.remote_type}
            </span>
            <span className="px-2.5 py-1 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded-lg font-medium capitalize">
              {job.employment_type.replace("_", " ")}
            </span>
            {job.experience_level && (
              <span className="px-2.5 py-1 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 rounded-lg font-medium">
                {job.experience_level}
              </span>
            )}
            {(job.salary_min || job.salary_max) && (
              <span className="px-2.5 py-1 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded-lg font-medium flex items-center gap-1">
                <DollarSign className="w-3.5 h-3.5" />
                {job.salary_min ? `$${job.salary_min.toLocaleString()}` : ""}
                {job.salary_max ? ` - $${job.salary_max.toLocaleString()}` : ""}{" "}
                {job.salary_currency || "USD"} / year
              </span>
            )}
          </div>
        </div>

        {/* Requisition Meta Details */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-slate-100 dark:border-slate-800 text-xs">
          <div>
            <span className="text-slate-400 block font-medium">Published</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 flex items-center gap-1">
              <Calendar className="w-3 h-3 text-slate-400" />
              {new Date(job.published_at || job.created_at || Date.now()).toLocaleDateString()}
            </span>
          </div>

          <div>
            <span className="text-slate-400 block font-medium">Deadline</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 flex items-center gap-1">
              <Clock className="w-3 h-3 text-slate-400" />
              {job.application_deadline
                ? new Date(job.application_deadline).toLocaleDateString()
                : "Open until filled"}
            </span>
          </div>

          <div>
            <span className="text-slate-400 block font-medium">Work Arrangement</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 capitalize">
              {job.remote_type}
            </span>
          </div>

          <div>
            <span className="text-slate-400 block font-medium">Employment Type</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 capitalize">
              {job.employment_type.replace("_", " ")}
            </span>
          </div>
        </div>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Description & Details */}
        <div className="lg:col-span-2 space-y-6">
          {/* Description Section */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-primary-600" />
              <span>Role Overview & Responsibilities</span>
            </h2>

            <div className="prose dark:prose-invert max-w-none text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
              {job.description}
            </div>
          </div>

          {/* Requirements Section if available */}
          {job.requirements && (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
              <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Sparkles className="w-4 h-4 text-primary-600" />
                <span>Qualifications & Requirements</span>
              </h2>

              <div className="prose dark:prose-invert max-w-none text-xs sm:text-sm text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
                {job.requirements}
              </div>
            </div>
          )}
        </div>

        {/* Right Column: Skills & Organization Sidebar */}
        <div className="space-y-6">
          {/* Required Skills Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Required Skills & Competencies
            </h3>
            {skillsList.length > 0 ? (
              <div className="flex flex-wrap gap-1.5">
                {skillsList.map((skill, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 bg-slate-50 dark:bg-slate-800 text-slate-700 dark:text-slate-300 border border-slate-200 dark:border-slate-700 rounded-lg text-xs font-medium"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            ) : (
              <p className="text-xs text-slate-400">
                No specific mandatory skills specified for this position.
              </p>
            )}
          </div>

          {/* Preferred Skills Card if present */}
          {job.preferred_skills && job.preferred_skills.length > 0 && (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                Preferred Qualifications
              </h3>
              <div className="flex flex-wrap gap-1.5">
                {job.preferred_skills.map((skill, idx) => (
                  <span
                    key={idx}
                    className="px-2.5 py-1 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-800 rounded-lg text-xs font-medium"
                  >
                    {skill}
                  </span>
                ))}
              </div>
            </div>
          )}

          {/* Security & Integrity Assurance Card */}
          <div className="bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 space-y-2.5">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-slate-200">
              <CheckCircle2 className="w-4 h-4 text-emerald-600" />
              <span>Verified Enterprise Requisition</span>
            </div>
            <p className="text-[11px] text-slate-500 leading-relaxed">
              This position is posted directly by the verified organization. Candidate applications and resume snapshots are encrypted and retained strictly in compliance with EEOC, Section 503, and OFCCP privacy standards.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
