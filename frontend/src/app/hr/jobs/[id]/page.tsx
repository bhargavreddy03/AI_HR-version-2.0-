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
  MapPin,
  DollarSign,
  AlertCircle,
  RotateCw,
  UserCheck,
  Globe,
  Lock,
  Layers,
  X,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type { JobRequisition } from "@/types/hr";

export default function JobDetailPage() {
  const params = useParams();
  const router = useRouter();
  const jobId = String(params.id);

  const [job, setJob] = useState<JobRequisition | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Preview Modal & Delete Dialog
  const [showPreviewModal, setShowPreviewModal] = useState(false);
  const [showDeleteModal, setShowDeleteModal] = useState(false);
  const [deleteLoading, setDeleteLoading] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const loadJob = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await hrApi.getJob(jobId);
      setJob(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load requisition details";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    loadJob();
  }, [loadJob]);

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
      case "draft":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
            Draft
          </span>
        );
      case "paused":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-yellow-50 text-yellow-700 border border-yellow-200">
            Paused
          </span>
        );
      case "closed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
            Closed
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
            <div className="flex items-center gap-2.5">
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

        <div className="flex items-center gap-2">
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
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
            data-testid="edit-requisition-button"
          >
            <Edit2 className="w-3.5 h-3.5" />
            Edit Requisition
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
                <span className="font-medium text-slate-700 dark:text-slate-300">
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
