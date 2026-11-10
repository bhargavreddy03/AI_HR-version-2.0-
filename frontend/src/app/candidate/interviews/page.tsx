"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import {
  Calendar,
  Clock,
  Video,
  Building2,
  UserCheck,
  AlertCircle,
  ExternalLink,
  ChevronRight,
  Briefcase,
  AlertTriangle,
  CheckCircle2,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type { CandidateInterview } from "@/types/candidate";

export default function CandidateInterviewsPage() {
  const [interviews, setInterviews] = useState<CandidateInterview[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadInterviews() {
      try {
        setLoading(true);
        setError(null);
        const res = await candidateApi.getInterviews();
        setInterviews(Array.isArray(res?.interviews) ? res.interviews : []);
      } catch (err: unknown) {
        setError(err instanceof Error ? err.message : "Failed to load interviews");
      } finally {
        setLoading(false);
      }
    }
    loadInterviews();
  }, []);

  const getStatusBadge = (status: string) => {
    switch (status.toLowerCase()) {
      case "scheduled":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-blue-50 dark:bg-blue-950/40 text-blue-700 dark:text-blue-300 border border-blue-200 dark:border-blue-800">
            <Clock className="w-3 h-3" />
            Scheduled
          </span>
        );
      case "rescheduled":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-amber-50 dark:bg-amber-950/40 text-amber-700 dark:text-amber-300 border border-amber-200 dark:border-amber-800">
            <AlertTriangle className="w-3 h-3" />
            Rescheduled
          </span>
        );
      case "cancelled":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-red-50 dark:bg-red-950/40 text-red-700 dark:text-red-300 border border-red-200 dark:border-red-800">
            Cancelled
          </span>
        );
      case "completed":
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border border-emerald-200 dark:border-emerald-800">
            <CheckCircle2 className="w-3 h-3" />
            Completed
          </span>
        );
      default:
        return (
          <span className="px-2.5 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-700">
            {status}
          </span>
        );
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Interview Schedule
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            View scheduled interview rounds, meeting conference instructions, and interviewer details across all applications.
          </p>
        </div>

        <Link
          href="/candidate/applications"
          className="inline-flex items-center gap-2 px-4 py-2 border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 text-xs font-semibold text-slate-700 dark:text-slate-300 rounded-xl shadow-sm transition-colors self-start sm:self-auto"
        >
          <Briefcase className="w-3.5 h-3.5" />
          <span>My Applications</span>
        </Link>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs font-semibold text-red-800 dark:text-red-300 rounded-xl">
          <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          <span>{error}</span>
        </div>
      )}

      {loading ? (
        <div className="py-16 text-center text-xs text-slate-400 animate-pulse">
          Loading interview schedules...
        </div>
      ) : interviews.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-12 text-center shadow-sm space-y-4">
          <div className="w-12 h-12 rounded-2xl bg-indigo-50 dark:bg-indigo-950/40 border border-indigo-100 dark:border-indigo-900/50 flex items-center justify-center mx-auto text-indigo-600">
            <Calendar className="w-6 h-6" />
          </div>
          <div className="space-y-1">
            <h2 className="text-base font-bold text-slate-900 dark:text-white">
              No Scheduled Interviews
            </h2>
            <p className="text-xs text-slate-500 max-w-md mx-auto leading-relaxed">
              When a recruiter advances your application to an interview stage, scheduled sessions, video conference links, and meeting instructions will appear here.
            </p>
          </div>
          <Link
            href="/candidate/jobs"
            className="inline-flex items-center gap-1.5 px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
          >
            <Briefcase className="w-3.5 h-3.5" />
            <span>Explore Opportunities</span>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {interviews.map((item) => (
            <div
              key={item.id}
              className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4 hover:border-slate-300 dark:hover:border-slate-700 transition-colors flex flex-col justify-between"
            >
              <div className="space-y-3">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <h2 className="text-base font-bold text-slate-900 dark:text-white">
                      {item.job_title}
                    </h2>
                    <div className="flex items-center gap-1.5 text-xs text-slate-500 mt-0.5">
                      <Building2 className="w-3.5 h-3.5 text-primary-500" />
                      <span className="font-semibold text-slate-700 dark:text-slate-300">
                        {item.organization_name}
                      </span>
                    </div>
                  </div>
                  {getStatusBadge(item.status)}
                </div>

                {/* Date & Time Grid */}
                <div className="p-3.5 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2 text-xs">
                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 font-medium flex items-center gap-1">
                      <Calendar className="w-3.5 h-3.5 text-slate-400" /> Date & Time
                    </span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {new Date(item.scheduled_at).toLocaleDateString()} at{" "}
                      {new Date(item.scheduled_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                      })}
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 font-medium flex items-center gap-1">
                      <Clock className="w-3.5 h-3.5 text-slate-400" /> Duration & Timezone
                    </span>
                    <span className="font-semibold text-slate-800 dark:text-slate-200">
                      {item.duration_minutes} mins ({item.timezone})
                    </span>
                  </div>

                  <div className="flex items-center justify-between">
                    <span className="text-slate-500 font-medium">Interview Round</span>
                    <span className="font-semibold uppercase tracking-wider text-[11px] text-primary-600 dark:text-primary-400">
                      {item.interview_type}
                    </span>
                  </div>
                </div>

                {/* Interviewer details */}
                {item.interviewer_name && (
                  <div className="flex items-center gap-2 text-xs text-slate-600 dark:text-slate-400">
                    <UserCheck className="w-4 h-4 text-primary-500" />
                    <span>
                      Interviewer: <strong className="text-slate-800 dark:text-slate-200">{item.interviewer_name}</strong>
                      {item.interviewer_role && ` (${item.interviewer_role})`}
                    </span>
                  </div>
                )}

                {/* Reschedule / Cancellation Banner */}
                {item.rescheduled_reason && (
                  <p className="text-xs text-amber-700 bg-amber-50 dark:bg-amber-950/40 p-2.5 rounded-lg border border-amber-200 dark:border-amber-800 leading-relaxed">
                    Rescheduled: {item.rescheduled_reason}
                  </p>
                )}

                {item.cancellation_reason && (
                  <p className="text-xs text-red-700 bg-red-50 dark:bg-red-950/40 p-2.5 rounded-lg border border-red-200 dark:border-red-800 leading-relaxed">
                    Cancelled: {item.cancellation_reason}
                  </p>
                )}

                {/* Meeting Instructions */}
                {item.meeting_instructions && (
                  <p className="text-xs text-slate-500 leading-relaxed italic">
                    Instructions: &ldquo;{item.meeting_instructions}&rdquo;
                  </p>
                )}
              </div>

              {/* Action Buttons */}
              <div className="flex items-center justify-between pt-2 border-t border-slate-100 dark:border-slate-800">
                <Link
                  href={`/candidate/applications/${item.application_id}`}
                  className="text-xs font-semibold text-primary-600 hover:underline flex items-center gap-1"
                >
                  <span>View Application</span>
                  <ChevronRight className="w-3.5 h-3.5" />
                </Link>

                {item.meeting_url ? (
                  <a
                    href={item.meeting_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="inline-flex items-center gap-1 px-3 py-1.5 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-lg shadow-sm transition-colors"
                  >
                    <Video className="w-3.5 h-3.5" />
                    <span>Join Video Call</span>
                    <ExternalLink className="w-3 h-3 ml-0.5" />
                  </a>
                ) : (
                  <span className="text-[11px] text-slate-400">
                    Conference link will be sent prior to call
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
