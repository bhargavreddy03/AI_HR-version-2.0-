"use client";

import React, { useState, useEffect } from "react";
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
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import { ApplicationStatusBadge } from "@/components/candidate/ApplicationStatusBadge";
import type {
  CandidateApplicationSummary,
  CandidateApplicationDetail,
} from "@/types/candidate";

export default function CandidateApplicationsPage() {
  const [applications, setApplications] = useState<CandidateApplicationSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Detail Drawer / Modal
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
      const data = await candidateApi.getMyApplications();
      setApplications(data);
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
              note: "Application submitted.",
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
    if (!withdrawReason.trim()) {
      setWithdrawError("Please provide a reason for withdrawal.");
      return;
    }

    setWithdrawing(true);
    setWithdrawError(null);

    try {
      await candidateApi.withdrawApplication(withdrawTargetId, withdrawReason);
      setApplications((prev) =>
        prev.map((app) =>
          app.id === withdrawTargetId
            ? { ...app, candidate_status: "withdrawn" }
            : app
        )
      );
      if (selectedApp && selectedApp.id === withdrawTargetId) {
        setSelectedApp({
          ...selectedApp,
          candidate_status: "withdrawn",
          timeline: [
            ...selectedApp.timeline,
            {
              status: "withdrawn",
              changed_at: new Date().toISOString(),
              note: `Candidate withdrew: ${withdrawReason}`,
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

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          My Applications
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Track the lifecycle status, interview progress, and timeline history of your job applications.
        </p>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-4 text-sm text-amber-800 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>Note: Connect your session to sync live applications ({error})</span>
        </div>
      )}

      {/* Applications Table / Cards */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-sm overflow-hidden">
        <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            Application History ({applications.length})
          </h2>
          <span className="text-xs text-slate-500">
            Immutable Resume Version Sealed
          </span>
        </div>

        {loading ? (
          <div className="py-16 flex flex-col items-center justify-center space-y-2">
            <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
            <p className="text-xs text-slate-500">Loading your applications...</p>
          </div>
        ) : applications.length === 0 ? (
          <div className="p-12 text-center space-y-3">
            <Briefcase className="w-10 h-10 text-slate-400 mx-auto" />
            <p className="text-sm font-semibold text-slate-700 dark:text-slate-300">
              No applications submitted yet
            </p>
            <p className="text-xs text-slate-500">
              Explore open positions and apply with your verified skills.
            </p>
            <div className="pt-2">
              <Link
                href="/candidate/jobs"
                className="inline-flex items-center gap-2 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl transition-colors"
              >
                Browse Open Jobs
              </Link>
            </div>
          </div>
        ) : (
          <div className="divide-y divide-slate-100 dark:divide-slate-800">
            {applications.map((app) => (
              <div
                key={app.id}
                className="p-5 flex flex-col sm:flex-row sm:items-center justify-between gap-4 hover:bg-slate-50/50 dark:hover:bg-slate-800/40 transition-colors"
              >
                <div className="space-y-1.5">
                  <div className="flex items-center gap-2 flex-wrap">
                    <h3 className="text-base font-bold text-slate-900 dark:text-white">
                      {app.job?.title || "Position"}
                    </h3>
                    {app.resume_version_applied && (
                      <span className="px-2 py-0.5 text-[10px] font-bold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 rounded">
                        Resume v{app.resume_version_applied}
                      </span>
                    )}
                  </div>

                  <div className="flex items-center gap-3 text-xs text-slate-500">
                    {app.job?.department && (
                      <span className="flex items-center gap-1">
                        <Building2 className="w-3.5 h-3.5" />
                        {app.job.department}
                      </span>
                    )}
                    <span className="flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5" />
                      Applied on {new Date(app.applied_at).toLocaleDateString()}
                    </span>
                  </div>
                </div>

                <div className="flex items-center gap-3">
                  <ApplicationStatusBadge status={app.candidate_status} />

                  <button
                    type="button"
                    onClick={() => handleOpenDetail(app.id)}
                    className="px-3 py-1.5 text-xs font-semibold text-primary-600 dark:text-primary-400 hover:bg-primary-50 dark:hover:bg-primary-950/40 rounded-lg transition-colors"
                  >
                    View Details
                  </button>

                  {app.candidate_status !== "withdrawn" && app.candidate_status !== "rejected" && (
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
            ))}
          </div>
        )}
      </div>

      {/* Detail Modal */}
      {selectedApp && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-xl w-full p-6 space-y-5 shadow-xl max-h-[90vh] overflow-y-auto">
            <div className="flex items-start justify-between">
              <div>
                <h3 className="text-lg font-bold text-slate-900 dark:text-white">
                  {selectedApp.job?.title}
                </h3>
                <p className="text-xs text-slate-500">
                  {selectedApp.job?.department || "General"} &bull; {selectedApp.job?.location || "Remote"}
                </p>
              </div>
              <button
                onClick={() => setSelectedApp(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800/50 rounded-xl">
              <span className="text-xs font-medium text-slate-600 dark:text-slate-400">Current Status:</span>
              <ApplicationStatusBadge status={selectedApp.candidate_status} />
            </div>

            {selectedApp.cover_letter && (
              <div className="space-y-1.5">
                <p className="text-xs font-bold text-slate-700 dark:text-slate-300">
                  Submitted Cover Letter / Note
                </p>
                <div className="p-3 bg-slate-50 dark:bg-slate-800/40 rounded-xl text-xs text-slate-600 dark:text-slate-300 whitespace-pre-wrap leading-relaxed">
                  {selectedApp.cover_letter}
                </div>
              </div>
            )}

            {/* Application Timeline */}
            <div className="space-y-3">
              <p className="text-xs font-bold text-slate-700 dark:text-slate-300 flex items-center gap-1.5">
                <Clock className="w-4 h-4 text-primary-600" />
                Application History Timeline
              </p>

              <div className="border-l-2 border-slate-200 dark:border-slate-800 ml-2 pl-4 space-y-4">
                {selectedApp.timeline && selectedApp.timeline.length > 0 ? (
                  selectedApp.timeline.map((step, idx) => (
                    <div key={idx} className="relative space-y-0.5">
                      <div className="absolute -left-[21px] top-1 w-2.5 h-2.5 rounded-full bg-primary-600" />
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-bold capitalize text-slate-900 dark:text-white">
                          {step.status.replace("_", " ")}
                        </span>
                        <span className="text-[10px] text-slate-400">
                          {new Date(step.changed_at).toLocaleString()}
                        </span>
                      </div>
                      {step.note && (
                        <p className="text-xs text-slate-500">{step.note}</p>
                      )}
                    </div>
                  ))
                ) : (
                  <p className="text-xs text-slate-400">Applied on {new Date(selectedApp.applied_at).toLocaleDateString()}</p>
                )}
              </div>
            </div>

            <div className="flex justify-between items-center pt-2 border-t border-slate-100 dark:border-slate-800">
              {selectedApp.candidate_status !== "withdrawn" && selectedApp.candidate_status !== "rejected" ? (
                <button
                  type="button"
                  onClick={() => {
                    setWithdrawTargetId(selectedApp.id);
                    setWithdrawReason("");
                    setWithdrawError(null);
                  }}
                  className="text-xs text-red-600 hover:underline flex items-center gap-1"
                >
                  <Ban className="w-3.5 h-3.5" /> Withdraw Application
                </button>
              ) : <div />}

              <button
                type="button"
                onClick={() => setSelectedApp(null)}
                className="px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-xs font-semibold rounded-lg"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Withdrawal Confirmation Modal */}
      {withdrawTargetId && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-start justify-between">
              <h3 className="text-base font-bold text-slate-900 dark:text-white">
                Withdraw Application
              </h3>
              <button
                onClick={() => setWithdrawTargetId(null)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500 dark:text-slate-400">
              Are you sure you want to withdraw? This will notify the hiring team and stop further review for this role.
            </p>

            {withdrawError && (
              <div className="p-3 text-xs text-red-700 bg-red-50 dark:bg-red-950/40 border border-red-200 rounded-lg">
                {withdrawError}
              </div>
            )}

            <form onSubmit={handleWithdrawSubmit} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Reason for Withdrawal *
                </label>
                <textarea
                  rows={3}
                  required
                  value={withdrawReason}
                  onChange={(e) => setWithdrawReason(e.target.value)}
                  placeholder="e.g. Accepted another offer, personal reasons, timing not aligned..."
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setWithdrawTargetId(null)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={withdrawing}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-semibold rounded-lg flex items-center gap-1.5"
                >
                  {withdrawing && <Loader2 className="w-3.5 h-3.5 animate-spin" />}
                  Confirm Withdrawal
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
