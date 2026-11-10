"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Users,
  Search,
  Filter,
  FileText,
  Download,
  CheckSquare,
  Square,
  ArrowUpDown,
  RefreshCw,
  ExternalLink,
  Scale,
  UserCheck,
  Briefcase,
  MapPin,
  Calendar,
  X,
  AlertCircle,
  Clock,
  Sparkles,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type {
  ApplicantListItem,
  ApplicantListResponse,
  CandidateComparisonItem,
  JobRequisition,
  TeamMemberOption,
} from "@/types/hr";

export default function HrApplicantsPage() {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [data, setData] = useState<ApplicantListResponse>({
    items: [],
    total: 0,
    page: 1,
    page_size: 20,
    pages: 1,
  });

  // Filters & Search
  const [search, setSearch] = useState("");
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [selectedStatus, setSelectedStatus] = useState<string>("");
  const [selectedDepartment, setSelectedDepartment] = useState<string>("");
  const [minExp, setMinExp] = useState<string>("");
  const [sortBy, setSortBy] = useState("applied_at");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [page, setPage] = useState(1);

  // Available options
  const [jobs, setJobs] = useState<JobRequisition[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMemberOption[]>([]);

  // Selection
  const [selectedIds, setSelectedIds] = useState<string[]>([]);

  // Modals & Drawers
  const [showCompareModal, setShowCompareModal] = useState(false);
  const [compareData, setCompareData] = useState<CandidateComparisonItem[]>([]);
  const [compareLoading, setCompareLoading] = useState(false);
  const [compareError, setCompareError] = useState<string | null>(null);

  const [showAssignModal, setShowAssignModal] = useState(false);
  const [assignRecruiterId, setAssignRecruiterId] = useState("");
  const [assignLoading, setAssignLoading] = useState(false);
  const [assignSuccess, setAssignSuccess] = useState<string | null>(null);

  // Resume downloading status
  const [downloadingResumeAppId, setDownloadingResumeAppId] = useState<string | null>(null);

  // Load jobs and team members once
  useEffect(() => {
    async function loadOptions() {
      try {
        const [jobsRes, membersRes] = await Promise.all([
          hrApi.listJobs({ page_size: 100 }),
          hrApi.getTeamMembers().catch(() => []),
        ]);
        setJobs(jobsRes.items || []);
        setTeamMembers(membersRes || []);
      } catch {
        // Fallback gracefully
      }
    }
    loadOptions();
  }, []);

  // Load applicants
  const loadApplicants = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await hrApi.listApplicants({
        search: search.trim() || undefined,
        job_id: selectedJobId || undefined,
        department: selectedDepartment || undefined,
        status: selectedStatus || undefined,
        min_experience_years: minExp ? parseFloat(minExp) : undefined,
        page,
        page_size: 20,
        sort_by: sortBy,
        sort_order: sortOrder,
      });
      setData(res);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load applicant list";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [search, selectedJobId, selectedDepartment, selectedStatus, minExp, page, sortBy, sortOrder]);

  useEffect(() => {
    loadApplicants();
  }, [loadApplicants]);

  // Handle selection toggles
  const handleToggleSelectAll = () => {
    if (selectedIds.length === data.items.length) {
      setSelectedIds([]);
    } else {
      setSelectedIds(data.items.map((item) => item.id));
    }
  };

  const handleToggleSelect = (id: string) => {
    setSelectedIds((prev) =>
      prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
    );
  };

  // Compare candidates
  const handleOpenComparison = async () => {
    if (selectedIds.length < 2 || selectedIds.length > 4) return;
    try {
      setCompareLoading(true);
      setCompareError(null);
      setShowCompareModal(true);
      const res = await hrApi.compareCandidates(selectedIds);
      setCompareData(res.candidates);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate comparison matrix";
      setCompareError(msg);
    } finally {
      setCompareLoading(false);
    }
  };

  // Bulk assign recruiter
  const handleBulkAssign = async () => {
    if (!assignRecruiterId || selectedIds.length === 0) return;
    try {
      setAssignLoading(true);
      const res = await hrApi.bulkAssignRecruiter(selectedIds, assignRecruiterId);
      setAssignSuccess(`Assigned ${res.updated_count} applicants to ${res.recruiter_name}`);
      setTimeout(() => setAssignSuccess(null), 4000);
      setShowAssignModal(false);
      setSelectedIds([]);
      loadApplicants();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Bulk assignment failed";
      setError(msg);
    } finally {
      setAssignLoading(false);
    }
  };

  // Resume download with short-lived presigned URL
  const handleDownloadResume = async (applicationId: string) => {
    try {
      setDownloadingResumeAppId(applicationId);
      const res = await hrApi.getApplicationResumeUrl(applicationId);
      if (res.download_url) {
        window.open(res.download_url, "_blank", "noopener,noreferrer");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to retrieve resume";
      alert(`Resume access error: ${msg}`);
    } finally {
      setDownloadingResumeAppId(null);
    }
  };

  // Status badge styling
  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "hired":
        return "bg-emerald-50 text-emerald-700 border-emerald-200";
      case "offer":
      case "offer_stage":
        return "bg-indigo-50 text-indigo-700 border-indigo-200";
      case "interview":
      case "interview_stage":
      case "interviewing":
        return "bg-purple-50 text-purple-700 border-purple-200";
      case "shortlisted":
        return "bg-blue-50 text-blue-700 border-blue-200";
      case "in_screening":
      case "screening":
        return "bg-amber-50 text-amber-700 border-amber-200";
      case "rejected":
        return "bg-rose-50 text-rose-700 border-rose-200";
      case "withdrawn":
        return "bg-slate-100 text-slate-500 border-slate-200";
      default:
        return "bg-slate-50 text-slate-700 border-slate-200";
    }
  };

  return (
    <div className="space-y-6" data-testid="applicant-pool-page">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-2">
            <Users className="w-6 h-6 text-blue-600" />
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
              Applicant Pool & Candidates
            </h1>
          </div>
          <p className="text-xs text-slate-500 mt-1">
            Review, screen, and manage candidates across all active job openings ({data.total} total applications).
          </p>
        </div>

        <button
          type="button"
          onClick={() => loadApplicants()}
          disabled={loading}
          className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 transition-colors shadow-sm self-start sm:self-auto"
        >
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {/* Global Success / Alert Banner */}
      {assignSuccess && (
        <div className="p-3.5 rounded-xl border border-emerald-200 bg-emerald-50 text-emerald-800 text-xs flex items-center gap-2">
          <UserCheck className="w-4 h-4 text-emerald-600 flex-shrink-0" />
          <span>{assignSuccess}</span>
        </div>
      )}

      {error && (
        <div className="p-3.5 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-xs flex items-center gap-2">
          <AlertCircle className="w-4 h-4 text-rose-600 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Filter and Search Bar */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
          {/* Search Input */}
          <div className="relative lg:col-span-2">
            <Search className="w-4 h-4 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              placeholder="Search by candidate name, email, or role..."
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              className="w-full pl-9 pr-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              data-testid="applicant-search-input"
            />
          </div>

          {/* Job Requisition Filter */}
          <div>
            <select
              value={selectedJobId}
              onChange={(e) => {
                setSelectedJobId(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-slate-700 dark:text-slate-300"
              data-testid="filter-job-select"
            >
              <option value="">All Job Openings</option>
              {jobs.map((j) => (
                <option key={j.id} value={j.id}>
                  {j.title}
                </option>
              ))}
            </select>
          </div>

          {/* Application Stage / Status Filter */}
          <div>
            <select
              value={selectedStatus}
              onChange={(e) => {
                setSelectedStatus(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-slate-700 dark:text-slate-300"
              data-testid="filter-status-select"
            >
              <option value="">All Application Stages</option>
              <option value="submitted">Submitted</option>
              <option value="in_screening">In Screening</option>
              <option value="shortlisted">Shortlisted</option>
              <option value="interview_stage">Interview Stage</option>
              <option value="offer_stage">Offer Stage</option>
              <option value="hired">Hired</option>
              <option value="rejected">Rejected</option>
              <option value="withdrawn">Withdrawn</option>
            </select>
          </div>

          {/* Experience Filter */}
          <div>
            <select
              value={minExp}
              onChange={(e) => {
                setMinExp(e.target.value);
                setPage(1);
              }}
              className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20 text-slate-700 dark:text-slate-300"
              data-testid="filter-min-exp-select"
            >
              <option value="">Any Experience</option>
              <option value="1">1+ Years</option>
              <option value="3">3+ Years</option>
              <option value="5">5+ Years</option>
              <option value="8">8+ Years</option>
            </select>
          </div>
        </div>

        {/* Sorting row */}
        <div className="flex items-center justify-between text-xs text-slate-500 pt-1 border-t border-slate-100 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <span>Sort By:</span>
            <button
              type="button"
              onClick={() => {
                setSortBy("applied_at");
                setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
              }}
              className={`font-semibold hover:text-blue-600 transition-colors flex items-center gap-1 ${
                sortBy === "applied_at" ? "text-blue-600" : ""
              }`}
            >
              Application Date <ArrowUpDown className="w-3 h-3" />
            </button>
            <span>•</span>
            <button
              type="button"
              onClick={() => {
                setSortBy("candidate_name");
                setSortOrder((prev) => (prev === "desc" ? "asc" : "desc"));
              }}
              className={`font-semibold hover:text-blue-600 transition-colors flex items-center gap-1 ${
                sortBy === "candidate_name" ? "text-blue-600" : ""
              }`}
            >
              Candidate Name <ArrowUpDown className="w-3 h-3" />
            </button>
          </div>

          <span>
            Showing {data.items.length} of {data.total} applicants
          </span>
        </div>
      </div>

      {/* Bulk Action Toolbar */}
      {selectedIds.length > 0 && (
        <div className="p-3 bg-blue-50 dark:bg-blue-950/40 border border-blue-200 dark:border-blue-900 rounded-xl flex items-center justify-between flex-wrap gap-3">
          <div className="flex items-center gap-2 text-xs font-semibold text-blue-900 dark:text-blue-300">
            <CheckSquare className="w-4 h-4 text-blue-600" />
            <span>{selectedIds.length} candidate application{selectedIds.length === 1 ? "" : "s"} selected</span>
          </div>

          <div className="flex items-center gap-2">
            <button
              type="button"
              disabled={selectedIds.length < 2 || selectedIds.length > 4}
              onClick={handleOpenComparison}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed rounded-lg shadow-sm transition-colors"
              data-testid="btn-compare-candidates"
            >
              <Scale className="w-3.5 h-3.5" />
              Compare Candidates ({selectedIds.length}/4)
            </button>

            <button
              type="button"
              onClick={() => setShowAssignModal(true)}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 rounded-lg transition-colors"
              data-testid="btn-bulk-assign-recruiter"
            >
              <UserCheck className="w-3.5 h-3.5" />
              Assign Recruiter
            </button>

            <button
              type="button"
              onClick={() => setSelectedIds([])}
              className="px-2.5 py-1.5 text-xs font-medium text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
            >
              Clear
            </button>
          </div>
        </div>
      )}

      {/* Applicants Table */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 shadow-sm overflow-hidden">
        {loading ? (
          <div className="p-12 text-center text-xs text-slate-400 space-y-2">
            <RefreshCw className="w-6 h-6 animate-spin mx-auto text-blue-500" />
            <p>Loading organization applicant records...</p>
          </div>
        ) : data.items.length === 0 ? (
          <div className="p-12 text-center text-xs text-slate-400 space-y-2">
            <Users className="w-8 h-8 mx-auto text-slate-300" />
            <p className="font-semibold text-slate-600 dark:text-slate-400">No applicants found</p>
            <p>Adjust your search filters or check active job listings.</p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800 text-slate-500 font-semibold uppercase tracking-wider text-[11px]">
                  <th className="p-4 w-10 text-center">
                    <button
                      type="button"
                      onClick={handleToggleSelectAll}
                      className="text-slate-400 hover:text-slate-600"
                      data-testid="select-all-checkbox"
                    >
                      {selectedIds.length === data.items.length && data.items.length > 0 ? (
                        <CheckSquare className="w-4 h-4 text-blue-600" />
                      ) : (
                        <Square className="w-4 h-4" />
                      )}
                    </button>
                  </th>
                  <th className="p-4">Candidate</th>
                  <th className="p-4">Applied Role</th>
                  <th className="p-4">Experience & Skills</th>
                  <th className="p-4">Stage</th>
                  <th className="p-4">Resume</th>
                  <th className="p-4">Applied Date</th>
                  <th className="p-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800 text-slate-700 dark:text-slate-300">
                {data.items.map((app) => {
                  const isSelected = selectedIds.includes(app.id);
                  return (
                    <tr
                      key={app.id}
                      className={`hover:bg-slate-50/80 dark:hover:bg-slate-800/40 transition-colors ${
                        isSelected ? "bg-blue-50/40 dark:bg-blue-950/20" : ""
                      }`}
                      data-testid={`applicant-row-${app.id}`}
                    >
                      {/* Checkbox */}
                      <td className="p-4 text-center">
                        <button
                          type="button"
                          onClick={() => handleToggleSelect(app.id)}
                          className="text-slate-400 hover:text-slate-600"
                          data-testid={`checkbox-${app.id}`}
                        >
                          {isSelected ? (
                            <CheckSquare className="w-4 h-4 text-blue-600" />
                          ) : (
                            <Square className="w-4 h-4" />
                          )}
                        </button>
                      </td>

                      {/* Candidate Column */}
                      <td className="p-4">
                        <div className="flex items-start gap-3">
                          <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-bold flex items-center justify-center flex-shrink-0 text-xs">
                            {app.candidate_name
                              .split(" ")
                              .map((n) => n[0])
                              .slice(0, 2)
                              .join("")}
                          </div>
                          <div>
                            <Link
                              href={`/hr/candidates/${app.candidate_id}?applicationId=${app.id}`}
                              className="font-semibold text-slate-900 dark:text-slate-100 hover:text-blue-600 hover:underline"
                            >
                              {app.candidate_name}
                            </Link>
                            {app.candidate_headline && (
                              <div className="text-[11px] text-slate-500 line-clamp-1">
                                {app.candidate_headline}
                              </div>
                            )}
                            <div className="text-[11px] text-slate-400 mt-0.5 flex items-center gap-2">
                              <span>{app.candidate_email}</span>
                              {app.candidate_location && (
                                <>
                                  <span>•</span>
                                  <span className="flex items-center gap-0.5">
                                    <MapPin className="w-3 h-3" />
                                    {app.candidate_location}
                                  </span>
                                </>
                              )}
                            </div>
                          </div>
                        </div>
                      </td>

                      {/* Applied Role Column */}
                      <td className="p-4">
                        <div className="font-semibold text-slate-800 dark:text-slate-200">
                          {app.job_title}
                        </div>
                        <div className="text-[11px] text-slate-500 flex items-center gap-1.5 mt-0.5">
                          <span>{app.job_department}</span>
                          <span>•</span>
                          <span className="capitalize">{app.job_location}</span>
                        </div>
                      </td>

                      {/* Experience & Skills */}
                      <td className="p-4">
                        <div className="space-y-1.5">
                          <div className="flex items-center gap-1.5 text-[11px]">
                            <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 font-semibold text-slate-700 dark:text-slate-300 font-mono">
                              {app.experience_years} yrs exp
                            </span>
                            {app.current_job_title && (
                              <span className="text-slate-500 line-clamp-1">
                                {app.current_job_title}
                              </span>
                            )}
                          </div>
                          {app.skills && app.skills.length > 0 && (
                            <div className="flex flex-wrap gap-1 max-w-xs">
                              {app.skills.slice(0, 3).map((skill) => (
                                <span
                                  key={skill}
                                  className="px-1.5 py-0.5 rounded text-[10px] bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300"
                                >
                                  {skill}
                                </span>
                              ))}
                              {app.skills.length > 3 && (
                                <span className="text-[10px] text-slate-400 self-center">
                                  +{app.skills.length - 3}
                                </span>
                              )}
                            </div>
                          )}
                        </div>
                      </td>

                      {/* Stage Badge */}
                      <td className="p-4">
                        <span
                          className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-semibold border ${getStatusBadge(
                            app.status
                          )}`}
                        >
                          {app.status.replace(/_/g, " ")}
                        </span>
                      </td>

                      {/* Resume Download */}
                      <td className="p-4">
                        {app.resume_available ? (
                          <button
                            type="button"
                            disabled={downloadingResumeAppId === app.id}
                            onClick={() => handleDownloadResume(app.id)}
                            className="inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-medium text-blue-700 dark:text-blue-300 bg-blue-50 dark:bg-blue-900/30 hover:bg-blue-100 transition-colors"
                            data-testid={`btn-download-resume-${app.id}`}
                          >
                            <FileText className="w-3.5 h-3.5" />
                            {downloadingResumeAppId === app.id ? (
                              <RefreshCw className="w-3 h-3 animate-spin" />
                            ) : (
                              <span>PDF</span>
                            )}
                          </button>
                        ) : (
                          <span className="text-slate-400 text-[11px] italic">No resume</span>
                        )}
                      </td>

                      {/* Applied Date */}
                      <td className="p-4 text-slate-500 whitespace-nowrap">
                        {new Date(app.applied_at).toLocaleDateString()}
                      </td>

                      {/* Actions */}
                      <td className="p-4 text-right">
                        <Link
                          href={`/hr/candidates/${app.candidate_id}?applicationId=${app.id}`}
                          className="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 hover:bg-slate-50 transition-colors shadow-sm"
                          data-testid={`btn-view-profile-${app.id}`}
                        >
                          View Profile
                          <ExternalLink className="w-3 h-3 text-slate-400" />
                        </Link>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}

        {/* Pagination Bar */}
        {data.pages > 1 && (
          <div className="p-4 bg-slate-50 dark:bg-slate-800/40 border-t border-slate-200 dark:border-slate-800 flex items-center justify-between text-xs text-slate-500">
            <div>
              Page {data.page} of {data.pages}
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={data.page <= 1}
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 disabled:opacity-50 text-slate-700 dark:text-slate-200"
              >
                Previous
              </button>
              <button
                type="button"
                disabled={data.page >= data.pages}
                onClick={() => setPage((p) => Math.min(data.pages, p + 1))}
                className="px-3 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 disabled:opacity-50 text-slate-700 dark:text-slate-200"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Candidate Comparison Modal */}
      {showCompareModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 max-w-4xl w-full shadow-2xl p-6 space-y-5 my-8">
            <div className="flex items-center justify-between border-b pb-3 border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <Scale className="w-5 h-5 text-blue-600" />
                <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                  Candidate Comparison Matrix
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowCompareModal(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {compareLoading ? (
              <div className="p-12 text-center text-xs text-slate-400 space-y-2">
                <RefreshCw className="w-6 h-6 animate-spin mx-auto text-blue-500" />
                <p>Generating comparative candidate matrix...</p>
              </div>
            ) : compareError ? (
              <div className="p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-xs">
                {compareError}
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border-collapse">
                  <thead>
                    <tr className="bg-slate-50 dark:bg-slate-800/60 border-b border-slate-200 dark:border-slate-800">
                      <th className="p-3 w-40 text-slate-500 uppercase font-semibold text-[11px]">
                        Attribute
                      </th>
                      {compareData.map((c) => (
                        <th key={c.application_id} className="p-3 font-bold text-slate-900 dark:text-slate-100">
                          {c.candidate_name}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Current Role</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3 font-medium text-slate-800 dark:text-slate-200">
                          {c.current_job_title || "Not specified"}{" "}
                          {c.current_company && `at ${c.current_company}`}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Total Experience</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3 font-mono font-semibold text-blue-600">
                          {c.experience_years} Years
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Education</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3 text-slate-700 dark:text-slate-300">
                          {c.highest_education || "Degree not listed"}
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Matching Skills</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3">
                          <div className="flex flex-wrap gap-1">
                            {c.matching_skills.length > 0 ? (
                              c.matching_skills.map((s) => (
                                <span
                                  key={s}
                                  className="px-1.5 py-0.5 rounded bg-emerald-50 text-emerald-700 border border-emerald-200 text-[10px] font-semibold"
                                >
                                  {s}
                                </span>
                              ))
                            ) : (
                              <span className="text-slate-400 italic">None</span>
                            )}
                          </div>
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Missing Skills</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3">
                          <div className="flex flex-wrap gap-1">
                            {c.missing_skills.length > 0 ? (
                              c.missing_skills.map((s) => (
                                <span
                                  key={s}
                                  className="px-1.5 py-0.5 rounded bg-rose-50 text-rose-700 border border-rose-200 text-[10px]"
                                >
                                  {s}
                                </span>
                              ))
                            ) : (
                              <span className="text-emerald-600 font-semibold text-[10px]">All matched</span>
                            )}
                          </div>
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Skill Match %</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3">
                          <div className="flex items-center gap-2">
                            <div className="flex-1 bg-slate-100 dark:bg-slate-800 rounded-full h-2 overflow-hidden">
                              <div
                                className="bg-blue-600 h-2 rounded-full"
                                style={{ width: `${c.match_percentage}%` }}
                              />
                            </div>
                            <span className="font-mono font-bold text-slate-800 dark:text-slate-200">
                              {c.match_percentage}%
                            </span>
                          </div>
                        </td>
                      ))}
                    </tr>
                    <tr>
                      <td className="p-3 font-semibold text-slate-500">Resume Link</td>
                      {compareData.map((c) => (
                        <td key={c.application_id} className="p-3">
                          {c.resume_available ? (
                            <button
                              type="button"
                              onClick={() => handleDownloadResume(c.application_id)}
                              className="inline-flex items-center gap-1 text-xs text-blue-600 hover:underline"
                            >
                              <Download className="w-3.5 h-3.5" />
                              View Resume
                            </button>
                          ) : (
                            <span className="text-slate-400">None</span>
                          )}
                        </td>
                      ))}
                    </tr>
                  </tbody>
                </table>
              </div>
            )}

            <div className="flex justify-end pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setShowCompareModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-300 hover:bg-slate-100 rounded-lg"
              >
                Close Comparison
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Bulk Assign Recruiter Modal */}
      {showAssignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 max-w-md w-full shadow-2xl p-6 space-y-4">
            <div className="flex items-center justify-between border-b pb-3 border-slate-100 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <UserCheck className="w-5 h-5 text-blue-600" />
                Assign Recruiter
              </h3>
              <button
                type="button"
                onClick={() => setShowAssignModal(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Select an authorized recruiter from your organization to assign to the {selectedIds.length} selected candidate application(s).
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Recruiter
              </label>
              <select
                value={assignRecruiterId}
                onChange={(e) => setAssignRecruiterId(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                data-testid="select-assign-recruiter"
              >
                <option value="">Select a team recruiter...</option>
                {teamMembers.map((m) => (
                  <option key={m.id} value={m.id}>
                    {m.name} ({m.role}) - {m.email}
                  </option>
                ))}
              </select>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setShowAssignModal(false)}
                className="px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={assignLoading || !assignRecruiterId}
                onClick={handleBulkAssign}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 rounded-lg shadow-sm"
                data-testid="btn-confirm-bulk-assign"
              >
                {assignLoading && <RefreshCw className="w-3.5 h-3.5 animate-spin" />}
                Assign to {selectedIds.length} Applicants
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
