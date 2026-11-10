"use client";

import React, { useEffect, useState } from "react";
import Link from "next/link";
import {
  FileText,
  Briefcase,
  Bookmark,
  ChevronRight,
  TrendingUp,
  AlertCircle,
  Plus,
  Clock,
  CheckCircle2,
  Calendar,
  Bell,
  Sparkles,
  Building2,
  MapPin,
  RefreshCw,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import { ApplicationStatusBadge } from "@/components/candidate/ApplicationStatusBadge";
import { DashboardSkeleton } from "@/components/candidate/DashboardSkeleton";
import type {
  CandidateFullProfile,
  CandidateApplicationSummary,
  SavedJobItem,
  CandidateResume,
  CandidateNotification,
  JobPublicSummary,
} from "@/types/candidate";

export default function CandidateDashboardPage() {
  const [profile, setProfile] = useState<CandidateFullProfile | null>(null);
  const [applications, setApplications] = useState<CandidateApplicationSummary[]>([]);
  const [savedJobs, setSavedJobs] = useState<SavedJobItem[]>([]);
  const [resumes, setResumes] = useState<CandidateResume[]>([]);
  const [notifications, setNotifications] = useState<CandidateNotification[]>([]);
  const [recommendedJobs, setRecommendedJobs] = useState<JobPublicSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboardData = async () => {
    try {
      setLoading(true);
      setError(null);

      const [profRes, appsRes, savedRes, resumesRes, notifsRes, jobsRes] =
        await Promise.allSettled([
          candidateApi.getProfile(),
          candidateApi.getMyApplications(),
          candidateApi.getSavedJobs(),
          candidateApi.getResumes(),
          candidateApi.getNotifications(),
          candidateApi.searchJobs({ limit: 4 }),
        ]);

      if (profRes.status === "fulfilled") setProfile(profRes.value);
      if (appsRes.status === "fulfilled") setApplications(appsRes.value);
      if (savedRes.status === "fulfilled") setSavedJobs(savedRes.value);
      if (resumesRes.status === "fulfilled") setResumes(resumesRes.value);
      if (notifsRes.status === "fulfilled") setNotifications(notifsRes.value);
      if (jobsRes.status === "fulfilled") {
        const val = jobsRes.value as unknown;
        if (Array.isArray(val)) {
          setRecommendedJobs(val);
        } else if (val && typeof val === "object" && "jobs" in val && Array.isArray((val as { jobs: JobPublicSummary[] }).jobs)) {
          setRecommendedJobs((val as { jobs: JobPublicSummary[] }).jobs);
        }
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load candidate dashboard");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadDashboardData();
  }, []);

  if (loading) {
    return <DashboardSkeleton />;
  }

  // Calculate metrics from live authorized data
  const totalApplications = applications.length;
  const underReviewCount = applications.filter(
    (a) => a.candidate_status === "under_review"
  ).length;
  const shortlistedCount = applications.filter(
    (a) => a.candidate_status === "shortlisted"
  ).length;
  const interviewCount = applications.filter(
    (a) => a.candidate_status === "interviewing"
  ).length;
  const savedJobsCount = savedJobs.length;

  const completeness = profile?.profile_completeness_pct || 0;
  const candidateName = profile?.user?.full_name || "Candidate";

  return (
    <div className="space-y-6">
      {/* 1. Welcome Banner */}
      <div className="relative overflow-hidden bg-gradient-to-r from-white via-indigo-50/30 to-purple-50/20 dark:from-slate-900 dark:via-slate-900 dark:to-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div className="space-y-1">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-indigo-50 text-indigo-700 dark:bg-indigo-950/50 dark:text-indigo-300 border border-indigo-100 dark:border-indigo-900/60 mb-1">
              <Sparkles className="w-3 h-3" /> Candidate Career Portal
            </div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Welcome back, {candidateName}
            </h1>
            <p className="text-sm text-slate-500 dark:text-slate-400 max-w-2xl">
              {profile?.headline ||
                "Review your recruitment pipeline, upcoming interview stages, and career opportunities."}
            </p>
          </div>

          <div className="flex items-center gap-2.5 shrink-0">
            <Link
              href="/candidate/jobs"
              className="inline-flex items-center gap-2 px-4 py-2 bg-indigo-600 hover:bg-indigo-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors focus:ring-2 focus:ring-indigo-500 focus:outline-none"
            >
              <Briefcase className="w-3.5 h-3.5" />
              Find Jobs
            </Link>
            <Link
              href="/candidate/resumes"
              className="inline-flex items-center gap-2 px-4 py-2 bg-white dark:bg-slate-800 hover:bg-slate-50 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 border border-slate-200 dark:border-slate-700 text-xs font-semibold rounded-xl transition-colors focus:ring-2 focus:ring-slate-400 focus:outline-none"
            >
              <FileText className="w-3.5 h-3.5" />
              Upload Resume
            </Link>
          </div>
        </div>
      </div>

      {error && (
        <div
          role="alert"
          className="flex items-center justify-between p-4 text-xs text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 shrink-0" />
            <span>Note: Local session active. Offline sync ({error})</span>
          </div>
          <button
            type="button"
            onClick={loadDashboardData}
            className="inline-flex items-center gap-1 font-semibold hover:underline"
          >
            <RefreshCw className="w-3 h-3" /> Retry
          </button>
        </div>
      )}

      {/* 2. Profile Completeness Progress Card */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <div className="p-1.5 rounded-lg bg-indigo-50 dark:bg-indigo-950/50 text-indigo-600 dark:text-indigo-400">
              <TrendingUp className="w-4 h-4" />
            </div>
            <div>
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Profile Completeness
              </h2>
              <p className="text-[11px] text-slate-500">
                Complete your skills and resume to increase organizational recruiter visibility
              </p>
            </div>
          </div>
          <span className="text-sm font-bold text-indigo-600 dark:text-indigo-400">
            {completeness}%
          </span>
        </div>

        {/* Progress bar */}
        <div className="w-full bg-slate-100 dark:bg-slate-800 h-2.5 rounded-full overflow-hidden">
          <div
            className="bg-indigo-600 dark:bg-indigo-500 h-2.5 rounded-full transition-all duration-500 ease-out"
            style={{ width: `${completeness}%` }}
            role="progressbar"
            aria-valuenow={completeness}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>

        <div className="flex items-center justify-between text-xs text-slate-500 dark:text-slate-400 pt-0.5">
          <div className="flex items-center gap-3 text-[11px]">
            <span className="flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3 text-emerald-500" /> Verified Identity
            </span>
            <span className="flex items-center gap-1">
              {resumes.length > 0 ? (
                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
              ) : (
                <div className="w-3 h-3 rounded-full border border-slate-300" />
              )}
              {resumes.length > 0 ? "Resume Ingested" : "Resume Needed"}
            </span>
            <span className="flex items-center gap-1">
              {(profile?.self_declared_skills?.length || 0) > 0 ? (
                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
              ) : (
                <div className="w-3 h-3 rounded-full border border-slate-300" />
              )}
              Taxonomy Skills ({profile?.self_declared_skills?.length || 0})
            </span>
          </div>

          <Link
            href="/candidate/profile"
            className="font-medium text-indigo-600 dark:text-indigo-400 hover:underline inline-flex items-center gap-1 text-[11px]"
          >
            Edit Profile <ChevronRight className="w-3.5 h-3.5" />
          </Link>
        </div>
      </div>

      {/* 3. Five-Card Metrics Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3.5">
        {/* Total Applications */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Total Apps
            </span>
            <Briefcase className="w-4 h-4 text-blue-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5">
            {totalApplications}
          </p>
          <span className="text-[10px] text-slate-400">Submitted roles</span>
        </div>

        {/* Under Review */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Under Review
            </span>
            <Clock className="w-4 h-4 text-amber-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5">
            {underReviewCount}
          </p>
          <span className="text-[10px] text-slate-400">Active screening</span>
        </div>

        {/* Shortlisted */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Shortlisted
            </span>
            <CheckCircle2 className="w-4 h-4 text-purple-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5">
            {shortlistedCount}
          </p>
          <span className="text-[10px] text-slate-400">Candidate qualified</span>
        </div>

        {/* Upcoming Interviews */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-300 transition-colors">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Interviews
            </span>
            <Calendar className="w-4 h-4 text-indigo-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5">
            {interviewCount}
          </p>
          <span className="text-[10px] text-slate-400">Scheduled rounds</span>
        </div>

        {/* Saved Jobs */}
        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 shadow-sm hover:border-slate-300 transition-colors col-span-2 sm:col-span-1">
          <div className="flex items-center justify-between">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400">
              Saved Jobs
            </span>
            <Bookmark className="w-4 h-4 text-emerald-500" />
          </div>
          <p className="text-2xl font-bold text-slate-900 dark:text-white mt-1.5">
            {savedJobsCount}
          </p>
          <span className="text-[10px] text-slate-400">Bookmarked positions</span>
        </div>
      </div>

      {/* 4. Two-Column Dashboard Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (Span 2): Recent Applications & Relevant Jobs */}
        <div className="lg:col-span-2 space-y-6">
          {/* Recent Applications Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white">
                  Recent Applications
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Track your hiring progress across tenant organizations
                </p>
              </div>
              <Link
                href="/candidate/applications"
                className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
              >
                View all ({applications.length}) <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {applications.length === 0 ? (
              <div className="text-center py-10 border border-dashed border-slate-200 dark:border-slate-800 rounded-xl space-y-3">
                <Briefcase className="w-8 h-8 text-slate-400 mx-auto" />
                <div className="space-y-1">
                  <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                    No job applications submitted yet
                  </p>
                  <p className="text-xs text-slate-500 max-w-sm mx-auto">
                    Search active enterprise openings and apply with your verified skills.
                  </p>
                </div>
                <Link
                  href="/candidate/jobs"
                  className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold bg-indigo-600 text-white rounded-lg hover:bg-indigo-700 transition-colors"
                >
                  <Plus className="w-3.5 h-3.5" /> Explore Open Roles
                </Link>
              </div>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {applications.slice(0, 4).map((app) => (
                  <div
                    key={app.id}
                    className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3 hover:bg-slate-50/50 dark:hover:bg-slate-800/40 rounded-lg px-2 -mx-2 transition-colors"
                  >
                    <div className="space-y-1">
                      <p className="text-sm font-bold text-slate-900 dark:text-white">
                        {app.job?.title || "Open Position"}
                      </p>
                      <p className="text-xs text-slate-500 dark:text-slate-400">
                        {app.job?.department || "General"} &bull; {app.job?.location || "Remote"} &bull; Applied {new Date(app.applied_at).toLocaleDateString()}
                      </p>
                    </div>

                    <div className="flex items-center gap-3">
                      <ApplicationStatusBadge status={app.candidate_status} />
                      <Link
                        href="/candidate/applications"
                        className="p-1.5 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg text-slate-400 hover:text-slate-600 transition-colors"
                        title="View application history"
                      >
                        <ChevronRight className="w-4 h-4" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Relevant Jobs Preview */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div>
                <h2 className="text-base font-bold text-slate-900 dark:text-white">
                  Explore Open Opportunities
                </h2>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Positions currently accepting candidate applications
                </p>
              </div>
              <Link
                href="/candidate/jobs"
                className="text-xs font-semibold text-indigo-600 dark:text-indigo-400 hover:underline flex items-center gap-1"
              >
                Browse all <ChevronRight className="w-3.5 h-3.5" />
              </Link>
            </div>

            {recommendedJobs.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-6">
                No active jobs published at this moment.
              </p>
            ) : (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                {recommendedJobs.map((job) => (
                  <div
                    key={job.id}
                    className="p-4 border border-slate-100 dark:border-slate-800 rounded-xl hover:border-slate-200 dark:hover:border-slate-700 transition-all flex flex-col justify-between space-y-2 bg-slate-50/30 dark:bg-slate-800/20"
                  >
                    <div>
                      <h3 className="text-xs font-bold text-slate-900 dark:text-white line-clamp-1">
                        {job.title}
                      </h3>
                      <div className="flex items-center gap-2 text-[11px] text-slate-500 mt-0.5">
                        <span className="flex items-center gap-0.5">
                          <Building2 className="w-3 h-3" />
                          {job.department || "General"}
                        </span>
                        <span className="flex items-center gap-0.5">
                          <MapPin className="w-3 h-3" />
                          {job.location || "Remote"}
                        </span>
                      </div>
                    </div>

                    <div className="flex items-center justify-between pt-1 border-t border-slate-100 dark:border-slate-800/80">
                      <span className="text-[10px] uppercase font-semibold text-indigo-600 dark:text-indigo-400 bg-indigo-50 dark:bg-indigo-950/40 px-2 py-0.5 rounded">
                        {job.remote_type}
                      </span>
                      <Link
                        href="/candidate/jobs"
                        className="text-[11px] font-semibold text-slate-700 dark:text-slate-300 hover:text-indigo-600 inline-flex items-center gap-0.5"
                      >
                        View <ChevronRight className="w-3.5 h-3.5" />
                      </Link>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column (Span 1): Upcoming Interviews & Notifications */}
        <div className="space-y-6">
          {/* Upcoming Interview Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5">
              <div className="flex items-center gap-2">
                <Calendar className="w-4 h-4 text-indigo-600 dark:text-indigo-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white">
                  Upcoming Interviews
                </h3>
              </div>
              <span className="text-[10px] font-bold px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                {interviewCount} Scheduled
              </span>
            </div>

            {interviewCount === 0 ? (
              <div className="py-6 text-center space-y-2">
                <Calendar className="w-8 h-8 text-slate-300 dark:text-slate-600 mx-auto" />
                <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  No upcoming interview rounds scheduled.
                </p>
                <p className="text-[11px] text-slate-400">
                  When a recruiter advances your application to an interview round, details and calendar links will appear here.
                </p>
              </div>
            ) : (
              <div className="space-y-2.5">
                {applications
                  .filter((a) => a.candidate_status === "interviewing")
                  .map((app) => (
                    <div
                      key={app.id}
                      className="p-3 bg-indigo-50/50 dark:bg-indigo-950/30 border border-indigo-100 dark:border-indigo-900/50 rounded-xl space-y-1"
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-bold text-slate-900 dark:text-white">
                          {app.job?.title}
                        </span>
                        <span className="text-[10px] font-semibold text-indigo-700 dark:text-indigo-300 bg-white dark:bg-indigo-900 px-1.5 py-0.5 rounded">
                          Active Round
                        </span>
                      </div>
                      <p className="text-[11px] text-slate-500">
                        {app.job?.department || "Hiring Team"} &bull; Check your email for calendar invite
                      </p>
                    </div>
                  ))}
              </div>
            )}
          </div>

          {/* Recent In-App Notifications Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2.5">
              <div className="flex items-center gap-2">
                <Bell className="w-4 h-4 text-purple-600 dark:text-purple-400" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-900 dark:text-white">
                  Notifications
                </h3>
              </div>
              <span className="text-[10px] text-slate-400">
                {notifications.filter((n) => !n.is_read).length} unread
              </span>
            </div>

            {notifications.length === 0 ? (
              <p className="text-xs text-slate-400 py-4 text-center">
                No recent notifications.
              </p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800 space-y-2">
                {notifications.slice(0, 3).map((notif) => (
                  <div key={notif.id} className="pt-2 first:pt-0 space-y-1">
                    <div className="flex items-start justify-between gap-2">
                      <p className="text-xs font-semibold text-slate-800 dark:text-slate-200 line-clamp-1">
                        {notif.title}
                      </p>
                      {!notif.is_read && (
                        <div className="w-1.5 h-1.5 rounded-full bg-blue-600 shrink-0 mt-1" />
                      )}
                    </div>
                    <p className="text-[11px] text-slate-500 line-clamp-2 leading-relaxed">
                      {notif.body}
                    </p>
                    <span className="text-[10px] text-slate-400">
                      {new Date(notif.created_at).toLocaleDateString()}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
