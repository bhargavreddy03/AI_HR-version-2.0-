"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useParams, useSearchParams } from "next/navigation";
import {
  ArrowLeft,
  Mail,
  Phone,
  MapPin,
  Briefcase,
  GraduationCap,
  Award,
  Code,
  Globe,
  FileText,
  Download,
  Calendar,
  Clock,
  Building,
  Shield,
  History,
  Lock,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Eye,
  User,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type { CandidateDetailResponse, ResumeSignedUrlResponse } from "@/types/hr";

export default function CandidateDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const candidateId = params.id as string;
  const applicationId = searchParams.get("applicationId") || undefined;

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<CandidateDetailResponse | null>(null);

  // Resume downloading
  const [downloadingResume, setDownloadingResume] = useState(false);
  const [resumeUrl, setResumeUrl] = useState<string | null>(null);

  const loadCandidateData = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await hrApi.getCandidateDetails(candidateId, applicationId);
      setCandidate(data);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to load candidate details";
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [candidateId, applicationId]);

  useEffect(() => {
    loadCandidateData();
  }, [loadCandidateData]);

  const handleDownloadResume = async () => {
    if (!candidate?.current_application?.application_id) return;
    try {
      setDownloadingResume(true);
      const res: ResumeSignedUrlResponse = await hrApi.getApplicationResumeUrl(
        candidate.current_application.application_id
      );
      if (res.download_url) {
        setResumeUrl(res.download_url);
        window.open(res.download_url, "_blank", "noopener,noreferrer");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate resume download link";
      alert(`Resume download error: ${msg}`);
    } finally {
      setDownloadingResume(false);
    }
  };

  if (loading) {
    return (
      <div className="p-16 text-center text-xs text-slate-400 space-y-3" data-testid="candidate-loading">
        <RefreshCw className="w-8 h-8 animate-spin mx-auto text-blue-500" />
        <p className="font-semibold text-slate-600 dark:text-slate-300">
          Loading authorized candidate profile...
        </p>
      </div>
    );
  }

  if (error || !candidate) {
    return (
      <div className="p-8 max-w-xl mx-auto space-y-4 text-center">
        <div className="w-12 h-12 rounded-full bg-rose-50 text-rose-600 flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
          Candidate Access Error
        </h2>
        <p className="text-xs text-slate-500">{error || "Candidate profile not found."}</p>
        <div className="pt-2">
          <Link
            href="/hr/applicants"
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Applicant Pool
          </Link>
        </div>
      </div>
    );
  }

  const appCtx = candidate.current_application;

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-6" data-testid="candidate-detail-page">
      {/* Top Navigation */}
      <div className="flex items-center justify-between gap-4 pb-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <Link
            href="/hr/applicants"
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
              {candidate.full_name}
            </h1>
            <p className="text-xs text-slate-500">
              {candidate.headline || "Candidate Profile"}
            </p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {Boolean(appCtx?.resume_id || appCtx?.resume_snapshot_sha256) && (
            <button
              type="button"
              disabled={downloadingResume}
              onClick={handleDownloadResume}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
              data-testid="btn-candidate-download-resume"
            >
              {downloadingResume ? (
                <RefreshCw className="w-3.5 h-3.5 animate-spin" />
              ) : (
                <Download className="w-3.5 h-3.5" />
              )}
              Download Submitted Resume
            </button>
          )}
        </div>
      </div>

      {/* Candidate Profile Summary Header Card */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-14 h-14 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-300 font-bold flex items-center justify-center text-lg flex-shrink-0">
              {candidate.first_name[0]}
              {candidate.last_name[0]}
            </div>
            <div className="space-y-1">
              <h2 className="text-lg font-bold text-slate-900 dark:text-slate-100">
                {candidate.full_name}
              </h2>
              {candidate.preferred_title && (
                <p className="text-xs font-semibold text-blue-600">
                  {candidate.preferred_title}
                </p>
              )}
              {candidate.bio && (
                <p className="text-xs text-slate-600 dark:text-slate-400 max-w-2xl leading-relaxed">
                  {candidate.bio}
                </p>
              )}

              {/* Contact & Location Chips */}
              <div className="flex items-center flex-wrap gap-3 pt-2 text-xs text-slate-500">
                <span className="flex items-center gap-1">
                  <Mail className="w-3.5 h-3.5 text-slate-400" />
                  {candidate.email}
                </span>
                {candidate.phone_number && (
                  <>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Phone className="w-3.5 h-3.5 text-slate-400" />
                      {candidate.phone_number}
                    </span>
                  </>
                )}
                {(candidate.location_city || candidate.location_country) && (
                  <>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <MapPin className="w-3.5 h-3.5 text-slate-400" />
                      {[candidate.location_city, candidate.location_country]
                        .filter(Boolean)
                        .join(", ")}
                    </span>
                  </>
                )}
                {candidate.work_authorization && (
                  <>
                    <span>•</span>
                    <span className="flex items-center gap-1">
                      <Shield className="w-3.5 h-3.5 text-emerald-600" />
                      {candidate.work_authorization}
                    </span>
                  </>
                )}
              </div>
            </div>
          </div>

          {/* Quick Metrics */}
          <div className="flex sm:flex-col items-center sm:items-end justify-between gap-2 border-t sm:border-t-0 pt-3 sm:pt-0 border-slate-100 dark:border-slate-800">
            <div className="text-right">
              <div className="text-2xl font-mono font-bold text-slate-900 dark:text-slate-100">
                {candidate.experience_years}
              </div>
              <div className="text-[11px] text-slate-400 uppercase font-semibold">
                Years Experience
              </div>
            </div>
            <div className="text-right">
              <div className="text-sm font-semibold text-blue-600">
                {candidate.skills.length} Competencies
              </div>
            </div>
          </div>
        </div>

        {/* Portfolio URLs */}
        {candidate.portfolio_urls && candidate.portfolio_urls.length > 0 && (
          <div className="pt-2 border-t border-slate-100 dark:border-slate-800 flex items-center gap-2 flex-wrap text-xs">
            <span className="text-slate-400 font-semibold text-[11px] uppercase">Portfolio:</span>
            {candidate.portfolio_urls.map((url, i) => (
              <a
                key={i}
                href={url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-slate-100 dark:bg-slate-800 text-blue-600 hover:underline"
              >
                <Globe className="w-3 h-3" />
                {url.replace(/^https?:\/\//, "")}
              </a>
            ))}
          </div>
        )}
      </div>

      {/* Grid: 2 Columns */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column (2 Cols): Background & Portfolio */}
        <div className="lg:col-span-2 space-y-6">
          {/* Work Experience */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
              <Briefcase className="w-4 h-4 text-blue-600" />
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                Work Experience
              </h3>
            </div>

            {candidate.experiences.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No work experience history recorded.</p>
            ) : (
              <div className="space-y-4">
                {candidate.experiences.map((exp) => (
                  <div
                    key={exp.id}
                    className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 space-y-1.5"
                  >
                    <div className="flex items-start justify-between flex-wrap gap-2">
                      <div>
                        <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-xs">
                          {exp.job_title}
                        </h4>
                        <p className="text-xs text-slate-600 dark:text-slate-400">
                          {exp.company_name} {exp.location && `• ${exp.location}`}
                        </p>
                      </div>
                      <span className="text-[11px] font-mono text-slate-500">
                        {exp.start_date} – {exp.is_current ? "Present" : exp.end_date || "Present"}
                      </span>
                    </div>

                    {exp.description && (
                      <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-line pt-1">
                        {exp.description}
                      </p>
                    )}

                    {exp.skills && exp.skills.length > 0 && (
                      <div className="flex flex-wrap gap-1 pt-1">
                        {exp.skills.map((s) => (
                          <span
                            key={s}
                            className="px-2 py-0.5 rounded text-[10px] bg-white dark:bg-slate-800 text-slate-600 border border-slate-200 dark:border-slate-700"
                          >
                            {s}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Education & Credentials */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
              <GraduationCap className="w-4 h-4 text-indigo-600" />
              <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                Education & Credentials
              </h3>
            </div>

            {candidate.educations.length === 0 ? (
              <p className="text-xs text-slate-400 italic">No formal education entries recorded.</p>
            ) : (
              <div className="space-y-3">
                {candidate.educations.map((edu) => (
                  <div
                    key={edu.id}
                    className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 flex items-start justify-between flex-wrap gap-2 text-xs"
                  >
                    <div>
                      <h4 className="font-semibold text-slate-900 dark:text-slate-100">
                        {edu.degree} in {edu.field_of_study}
                      </h4>
                      <p className="text-slate-500">{edu.institution}</p>
                    </div>
                    {(edu.start_year || edu.end_year) && (
                      <span className="font-mono text-slate-500 text-[11px]">
                        {[edu.start_year, edu.end_year].filter(Boolean).join(" – ")}
                      </span>
                    )}
                  </div>
                ))}
              </div>
            )}

            {/* Certifications */}
            {candidate.certifications && candidate.certifications.length > 0 && (
              <div className="pt-3 border-t border-slate-100 dark:border-slate-800 space-y-2">
                <h4 className="text-xs font-semibold text-slate-500 uppercase tracking-wider">
                  Professional Certifications
                </h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
                  {candidate.certifications.map((cert) => (
                    <div
                      key={cert.id}
                      className="p-3 rounded-xl border border-slate-200 dark:border-slate-700 space-y-1"
                    >
                      <div className="font-semibold text-slate-800 dark:text-slate-200">
                        {cert.name}
                      </div>
                      <div className="text-slate-500 text-[11px]">{cert.issuing_organization}</div>
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>

          {/* Key Projects */}
          {candidate.projects && candidate.projects.length > 0 && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
                <Code className="w-4 h-4 text-emerald-600" />
                <h3 className="text-sm font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                  Key Projects & Portfolio
                </h3>
              </div>

              <div className="space-y-3">
                {candidate.projects.map((proj) => (
                  <div
                    key={proj.id}
                    className="p-3.5 rounded-xl bg-slate-50 dark:bg-slate-800/40 border border-slate-100 dark:border-slate-800 space-y-1 text-xs"
                  >
                    <div className="flex items-center justify-between">
                      <h4 className="font-semibold text-slate-900 dark:text-slate-100">
                        {proj.title}
                      </h4>
                      {proj.project_url && (
                        <a
                          href={proj.project_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-blue-600 hover:underline inline-flex items-center gap-0.5 text-[11px]"
                        >
                          View Project <ExternalLink className="w-3 h-3" />
                        </a>
                      )}
                    </div>
                    {proj.role && <p className="text-slate-500 text-[11px]">{proj.role}</p>}
                    {proj.description && (
                      <p className="text-slate-700 dark:text-slate-300 pt-1 leading-relaxed">
                        {proj.description}
                      </p>
                    )}
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right Column (1 Col): Application Context & Timelines */}
        <div className="space-y-6">
          {/* Current Application Summary */}
          {appCtx && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
                <Briefcase className="w-4 h-4 text-blue-600" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                  Current Application Context
                </h3>
              </div>

              <div className="space-y-2 text-xs">
                <div>
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                    Position Applied
                  </span>
                  <Link
                    href={`/hr/jobs/${appCtx.job_id}`}
                    className="font-semibold text-slate-900 dark:text-slate-100 hover:text-blue-600 hover:underline"
                  >
                    {appCtx.job_title}
                  </Link>
                </div>

                <div className="flex justify-between">
                  <span className="text-slate-500">Department:</span>
                  <span className="font-medium text-slate-800 dark:text-slate-200">
                    {appCtx.job_department}
                  </span>
                </div>

                <div className="flex justify-between">
                  <span className="text-slate-500">Status:</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 capitalize">
                    {appCtx.status.replace(/_/g, " ")}
                  </span>
                </div>

                <div className="flex justify-between">
                  <span className="text-slate-500">Applied At:</span>
                  <span className="font-medium text-slate-800 dark:text-slate-200">
                    {new Date(appCtx.applied_at).toLocaleDateString()}
                  </span>
                </div>

                {appCtx.recruiter_name && (
                  <div className="flex justify-between">
                    <span className="text-slate-500">Assigned Recruiter:</span>
                    <span className="font-medium text-slate-800 dark:text-slate-200">
                      {appCtx.recruiter_name}
                    </span>
                  </div>
                )}
              </div>

              {/* Cover Letter */}
              {appCtx.cover_letter && (
                <div className="pt-2 border-t border-slate-100 dark:border-slate-800 space-y-1">
                  <span className="text-slate-400 block text-[10px] uppercase font-semibold">
                    Cover Letter
                  </span>
                  <p className="text-xs text-slate-700 dark:text-slate-300 italic whitespace-pre-line bg-slate-50 dark:bg-slate-800/40 p-3 rounded-lg border border-slate-100 dark:border-slate-800">
                    &ldquo;{appCtx.cover_letter}&rdquo;
                  </p>
                </div>
              )}
            </div>
          )}

          {/* Candidate Skills Widget */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 pb-2 border-b border-slate-100 dark:border-slate-800">
              Verified & Extracted Skills
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {candidate.skills.map((skill) => (
                <span
                  key={skill}
                  className="px-2.5 py-1 rounded-lg text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-100 dark:border-blue-900/40"
                >
                  {skill}
                </span>
              ))}
            </div>
          </div>

          {/* Separated Activity Timelines */}
          {appCtx && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-4">
              {/* Internal HR Notes & Activity */}
              <div>
                <div className="flex items-center gap-1.5 text-xs font-bold text-amber-700 dark:text-amber-400 pb-2 border-b border-slate-100 dark:border-slate-800">
                  <Lock className="w-3.5 h-3.5" />
                  <span>Internal HR Activity & Notes</span>
                </div>

                {appCtx.internal_timeline.length === 0 ? (
                  <p className="text-xs text-slate-400 italic pt-2">No internal notes recorded.</p>
                ) : (
                  <div className="relative pl-4 space-y-3 pt-3 before:absolute before:left-1 before:top-4 before:bottom-2 before:w-0.5 before:bg-amber-200 dark:before:bg-amber-900/60">
                    {appCtx.internal_timeline.map((event, idx) => (
                      <div key={idx} className="relative space-y-0.5 text-xs">
                        <div className="absolute -left-4 top-1 w-2 h-2 rounded-full bg-amber-500" />
                        <div className="font-semibold text-slate-800 dark:text-slate-200">
                          {event.note || event.status}
                        </div>
                        <div className="text-[10px] text-slate-400">
                          {new Date(event.changed_at).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {/* Candidate-Facing Timeline */}
              <div className="pt-2 border-t border-slate-100 dark:border-slate-800">
                <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700 dark:text-slate-300 pb-2 border-b border-slate-100 dark:border-slate-800">
                  <Eye className="w-3.5 h-3.5 text-blue-500" />
                  <span>Candidate-Facing Journey</span>
                </div>

                {appCtx.candidate_timeline.length === 0 ? (
                  <p className="text-xs text-slate-400 italic pt-2">No candidate events recorded.</p>
                ) : (
                  <div className="relative pl-4 space-y-3 pt-3 before:absolute before:left-1 before:top-4 before:bottom-2 before:w-0.5 before:bg-blue-200 dark:before:bg-blue-900/60">
                    {appCtx.candidate_timeline.map((event, idx) => (
                      <div key={idx} className="relative space-y-0.5 text-xs">
                        <div className="absolute -left-4 top-1 w-2 h-2 rounded-full bg-blue-500" />
                        <div className="font-semibold text-slate-800 dark:text-slate-200 capitalize">
                          {event.status.replace(/_/g, " ")}
                        </div>
                        {event.note && <div className="text-slate-500">{event.note}</div>}
                        <div className="text-[10px] text-slate-400">
                          {new Date(event.changed_at).toLocaleString()}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Organization Application History (Strictly scoped) */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700 dark:text-slate-300">
                <History className="w-3.5 h-3.5 text-purple-600" />
                <span>Organization Application History</span>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                {candidate.organization_application_history.length} record(s)
              </span>
            </div>

            <p className="text-[11px] text-slate-400">
              Candidate application history within this organization.
            </p>

            <div className="space-y-2">
              {candidate.organization_application_history.map((hist) => (
                <div
                  key={hist.application_id}
                  className="p-2.5 rounded-lg border border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-800/40 text-xs space-y-1"
                >
                  <div className="font-semibold text-slate-800 dark:text-slate-200">
                    {hist.job_title}
                  </div>
                  <div className="flex items-center justify-between text-[11px] text-slate-500">
                    <span>{new Date(hist.applied_at).toLocaleDateString()}</span>
                    <span className="capitalize font-mono text-[10px] px-1.5 py-0.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700">
                      {hist.status}
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
