"use client";

import React, { useState, useEffect, useMemo } from "react";
import Link from "next/link";
import {
  Briefcase,
  Building2,
  Calendar,
  AlertCircle,
  Loader2,
  X,
  FileText,
  Clock,
  Ban,
  ChevronRight,
  Search,
  ShieldCheck,
  CheckCircle2,
  Filter,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import { ApplicationStatusBadge } from "@/components/candidate/ApplicationStatusBadge";
import type {
  CandidateApplicationSummary,
  CandidateApplicationDetail,
} from "@/types/candidate";

type FilterTab = "all" | "in_review" | "interviewing" | "concluded";

export default function CandidateApplicationsPage() {
  const [applications, setApplications] = useState<CandidateApplicationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters & search
  const [activeTab, setActiveTab] = useState<FilterTab>("all");
  const [searchQuery, setSearchQuery] = useState("");

  // Quick Detail Drawer / Modal
  const [selectedApp, setSelectedApp] = useState<CandidateApplicationDetail | null>(null);
  const [loadingDetail, setLoadingDetail] = useState(false);

  // Withdrawal Modal
  const [withdrawTargetId, setWithdrawTargetId] = useState<string | null>(null);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawError, setWithdrawError] = useState<string | null>(null);

  const loadApplications = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await candidateApi.getMyApplications();
      setApplications(Array.isArray(data) ? data : []);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Failed to load applications");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadApplications();
  }, []);

  const handleOpenDetail = async (appId: string) => {
    setLoadingDetail(true);
    try {
      const detail = await candidateApi.getApplicationDetail(appId);
      setSelectedApp(detail);
    } catch {
      // Fallback: construct from summary
      const sum = applications.find((a) => a.id === appId);
      if (sum) {
        setSelectedApp({
          ...sum,
          timeline: [
            {
              status: sum.candidate_status,
              changed_at: sum.applied_at,
              note: "Application submitted and evidence sealed.",
            },
          ],
        });
      }
    } finally {
      setLoadingDetail(false);
    }
  };

  const handleWithdrawSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!withdrawTargetId) return;
    if (!withdrawReason.trim() || withdrawReason.trim().length < 3) {
      setWithdrawError("Please provide a valid reason for withdrawal (at least 3 characters).");
      return;
    }

    setWithdrawing(true);
    setWithdrawError(null);

    try {
      await candidateApi.withdrawApplication(withdrawTargetId, withdrawReason.trim());
      setApplications((prev) =>
        prev.map((app) =>
          app.id === withdrawTargetId
            ? { ...app, candidate_status: "withdrawn", withdrawn_at: new Date().toISOString(), withdrawal_reason: withdrawReason.trim() }
            : app
        )
      );
      if (selectedApp && selectedApp.id === withdrawTargetId) {
        setSelectedApp({
          ...selectedApp,
          candidate_status: "withdrawn",
          withdrawn_at: new Date().toISOString(),
          withdrawal_reason: withdrawReason.trim(),
          timeline: [
            ...(selectedApp.timeline || []),
            {
              status: "withdrawn",
              changed_at: new Date().toISOString(),
              note: `Candidate withdrew: ${withdrawReason.trim()}`,
            },
          ],
        });
      }
      setWithdrawTargetId(null);
      setWithdrawReason("");
    } catch (err: unknown) {
      setWithdrawError(err instanceof Error ? err.message : "Failed to withdraw application");
    } finally {
      setWithdrawing(false);
    }
  };

  // Filtered applications
  const filteredApps = useMemo(() => {
    return applications.filter((app) => {
      // Search filter
      const q = searchQuery.toLowerCase().trim();
      const title = (app.job_title || app.job?.title || "").toLowerCase();
      const org = (app.organization_name || app.job?.organization_name || "").toLowerCase();
      const matchesQuery = !q || title.includes(q) || org.includes(q);

      if (!matchesQuery) return false;

      // Tab filter
      const st = (app.candidate_status || "").toLowerCase();
      if (activeTab === "all") return true;
      if (activeTab === "in_review") {
        return (
          st === "submitted" ||
          st === "received" ||
          st === "under_review" ||
          st === "in_screening" ||
          st === "shortlisted"
        );
      }
      if (activeTab === "interviewing") {
        return st === "interview_stage" || st === "interviewing";
      }
      if (activeTab === "concluded") {
        return (
          st === "offer" ||
          st === "offer_stage" ||
          st === "not_selected" ||
          st === "rejected" ||
          st === "withdrawn"
        );
      }
      return true;
    });
  }, [applications, activeTab, searchQuery]);

  return (
    <div className="space-y-6 max-w-6xl mx-auto">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            My Applications
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Track your submission history, interview schedules, and candidate status milestones.
          </p>
        </div>

        <Link
          href="/candidate/jobs"
          className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors self-start sm:self-auto"
        >
          <Briefcase className="w-3.5 h-3.5" />
          <span>Explore More Jobs</span>
        </Link>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-xs text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0 text-amber-600" />
          <span>Note: Connect your session to sync live applications ({error})</span>
        </div>
      )}

      {/* Filter Tabs & Search Bar */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-3">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          {/* Tabs */}
          <div className="flex items-center gap-1.5 p-1 bg-slate-100 dark:bg-slate-800/80 rounded-xl text-xs font-semibold overflow-x-auto">
            <button
              type="button"
              onClick={() => setActiveTab("all")}
              className={`px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
                activeTab === "all"
                  ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              All ({applications.length})
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("in_review")}
              className={`px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
                activeTab === "in_review"
                  ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              In Review
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("interviewing")}
              className={`px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
                activeTab === "interviewing"
                  ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Interviewing
            </button>
            <button
              type="button"
              onClick={() => setActiveTab("concluded")}
              className={`px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap ${
                activeTab === "concluded"
                  ? "bg-white dark:bg-slate-900 text-slate-900 dark:text-white shadow-sm"
                  : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white"
              }`}
            >
              Concluded / Withdrawn
            </button>
          </div>

          {/* Search Box */}
          <div className="relative sm:w-64">
            <Search className="w-3.5 h-3.5 absolute left-3 top-2.5 text-slate-400" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search by role or company..."
              className="w-full pl-9 pr-3 py-1.5 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>
        </div>
      </div>

      {/* Applications List */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden">
        <div className="px-5 py-4 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <h2 className="text-sm font-bold text-slate-900 dark:text-white">
            Submitted Applications ({filteredApps.length})
          </h2>
          <span className="text-xs text-slate-400 flex items-center gap-1">
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-600" />
            <span>Cryptographic Resume Evidence Preserved</span>
          </span>
        </div>

        {loading ? (
          <div className="py-20 flex flex-col items-center justify-center space-y-2">
            <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
            <p className="text-xs text-slate-500 font-medium">Loading your applications...</p>
          </div>
        ) : filteredApps.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Briefcase className="w-10 h-10 text-slate-400 mx-auto" />
            <p className="text-base font-semibold text-slate-700 dark:text-slate-300">
              No matching applications found
            </p>
            <p className="text-xs text-slate-500 max-w-sm mx-auto">
              {searchQuery
                ? "Try adjusting your search query or switching tabs."
                : "Explore verified enterprise roles and submit your application with cryptographic evidence integrity."}
            </p>
            <div className="pt-2">
              <Link
                href="/candidate/jobs"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl transition-colors shadow-sm"
              >
                Browse Open Roles
              </Link>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {filteredApps.map((app) => {
              const jobTitle = app.job_title || app.job?.title || "Requisition";
              const orgName = app.organization_name || app.job?.organization_name || "Enterprise Employer";
              const department = app.job_department || app.job?.department;
              const location = app.job_location || app.job?.location;
              const isWithdrawn = app.candidate_status === "withdrawn";
              const isRejected = app.candidate_status === "rejected" || app.candidate_status === "not_selected";
              const isOffer = app.candidate_status === "offer" || app.candidate_status === "offer_stage";
              const canWithdraw = !isWithdrawn && !isRejected && !isOffer;

              return (
                <div
                  key={app.id}
                  className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors"
                >
                  <div className="space-y-1.5 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <Link
                        href={`/candidate/applications/${app.id}`}
                        className="text-base font-bold text-slate-900 dark:text-white hover:text-primary-600 transition-colors"
                      >
                        {jobTitle}
                      </Link>

                      {app.resume_version_applied && (
                        <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded border border-slate-200 dark:border-slate-700">
                          Resume v{app.resume_version_applied}
                        </span>
                      )}

                      {app.resume_snapshot_sha256 && (
                        <span className="px-2 py-0.5 text-[10px] font-mono bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 rounded border border-emerald-200 dark:border-emerald-800 flex items-center gap-1">
                          <ShieldCheck className="w-3 h-3" />
                          SHA-256 Sealed
                        </span>
                      )}
                    </div>

                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
                      <span className="flex items-center gap-1 font-semibold text-slate-700 dark:text-slate-300">
                        <Building2 className="w-3.5 h-3.5 text-primary-500" />
                        {orgName}
                      </span>
                      {department && <span>&bull; {department}</span>}
                      {location && <span>&bull; {location}</span>}
                      <span className="flex items-center gap-1">
                        <Calendar className="w-3.5 h-3.5" />
                        Applied {new Date(app.applied_at).toLocaleDateString()}
                      </span>
                    </div>

                    {isWithdrawn && app.withdrawal_reason && (
                      <p className="text-xs text-slate-400 italic">
                        Withdrawn: &ldquo;{app.withdrawal_reason}&rdquo;
                      </p>
                    )}
                  </div>

                  <div className="flex items-center gap-2.5 sm:self-center">
                    <ApplicationStatusBadge status={app.candidate_status} />

                    <Link
                      href={`/candidate/applications/${app.id}`}
                      className="px-3 py-1.5 text-xs font-semibold text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-950/40 border border-transparent hover:border-primary-200 dark:hover:border-primary-800 rounded-lg transition-colors inline-flex items-center gap-1"
                    >
                      <span>Details</span>
                      <ChevronRight className="w-3.5 h-3.5" />
                    </Link>

                    {canWithdraw && (
                      <button
                        type="button"
                        onClick={() => {
                          setWithdrawTargetId(app.id);
                          setWithdrawReason("");
                          setWithdrawError(null);
                        }}
                        className="px-2.5 py-1.5 text-xs font-medium text-slate-400 hover:text-red-600 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                        title="Withdraw application"
                      >
                        Withdraw
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {/* Withdrawal Confirmation Modal */}
      {withdrawTargetId && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-start justify-between">
              <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Ban className="w-5 h-5 text-red-600" />
                <span>Confirm Application Withdrawal</span>
              </h3>
              <button
                type="button"
                onClick={() => setWithdrawTargetId(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              Are you sure you wish to withdraw your application? This action will notify the hiring team and conclude review for this position. Your historical evidence record will be preserved for compliance.
            </p>

            {withdrawError && (
              <div
                role="alert"
                className="p-3 text-xs text-red-700 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl"
              >
                {withdrawError}
              </div>
            )}

            <form onSubmit={handleWithdrawSubmit} className="space-y-3 pt-1">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Reason for Withdrawal *
                </label>
                <textarea
                  rows={3}
                  required
                  value={withdrawReason}
                  onChange={(e) => setWithdrawReason(e.target.value)}
                  placeholder="e.g. Accepted another offer, personal reasons, compensation or timing misalignment..."
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setWithdrawTargetId(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                >
                  Keep Application
                </button>
                <button
                  type="submit"
                  disabled={withdrawing || withdrawReason.trim().length < 3}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors flex items-center gap-1.5"
                >
                  {withdrawing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  <span>Confirm Withdrawal</span>
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
