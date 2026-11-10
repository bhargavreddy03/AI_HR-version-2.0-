"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Search,
  MapPin,
  Building2,
  Bookmark,
  Briefcase,
  DollarSign,
  Loader2,
  Calendar,
  Clock,
  Filter,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  ArrowUpDown,
  RotateCcw,
  AlertCircle,
  ExternalLink,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type {
  JobPublicSummary,
  JobListResponse,
} from "@/types/candidate";

export default function CandidateJobsPage() {
  const [jobs, setJobs] = useState<JobPublicSummary[]>([]);
  const [savedJobIds, setSavedJobIds] = useState<Set<string>>(new Set());
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Pagination & counts
  const [total, setTotal] = useState(0);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(12);
  const [totalPages, setTotalPages] = useState(1);

  // Search & Filter state
  const [searchQuery, setSearchQuery] = useState("");
  const [department, setDepartment] = useState("");
  const [location, setLocation] = useState("");
  const [remoteType, setRemoteType] = useState("");
  const [employmentType, setEmploymentType] = useState("");
  const [experienceLevel, setExperienceLevel] = useState("");
  const [skillsFilter, setSkillsFilter] = useState("");
  const [minSalary, setMinSalary] = useState<string>("");
  const [maxSalary, setMaxSalary] = useState<string>("");
  const [postedWithinDays, setPostedWithinDays] = useState<string>("");
  const [sortBy, setSortBy] = useState<"recent" | "closing_soon" | "salary_high">("recent");

  // Filter drawer toggle for mobile/desktop
  const [showFilters, setShowFilters] = useState(false);

  const fetchJobs = useCallback(async (currentPage: number = page) => {
    try {
      setLoading(true);
      setError(null);
      const res = await candidateApi.searchJobs({
        query: searchQuery.trim() || undefined,
        department: department.trim() || undefined,
        location: location.trim() || undefined,
        remote_type: remoteType || undefined,
        employment_type: employmentType || undefined,
        experience_level: experienceLevel || undefined,
        skills: skillsFilter.trim() || undefined,
        min_salary: minSalary ? parseFloat(minSalary) : undefined,
        max_salary: maxSalary ? parseFloat(maxSalary) : undefined,
        posted_within_days: postedWithinDays ? parseInt(postedWithinDays, 10) : undefined,
        sort_by: sortBy,
        page: currentPage,
        page_size: pageSize,
      });

      // Support both structured response and raw array
      if (res && Array.isArray((res as JobListResponse).jobs)) {
        const listRes = res as JobListResponse;
        setJobs(listRes.jobs);
        setTotal(listRes.total);
        setTotalPages(listRes.total_pages || 1);
        setPage(listRes.page || 1);
      } else if (Array.isArray(res)) {
        setJobs(res as JobPublicSummary[]);
        setTotal((res as JobPublicSummary[]).length);
        setTotalPages(1);
      } else {
        setJobs([]);
        setTotal(0);
        setTotalPages(1);
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load open positions");
    } finally {
      setLoading(false);
    }
  }, [
    searchQuery,
    department,
    location,
    remoteType,
    employmentType,
    experienceLevel,
    skillsFilter,
    minSalary,
    maxSalary,
    postedWithinDays,
    sortBy,
    page,
    pageSize,
  ]);

  // Initial load
  useEffect(() => {
    async function init() {
      try {
        const saved = await candidateApi.getSavedJobs();
        if (Array.isArray(saved)) {
          setSavedJobIds(new Set(saved.map((s) => s.job_id)));
        }
      } catch {
        // non-blocking
      }
      fetchJobs(1);
    }
    init();
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  const handleSearchSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(1);
    fetchJobs(1);
  };

  const handleResetFilters = () => {
    setSearchQuery("");
    setDepartment("");
    setLocation("");
    setRemoteType("");
    setEmploymentType("");
    setExperienceLevel("");
    setSkillsFilter("");
    setMinSalary("");
    setMaxSalary("");
    setPostedWithinDays("");
    setSortBy("recent");
    setPage(1);
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
      alert(err instanceof Error ? err.message : "Failed to update saved job");
    }
  };

  const handlePageChange = (newPage: number) => {
    if (newPage >= 1 && newPage <= totalPages) {
      setPage(newPage);
      fetchJobs(newPage);
      window.scrollTo({ top: 0, behavior: "smooth" });
    }
  };

  return (
    <div className="space-y-6 max-w-7xl mx-auto">
      {/* Top Banner */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Find Career Opportunities
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Discover verified enterprise opportunities matching your skills and career aspirations.
          </p>
        </div>
        <Link
          href="/candidate/saved-jobs"
          className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800/80 text-xs font-semibold text-slate-700 dark:text-slate-300 rounded-xl shadow-sm transition-colors self-start sm:self-auto"
        >
          <Bookmark className="w-3.5 h-3.5 text-amber-500 fill-amber-500" />
          <span>Saved Jobs ({savedJobIds.size})</span>
        </Link>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-xs text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
          <span>Note: Connect your session to sync live published roles ({error})</span>
        </div>
      )}

      {/* Main Search Bar & Quick Controls */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
        <form onSubmit={handleSearchSubmit} className="flex flex-col sm:flex-row gap-2.5">
          <div className="relative flex-1">
            <Search className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by role title, keywords, skills (e.g. Python, Architect)..."
              className="w-full pl-10 pr-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>
          <div className="relative sm:w-60">
            <MapPin className="w-4 h-4 absolute left-3.5 top-3 text-slate-400" />
            <input
              type="text"
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              placeholder="City, state, or country..."
              className="w-full pl-10 pr-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>
          <button
            type="submit"
            className="px-5 py-2 bg-primary-600 hover:bg-primary-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors flex items-center justify-center gap-1.5"
          >
            <Search className="w-4 h-4" />
            <span>Search</span>
          </button>
          <button
            type="button"
            onClick={() => setShowFilters(!showFilters)}
            className={`px-4 py-2 border rounded-xl text-sm font-medium flex items-center justify-center gap-1.5 transition-colors ${
              showFilters
                ? "bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-600 text-slate-900 dark:text-white"
                : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800"
            }`}
            aria-expanded={showFilters}
          >
            <Filter className="w-4 h-4" />
            <span>Filters</span>
          </button>
        </form>

        {/* Collapsible Filter Panel */}
        {showFilters && (
          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 space-y-3">
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-3 text-xs">
              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Work Arrangement
                </label>
                <select
                  value={remoteType}
                  onChange={(e) => setRemoteType(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                >
                  <option value="">All Arrangements</option>
                  <option value="remote">Fully Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On-Site</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Employment Type
                </label>
                <select
                  value={employmentType}
                  onChange={(e) => setEmploymentType(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                >
                  <option value="">All Types</option>
                  <option value="full_time">Full-Time</option>
                  <option value="part_time">Part-Time</option>
                  <option value="contract">Contract</option>
                  <option value="internship">Internship</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Experience Level
                </label>
                <select
                  value={experienceLevel}
                  onChange={(e) => setExperienceLevel(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                >
                  <option value="">Any Experience</option>
                  <option value="Entry-level">Entry-level</option>
                  <option value="Mid-level">Mid-level</option>
                  <option value="Senior">Senior</option>
                  <option value="Lead">Lead / Staff</option>
                  <option value="Executive">Executive</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Date Posted
                </label>
                <select
                  value={postedWithinDays}
                  onChange={(e) => setPostedWithinDays(e.target.value)}
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                >
                  <option value="">Any Time</option>
                  <option value="1">Past 24 Hours</option>
                  <option value="7">Past 7 Days</option>
                  <option value="14">Past 14 Days</option>
                  <option value="30">Past 30 Days</option>
                </select>
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Required Skill(s)
                </label>
                <input
                  type="text"
                  value={skillsFilter}
                  onChange={(e) => setSkillsFilter(e.target.value)}
                  placeholder="e.g. Python, Docker"
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Department
                </label>
                <input
                  type="text"
                  value={department}
                  onChange={(e) => setDepartment(e.target.value)}
                  placeholder="e.g. Engineering, Sales"
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Min Salary ($/yr)
                </label>
                <input
                  type="number"
                  min="0"
                  step="5000"
                  value={minSalary}
                  onChange={(e) => setMinSalary(e.target.value)}
                  placeholder="Min base"
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                />
              </div>

              <div>
                <label className="block text-slate-500 dark:text-slate-400 mb-1 font-medium">
                  Max Salary ($/yr)
                </label>
                <input
                  type="number"
                  min="0"
                  step="5000"
                  value={maxSalary}
                  onChange={(e) => setMaxSalary(e.target.value)}
                  placeholder="Max base"
                  className="w-full px-2.5 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent text-slate-800 dark:text-slate-200"
                />
              </div>
            </div>

            <div className="flex items-center justify-between pt-2">
              <button
                type="button"
                onClick={handleResetFilters}
                className="inline-flex items-center gap-1.5 text-xs text-slate-500 hover:text-slate-700 dark:hover:text-slate-300"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset all filters</span>
              </button>
              <button
                type="button"
                onClick={() => {
                  setPage(1);
                  fetchJobs(1);
                }}
                className="px-4 py-1.5 bg-slate-900 text-white dark:bg-white dark:text-slate-900 text-xs font-semibold rounded-lg shadow-sm"
              >
                Apply Filters
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Results Header: Count & Sort */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs text-slate-500">
        <div>
          <span>
            Showing <strong className="text-slate-800 dark:text-slate-200">{jobs.length}</strong> of{" "}
            <strong className="text-slate-800 dark:text-slate-200">{total}</strong> open opportunities
          </span>
        </div>

        <div className="flex items-center gap-2">
          <ArrowUpDown className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-medium">Sort by:</span>
          <select
            value={sortBy}
            onChange={(e) => {
              const val = e.target.value as "recent" | "closing_soon" | "salary_high";
              setSortBy(val);
              setPage(1);
            }}
            className="px-2 py-1 text-xs border border-slate-200 dark:border-slate-700 rounded-lg bg-white dark:bg-slate-900 text-slate-700 dark:text-slate-300 font-medium"
          >
            <option value="recent">Most Recent</option>
            <option value="closing_soon">Closing Soon</option>
            <option value="salary_high">Highest Salary</option>
          </select>
        </div>
      </div>

      {/* Jobs Grid */}
      {loading ? (
        <div className="py-20 flex flex-col items-center justify-center space-y-3">
          <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
          <p className="text-xs text-slate-500 font-medium">Querying open opportunities...</p>
        </div>
      ) : jobs.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-12 text-center space-y-3">
          <Briefcase className="w-10 h-10 text-slate-400 mx-auto" />
          <h3 className="text-base font-semibold text-slate-800 dark:text-slate-200">
            No published roles match your criteria
          </h3>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            Only currently active and published enterprise roles are displayed. Try adjusting your search keywords, location, or clearing specific filters.
          </p>
          <div className="pt-2">
            <button
              type="button"
              onClick={handleResetFilters}
              className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
            >
              Clear All Filters
            </button>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {jobs.map((job) => {
            const isSaved = savedJobIds.has(job.id);
            const skillsList = job.required_skills || job.skills_required || [];

            return (
              <div
                key={job.id}
                className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm hover:border-slate-300 dark:hover:border-slate-700 transition-all flex flex-col justify-between space-y-4"
              >
                <div className="space-y-3">
                  {/* Card Header */}
                  <div className="flex items-start justify-between gap-3">
                    <div className="space-y-1">
                      <Link
                        href={`/candidate/jobs/${job.id}`}
                        className="text-base font-bold text-slate-900 dark:text-white hover:text-primary-600 transition-colors line-clamp-1 inline-flex items-center gap-1.5"
                      >
                        <span>{job.title}</span>
                        <ExternalLink className="w-3.5 h-3.5 text-slate-400 inline shrink-0" />
                      </Link>

                      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                        {job.organization_name && (
                          <span className="flex items-center gap-1 font-medium text-slate-700 dark:text-slate-300">
                            <Building2 className="w-3.5 h-3.5 text-primary-500" />
                            {job.organization_name}
                          </span>
                        )}
                        {job.department && (
                          <span className="text-slate-500">
                            &bull; {job.department}
                          </span>
                        )}
                        {job.location && (
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5 text-slate-400" />
                            {job.location}
                          </span>
                        )}
                      </div>
                    </div>

                    <div className="flex items-center gap-1">
                      {job.has_applied && (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800 rounded-full text-[11px] font-semibold">
                          <CheckCircle2 className="w-3 h-3" />
                          Applied
                        </span>
                      )}
                      <button
                        type="button"
                        onClick={() => handleToggleSave(job.id)}
                        className={`p-2 rounded-xl transition-colors ${
                          isSaved
                            ? "bg-amber-50 dark:bg-amber-950/40 text-amber-600 dark:text-amber-400"
                            : "text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800"
                        }`}
                        aria-label={isSaved ? "Unsave job" : "Save job"}
                        title={isSaved ? "Remove from saved jobs" : "Save job for later"}
                      >
                        <Bookmark className={`w-4 h-4 ${isSaved ? "fill-current" : ""}`} />
                      </button>
                    </div>
                  </div>

                  {/* Badges Row */}
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
                        {job.salary_max ? ` - ${job.salary_max.toLocaleString()}` : ""}{" "}
                        {job.salary_currency || "USD"}
                      </span>
                    )}
                  </div>

                  {/* Skills Chips */}
                  {skillsList.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-1">
                      {skillsList.slice(0, 4).map((skill, idx) => (
                        <span
                          key={idx}
                          className="text-[10px] px-2 py-0.5 bg-slate-50 dark:bg-slate-800/60 text-slate-600 dark:text-slate-400 border border-slate-200 dark:border-slate-700 rounded-md"
                        >
                          {skill}
                        </span>
                      ))}
                      {skillsList.length > 4 && (
                        <span className="text-[10px] text-slate-400 self-center">
                          +{skillsList.length - 4} more
                        </span>
                      )}
                    </div>
                  )}
                </div>

                {/* Card Footer */}
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between gap-2 text-[11px] text-slate-400">
                  <div className="flex items-center gap-2">
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3 h-3" />
                      {new Date(job.published_at || job.created_at || Date.now()).toLocaleDateString()}
                    </span>
                    {job.application_deadline && (
                      <span className="flex items-center gap-1 text-amber-600 dark:text-amber-400">
                        <Clock className="w-3 h-3" />
                        Closes {new Date(job.application_deadline).toLocaleDateString()}
                      </span>
                    )}
                  </div>

                  <Link
                    href={`/candidate/jobs/${job.id}`}
                    className="px-3.5 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors inline-flex items-center gap-1"
                  >
                    View Details
                  </Link>
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Pagination Controls */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between border-t border-slate-200 dark:border-slate-800 pt-4 text-xs">
          <p className="text-slate-500">
            Page <span className="font-semibold text-slate-700 dark:text-slate-300">{page}</span> of{" "}
            <span className="font-semibold text-slate-700 dark:text-slate-300">{totalPages}</span>
          </p>

          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={() => handlePageChange(page - 1)}
              disabled={page <= 1}
              className="inline-flex items-center gap-1 px-3 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Previous</span>
            </button>

            <button
              type="button"
              onClick={() => handlePageChange(page + 1)}
              disabled={page >= totalPages}
              className="inline-flex items-center gap-1 px-3 py-1.5 border border-slate-200 dark:border-slate-700 rounded-lg text-slate-700 dark:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
