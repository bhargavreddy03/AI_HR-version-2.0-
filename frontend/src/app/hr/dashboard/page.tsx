"use client";

import React, { useState, useEffect, useCallback } from "react";
import Link from "next/link";
import {
  Users,
  Briefcase,
  Clock,
  CheckCircle2,
  Calendar,
  Award,
  Filter,
  ArrowRight,
  TrendingUp,
  AlertCircle,
  PlusCircle,
  Kanban,
  FileText,
  RotateCw,
} from "lucide-react";
import {
  ResponsiveContainer,
  AreaChart,
  Area,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
} from "recharts";
import { hrApi } from "@/lib/hrApi";
import type {
  HrDashboardOverviewResponse,
  HrDashboardFilterParams,
} from "@/types/hr";

export default function HrDashboardPage() {
  const [data, setData] = useState<HrDashboardOverviewResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filter States
  const [dateRange, setDateRange] = useState<string>("30");
  const [department, setDepartment] = useState<string>("");
  const [stage, setStage] = useState<string>("");

  const loadDashboard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);

      const filters: HrDashboardFilterParams = {};
      if (department) filters.department = department;
      if (stage) filters.stage = stage;

      if (dateRange !== "all") {
        const days = Number(dateRange);
        const start = new Date();
        start.setDate(start.getDate() - days);
        filters.start_date = start.toISOString();
      }

      const res = await hrApi.getDashboardOverview(filters);
      setData(res);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load HR dashboard overview");
    } finally {
      setLoading(false);
    }
  }, [dateRange, department, stage]);

  useEffect(() => {
    loadDashboard();
  }, [loadDashboard]);

  // Stage badge color mapping
  const getStageBadge = (stageName: string) => {
    const s = stageName.toLowerCase();
    if (s.includes("hired") || s.includes("offer")) {
      return "bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800";
    }
    if (s.includes("interview")) {
      return "bg-purple-50 text-purple-700 dark:bg-purple-950/40 dark:text-purple-300 border-purple-200 dark:border-purple-800";
    }
    if (s.includes("shortlist")) {
      return "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300 border-blue-200 dark:border-blue-800";
    }
    if (s.includes("review") || s.includes("applied") || s.includes("submit")) {
      return "bg-amber-50 text-amber-700 dark:bg-amber-950/40 dark:text-amber-300 border-amber-200 dark:border-amber-800";
    }
    if (s.includes("reject") || s.includes("withdraw")) {
      return "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300 border-slate-200 dark:border-slate-700";
    }
    return "bg-indigo-50 text-indigo-700 dark:bg-indigo-950/40 dark:text-indigo-300 border-indigo-200 dark:border-indigo-800";
  };

  return (
    <div className="space-y-8 pb-12">
      {/* 1. Header with Title & Quick Action Buttons */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Recruitment Overview
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 dark:bg-indigo-950/50 text-primary-700 dark:text-primary-300 border border-primary-200/60 dark:border-primary-800/60">
              Live Analytics
            </span>
          </div>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            Enterprise recruitment pipeline performance, candidate conversion velocity, and real-time requisitions.
          </p>
        </div>

        <div className="flex items-center gap-2.5 self-start md:self-auto">
          <button
            type="button"
            onClick={loadDashboard}
            aria-label="Refresh dashboard metrics"
            className="p-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-300 rounded-xl transition-colors shadow-sm"
          >
            <RotateCw className="w-4 h-4" />
          </button>

          <Link
            href="/hr/pipeline"
            className="inline-flex items-center gap-1.5 px-3.5 py-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 rounded-xl transition-colors shadow-sm"
          >
            <Kanban className="w-3.5 h-3.5 text-primary-600" />
            <span>Pipeline Board</span>
          </Link>

          <Link
            href="/hr/jobs/new"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
          >
            <PlusCircle className="w-3.5 h-3.5" />
            <span>Create Requisition</span>
          </Link>
        </div>
      </div>

      {/* 2. Global Filter Toolbar (Backend Query Integrated) */}
      <div className="p-4 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm space-y-3">
        <div className="flex items-center gap-2 text-xs font-bold text-slate-800 dark:text-slate-200 pb-2 border-b border-slate-100 dark:border-slate-800">
          <Filter className="w-3.5 h-3.5 text-primary-600" />
          <span>Analytics Filters</span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {/* Date Range Filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">
              Time Horizon
            </label>
            <select
              value={dateRange}
              onChange={(e) => setDateRange(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            >
              <option value="7">Past 7 Days</option>
              <option value="30">Past 30 Days</option>
              <option value="90">Past 90 Days</option>
              <option value="all">All Time History</option>
            </select>
          </div>

          {/* Department Filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">
              Department
            </label>
            <input
              type="text"
              placeholder="All Departments (e.g. Engineering)"
              value={department}
              onChange={(e) => setDepartment(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none placeholder:text-slate-400"
            />
          </div>

          {/* Pipeline Stage Filter */}
          <div>
            <label className="block text-[11px] font-semibold text-slate-500 mb-1">
              Application Stage
            </label>
            <select
              value={stage}
              onChange={(e) => setStage(e.target.value)}
              className="w-full px-3 py-1.5 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            >
              <option value="">All Stages</option>
              <option value="submitted">Submitted / New</option>
              <option value="under_review">Under Review</option>
              <option value="shortlisted">Shortlisted</option>
              <option value="interviewing">Interviewing</option>
              <option value="hired">Hired / Closed</option>
            </select>
          </div>
        </div>
      </div>

      {/* Error Banner */}
      {error && (
        <div className="flex items-center gap-2 p-4 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs font-semibold text-red-800 dark:text-red-300 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      )}

      {/* 3. High-Level KPI Metric Cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 sm:gap-4">
        {/* Total Candidates */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold">Total Candidates</span>
            <Users className="w-3.5 h-3.5 text-primary-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">
            {loading ? "..." : data?.metrics.total_candidates ?? 0}
          </p>
          <span className="text-[10px] text-slate-400">Unique Applicants</span>
        </div>

        {/* Total Applications */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold">Applications</span>
            <FileText className="w-3.5 h-3.5 text-indigo-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">
            {loading ? "..." : data?.metrics.total_applications ?? 0}
          </p>
          <span className="text-[10px] text-emerald-600 font-medium">All Open Jobs</span>
        </div>

        {/* Active Jobs */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-slate-500">
            <span className="text-[11px] font-semibold">Active Jobs</span>
            <Briefcase className="w-3.5 h-3.5 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white">
            {loading ? "..." : data?.metrics.active_jobs ?? 0}
          </p>
          <span className="text-[10px] text-slate-400">
            {data?.metrics.draft_jobs ? `${data.metrics.draft_jobs} drafts` : "Published"}
          </span>
        </div>

        {/* Awaiting Review */}
        <div className="bg-white dark:bg-slate-900 border border-amber-200/80 dark:border-amber-900/60 rounded-2xl p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-amber-700 dark:text-amber-400">
            <span className="text-[11px] font-semibold">Needs Review</span>
            <Clock className="w-3.5 h-3.5" />
          </div>
          <p className="text-2xl font-bold text-amber-900 dark:text-amber-300">
            {loading ? "..." : data?.metrics.applications_awaiting_review ?? 0}
          </p>
          <span className="text-[10px] text-amber-700 font-medium">Triage Queue</span>
        </div>

        {/* Scheduled Interviews */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-purple-600">
            <span className="text-[11px] font-semibold">Interviews</span>
            <Calendar className="w-3.5 h-3.5" />
          </div>
          <p className="text-2xl font-bold text-purple-900 dark:text-purple-300">
            {loading ? "..." : data?.metrics.scheduled_interviews ?? 0}
          </p>
          <span className="text-[10px] text-purple-600 font-medium">Active Rounds</span>
        </div>

        {/* Hired Candidates */}
        <div className="bg-white dark:bg-slate-900 border border-emerald-200/80 dark:border-emerald-900/60 rounded-2xl p-4 shadow-sm space-y-2">
          <div className="flex items-center justify-between text-emerald-600">
            <span className="text-[11px] font-semibold">Hired</span>
            <Award className="w-3.5 h-3.5" />
          </div>
          <p className="text-2xl font-bold text-emerald-800 dark:text-emerald-300">
            {loading ? "..." : data?.metrics.hired_candidates ?? 0}
          </p>
          <span className="text-[10px] text-emerald-600 font-medium">Offers Completed</span>
        </div>
      </div>

      {/* 4. Visualizations: Recruitment Funnel & Applications Over Time */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Recruitment Funnel Chart */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Recruitment Funnel Conversion
              </h2>
              <p className="text-[11px] text-slate-500">
                Conversion ratios across pipeline stages from application to hire.
              </p>
            </div>
            <TrendingUp className="w-4 h-4 text-primary-500" />
          </div>

          {loading ? (
            <div className="h-64 flex items-center justify-center text-xs text-slate-400 animate-pulse">
              Generating recruitment funnel...
            </div>
          ) : (data?.recruitment_funnel.length ?? 0) === 0 ? (
            <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400">
              <p>No application pipeline data recorded for selected filters.</p>
            </div>
          ) : (
            <div className="space-y-3 pt-2">
              {data?.recruitment_funnel.map((item) => (
                <div key={item.stage} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <span className="font-semibold text-slate-700 dark:text-slate-300">
                      {item.label}
                    </span>
                    <div className="flex items-center gap-2">
                      <span className="font-bold text-slate-900 dark:text-white">
                        {item.count}
                      </span>
                      <span className="text-[11px] text-slate-400">
                        ({item.percentage}%)
                      </span>
                    </div>
                  </div>
                  <div className="w-full h-2.5 bg-slate-100 dark:bg-slate-800 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-gradient-to-r from-primary-600 to-indigo-500 rounded-full transition-all duration-500"
                      style={{ width: `${Math.max(item.percentage, item.count > 0 ? 5 : 0)}%` }}
                    />
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Applications Over Time AreaChart */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Application Influx Over Time
              </h2>
              <p className="text-[11px] text-slate-500">
                Daily application submission velocity across active requisitions.
              </p>
            </div>
            <Calendar className="w-4 h-4 text-primary-500" />
          </div>

          {loading ? (
            <div className="h-64 flex items-center justify-center text-xs text-slate-400 animate-pulse">
              Loading submission trend...
            </div>
          ) : (data?.applications_over_time.length ?? 0) === 0 ? (
            <div className="h-64 flex flex-col items-center justify-center text-xs text-slate-400">
              <p>No daily timeline submissions found for current time window.</p>
            </div>
          ) : (
            <div className="h-64 pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart
                  data={data?.applications_over_time}
                  margin={{ top: 10, right: 10, left: -20, bottom: 0 }}
                >
                  <defs>
                    <linearGradient id="colorApps" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#4f46e5" stopOpacity={0.4} />
                      <stop offset="95%" stopColor="#4f46e5" stopOpacity={0.0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      borderRadius: "12px",
                      color: "#fff",
                      fontSize: "12px",
                      border: "none",
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="applications_count"
                    name="Applications"
                    stroke="#4f46e5"
                    strokeWidth={2}
                    fillOpacity={1}
                    fill="url(#colorApps)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      </div>

      {/* 5. Department Distribution & Active Requisitions Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Applications by Department BarChart */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <h2 className="text-sm font-bold text-slate-900 dark:text-white">
              By Department
            </h2>
            <span className="text-[11px] text-slate-400 font-medium">Distribution</span>
          </div>

          {loading ? (
            <div className="h-56 flex items-center justify-center text-xs text-slate-400 animate-pulse">
              Aggregating department metrics...
            </div>
          ) : (data?.applications_by_department.length ?? 0) === 0 ? (
            <div className="h-56 flex items-center justify-center text-xs text-slate-400">
              No department data available.
            </div>
          ) : (
            <div className="h-56 pt-2">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={data?.applications_by_department} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" vertical={false} opacity={0.15} />
                  <XAxis dataKey="department" tick={{ fontSize: 10 }} />
                  <YAxis allowDecimals={false} tick={{ fontSize: 10 }} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: "#0f172a",
                      borderRadius: "12px",
                      color: "#fff",
                      fontSize: "12px",
                      border: "none",
                    }}
                  />
                  <Bar dataKey="applications_count" name="Applications" fill="#6366f1" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>

        {/* Active Jobs Overview Table */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4 lg:col-span-2 flex flex-col justify-between">
          <div>
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Briefcase className="w-4 h-4 text-primary-600" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                  Active Requisitions Breakdown
                </h2>
              </div>
              <Link
                href="/hr/jobs"
                className="text-xs font-semibold text-primary-600 hover:underline flex items-center gap-1"
              >
                <span>View All Jobs</span>
                <ArrowRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {loading ? (
              <div className="py-12 text-center text-xs text-slate-400 animate-pulse">
                Loading job requisitions...
              </div>
            ) : (data?.applications_by_job.length ?? 0) === 0 ? (
              <div className="py-12 text-center text-xs text-slate-400">
                No active job requisitions published yet.
              </div>
            ) : (
              <div className="overflow-x-auto pt-2">
                <table className="w-full text-left text-xs">
                  <thead>
                    <tr className="border-b border-slate-100 dark:border-slate-800 text-slate-400 text-[11px]">
                      <th className="pb-2 font-semibold">Requisition Title</th>
                      <th className="pb-2 font-semibold">Department</th>
                      <th className="pb-2 font-semibold">Total Apps</th>
                      <th className="pb-2 font-semibold">In Pipeline</th>
                      <th className="pb-2 font-semibold text-right">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                    {data?.applications_by_job.map((j) => (
                      <tr key={j.job_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                        <td className="py-2.5 font-bold text-slate-900 dark:text-white">
                          {j.job_title}
                        </td>
                        <td className="py-2.5 text-slate-500">{j.department}</td>
                        <td className="py-2.5 font-semibold text-slate-800 dark:text-slate-200">
                          {j.applications_count}
                        </td>
                        <td className="py-2.5 text-primary-600 font-semibold">
                          {j.active_count}
                        </td>
                        <td className="py-2.5 text-right">
                          <span className="inline-block px-2 py-0.5 rounded-full text-[10px] font-semibold uppercase bg-emerald-50 text-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
                            {j.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* 6. Recent Applicants Table & Quick Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Recent Applicants Review Table */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4 lg:col-span-2">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Users className="w-4 h-4 text-primary-600" />
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Recent Candidate Submissions
              </h2>
            </div>
            <Link
              href="/hr/applicants"
              className="text-xs font-semibold text-primary-600 hover:underline flex items-center gap-1"
            >
              <span>Applicant Workspace</span>
              <ArrowRight className="w-3.5 h-3.5" />
            </Link>
          </div>

          {loading ? (
            <div className="py-12 text-center text-xs text-slate-400 animate-pulse">
              Loading recent candidate submissions...
            </div>
          ) : (data?.recent_applicants.length ?? 0) === 0 ? (
            <div className="py-12 text-center text-xs text-slate-400">
              No recent candidate submissions found.
            </div>
          ) : (
            <div className="overflow-x-auto pt-1">
              <table className="w-full text-left text-xs">
                <thead>
                  <tr className="border-b border-slate-100 dark:border-slate-800 text-slate-400 text-[11px]">
                    <th className="pb-2 font-semibold">Candidate</th>
                    <th className="pb-2 font-semibold">Role Applied</th>
                    <th className="pb-2 font-semibold">Top Skills</th>
                    <th className="pb-2 font-semibold">Applied At</th>
                    <th className="pb-2 font-semibold text-right">Stage</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                  {data?.recent_applicants.map((cand) => (
                    <tr key={cand.application_id} className="hover:bg-slate-50/50 dark:hover:bg-slate-800/40">
                      <td className="py-3">
                        <div className="font-bold text-slate-900 dark:text-white">
                          {cand.candidate_name}
                        </div>
                        <div className="text-[11px] text-slate-400">{cand.candidate_email}</div>
                      </td>
                      <td className="py-3">
                        <div className="font-semibold text-slate-800 dark:text-slate-200">
                          {cand.job_title}
                        </div>
                        <div className="text-[10px] text-slate-400">{cand.department}</div>
                      </td>
                      <td className="py-3">
                        <div className="flex flex-wrap gap-1">
                          {cand.top_skills.slice(0, 2).map((skill) => (
                            <span
                              key={skill}
                              className="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-medium"
                            >
                              {skill}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="py-3 text-[11px] text-slate-500">
                        {new Date(cand.applied_at).toLocaleDateString()}
                      </td>
                      <td className="py-3 text-right">
                        <span
                          className={`inline-block px-2.5 py-0.5 rounded-full text-[10px] font-semibold border capitalize ${getStageBadge(
                            cand.stage
                          )}`}
                        >
                          {cand.stage.replace("_", " ")}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* Recent Recruitment Activity Feed & Quick Actions */}
        <div className="space-y-6">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Recent Recruitment Activity
              </h2>
              <Clock className="w-3.5 h-3.5 text-slate-400" />
            </div>

            {loading ? (
              <div className="py-8 text-center text-xs text-slate-400 animate-pulse">
                Loading activity log...
              </div>
            ) : (data?.recent_activities.length ?? 0) === 0 ? (
              <div className="py-8 text-center text-xs text-slate-400">
                No recent activity events recorded.
              </div>
            ) : (
              <div className="space-y-3.5 pt-1">
                {data?.recent_activities.map((act) => (
                  <div key={act.id} className="flex items-start gap-2.5 text-xs">
                    <div className="w-2 h-2 rounded-full bg-primary-600 mt-1.5 shrink-0" />
                    <div className="space-y-0.5">
                      <p className="font-semibold text-slate-800 dark:text-slate-200">
                        {act.title}
                      </p>
                      <p className="text-[11px] text-slate-500 leading-snug">
                        {act.description}
                      </p>
                      <span className="text-[10px] text-slate-400">
                        {new Date(act.timestamp).toLocaleTimeString([], {
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Quick Action Navigation Card */}
          <div className="bg-gradient-to-tr from-slate-900 to-indigo-950 text-white rounded-2xl p-5 shadow-sm space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-primary-300">
              Recruitment Quick Actions
            </h3>
            <div className="grid grid-cols-1 gap-2 text-xs">
              <Link
                href="/hr/jobs/new"
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/10 hover:bg-white/15 transition-colors font-medium"
              >
                <span>Draft New Requisition</span>
                <PlusCircle className="w-3.5 h-3.5 text-primary-300" />
              </Link>
              <Link
                href="/hr/pipeline"
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/10 hover:bg-white/15 transition-colors font-medium"
              >
                <span>Review Active Pipeline</span>
                <Kanban className="w-3.5 h-3.5 text-primary-300" />
              </Link>
              <Link
                href="/hr/applicants"
                className="flex items-center justify-between p-2.5 rounded-xl bg-white/10 hover:bg-white/15 transition-colors font-medium"
              >
                <span>Triage Pending Applicants</span>
                <CheckCircle2 className="w-3.5 h-3.5 text-primary-300" />
              </Link>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
