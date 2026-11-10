"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  UserCheck,
  Briefcase,
  Users,
  Clock,
  AlertTriangle,
  CheckCircle2,
  RefreshCw,
  Search,
  ArrowRight,
  History,
  Shield,
  Layers,
  FileText,
  User,
  X,
  AlertCircle,
  ExternalLink,
  ChevronRight,
  TrendingUp,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type {
  AssignedVacancyItem,
  JobAssignmentHistoryItem,
  JobRequisition,
  TeamMemberOption,
  TeamWorkloadResponse,
  UserWorkloadItem,
} from "@/types/hr";

export default function HrAssignmentsPage() {
  const [activeTab, setActiveTab] = useState<"workload" | "my_vacancies">("workload");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Data states
  const [workloadData, setWorkloadData] = useState<TeamWorkloadResponse | null>(null);
  const [myVacancies, setMyVacancies] = useState<AssignedVacancyItem[]>([]);
  const [jobs, setJobs] = useState<JobRequisition[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMemberOption[]>([]);

  // Search filter
  const [memberSearch, setMemberSearch] = useState("");

  // Reassign Modal
  const [showReassignModal, setShowReassignModal] = useState(false);
  const [reassignJobId, setReassignJobId] = useState("");
  const [selectedRecruiterId, setSelectedRecruiterId] = useState<string>("KEEP");
  const [selectedHmId, setSelectedHmId] = useState<string>("KEEP");
  const [reassignReason, setReassignReason] = useState("");
  const [reassignSubmitting, setReassignSubmitting] = useState(false);
  const [reassignError, setReassignError] = useState<string | null>(null);
  const [reassignSuccess, setReassignSuccess] = useState<string | null>(null);

  // History Modal
  const [historyJob, setHistoryJob] = useState<{ id: string; title: string } | null>(null);
  const [historyItems, setHistoryItems] = useState<JobAssignmentHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Load workload and my vacancies
  const loadData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [workloadRes, myVacRes, jobsRes, membersRes] = await Promise.all([
        hrApi.getTeamWorkload(),
        hrApi.getMyAssignedVacancies().catch(() => ({ tenant_id: "", vacancies: [], total: 0 })),
        hrApi.listJobs({ page_size: 100 }).catch(() => ({ items: [], total: 0, page: 1, page_size: 100, pages: 1 })),
        hrApi.getTeamMembers().catch(() => []),
      ]);
      setWorkloadData(workloadRes);
      setMyVacancies(myVacRes.vacancies || []);
      setJobs(jobsRes.items || []);
      setTeamMembers(membersRes || []);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load team assignments and workload");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Handle reassign submit
  const handleReassignSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!reassignJobId) return;

    const updateRecruiter = selectedRecruiterId !== "KEEP";
    const updateHm = selectedHmId !== "KEEP";

    if (!updateRecruiter && !updateHm) {
      setReassignError("Please select a new Recruiter or Hiring Manager, or choose to unassign.");
      return;
    }

    try {
      setReassignSubmitting(true);
      setReassignError(null);
      await hrApi.updateJobAssignments(reassignJobId, {
        recruiter_id: updateRecruiter ? (selectedRecruiterId === "NONE" ? null : selectedRecruiterId) : undefined,
        hiring_manager_id: updateHm ? (selectedHmId === "NONE" ? null : selectedHmId) : undefined,
        update_recruiter: updateRecruiter,
        update_hiring_manager: updateHm,
        reason: reassignReason.trim() || null,
      });

      setReassignSuccess("Job recruitment assignments updated successfully.");
      setTimeout(() => {
        setShowReassignModal(false);
        setReassignSuccess(null);
        setReassignJobId("");
        setSelectedRecruiterId("KEEP");
        setSelectedHmId("KEEP");
        setReassignReason("");
      }, 1200);

      await loadData();
    } catch (err) {
      setReassignError(err instanceof Error ? err.message : "Failed to update assignments");
    } finally {
      setReassignSubmitting(false);
    }
  };

  // Open history modal
  const openHistory = async (jobId: string, jobTitle: string) => {
    setHistoryJob({ id: jobId, title: jobTitle });
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const items = await hrApi.getJobAssignmentHistory(jobId);
      setHistoryItems(items);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Failed to load assignment history");
    } finally {
      setHistoryLoading(false);
    }
  };

  // Filter team members by search
  const filteredRecruiters = (workloadData?.recruiters || []).filter(
    (r) =>
      r.name.toLowerCase().includes(memberSearch.toLowerCase()) ||
      r.email.toLowerCase().includes(memberSearch.toLowerCase())
  );

  const filteredHms = (workloadData?.hiring_managers || []).filter(
    (h) =>
      h.name.toLowerCase().includes(memberSearch.toLowerCase()) ||
      h.email.toLowerCase().includes(memberSearch.toLowerCase())
  );

  // Status badge styling
  const renderCapacityBadge = (status: UserWorkloadItem["workload_status"]) => {
    switch (status) {
      case "critical":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 dark:bg-rose-950/60 dark:text-rose-300 border border-rose-200 dark:border-rose-800">
            Critical Overload
          </span>
        );
      case "high":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 dark:bg-amber-950/60 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
            Near Capacity
          </span>
        );
      case "balanced":
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 dark:bg-emerald-950/60 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
            Balanced
          </span>
        );
      case "low":
      default:
        return (
          <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300">
            Available
          </span>
        );
    }
  };

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Recruitment Team & Assignments
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/50 dark:border-indigo-800">
              {workloadData?.summary.total_team_members ?? 0} Members
            </span>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Manage lead recruiter and hiring manager assignments, workload distribution, and vacancy reviews.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setReassignJobId(jobs[0]?.id || "");
              setSelectedRecruiterId("KEEP");
              setSelectedHmId("KEEP");
              setReassignReason("");
              setReassignError(null);
              setReassignSuccess(null);
              setShowReassignModal(true);
            }}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm transition-colors"
          >
            <UserCheck className="w-4 h-4" />
            Assign Vacancy
          </button>

          <button
            type="button"
            onClick={() => loadData()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700 shadow-sm"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* High-Level Workload Summary Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Assigned Vacancies
            </span>
            <div className="p-2 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-600 dark:text-indigo-400">
              <Briefcase className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            {workloadData?.summary.total_assigned_jobs ?? 0}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Active roles under recruiter lead
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Unassigned Vacancies
            </span>
            <div className={`p-2 rounded-lg ${
              (workloadData?.summary.total_unassigned_jobs ?? 0) > 0
                ? "bg-amber-50 dark:bg-amber-950/60 text-amber-600"
                : "bg-emerald-50 dark:bg-emerald-950/60 text-emerald-600"
            }`}>
              <AlertTriangle className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            {workloadData?.summary.total_unassigned_jobs ?? 0}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            {(workloadData?.summary.total_unassigned_jobs ?? 0) > 0 ? "Awaiting team assignment" : "All vacancies staffed"}
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              Active Candidates
            </span>
            <div className="p-2 rounded-lg bg-blue-50 dark:bg-blue-950/60 text-blue-600 dark:text-blue-400">
              <Users className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            {workloadData?.summary.total_active_applications ?? 0}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Applications across active pipeline
          </div>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between">
            <span className="text-xs font-semibold text-slate-500 dark:text-slate-400 uppercase tracking-wider">
              My Assigned Roles
            </span>
            <div className="p-2 rounded-lg bg-purple-50 dark:bg-purple-950/60 text-purple-600 dark:text-purple-400">
              <UserCheck className="w-4 h-4" />
            </div>
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-white">
            {myVacancies.length}
          </div>
          <div className="mt-1 text-xs text-slate-500 dark:text-slate-400">
            Vacancies you lead or manage
          </div>
        </div>
      </div>

      {/* Tabs */}
      <div className="border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-6">
          <button
            type="button"
            onClick={() => setActiveTab("workload")}
            className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "workload"
                ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400"
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            Team Workload & Capacity
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("my_vacancies")}
            className={`pb-3 text-sm font-semibold border-b-2 transition-colors flex items-center gap-2 ${
              activeTab === "my_vacancies"
                ? "border-indigo-600 text-indigo-600 dark:border-indigo-400 dark:text-indigo-400"
                : "border-transparent text-slate-500 hover:text-slate-700 dark:text-slate-400"
            }`}
          >
            <Briefcase className="w-4 h-4" />
            My Assigned Vacancies ({myVacancies.length})
          </button>
        </div>

        {activeTab === "workload" && (
          <div className="relative w-64 pb-2">
            <Search className="w-4 h-4 absolute left-3 top-2 text-slate-400" />
            <input
              type="text"
              value={memberSearch}
              onChange={(e) => setMemberSearch(e.target.value)}
              placeholder="Search team member..."
              className="w-full pl-9 pr-3 py-1.5 text-xs rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>
        )}
      </div>

      {/* Error alert */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-600" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* TAB 1: TEAM WORKLOAD */}
      {activeTab === "workload" && (
        <div className="space-y-8">
          {/* Recruiters Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Users className="w-5 h-5 text-indigo-600" />
                Recruiter Workload & Capacity
              </h2>
              <span className="text-xs text-slate-500">
                {filteredRecruiters.length} active recruiter{filteredRecruiters.length === 1 ? "" : "s"}
              </span>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
                  <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                    <tr>
                      <th className="px-4 py-3">Recruiter</th>
                      <th className="px-4 py-3">Assigned Jobs</th>
                      <th className="px-4 py-3">Active Pipeline</th>
                      <th className="px-4 py-3">Pending Reviews</th>
                      <th className="px-4 py-3">Interviews</th>
                      <th className="px-4 py-3">Capacity Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {filteredRecruiters.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-slate-400 text-xs">
                          No recruiters found matching query.
                        </td>
                      </tr>
                    ) : (
                      filteredRecruiters.map((rec) => (
                        <tr key={rec.user_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                          <td className="px-4 py-3.5">
                            <div className="flex items-center gap-2.5">
                              <div className="w-8 h-8 rounded-full bg-indigo-100 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 flex items-center justify-center font-bold text-xs">
                                {rec.name.charAt(0)}
                              </div>
                              <div>
                                <div className="font-semibold text-slate-900 dark:text-white">
                                  {rec.name}
                                </div>
                                <div className="text-xs text-slate-400">{rec.email}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5 font-medium text-slate-800 dark:text-slate-200">
                            {rec.assigned_jobs_count} jobs ({rec.active_jobs_count} active)
                          </td>
                          <td className="px-4 py-3.5 font-medium text-slate-800 dark:text-slate-200">
                            {rec.total_applications_count} candidates
                          </td>
                          <td className="px-4 py-3.5">
                            <span className={`font-semibold ${
                              rec.pending_reviews_count > 10 ? "text-rose-600" : "text-slate-700 dark:text-slate-300"
                            }`}>
                              {rec.pending_reviews_count}
                            </span>
                          </td>
                          <td className="px-4 py-3.5 text-slate-700 dark:text-slate-300">
                            {rec.active_interviews_count}
                          </td>
                          <td className="px-4 py-3.5">
                            {renderCapacityBadge(rec.workload_status)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>

          {/* Hiring Managers Section */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-lg font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Briefcase className="w-5 h-5 text-indigo-600" />
                Hiring Manager Vacancy Allocations
              </h2>
              <span className="text-xs text-slate-500">
                {filteredHms.length} active hiring manager{filteredHms.length === 1 ? "" : "s"}
              </span>
            </div>

            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
              <div className="overflow-x-auto">
                <table className="w-full text-left text-sm text-slate-600 dark:text-slate-300">
                  <thead className="bg-slate-50 dark:bg-slate-800/80 text-xs font-semibold uppercase text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800">
                    <tr>
                      <th className="px-4 py-3">Hiring Manager</th>
                      <th className="px-4 py-3">Assigned Vacancies</th>
                      <th className="px-4 py-3">Active Candidates</th>
                      <th className="px-4 py-3">Pending Reviews</th>
                      <th className="px-4 py-3">Interviews</th>
                      <th className="px-4 py-3">Capacity</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {filteredHms.length === 0 ? (
                      <tr>
                        <td colSpan={6} className="px-4 py-8 text-center text-slate-400 text-xs">
                          No hiring managers found matching query.
                        </td>
                      </tr>
                    ) : (
                      filteredHms.map((hm) => (
                        <tr key={hm.user_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/50">
                          <td className="px-4 py-3.5">
                            <div className="flex items-center gap-2.5">
                              <div className="w-8 h-8 rounded-full bg-purple-100 dark:bg-purple-950/60 text-purple-700 dark:text-purple-300 flex items-center justify-center font-bold text-xs">
                                {hm.name.charAt(0)}
                              </div>
                              <div>
                                <div className="font-semibold text-slate-900 dark:text-white">
                                  {hm.name}
                                </div>
                                <div className="text-xs text-slate-400">{hm.email}</div>
                              </div>
                            </div>
                          </td>
                          <td className="px-4 py-3.5 font-medium text-slate-800 dark:text-slate-200">
                            {hm.assigned_jobs_count} vacancies
                          </td>
                          <td className="px-4 py-3.5 font-medium text-slate-800 dark:text-slate-200">
                            {hm.total_applications_count}
                          </td>
                          <td className="px-4 py-3.5 text-slate-700 dark:text-slate-300">
                            {hm.pending_reviews_count}
                          </td>
                          <td className="px-4 py-3.5 text-slate-700 dark:text-slate-300">
                            {hm.active_interviews_count}
                          </td>
                          <td className="px-4 py-3.5">
                            {renderCapacityBadge(hm.workload_status)}
                          </td>
                        </tr>
                      ))
                    )}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: MY ASSIGNED VACANCIES */}
      {activeTab === "my_vacancies" && (
        <div className="space-y-4">
          {myVacancies.length === 0 ? (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-12 text-center text-slate-500">
              <Briefcase className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <h3 className="font-semibold text-slate-800 dark:text-slate-200">
                No vacancies currently assigned to your account
              </h3>
              <p className="text-xs text-slate-400 mt-1">
                You will see vacancies here once you are assigned as lead recruiter or hiring manager.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {myVacancies.map((vac) => (
                <div
                  key={vac.id}
                  className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-4"
                >
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <h3 className="font-semibold text-base text-slate-900 dark:text-white">
                          {vac.title}
                        </h3>
                        <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 uppercase">
                          {vac.status}
                        </span>
                      </div>
                      <p className="text-xs text-slate-500 mt-0.5">
                        {vac.department} &bull; {vac.work_arrangement} &bull; {vac.vacancies} open position{vac.vacancies === 1 ? "" : "s"}
                      </p>
                    </div>

                    <button
                      type="button"
                      onClick={() => openHistory(vac.id, vac.title)}
                      title="View assignment audit history"
                      className="p-1.5 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                      <History className="w-4 h-4" />
                    </button>
                  </div>

                  {/* Metrics Row */}
                  <div className="grid grid-cols-3 gap-2 p-3 bg-slate-50 dark:bg-slate-800/60 rounded-lg text-center text-xs">
                    <div>
                      <div className="font-bold text-slate-900 dark:text-white text-base">
                        {vac.active_applications_count}
                      </div>
                      <div className="text-[11px] text-slate-400">Total Applicants</div>
                    </div>
                    <div>
                      <div className="font-bold text-indigo-600 text-base">
                        {vac.pending_reviews_count}
                      </div>
                      <div className="text-[11px] text-slate-400">Pending Review</div>
                    </div>
                    <div>
                      <div className="font-bold text-purple-600 text-base">
                        {vac.scheduled_interviews_count}
                      </div>
                      <div className="text-[11px] text-slate-400">In Interview</div>
                    </div>
                  </div>

                  {/* Team Staffing */}
                  <div className="text-xs space-y-1 text-slate-600 dark:text-slate-300">
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Lead Recruiter:</span>
                      <span className="font-medium text-slate-800 dark:text-slate-200">
                        {vac.recruiter_name || "Unassigned"}
                      </span>
                    </div>
                    <div className="flex items-center justify-between">
                      <span className="text-slate-400">Hiring Manager:</span>
                      <span className="font-medium text-slate-800 dark:text-slate-200">
                        {vac.hiring_manager_name || "Unassigned"}
                      </span>
                    </div>
                  </div>

                  {/* Action Buttons */}
                  <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
                    <Link
                      href={`/hr/jobs/${vac.id}`}
                      className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 flex items-center gap-1"
                    >
                      View Details
                      <ExternalLink className="w-3 h-3" />
                    </Link>

                    <Link
                      href={`/hr/pipeline?job_id=${vac.id}`}
                      className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 hover:bg-indigo-100 flex items-center gap-1"
                    >
                      Open Pipeline
                      <ChevronRight className="w-3.5 h-3.5" />
                    </Link>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* REASSIGN VACANCY MODAL */}
      {showReassignModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white">
                  Assign Vacancy Leads
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Update lead recruiter and hiring manager assignments with audit logging.
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowReassignModal(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form noValidate onSubmit={handleReassignSubmit} className="p-5 space-y-4">
              {/* Job Selector */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                  Job Requisition *
                </label>
                <select
                  data-testid="reassign-job-select"
                  value={reassignJobId}
                  onChange={(e) => setReassignJobId(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {jobs.map((job) => (
                    <option key={job.id} value={job.id}>
                      {job.title} ({job.department})
                    </option>
                  ))}
                </select>
              </div>

              {/* Recruiter Selector */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                  Lead Recruiter
                </label>
                <select
                  data-testid="reassign-recruiter-select"
                  value={selectedRecruiterId}
                  onChange={(e) => setSelectedRecruiterId(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="KEEP">-- Keep Current Assignment --</option>
                  <option value="NONE">-- Remove Assignment (Unassigned) --</option>
                  {teamMembers
                    .filter((m) => ["recruiter", "org_admin", "admin", "platform_super_admin"].includes(m.role))
                    .map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.email})
                      </option>
                    ))}
                </select>
              </div>

              {/* Hiring Manager Selector */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                  Hiring Manager
                </label>
                <select
                  data-testid="reassign-hm-select"
                  value={selectedHmId}
                  onChange={(e) => setSelectedHmId(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  <option value="KEEP">-- Keep Current Assignment --</option>
                  <option value="NONE">-- Remove Assignment (Unassigned) --</option>
                  {teamMembers
                    .filter((m) => ["hiring_manager", "org_admin", "admin", "platform_super_admin"].includes(m.role))
                    .map((m) => (
                      <option key={m.id} value={m.id}>
                        {m.name} ({m.email})
                      </option>
                    ))}
                </select>
              </div>

              {/* Handover Reason */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                  Business Reason / Handover Notes (Optional)
                </label>
                <textarea
                  rows={2}
                  value={reassignReason}
                  onChange={(e) => setReassignReason(e.target.value)}
                  placeholder="e.g. Q4 staffing reallocation, team coverage..."
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                />
              </div>

              {/* Status alerts */}
              {reassignError && (
                <div className="p-3 rounded-lg bg-rose-50 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0" />
                  <span>{reassignError}</span>
                </div>
              )}

              {reassignSuccess && (
                <div className="p-3 rounded-lg bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 text-xs flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4 flex-shrink-0 text-emerald-600" />
                  <span>{reassignSuccess}</span>
                </div>
              )}

              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowReassignModal(false)}
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 dark:text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={reassignSubmitting}
                  className="px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 shadow-sm flex items-center gap-2"
                >
                  {reassignSubmitting ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Saving...
                    </>
                  ) : (
                    "Save Assignment"
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ASSIGNMENT AUDIT HISTORY MODAL */}
      {historyJob && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <History className="w-4 h-4 text-indigo-500" />
                  Assignment History
                </h3>
                <p className="text-xs text-slate-500 mt-0.5 truncate max-w-xs">
                  {historyJob.title}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setHistoryJob(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 max-h-96 overflow-y-auto">
              {historyLoading ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-600" />
                  Loading assignment audit logs...
                </div>
              ) : historyError ? (
                <div className="p-3 text-xs text-rose-600 bg-rose-50 dark:bg-rose-950/40 rounded-lg">
                  {historyError}
                </div>
              ) : historyItems.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  No historical assignment changes recorded for this vacancy yet.
                </div>
              ) : (
                <div className="space-y-4">
                  {historyItems.map((entry) => (
                    <div
                      key={entry.id}
                      className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                        <span className="flex items-center gap-1 font-mono text-[11px]">
                          <Clock className="w-3 h-3" />
                          {new Date(entry.created_at).toLocaleString()}
                        </span>
                        <span className="font-medium text-slate-700 dark:text-slate-300">
                          {entry.actor_name || "System"}
                        </span>
                      </div>

                      <div className="flex items-center gap-2 font-semibold">
                        <span className="px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700 text-[10px] uppercase">
                          {entry.assignment_type === "recruiter" ? "Lead Recruiter" : "Hiring Manager"}
                        </span>
                        <span className="text-slate-500">
                          {entry.previous_user_name || "Unassigned"}
                        </span>
                        <ArrowRight className="w-3 h-3 text-slate-400" />
                        <span className="text-indigo-600 dark:text-indigo-400">
                          {entry.new_user_name || "Unassigned"}
                        </span>
                      </div>

                      {entry.reason && (
                        <p className="text-slate-600 dark:text-slate-300 pt-1 border-t border-slate-200/60 dark:border-slate-700/60">
                          <span className="font-medium text-slate-500">Reason:</span>{" "}
                          {entry.reason}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex justify-end">
              <button
                type="button"
                onClick={() => setHistoryJob(null)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-white border border-slate-300 dark:bg-slate-800 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50"
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
