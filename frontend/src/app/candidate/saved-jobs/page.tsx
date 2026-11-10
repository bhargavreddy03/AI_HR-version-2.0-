"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Bookmark,
  Building2,
  MapPin,
  Trash2,
  Briefcase,
  Loader2,
  ChevronRight,
  AlertCircle,
  Clock,
  CheckCircle2,
  DollarSign,
  AlertTriangle,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type { SavedJobItem } from "@/types/candidate";

export default function CandidateSavedJobsPage() {
  const [savedJobs, setSavedJobs] = useState<SavedJobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [removingId, setRemovingId] = useState<string | null>(null);

  const loadSavedJobs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await candidateApi.getSavedJobs();
      setSavedJobs(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load saved jobs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadSavedJobs();
  }, []);

  const handleRemove = async (jobId: string) => {
    try {
      setRemovingId(jobId);
      await candidateApi.unsaveJob(jobId);
      setSavedJobs((prev) => prev.filter((item) => item.job_id !== jobId));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to remove saved job");
    } finally {
      setRemovingId(null);
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Saved Opportunities
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Bookmarked positions you want to review, track, or apply to later.
          </p>
        </div>

        <Link
          href="/candidate/jobs"
          className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors self-start sm:self-auto"
        >
          <Briefcase className="w-3.5 h-3.5" />
          <span>Explore More Jobs</span>
        </Link>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-xs text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
          <span>Note: Connect your session to sync live saved jobs ({error})</span>
        </div>
      )}

      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center space-y-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
          <p className="text-xs text-slate-500 font-medium">Loading your bookmarked positions...</p>
        </div>
      ) : savedJobs.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-12 text-center space-y-3 shadow-sm">
          <Bookmark className="w-10 h-10 text-slate-400 mx-auto" />
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-200">
            No saved jobs yet
          </h3>
          <p className="text-xs text-slate-500 max-w-sm mx-auto">
            Browse open positions across verified organizations and click the bookmark icon to save roles here.
          </p>
          <div className="pt-2">
            <Link
              href="/candidate/jobs"
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl transition-colors shadow-sm"
            >
              <Briefcase className="w-3.5 h-3.5" />
              <span>Explore Open Roles</span>
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {savedJobs.map((item) => {
            const job = item.job || {};
            const isExpired = Boolean(job.is_expired);
            const hasApplied = Boolean(job.has_applied);

            return (
              <div
                key={item.id || item.job_id}
                className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-300 dark:hover:border-slate-700 transition-all flex flex-col justify-between space-y-4"
              >
                <div className="space-y-3">
                  {/* Header & Delete */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <Link
                        href={`/candidate/jobs/${item.job_id}`}
                        className="text-base font-bold text-slate-900 dark:text-white hover:text-primary-600 transition-colors line-clamp-1"
                      >
                        {job.title}
                      </Link>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                        {job.organization_name && (
                          <span className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                            <Building2 className="w-3.5 h-3.5 text-primary-500" />
                            {job.organization_name}
                          </span>
                        )}
                        {job.department && <span>&bull; {job.department}</span>}
                        {job.location && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5 text-slate-400" />
                            {job.location}
                          </span>
                        )}
                      </div>
                    </div>

                    <button
                      type="button"
                      onClick={() => handleRemove(item.job_id)}
                      disabled={removingId === item.job_id}
                      className="p-1.5 text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors disabled:opacity-50"
                      title="Remove from saved jobs"
                      aria-label="Remove saved job"
                    >
                      {removingId === item.job_id ? (
                        <Loader2 className="w-4 h-4 animate-spin text-slate-400" />
                      ) : (
                        <Trash2 className="w-4 h-4" />
                      )}
                    </button>
                  </div>

                  {/* Status Badges: Expired / Applied */}
                  <div className="flex flex-wrap items-center gap-1.5 text-[11px]">
                    {hasApplied && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-full font-semibold">
                        <CheckCircle2 className="w-3 h-3" />
                        Applied
                      </span>
                    )}

                    {isExpired && (
                      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800 rounded-full font-semibold">
                        <AlertTriangle className="w-3 h-3" />
                        Position Closed / Expired
                      </span>
                    )}

                    {job.remote_type && (
                      <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded font-medium capitalize">
                        {job.remote_type}
                      </span>
                    )}

                    {job.employment_type && (
                      <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded font-medium capitalize">
                        {job.employment_type.replace("_", " ")}
                      </span>
                    )}

                    {(job.salary_min || job.salary_max) && (
                      <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded font-medium flex items-center gap-0.5">
                        <DollarSign className="w-3 h-3" />
                        {job.salary_min ? `${job.salary_min.toLocaleString()}` : ""}
                        {job.salary_max ? ` - ${job.salary_max.toLocaleString()}` : ""}{" "}
                        {job.salary_currency || "USD"}
                      </span>
                    )}
                  </div>
                </div>

                {/* Footer */}
                <div className="pt-2.5 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between text-[11px] text-slate-400">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1">
                      <Clock className="w-3 h-3" />
                      Saved on {new Date(item.saved_at).toLocaleDateString()}
                    </span>
                  </div>

                  <Link
                    href={`/candidate/jobs/${item.job_id}`}
                    className="inline-flex items-center gap-1 px-3 py-1.5 bg-slate-900 text-white dark:bg-white dark:text-slate-900 hover:opacity-90 text-xs font-semibold rounded-lg shadow-sm transition-colors"
                  >
                    <span>View Requisition</span>
                    <ChevronRight className="w-3.5 h-3.5" />
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
