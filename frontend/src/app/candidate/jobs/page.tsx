"use client";

import React, { useState, useEffect } from "react";
import {
  Search,
  MapPin,
  Building2,
  Bookmark,
  Briefcase,
  DollarSign,
  Loader2,
  X,
  CheckCircle,
  AlertCircle,
  Send,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type {
  JobPublicSummary,
  JobDetail,
  CandidateResume,
} from "@/types/candidate";

export default function CandidateJobsPage() {
  const [jobs, setJobs] = useState<JobPublicSummary[]>([]);
  const [savedJobIds, setSavedJobIds] = useState<Set<string>>(new Set());
  const [resumes, setResumes] = useState<CandidateResume[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [searchQuery, setSearchQuery] = useState("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [remoteType, setRemoteType] = useState("");
  const [employmentType, setEmploymentType] = useState("");

  // Apply Modal state
  const [applyingJob, setApplyingJob] = useState<JobDetail | null>(null);
  const [loadingJobDetail, setLoadingJobDetail] = useState(false);
  const [selectedResumeId, setSelectedResumeId] = useState<string>("");
  const [coverLetter, setCoverLetter] = useState("");
  const [submittingApply, setSubmittingApply] = useState(false);
  const [applySuccess, setApplySuccess] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);

  const fetchJobs = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await candidateApi.searchJobs({
        query: searchQuery || undefined,
        department: department || undefined,
        location: location || undefined,
        remote_type: remoteType || undefined,
        employment_type: employmentType || undefined,
      });
      setJobs(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load jobs");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // Initial fetch: jobs, saved jobs, resumes
    async function init() {
      try {
        const [saved, resList] = await Promise.allSettled([
          candidateApi.getSavedJobs(),
          candidateApi.getResumes(),
        ]);
        if (saved.status === "fulfilled") {
          setSavedJobIds(new Set(saved.value.map((s) => s.job_id)));
        }
        if (resList.status === "fulfilled") {
          setResumes(resList.value);
          const def = resList.value.find((r) => r.is_default);
          if (def) setSelectedResumeId(def.id);
          else if (resList.value.length > 0) setSelectedResumeId(resList.value[0].id);
        }
      } catch {
        // non-blocking
      }
      fetchJobs();
    }
    init();
  }, []);

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    fetchJobs();
  };

  const handleToggleSave = async (jobId: string) => {
    const isSaved = savedJobIds.has(jobId);
    try {
      if (isSaved) {
        await candidateApi.unsaveJob(jobId);
        setSavedJobIds((prev) => {
          const next = new Set(prev);
          next.delete(jobId);
          return next;
        });
      } else {
        await candidateApi.saveJob(jobId);
        setSavedJobIds((prev) => new Set(prev).add(jobId));
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to bookmark job");
    }
  };

  const handleOpenApplyModal = async (jobId: string) => {
    setApplyError(null);
    setApplySuccess(false);
    setCoverLetter("");
    setLoadingJobDetail(true);
    try {
      const detail = await candidateApi.getJob(jobId);
      setApplyingJob(detail);
    } catch {
      // Fallback: construct from summary if getJob endpoint fails
      const sum = jobs.find((j) => j.id === jobId);
      if (sum) {
        setApplyingJob({
          ...sum,
          description: "Role responsibilities and requirements for this position.",
          preferred_skills: [],
        });
      }
    } finally {
      setLoadingJobDetail(false);
    }
  };

  const handleSubmitApplication = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!applyingJob) return;
    setSubmittingApply(true);
    setApplyError(null);

    try {
      await candidateApi.applyJob(applyingJob.id, {
        resume_id: selectedResumeId || undefined,
        cover_letter: coverLetter || undefined,
      });
      setApplySuccess(true);
    } catch (err: unknown) {
      setApplyError(err instanceof Error ? err.message : "Failed to submit application");
    } finally {
      setSubmittingApply(false);
    }
  };

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Explore Career Opportunities
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Search and apply to open enterprise roles across verified tenant organizations.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Note: Connect your session to sync live jobs ({error})</span>
        </div>
      )}

      {/* Search & Filter Bar */}
      <form
        onSubmit={handleSearchSubmit}
        className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-4"
      >
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by role title, keyword, or skills (e.g. Backend, FastAPI)..."
              className="w-full pl-10 pr-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="px-5 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
          >
            Search Jobs
          </button>
        </div>

        <div className="grid grid-cols-2 md:grid-cols-4 gap-3 pt-1 text-xs">
          <div>
            <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">Department</label>
            <input
              type="text"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              placeholder="e.g. Engineering"
              className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
            />
          </div>

          <div>
            <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">Location</label>
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="e.g. San Francisco, CA"
              className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
            />
          </div>

          <div>
            <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">Work Arrangement</label>
            <select
              value={remoteType}
              onChange={(e) => setRemoteType(e.target.value)}
              className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
            >
              <option value="">All Arrangements</option>
              <option value="remote">Fully Remote</option>
              <option value="hybrid">Hybrid</option>
              <option value="onsite">On-Site</option>
            </select>
          </div>

          <div>
            <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">Employment Type</label>
            <select
              value={employmentType}
              onChange={(e) => setEmploymentType(e.target.value)}
              className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
            >
              <option value="">All Types</option>
              <option value="full_time">Full-Time</option>
              <option value="part_time">Part-Time</option>
              <option value="contract">Contract</option>
              <option value="internship">Internship</option>
            </select>
          </div>
        </div>
      </form>

      {/* Jobs Results */}
      <div className="space-y-4">
        <div className="flex items-center justify-between text-xs text-slate-500">
          <span>Found {jobs.length} open position{jobs.length === 1 ? "" : "s"}</span>
        </div>

        {loading ? (
          <div className="py-16 flex flex-col items-center justify-center space-y-2">
            <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
            <p className="text-xs text-slate-500">Searching open positions...</p>
          </div>
        ) : jobs.length === 0 ? (
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-12 text-center space-y-3">
            <Briefcase className="w-10 h-10 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              No matching jobs found
            </p>
            <p className="text-xs text-slate-500">
              Try adjusting your search criteria or clearing filters.
            </p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {jobs.map((job) => {
              const isSaved = savedJobIds.has(job.id);
              return (
                <div
                  key={job.id}
                  className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-300 dark:hover:border-slate-700 transition-all flex flex-col justify-between space-y-4"
                >
                  <div className="space-y-2.5">
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <h3 className="text-base font-bold text-slate-900 dark:text-white hover:text-primary-600">
                          {job.title}
                        </h3>
                        <div className="flex items-center gap-2 text-xs text-slate-500 mt-0.5">
                          {job.department && (
                            <span className="flex items-center gap-1">
                              <Building2 className="w-3.5 h-3.5" />
                              {job.department}
                            </span>
                          )}
                          {job.location && (
                            <span className="flex items-center gap-1">
                              <MapPin className="w-3.5 h-3.5" />
                              {job.location}
                            </span>
                          )}
                        </div>
                      </div>

                      <button
                        type="button"
                        onClick={() => handleToggleSave(job.id)}
                        className={`p-2 rounded-xl transition-colors ${
                          isSaved
                            ? "bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400"
                            : "text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                        }`}
                        aria-label={isSaved ? "Unsave job" : "Save job"}
                      >
                        <Bookmark className={`w-4 h-4 ${isSaved ? "fill-current" : ""}`} />
                      </button>
                    </div>

                    {/* Badges */}
                    <div className="flex flex-wrap gap-1.5 text-[11px]">
                      <span className="px-2 py-0.5 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 rounded font-medium capitalize">
                        {job.remote_type}
                      </span>
                      <span className="px-2 py-0.5 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 rounded font-medium capitalize">
                        {job.employment_type.replace("_", " ")}
                      </span>
                      {job.experience_level && (
                        <span className="px-2 py-0.5 bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 rounded font-medium">
                          {job.experience_level}
                        </span>
                      )}
                      {(job.salary_min || job.salary_max) && (
                        <span className="px-2 py-0.5 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded font-medium flex items-center gap-0.5">
                          <DollarSign className="w-3 h-3" />
                          {job.salary_min ? `${job.salary_min.toLocaleString()}` : ""}
                          {job.salary_max ? ` - ${job.salary_max.toLocaleString()}` : ""} {job.salary_currency || "USD"}
                        </span>
                      )}
                    </div>

                    {/* Required Skills */}
                    {job.required_skills && job.required_skills.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {job.required_skills.slice(0, 4).map((skill, idx) => (
                          <span
                            key={idx}
                            className="text-[10px] px-2 py-0.5 bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 rounded-md"
                          >
                            {skill}
                          </span>
                        ))}
                        {job.required_skills.length > 4 && (
                          <span className="text-[10px] text-slate-400 self-center">
                            +{job.required_skills.length - 4} more
                          </span>
                        )}
                      </div>
                    )}
                  </div>

                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                    <span className="text-[11px] text-slate-400">
                      Posted {new Date(job.created_at).toLocaleDateString()}
                    </span>
                    <button
                      type="button"
                      onClick={() => handleOpenApplyModal(job.id)}
                      className="px-4 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                    >
                      Apply Now
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Application Modal */}
      {applyingJob && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-4 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  Apply for {applyingJob.title}
                </h3>
                <p className="text-xs text-slate-500">
                  {applyingJob.department || "General"} &bull; {applyingJob.location || "Remote"}
                </p>
              </div>
              <button
                onClick={() => setApplyingJob(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {applySuccess ? (
              <div className="py-8 text-center space-y-3">
                <div className="w-12 h-12 bg-emerald-50 dark:bg-emerald-950/40 text-emerald-600 dark:text-emerald-400 rounded-full flex items-center justify-center mx-auto">
                  <CheckCircle className="w-7 h-7" />
                </div>
                <h4 className="text-base font-bold text-slate-900 dark:text-white">
                  Application Submitted Successfully!
                </h4>
                <p className="text-xs text-slate-500 max-w-sm mx-auto">
                  Your resume snapshot has been sealed with SHA-256 integrity and delivered to the hiring team.
                </p>
                <div className="pt-2">
                  <button
                    type="button"
                    onClick={() => setApplyingJob(null)}
                    className="px-5 py-2 bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold rounded-xl"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleSubmitApplication} className="space-y-4">
                {applyError && (
                  <div
                    role="alert"
                    className="flex items-center gap-2 p-3 text-xs text-red-700 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-lg"
                  >
                    <AlertCircle className="w-4 h-4 shrink-0" />
                    <span>{applyError}</span>
                  </div>
                )}

                {/* Job Description Preview */}
                <div className="p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl space-y-1">
                  <p className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                    Role Summary
                  </p>
                  <p className="text-xs text-slate-600 dark:text-slate-400 line-clamp-3">
                    {applyingJob.description}
                  </p>
                </div>

                {/* Resume Selector */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Select Resume Version *
                  </label>
                  {resumes.length === 0 ? (
                    <div className="text-xs text-amber-700 bg-amber-50 dark:bg-amber-950/40 p-3 rounded-lg border border-amber-200">
                      No resume uploaded yet. Please upload a resume first under Resumes tab.
                    </div>
                  ) : (
                    <select
                      value={selectedResumeId}
                      onChange={(e) => setSelectedResumeId(e.target.value)}
                      className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                    >
                      {resumes.map((r) => (
                        <option key={r.id} value={r.id}>
                          {r.file_name} (v{r.version_number}) {r.is_default ? "— [Default]" : ""}
                        </option>
                      ))}
                    </select>
                  )}
                  <p className="text-[11px] text-slate-400 mt-1">
                    An immutable SHA-256 snapshot of your selected resume will be preserved with your application.
                  </p>
                </div>

                {/* Cover Letter */}
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Cover Letter / Note to Hiring Team (Optional)
                  </label>
                  <textarea
                    rows={4}
                    value={coverLetter}
                    onChange={(e) => setCoverLetter(e.target.value)}
                    placeholder="Share why you're a great fit for this position..."
                    className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setApplyingJob(null)}
                    className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={submittingApply || resumes.length === 0}
                    className="inline-flex items-center gap-1.5 px-5 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                  >
                    {submittingApply ? (
                      <Loader2 className="w-3.5 h-3.5 animate-spin" />
                    ) : (
                      <Send className="w-3.5 h-3.5" />
                    )}
                    Submit Application
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
