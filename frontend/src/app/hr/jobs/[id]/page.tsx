"use client";

import React, { useState, useEffect, useCallback } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import {
  Briefcase,
  ArrowLeft,
  Edit2,
  Trash2,
  Users,
  Eye,
  CheckCircle2,
  Clock,
  Calendar,
  Building,
  DollarSign,
  AlertCircle,
  RotateCw,
  UserCheck,
  Globe,
  Lock,
  X,
  Send,
  Check,
  RotateCcw,
  Pause,
  Play,
  Archive,
  ShieldAlert,
  History,
  FileText,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type {
  JobRequisition,
  JobLifecycleHistoryItem,
  JobLifecyclePermittedActionsResponse,
} from "@/types/hr";

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = String(params.id);

  const [job, setJob] = useState<JobRequisition | null>(null);
  const [history, setHistory] = useState<JobLifecycleHistoryItem[]>([]);
  const [permittedActions, setPermittedActions] =
    useState<JobLifecyclePermittedActionsResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Lifecycle Action State
  const [actionLoading, setActionLoading] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);

  // Modals
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const [showRequestChangesModal, setShowRequestChangesModal] = useState(false);
  const [changesReason, setChangesReason] = useState("");

  const [showPublishModal, setShowPublishModal] = useState(false);

  const [showCloseModal, setShowCloseModal] = useState(false);
  const [closeReason, setCloseReason] = useState("");

  const loadJobData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const [jobData, historyData, permData] = await Promise.all([
        hrApi.getJob(jobId),
        hrApi.getJobLifecycleHistory(jobId).catch(() => []),
        hrApi.getPermittedLifecycleActions(jobId).catch(() => null),
      ]);
      setJob(jobData);
      setHistory(historyData);
      setPermittedActions(permData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load requisition details";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    loadJobData();
  }, [loadJobData]);

  const handleLifecycleAction = async (action: string, reason?: string | null) => {
    try {
      setActionLoading(true);
      setActionError(null);
      const res = await hrApi.executeLifecycleAction(jobId, { action, reason });
      setJob(res.job);
      setShowRequestChangesModal(false);
      setShowPublishModal(false);
      setShowCloseModal(false);
      setChangesReason("");
      setCloseReason("");

      // Refresh history & permissions
      const [histData, permData] = await Promise.all([
        hrApi.getJobLifecycleHistory(jobId).catch(() => []),
        hrApi.getPermittedLifecycleActions(jobId).catch(() => null),
      ]);
      setHistory(histData);
      setPermittedActions(permData);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to execute lifecycle action";
      setActionError(msg);
    } finally {
      setActionLoading(false);
    }
  };

  const handleDelete = async () => {
    try {
      setDeleteLoading(true);
      setDeleteError(null);
      await hrApi.deleteJob(jobId);
      router.push("/hr/jobs");
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to delete requisition";
      setDeleteError(msg);
    } finally {
      setDeleteLoading(false);
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "published":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-600" />
            Published
          </span>
        );
      case "pending_approval":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
            <Clock className="w-3.5 h-3.5 text-amber-600" />
            Pending Approval
          </span>
        );
      case "approved":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
            <Check className="w-3.5 h-3.5 text-indigo-600" />
            Approved
          </span>
        );
      case "draft":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Draft
          </span>
        );
      case "paused":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-yellow-50 text-yellow-700 border border-yellow-200">
            <Pause className="w-3.5 h-3.5 text-yellow-600" />
            Paused
          </span>
        );
      case "closed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            Closed
          </span>
        );
      case "archived":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-500 border border-slate-200">
            Archived
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-600 border border-slate-200">
            {status}
          </span>
        );
    }
  };

  const getVisibilityBadge = (vis: string) => {
    switch (vis) {
      case "public":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200">
            <Globe className="w-3 h-3 text-blue-600" />
            Public
          </span>
        );
      case "internal":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-medium bg-purple-50 text-purple-700 border border-purple-200">
            <Lock className="w-3 h-3 text-purple-600" />
            Internal Only
          </span>
        );
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-md text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
            {vis}
          </span>
        );
    }
  };

  if (loading) {
    return (
      <div className="p-12 text-center max-w-5xl mx-auto">
        <RotateCw className="w-8 h-8 text-blue-600 animate-spin mx-auto mb-3" />
        <p className="text-sm font-medium text-slate-600 dark:text-slate-400">
          Loading requisition details...
        </p>
      </div>
    );
  }

  if (error || !job) {
    return (
      <div className="p-8 max-w-3xl mx-auto">
        <div className="p-6 rounded-2xl border border-rose-200 bg-rose-50 text-rose-800 space-y-4">
          <div className="flex items-center gap-3">
            <AlertCircle className="w-6 h-6 text-rose-600 flex-shrink-0" />
            <h2 className="text-lg font-bold">Failed to load requisition</h2>
          </div>
          <p className="text-sm text-rose-700">{error || "Requisition not found."}</p>
          <div className="pt-2">
            <Link
              href="/hr/jobs"
              className="inline-flex items-center gap-2 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5" />
              Back to Job Requisitions
            </Link>
          </div>
        </div>
      </div>
    );
  }

  const actionsList = permittedActions?.permitted_actions || [];

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-6" data-testid="job-detail-page">
      {/* Top Breadcrumb & Actions Bar */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <Link
            href="/hr/jobs"
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
                {job.title}
              </h1>
              {getStatusBadge(job.status)}
              {getVisibilityBadge(job.visibility)}
            </div>
            <div className="flex items-center gap-3 text-xs text-slate-500 mt-1">
              <span className="font-mono">ID: {job.id.slice(0, 8)}</span>
              <span>•</span>
              <span>{job.department}</span>
              <span>•</span>
              <span>{job.location}</span>
              <span>•</span>
              <span className="capitalize">{job.remote_type}</span>
            </div>
          </div>
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          <button
            type="button"
            onClick={() => setShowPreviewModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
            data-testid="preview-candidate-view-button"
          >
            <Eye className="w-3.5 h-3.5" />
            Candidate Preview
          </button>
          <Link
            href={`/hr/jobs/${job.id}/edit`}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
            data-testid="edit-requisition-button"
          >
            <Edit2 className="w-3.5 h-3.5" />
            Edit
          </Link>
          {job.status === "draft" && job.applications_count === 0 && (
            <button
              type="button"
              onClick={() => setShowDeleteModal(true)}
              className="p-2 text-slate-400 hover:text-rose-600 rounded-lg border border-slate-200 dark:border-slate-700 hover:bg-slate-50 transition-colors"
              title="Delete Draft"
              data-testid="delete-draft-button"
            >
              <Trash2 className="w-4 h-4" />
            </button>
          )}
        </div>
      </div>

      {/* Lifecycle Workflow Stepper & Actions Box */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-3 border-b border-slate-100 dark:border-slate-800">
          <div>
            <h2 className="text-sm font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
              Publication & Approval Lifecycle
            </h2>
            <p className="text-xs text-slate-400 mt-0.5">
              Governed state transitions, separation of duties, and career site publishing controls.
            </p>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2 flex-wrap">
            {actionsList.includes("submit_for_approval") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("submit_for_approval")}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
                data-testid="btn-submit-for-approval"
              >
                {actionLoading ? <RotateCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
                Submit for Approval
              </button>
            )}

            {actionsList.includes("approve") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("approve")}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm transition-colors"
                data-testid="btn-approve-requisition"
              >
                {actionLoading ? <RotateCw className="w-3.5 h-3.5 animate-spin" /> : <Check className="w-3.5 h-3.5" />}
                Approve Requisition
              </button>
            )}

            {actionsList.includes("request_changes") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowRequestChangesModal(true)}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 hover:bg-amber-100 rounded-lg transition-colors"
                data-testid="btn-request-changes"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Request Changes
              </button>
            )}

            {actionsList.includes("publish") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowPublishModal(true)}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
                data-testid="btn-publish-job"
              >
                {actionLoading ? <RotateCw className="w-3.5 h-3.5 animate-spin" /> : <Globe className="w-3.5 h-3.5" />}
                Publish to Careers Site
              </button>
            )}

            {actionsList.includes("return_to_draft") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("return_to_draft")}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-slate-700 bg-slate-100 border border-slate-200 hover:bg-slate-200 rounded-lg transition-colors"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                Return to Draft
              </button>
            )}

            {actionsList.includes("pause") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("pause")}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-yellow-800 bg-yellow-50 border border-yellow-200 hover:bg-yellow-100 rounded-lg transition-colors"
                data-testid="btn-pause-job"
              >
                <Pause className="w-3.5 h-3.5" />
                Pause Requisition
              </button>
            )}

            {actionsList.includes("reopen") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("reopen")}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-white bg-emerald-600 hover:bg-emerald-700 rounded-lg shadow-sm transition-colors"
                data-testid="btn-reopen-job"
              >
                <Play className="w-3.5 h-3.5" />
                Reopen Job
              </button>
            )}

            {actionsList.includes("close") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowCloseModal(true)}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-rose-700 bg-rose-50 border border-rose-200 hover:bg-rose-100 rounded-lg transition-colors"
                data-testid="btn-close-job"
              >
                <Lock className="w-3.5 h-3.5" />
                Close Job
              </button>
            )}

            {actionsList.includes("archive") && (
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("archive")}
                className="inline-flex items-center gap-1.5 px-3.5 py-1.5 text-xs font-semibold text-slate-600 bg-slate-100 border border-slate-200 hover:bg-slate-200 rounded-lg transition-colors"
                data-testid="btn-archive-job"
              >
                <Archive className="w-3.5 h-3.5" />
                Archive Requisition
              </button>
            )}
          </div>
        </div>

        {/* Separation of Duties Alert Banner */}
        {permittedActions?.separation_of_duties_active && (
          <div className="p-3.5 rounded-xl border border-amber-200 bg-amber-50 text-amber-800 text-xs flex items-center gap-2.5">
            <ShieldAlert className="w-5 h-5 text-amber-600 flex-shrink-0" />
            <div>
              <span className="font-semibold">Separation of Duties Policy Active:</span> You are assigned as the lead recruiter for this job requisition. In compliance with governance policies, a recruiter cannot approve their own requisition. A designated hiring manager or organization administrator must review and approve it.
            </div>
          </div>
        )}

        {/* Changes Requested Banner */}
        {job.approval_status === "changes_requested" && job.change_request_reason && (
          <div className="p-3.5 rounded-xl border border-rose-200 bg-rose-50 text-rose-800 text-xs flex items-start gap-2.5">
            <AlertCircle className="w-5 h-5 text-rose-600 flex-shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold">Reviewer Requested Changes:</span>
              <p className="mt-0.5 text-rose-700 italic">
                &ldquo;{job.change_request_reason}&rdquo;
              </p>
              <p className="mt-1 text-[11px] text-rose-600">
                Please edit the requisition to address this feedback, then re-submit for approval.
              </p>
            </div>
          </div>
        )}

        {/* Global Action Error Banner */}
        {actionError && (
          <div className="p-3.5 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-xs flex items-center gap-2">
            <AlertCircle className="w-4 h-4 flex-shrink-0" />
            <span>{actionError}</span>
          </div>
        )}

        {/* Visual Workflow Pipeline Stepper */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 pt-1 text-center">
          <div
            className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 ${
              job.status === "draft"
                ? "bg-blue-50 text-blue-700 border-blue-200 ring-2 ring-blue-500/20"
                : "bg-slate-50 text-slate-500 border-slate-200"
            }`}
          >
            <span>1. Draft Requisition</span>
          </div>

          <div
            className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 ${
              job.status === "pending_approval"
                ? "bg-amber-50 text-amber-700 border-amber-200 ring-2 ring-amber-500/20"
                : "bg-slate-50 text-slate-500 border-slate-200"
            }`}
          >
            <span>2. Under Review</span>
          </div>

          <div
            className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 ${
              job.status === "approved"
                ? "bg-indigo-50 text-indigo-700 border-indigo-200 ring-2 ring-indigo-500/20"
                : "bg-slate-50 text-slate-500 border-slate-200"
            }`}
          >
            <span>3. Approved</span>
          </div>

          <div
            className={`p-3 rounded-xl border text-xs font-semibold flex items-center justify-center gap-2 ${
              job.status === "published"
                ? "bg-emerald-50 text-emerald-700 border-emerald-200 ring-2 ring-emerald-500/20"
                : job.status === "paused"
                ? "bg-yellow-50 text-yellow-700 border-yellow-200"
                : job.status === "closed"
                ? "bg-rose-50 text-rose-700 border-rose-200"
                : job.status === "archived"
                ? "bg-slate-100 text-slate-500 border-slate-200"
                : "bg-slate-50 text-slate-500 border-slate-200"
            }`}
          >
            <span>
              4. {job.status === "published" ? "Published & Live" : job.status === "paused" ? "Paused" : job.status === "closed" ? "Closed" : job.status === "archived" ? "Archived" : "Career Site"}
            </span>
          </div>
        </div>
      </div>

      {/* KPI Stats Overview Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Candidates Applied</span>
            <Users className="w-4 h-4 text-blue-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100">
            {job.applications_count}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Submitted applications</p>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Target Vacancies</span>
            <Building className="w-4 h-4 text-emerald-500" />
          </div>
          <div className="mt-2 text-2xl font-bold text-slate-900 dark:text-slate-100">
            {job.vacancies_count}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Hiring allocation</p>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Target Annual Base</span>
            <DollarSign className="w-4 h-4 text-amber-500" />
          </div>
          <div className="mt-2 text-lg font-bold text-slate-900 dark:text-slate-100 truncate">
            {job.salary_min || job.salary_max ? (
              <>
                {job.salary_min ? `${job.salary_currency} ${job.salary_min.toLocaleString()}` : ""}
                {job.salary_min && job.salary_max ? " - " : ""}
                {job.salary_max ? `${job.salary_currency} ${job.salary_max.toLocaleString()}` : ""}
              </>
            ) : (
              <span className="text-slate-400 font-medium">Unspecified</span>
            )}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Annual salary range</p>
        </div>

        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-500">
            <span>Deadline</span>
            <Calendar className="w-4 h-4 text-purple-500" />
          </div>
          <div className="mt-2 text-sm font-bold text-slate-900 dark:text-slate-100 truncate">
            {job.application_deadline ? (
              new Date(job.application_deadline).toLocaleDateString()
            ) : (
              <span className="text-slate-400 font-medium">Open until filled</span>
            )}
          </div>
          <p className="text-[11px] text-slate-400 mt-1">Application deadline</p>
        </div>
      </div>

      {/* Main Grid: Specification Details + Internal Assignments */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Job Description & Qualifications (2 cols) */}
        <div className="lg:col-span-2 space-y-6">
          {/* Overview */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-3">
            <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
              Role Overview
            </h3>
            <p className="text-sm text-slate-800 dark:text-slate-200 whitespace-pre-line leading-relaxed">
              {job.description}
            </p>
          </div>

          {/* Responsibilities */}
          {job.responsibilities && (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-3">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
                Core Responsibilities
              </h3>
              <p className="text-sm text-slate-800 dark:text-slate-200 whitespace-pre-line leading-relaxed">
                {job.responsibilities}
              </p>
            </div>
          )}

          {/* Skills Specification */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
                Canonical Skill Requirements
              </h3>
              <span className="text-xs text-slate-400 font-mono">Taxonomy Registry v1.0</span>
            </div>

            <div>
              <div className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2">
                Mandatory Competencies:
              </div>
              {job.skills_required && job.skills_required.length > 0 ? (
                <div className="flex flex-wrap gap-1.5">
                  {job.skills_required.map((skill) => (
                    <span
                      key={skill}
                      className="px-2.5 py-1 text-xs font-semibold rounded-md bg-blue-50 text-blue-700 border border-blue-200"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              ) : (
                <p className="text-xs text-slate-400 italic">No specific skills listed.</p>
              )}
            </div>

            {job.preferred_skills && job.preferred_skills.length > 0 && (
              <div>
                <div className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-2">
                  Preferred / Nice-to-Have Competencies:
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {job.preferred_skills.map((skill) => (
                    <span
                      key={skill}
                      className="px-2.5 py-1 text-xs font-semibold rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200"
                    >
                      {skill}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Qualifications & Education */}
          {(job.required_qualifications || job.education_requirements) && (
            <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-500">
                Candidate Qualifications & Education
              </h3>

              {job.required_qualifications && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Required Experience & Qualifications:
                  </h4>
                  <p className="text-sm text-slate-800 dark:text-slate-200 whitespace-pre-line leading-relaxed">
                    {job.required_qualifications}
                  </p>
                </div>
              )}

              {job.education_requirements && (
                <div>
                  <h4 className="text-xs font-semibold text-slate-600 dark:text-slate-400 mb-1">
                    Education & Credentials:
                  </h4>
                  <p className="text-sm text-slate-800 dark:text-slate-200 whitespace-pre-line leading-relaxed">
                    {job.education_requirements}
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Immutable Lifecycle History Audit Trail */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-slate-500" />
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                  Lifecycle Audit History
                </h3>
              </div>
              <span className="text-xs text-slate-400 font-mono">
                {history.length} transition{history.length === 1 ? "" : "s"} recorded
              </span>
            </div>

            {history.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No state transitions recorded yet.</p>
            ) : (
              <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200 dark:before:bg-slate-800">
                {history.map((item) => (
                  <div key={item.id} className="relative space-y-1 text-xs">
                    <div className="absolute -left-6 top-1 w-2.5 h-2.5 rounded-full bg-blue-600 ring-4 ring-white dark:ring-slate-900" />
                    <div className="flex items-center justify-between flex-wrap gap-2">
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-slate-900 dark:text-slate-100 capitalize">
                          {item.action.replace(/_/g, " ")}
                        </span>
                        <span className="text-slate-400">•</span>
                        <span className="px-2 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300 font-mono text-[11px]">
                          {item.previous_status} → {item.new_status}
                        </span>
                      </div>
                      <span className="text-slate-400 text-[11px]">
                        {new Date(item.created_at).toLocaleString()}
                      </span>
                    </div>

                    <div className="text-slate-500">
                      By <span className="font-medium text-slate-800 dark:text-slate-200">{item.actor_name || "System"}</span>{" "}
                      {item.actor_role && (
                        <span className="capitalize text-[10px] px-1.5 py-0.5 rounded bg-slate-100 text-slate-600 font-mono">
                          {item.actor_role}
                        </span>
                      )}
                    </div>

                    {item.reason && (
                      <div className="mt-1.5 p-2.5 rounded-lg bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300">
                        <span className="font-semibold text-slate-500 text-[10px] uppercase block mb-0.5">
                          Note / Feedback
                        </span>
                        {item.reason}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Internal Assignments & Audit Metadata (1 col) */}
        <div className="space-y-6">
          {/* Internal Assignments Card */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 pb-2 border-b border-slate-100 dark:border-slate-800">
              Recruitment Team Assignments
            </h3>

            {/* Lead Recruiter */}
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-blue-50 text-blue-700 border border-blue-200 mt-0.5">
                <UserCheck className="w-4 h-4" />
              </div>
              <div className="text-xs flex-1">
                <div className="text-slate-400 uppercase font-semibold text-[10px]">
                  Lead Recruiter
                </div>
                <div className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                  {job.recruiter_name || "Unassigned"}
                </div>
                {job.recruiter_email && (
                  <div className="text-slate-500 truncate">{job.recruiter_email}</div>
                )}
              </div>
            </div>

            {/* Hiring Manager */}
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-purple-50 text-purple-700 border border-purple-200 mt-0.5">
                <Building className="w-4 h-4" />
              </div>
              <div className="text-xs flex-1">
                <div className="text-slate-400 uppercase font-semibold text-[10px]">
                  Hiring Manager
                </div>
                <div className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
                  {job.hiring_manager_name || "Unassigned"}
                </div>
                {job.hiring_manager_email && (
                  <div className="text-slate-500 truncate">{job.hiring_manager_email}</div>
                )}
              </div>
            </div>
          </div>

          {/* Audit Metadata */}
          <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3 text-xs">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500 pb-2 border-b border-slate-100 dark:border-slate-800">
              Requisition Metadata
            </h3>

            <div className="flex items-center justify-between">
              <span className="text-slate-400">Created:</span>
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {new Date(job.created_at).toLocaleString()}
              </span>
            </div>

            <div className="flex items-center justify-between">
              <span className="text-slate-400">Last Updated:</span>
              <span className="font-medium text-slate-700 dark:text-slate-300">
                {new Date(job.updated_at).toLocaleString()}
              </span>
            </div>

            {job.published_at && (
              <div className="flex items-center justify-between">
                <span className="text-slate-400">Published At:</span>
                <span className="font-medium text-emerald-600 font-semibold">
                  {new Date(job.published_at).toLocaleString()}
                </span>
              </div>
            )}

            <div className="flex items-center justify-between">
              <span className="text-slate-400">Approval State:</span>
              <span className="font-medium capitalize text-slate-700 dark:text-slate-300">
                {job.approval_status}
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Modal 1: Request Changes Feedback Modal */}
      {showRequestChangesModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3 border-slate-100 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100">
                Request Requisition Changes
              </h3>
              <button
                type="button"
                onClick={() => setShowRequestChangesModal(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500">
              Provide actionable feedback for the drafting recruiter. The requisition will be returned to <span className="font-semibold text-slate-700 dark:text-slate-300">Draft</span> state with your notes attached.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Feedback & Required Adjustments <span className="text-rose-500">*</span>
              </label>
              <textarea
                rows={4}
                placeholder="e.g. Please update the required qualifications to include 5+ years with Kubernetes, and adjust the compensation range..."
                value={changesReason}
                onChange={(e) => setChangesReason(e.target.value)}
                className="w-full p-3 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-amber-500/20"
                data-testid="textarea-changes-reason"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowRequestChangesModal(false)}
                className="px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionLoading || !changesReason.trim()}
                onClick={() => handleLifecycleAction("request_changes", changesReason)}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-700 disabled:opacity-50 rounded-lg shadow-sm"
                data-testid="btn-confirm-request-changes"
              >
                {actionLoading && <RotateCw className="w-3.5 h-3.5 animate-spin" />}
                Return to Draft with Feedback
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 2: Publish Job Modal */}
      {showPublishModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3 border-slate-100 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <Globe className="w-5 h-5 text-blue-600" />
                Publish Job to Career Site
              </h3>
              <button
                type="button"
                onClick={() => setShowPublishModal(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Publishing will make <span className="font-semibold text-slate-800 dark:text-slate-200">&ldquo;{job.title}&rdquo;</span> active and visible to candidates on the career portal according to its <span className="font-semibold capitalize text-blue-600">{job.visibility}</span> visibility setting.
            </p>

            <div className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 text-xs space-y-1.5">
              <div className="flex justify-between">
                <span className="text-slate-500">Target Vacancies:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">{job.vacancies_count}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Visibility:</span>
                <span className="font-semibold capitalize text-slate-800 dark:text-slate-200">{job.visibility}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Application Deadline:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200">
                  {job.application_deadline ? new Date(job.application_deadline).toLocaleDateString() : "Open until filled"}
                </span>
              </div>
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowPublishModal(false)}
                className="px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("publish")}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm"
                data-testid="btn-confirm-publish"
              >
                {actionLoading && <RotateCw className="w-3.5 h-3.5 animate-spin" />}
                Confirm & Publish Now
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: Close Job Modal */}
      {showCloseModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 max-w-lg w-full shadow-2xl space-y-4">
            <div className="flex items-center justify-between border-b pb-3 border-slate-100 dark:border-slate-800">
              <h3 className="text-base font-bold text-slate-900 dark:text-slate-100 flex items-center gap-2">
                <Lock className="w-5 h-5 text-rose-600" />
                Close Job Requisition
              </h3>
              <button
                type="button"
                onClick={() => setShowCloseModal(false)}
                className="p-1 text-slate-400 hover:text-slate-600 rounded"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
              Closing this requisition will immediately stop accepting new candidate applications and remove it from public career searches.
            </p>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Closing Reason (Optional)
              </label>
              <input
                type="text"
                placeholder="e.g. Candidate hired, position fulfilled, budget reallocation"
                value={closeReason}
                onChange={(e) => setCloseReason(e.target.value)}
                className="w-full px-3 py-2 text-xs bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-rose-500/20"
                data-testid="input-close-reason"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-2">
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => setShowCloseModal(false)}
                className="px-3.5 py-2 text-xs font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={() => handleLifecycleAction("close", closeReason)}
                className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-rose-600 hover:bg-rose-700 rounded-lg shadow-sm"
                data-testid="btn-confirm-close"
              >
                {actionLoading && <RotateCw className="w-3.5 h-3.5 animate-spin" />}
                Confirm Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Candidate View Preview Modal */}
      {showPreviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 max-w-3xl w-full shadow-2xl overflow-hidden my-8">
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                  Public Candidate View Preview
                </span>
                <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mt-1">
                  {job.title}
                </h3>
                <p className="text-xs text-slate-500">
                  {job.department} • {job.location} • {job.remote_type} • {job.employment_type}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                className="p-2 text-slate-400 hover:text-slate-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto text-sm text-slate-700 dark:text-slate-300">
              <div>
                <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                  Role Overview
                </h4>
                <p className="whitespace-pre-line text-slate-800 dark:text-slate-200">
                  {job.description}
                </p>
              </div>

              {job.responsibilities && (
                <div>
                  <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                    Key Responsibilities
                  </h4>
                  <p className="whitespace-pre-line text-slate-800 dark:text-slate-200">
                    {job.responsibilities}
                  </p>
                </div>
              )}

              {job.skills_required && job.skills_required.length > 0 && (
                <div>
                  <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                    Required Competencies
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {job.skills_required.map((s) => (
                      <span
                        key={s}
                        className="px-2.5 py-1 text-xs rounded-md bg-blue-50 text-blue-700 border border-blue-200 font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {(job.salary_min || job.salary_max) && (
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <span className="text-xs text-slate-500">Estimated Annual Base</span>
                  <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    {job.salary_min ? `${job.salary_currency} ${job.salary_min.toLocaleString()}` : ""}
                    {job.salary_min && job.salary_max ? " - " : ""}
                    {job.salary_max ? `${job.salary_currency} ${job.salary_max.toLocaleString()}` : ""}
                  </span>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex justify-end">
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-100"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Delete Confirmation Dialog */}
      {showDeleteModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 max-w-md w-full shadow-xl">
            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">
              Delete Draft Requisition?
            </h3>
            <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">
              Are you sure you want to permanently delete draft requisition{" "}
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                &ldquo;{job.title}&rdquo;
              </span>
              ?
            </p>

            {deleteError && (
              <div className="mt-3 p-3 rounded-lg bg-rose-50 text-rose-700 text-xs flex items-center gap-2">
                <AlertCircle className="w-4 h-4 flex-shrink-0" />
                <span>{deleteError}</span>
              </div>
            )}

            <div className="mt-6 flex items-center justify-end gap-3">
              <button
                type="button"
                onClick={() => {
                  setShowDeleteModal(false);
                  setDeleteError(null);
                }}
                disabled={deleteLoading}
                className="px-4 py-2 text-sm font-medium text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 rounded-lg transition-colors"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={handleDelete}
                disabled={deleteLoading}
                className="px-4 py-2 text-sm font-semibold text-white bg-rose-600 hover:bg-rose-700 active:bg-rose-800 rounded-lg shadow-sm transition-colors flex items-center gap-2"
                data-testid="confirm-delete-button"
              >
                {deleteLoading && <RotateCw className="w-4 h-4 animate-spin" />}
                Confirm Delete
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
