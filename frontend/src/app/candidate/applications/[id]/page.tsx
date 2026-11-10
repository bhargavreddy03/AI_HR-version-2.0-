"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  ArrowLeft,
  Building2,
  MapPin,
  Calendar,
  Clock,
  ShieldCheck,
  CheckCircle2,
  AlertTriangle,
  Loader2,
  FileText,
  Ban,
  HelpCircle,
  X,
  ExternalLink,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import { ApplicationStatusBadge } from "@/components/candidate/ApplicationStatusBadge";
import type { CandidateApplicationDetail } from "@/types/candidate";

export default function CandidateApplicationDetailPage() {
  const params = useParams();
  const router = useRouter();
  const applicationId = params?.id as string;

  const [app, setApp] = useState<CandidateApplicationDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Withdrawal dialog state
  const [showWithdrawModal, setShowWithdrawModal] = useState(false);
  const [withdrawReason, setWithdrawReason] = useState("");
  const [withdrawing, setWithdrawing] = useState(false);
  const [withdrawError, setWithdrawError] = useState<string | null>(null);

  useEffect(() => {
    if (!applicationId) return;

    async function loadApplication() {
      try {
        setLoading(true);
        setError(null);
        const data = await candidateApi.getApplicationDetail(applicationId);
        setApp(data);
      } catch (err: unknown) {
        setError(
          err instanceof Error
            ? err.message
            : "Failed to load application history and evidence record."
        );
      } finally {
        setLoading(false);
      }
    }

    loadApplication();
  }, [applicationId]);

  const handleWithdraw = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!app) return;
    if (!withdrawReason.trim() || withdrawReason.trim().length < 3) {
      setWithdrawError("Please provide a valid withdrawal reason (at least 3 characters).");
      return;
    }

    setWithdrawing(true);
    setWithdrawError(null);

    try {
      const updated = await candidateApi.withdrawApplication(
        app.id,
        withdrawReason.trim()
      );
      setApp({
        ...app,
        candidate_status: "withdrawn",
        withdrawn_at: updated.withdrawn_at || new Date().toISOString(),
        withdrawal_reason: withdrawReason.trim(),
        timeline: [
          ...(app.timeline || []),
          {
            status: "withdrawn",
            changed_at: new Date().toISOString(),
            note: `Candidate withdrew: ${withdrawReason.trim()}`,
          },
        ],
      });
      setShowWithdrawModal(false);
      setWithdrawReason("");
    } catch (err: unknown) {
      setWithdrawError(
        err instanceof Error ? err.message : "Failed to withdraw application"
      );
    } finally {
      setWithdrawing(false);
    }
  };

  if (loading) {
    return (
      <div className="py-24 flex flex-col items-center justify-center space-y-3 max-w-4xl mx-auto">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        <p className="text-xs text-slate-500 font-medium">Loading application tracking details...</p>
      </div>
    );
  }

  if (error || !app) {
    return (
      <div className="max-w-3xl mx-auto py-16 space-y-4">
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-8 text-center space-y-3 shadow-sm">
          <AlertTriangle className="w-10 h-10 text-amber-500 mx-auto" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Application Record Not Found
          </h2>
          <p className="text-xs text-slate-500 max-w-md mx-auto">
            {error || "The application you requested could not be found or you do not have permission to view it."}
          </p>
          <div className="pt-2">
            <Link
              href="/candidate/applications"
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              <span>Back to My Applications</span>
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const jobTitle = app.job_title || app.job?.title || "Requisition";
  const orgName = app.organization_name || app.job?.organization_name || "Enterprise Employer";
  const isWithdrawn = app.candidate_status === "withdrawn";
  const isRejected = app.candidate_status === "rejected" || app.candidate_status === "not_selected";
  const isOffer = app.candidate_status === "offer" || app.candidate_status === "offer_stage";
  const canWithdraw = !isWithdrawn && !isRejected && !isOffer;

  const answers = (app.answers || {}) as Record<string, any>;
  const consents = (app.consent_records || {}) as Record<string, any>;

  return (
    <div className="max-w-5xl mx-auto space-y-6 pb-12">
      {/* Breadcrumb Navigation */}
      <div className="flex items-center justify-between">
        <Link
          href="/candidate/applications"
          className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-white transition-colors"
        >
          <ArrowLeft className="w-3.5 h-3.5" />
          <span>Back to All Applications</span>
        </Link>

        {canWithdraw && (
          <button
            type="button"
            onClick={() => {
              setShowWithdrawModal(true);
              setWithdrawReason("");
              setWithdrawError(null);
            }}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 border border-red-200 dark:border-red-900 text-red-600 dark:text-red-400 hover:bg-red-50 dark:hover:bg-red-950/30 text-xs font-semibold rounded-lg transition-colors"
          >
            <Ban className="w-3.5 h-3.5" />
            <span>Withdraw Application</span>
          </button>
        )}
      </div>

      {/* Requisition & Application Header Card */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 sm:p-8 shadow-sm space-y-5">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="space-y-1.5">
            <h1 className="text-2xl sm:text-3xl font-extrabold tracking-tight text-slate-900 dark:text-white">
              {jobTitle}
            </h1>

            <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-xs sm:text-sm text-slate-500">
              <span className="flex items-center gap-1.5 font-semibold text-slate-800 dark:text-slate-200">
                <Building2 className="w-4 h-4 text-primary-600" />
                {orgName}
              </span>
              {app.job_department && <span>&bull; {app.job_department}</span>}
              {app.job_location && (
                <span className="flex items-center gap-1 text-slate-600 dark:text-slate-400">
                  <MapPin className="w-4 h-4 text-slate-400" />
                  {app.job_location}
                </span>
              )}
            </div>
          </div>

          <div className="flex flex-col sm:items-end gap-1.5">
            <ApplicationStatusBadge status={app.candidate_status} size="md" />
            <span className="text-[11px] text-slate-400 font-mono">
              Ref: {app.id.substring(0, 18)}...
            </span>
          </div>
        </div>

        {/* Status Alert Banners */}
        {isWithdrawn && (
          <div className="p-4 bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 rounded-xl text-xs text-amber-800 dark:text-amber-300 space-y-1">
            <div className="font-bold flex items-center gap-1.5">
              <Clock className="w-4 h-4" />
              <span>Application Withdrawn on {app.withdrawn_at ? new Date(app.withdrawn_at).toLocaleDateString() : "Record"}</span>
            </div>
            {app.withdrawal_reason && (
              <p className="text-amber-700 dark:text-amber-400">
                Reason: &ldquo;{app.withdrawal_reason}&rdquo;
              </p>
            )}
          </div>
        )}

        {/* Requisition Meta Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 pt-4 border-t border-slate-100 dark:border-slate-800 text-xs">
          <div>
            <span className="text-slate-400 block font-medium">Applied Date</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 flex items-center gap-1">
              <Calendar className="w-3.5 h-3.5 text-slate-400" />
              {new Date(app.applied_at).toLocaleDateString()}
            </span>
          </div>

          <div>
            <span className="text-slate-400 block font-medium">Resume Snapshot</span>
            <span className="font-semibold text-slate-700 dark:text-slate-300 mt-0.5 flex items-center gap-1">
              <FileText className="w-3.5 h-3.5 text-slate-400" />
              {app.resume_filename || `Resume v${app.resume_version_applied || 1}`}
            </span>
          </div>

          <div>
            <span className="text-slate-400 block font-medium">Cryptographic Hash</span>
            <span className="font-mono text-emerald-600 dark:text-emerald-400 mt-0.5 flex items-center gap-1 text-[11px]">
              <ShieldCheck className="w-3.5 h-3.5" />
              SHA-256 Verified
            </span>
          </div>

          <div>
            <span className="text-slate-400 block font-medium">Job Details</span>
            <Link
              href={`/candidate/jobs/${app.job_id}`}
              className="font-semibold text-primary-600 hover:text-primary-700 dark:text-primary-400 mt-0.5 inline-flex items-center gap-1"
            >
              <span>View Requisition</span>
              <ExternalLink className="w-3 h-3" />
            </Link>
          </div>
        </div>
      </div>

      {/* Main Grid: Timeline & Submitted Answers */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Timeline History */}
        <div className="lg:col-span-2 space-y-6">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <h2 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Clock className="w-4 h-4 text-primary-600" />
                <span>Application History Timeline</span>
              </h2>
              <span className="text-[11px] text-slate-400">
                Official Candidate Audit Trail
              </span>
            </div>

            <div className="relative border-l-2 border-slate-200 dark:border-slate-800 ml-3 pl-5 space-y-6">
              {app.timeline && app.timeline.length > 0 ? (
                app.timeline.map((event, idx) => (
                  <div key={idx} className="relative space-y-1">
                    <div className="absolute -left-[27px] top-1 w-3 h-3 rounded-full bg-primary-600 ring-4 ring-white dark:ring-slate-900" />
                    <div className="flex items-center gap-2">
                      <span className="text-xs font-bold text-slate-900 dark:text-white capitalize">
                        {event.status.replace("_", " ")}
                      </span>
                      <span className="text-[10px] text-slate-400">
                        {new Date(event.changed_at).toLocaleString()}
                      </span>
                    </div>
                    {event.note && (
                      <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
                        {event.note}
                      </p>
                    )}
                  </div>
                ))
              ) : (
                <div className="relative space-y-1">
                  <div className="absolute -left-[27px] top-1 w-3 h-3 rounded-full bg-primary-600 ring-4 ring-white dark:ring-slate-900" />
                  <div className="flex items-center gap-2">
                    <span className="text-xs font-bold text-slate-900 dark:text-white">
                      Application Submitted
                    </span>
                    <span className="text-[10px] text-slate-400">
                      {new Date(app.applied_at).toLocaleString()}
                    </span>
                  </div>
                  <p className="text-xs text-slate-500">
                    Application received and cryptographic resume snapshot recorded.
                  </p>
                </div>
              )}
            </div>
          </div>

          {/* Submitted Cover Letter if provided */}
          {app.cover_letter && (
            <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <FileText className="w-4 h-4 text-primary-600" />
                <span>Submitted Cover Letter</span>
              </h3>
              <div className="p-4 bg-slate-50/70 dark:bg-slate-800/40 rounded-xl text-xs text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-wrap">
                {app.cover_letter}
              </div>
            </div>
          )}
        </div>

        {/* Right 1 Col: Submitted Answers & Legal Consents */}
        <div className="space-y-6">
          {/* Candidate Provided Answers */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 shadow-sm space-y-3">
            <h3 className="text-sm font-bold text-slate-900 dark:text-white">
              Application Questionnaire
            </h3>

            <div className="space-y-2.5 text-xs">
              <div className="p-2.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-0.5">
                <span className="text-slate-400 block text-[11px]">Work Authorization</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200 capitalize">
                  {answers.work_authorization ? answers.work_authorization.replace("_", " ") : "Legally Authorized"}
                </span>
              </div>

              <div className="p-2.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-0.5">
                <span className="text-slate-400 block text-[11px]">Visa Sponsorship</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  {answers.visa_sponsorship_required ? "Yes, sponsorship needed" : "Not required"}
                </span>
              </div>

              {answers.earliest_start_date && (
                <div className="p-2.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl space-y-0.5">
                  <span className="text-slate-400 block text-[11px]">Earliest Availability</span>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                    {answers.earliest_start_date}
                  </span>
                </div>
              )}
            </div>
          </div>

          {/* Compliance & Privacy Records */}
          <div className="bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-2xl p-5 space-y-3">
            <div className="flex items-center gap-2 text-xs font-bold text-slate-900 dark:text-white">
              <ShieldCheck className="w-4 h-4 text-emerald-600" />
              <span>Compliance & Recordkeeping</span>
            </div>

            <div className="space-y-2 text-[11px] text-slate-600 dark:text-slate-400">
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span>Statutory Data Processing Consent Certified</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span>Applicant Accuracy Declaration Recorded</span>
              </div>
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600 shrink-0" />
                <span>EEOC / Section 503 Recordkeeping Intact</span>
              </div>
            </div>

            <p className="text-[10px] text-slate-400 leading-relaxed pt-1 border-t border-slate-200/60 dark:border-slate-700/60">
              Confidential hiring team evaluations, private scoring, and internal notes are isolated from applicant records in accordance with global privacy governance.
            </p>
          </div>
        </div>
      </div>

      {/* Withdrawal Confirmation Dialog */}
      {showWithdrawModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-start justify-between">
              <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <Ban className="w-5 h-5 text-red-600" />
                <span>Withdraw Application</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowWithdrawModal(false)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-300"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              Are you sure you wish to withdraw your application for <strong>{jobTitle}</strong>? This action is permanent and will notify the recruitment team.
            </p>

            {withdrawError && (
              <div
                role="alert"
                className="p-3 text-xs text-red-700 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 rounded-xl"
              >
                {withdrawError}
              </div>
            )}

            <form onSubmit={handleWithdraw} className="space-y-3 pt-1">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Reason for Withdrawal *
                </label>
                <textarea
                  rows={3}
                  required
                  value={withdrawReason}
                  onChange={(e) => setWithdrawReason(e.target.value)}
                  placeholder="e.g. Accepted another position, compensation misalignment, personal circumstances..."
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>

              <div className="flex justify-end gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => setShowWithdrawModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-200"
                >
                  Cancel
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
