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
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type { SavedJobItem } from "@/types/candidate";

export default function CandidateSavedJobsPage() {
  const [savedJobs, setSavedJobs] = useState<SavedJobItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadSavedJobs = async () => {
    try {
      setLoading(true);
      const data = await candidateApi.getSavedJobs();
      setSavedJobs(data);
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
      await candidateApi.unsaveJob(jobId);
      setSavedJobs((prev) => prev.filter((item) => item.job_id !== jobId));
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to remove saved job");
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Saved Jobs
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Bookmarked positions you want to review or apply to later.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Note: Connect your session to sync live saved jobs ({error})</span>
        </div>
      )}

      {loading ? (
        <div className="py-16 flex flex-col items-center justify-center space-y-2">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
          <p className="text-xs text-slate-500">Loading your saved jobs...</p>
        </div>
      ) : savedJobs.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-12 text-center space-y-3">
          <Bookmark className="w-10 h-10 text-slate-400 mx-auto" />
          <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
            No saved jobs yet
          </p>
          <p className="text-xs text-slate-500">
            Browse open positions and click the bookmark icon to save roles for later.
          </p>
          <div className="pt-2">
            <Link
              href="/candidate/jobs"
              className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl transition-colors"
            >
              <Briefcase className="w-3.5 h-3.5" /> Explore Jobs
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {savedJobs.map((item) => (
            <div
              key={item.id}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm flex flex-col justify-between space-y-4"
            >
              <div className="space-y-2">
                <div className="flex items-start justify-between gap-3">
                  <h3 className="text-base font-bold text-slate-900 dark:text-white">
                    {item.job.title}
                  </h3>
                  <button
                    type="button"
                    onClick={() => handleRemove(item.job_id)}
                    className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                    title="Remove from saved jobs"
                  >
                    <Trash2 className="w-4 h-4" />
                  </button>
                </div>

                <div className="flex items-center gap-3 text-xs text-slate-500">
                  {item.job.department && (
                    <span className="flex items-center gap-1">
                      <Building2 className="w-3.5 h-3.5" />
                      {item.job.department}
                    </span>
                  )}
                  {item.job.location && (
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5" />
                      {item.job.location}
                    </span>
                  )}
                </div>

                <div className="flex flex-wrap gap-1.5 text-[11px] pt-1">
                  <span className="px-2 py-0.5 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 rounded font-medium capitalize">
                    {item.job.remote_type}
                  </span>
                  <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded font-medium capitalize">
                    {item.job.employment_type.replace("_", " ")}
                  </span>
                </div>
              </div>

              <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                <span className="text-[11px] text-slate-400">
                  Saved on {new Date(item.saved_at).toLocaleDateString()}
                </span>
                <Link
                  href="/candidate/jobs"
                  className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                >
                  Apply in Jobs <ChevronRight className="w-3.5 h-3.5" />
                </Link>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
