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
  Shield,
  History,
  Lock,
  ExternalLink,
  RefreshCw,
  AlertCircle,
  CheckCircle,
  Eye,
  User,
  MessageSquare,
  CheckSquare,
  Star,
  Plus,
  Trash2,
  Edit3,
  ThumbsUp,
  ThumbsDown,
  Sparkles,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type {
  CandidateActivityTimelineResponse,
  CandidateDetailResponse,
  InternalNoteResponse,
  RecruitmentTaskResponse,
  ResumeSignedUrlResponse,
  ReviewFeedbackResponse,
  TeamMemberOption,
} from "@/types/hr";

export default function CandidateDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const candidateId = params.id as string;
  const applicationId = searchParams.get("applicationId") || undefined;

  const [activeTab, setActiveTab] = useState<
    "profile" | "notes" | "scorecards" | "tasks" | "timeline"
  >("profile");

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [candidate, setCandidate] = useState<CandidateDetailResponse | null>(null);

  // Resume downloading
  const [downloadingResume, setDownloadingResume] = useState(false);

  // ----------------------------------------------------------------------
  // Notes State
  // ----------------------------------------------------------------------
  const [notes, setNotes] = useState<InternalNoteResponse[]>([]);
  const [notesLoading, setNotesLoading] = useState(false);
  const [newNoteContent, setNewNoteContent] = useState("");
  const [newNoteCategory, setNewNoteCategory] = useState("general");
  const [newNoteConfidential, setNewNoteConfidential] = useState(false);
  const [editingNoteId, setEditingNoteId] = useState<string | null>(null);
  const [editingContent, setEditingContent] = useState("");
  const [submittingNote, setSubmittingNote] = useState(false);

  // ----------------------------------------------------------------------
  // Review Scorecards State
  // ----------------------------------------------------------------------
  const [reviews, setReviews] = useState<ReviewFeedbackResponse[]>([]);
  const [reviewsLoading, setReviewsLoading] = useState(false);
  const [showReviewForm, setShowReviewForm] = useState(false);
  const [recommendation, setRecommendation] = useState<
    "strong_yes" | "yes" | "neutral" | "no" | "strong_no"
  >("yes");
  const [overallRating, setOverallRating] = useState<number>(4);
  const [technicalRating, setTechnicalRating] = useState<number>(4);
  const [communicationRating, setCommunicationRating] = useState<number>(4);
  const [culturalRating, setCulturalRating] = useState<number>(4);
  const [reviewSummary, setReviewSummary] = useState("");
  const [reviewPros, setReviewPros] = useState("");
  const [reviewCons, setReviewCons] = useState("");
  const [submittingReview, setSubmittingReview] = useState(false);

  // ----------------------------------------------------------------------
  // Recruitment Tasks State
  // ----------------------------------------------------------------------
  const [tasks, setTasks] = useState<RecruitmentTaskResponse[]>([]);
  const [tasksLoading, setTasksLoading] = useState(false);
  const [teamMembers, setTeamMembers] = useState<TeamMemberOption[]>([]);
  const [showTaskForm, setShowTaskForm] = useState(false);
  const [taskTitle, setTaskTitle] = useState("");
  const [taskDescription, setTaskDescription] = useState("");
  const [taskType, setTaskType] = useState("general");
  const [taskAssigneeId, setTaskAssigneeId] = useState<string>("");
  const [taskDueDate, setTaskDueDate] = useState<string>("");
  const [submittingTask, setSubmittingTask] = useState(false);

  // ----------------------------------------------------------------------
  // Activity Timeline State
  // ----------------------------------------------------------------------
  const [timeline, setTimeline] = useState<CandidateActivityTimelineResponse | null>(null);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineFilter, setTimelineFilter] = useState<"all" | "internal" | "candidate">("all");

  // ----------------------------------------------------------------------
  // Data Loaders
  // ----------------------------------------------------------------------
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

  const loadNotes = useCallback(async () => {
    try {
      setNotesLoading(true);
      const data = await hrApi.getInternalNotes(candidateId, applicationId);
      setNotes(data);
    } catch {
      // Ignore or log error
    } finally {
      setNotesLoading(false);
    }
  }, [candidateId, applicationId]);

  const loadReviews = useCallback(async (appId: string) => {
    try {
      setReviewsLoading(true);
      const data = await hrApi.getApplicationReviews(appId);
      setReviews(data);
    } catch {
      // Ignore
    } finally {
      setReviewsLoading(false);
    }
  }, []);

  const loadTasks = useCallback(async () => {
    try {
      setTasksLoading(true);
      const data = await hrApi.listRecruitmentTasks({ candidate_id: candidateId });
      setTasks(data);
    } catch {
      // Ignore
    } finally {
      setTasksLoading(false);
    }
  }, [candidateId]);

  const loadTimeline = useCallback(async () => {
    try {
      setTimelineLoading(true);
      const data = await hrApi.getCandidateTimeline(candidateId, applicationId);
      setTimeline(data);
    } catch {
      // Ignore
    } finally {
      setTimelineLoading(false);
    }
  }, [candidateId, applicationId]);

  const loadTeamMembers = useCallback(async () => {
    try {
      const members = await hrApi.getTeamMembers();
      setTeamMembers(members);
    } catch {
      // Ignore
    }
  }, []);

  useEffect(() => {
    loadCandidateData();
    loadNotes();
    loadTasks();
    loadTimeline();
    loadTeamMembers();
  }, [loadCandidateData, loadNotes, loadTasks, loadTimeline, loadTeamMembers]);

  useEffect(() => {
    const appId = candidate?.current_application?.application_id || applicationId;
    if (appId) {
      loadReviews(appId);
    }
  }, [candidate, applicationId, loadReviews]);

  // ----------------------------------------------------------------------
  // Handlers
  // ----------------------------------------------------------------------
  const handleDownloadResume = async () => {
    if (!candidate?.current_application?.application_id) return;
    try {
      setDownloadingResume(true);
      const res: ResumeSignedUrlResponse = await hrApi.getApplicationResumeUrl(
        candidate.current_application.application_id
      );
      if (res.download_url) {
        window.open(res.download_url, "_blank", "noopener,noreferrer");
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to generate resume download link";
      alert(`Resume download error: ${msg}`);
    } finally {
      setDownloadingResume(false);
    }
  };

  const handleAddNote = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newNoteContent.trim()) return;
    try {
      setSubmittingNote(true);
      await hrApi.addInternalNote(candidateId, {
        application_id: applicationId || candidate?.current_application?.application_id || null,
        content: newNoteContent.trim(),
        category: newNoteCategory,
        is_confidential: newNoteConfidential,
      });
      setNewNoteContent("");
      setNewNoteConfidential(false);
      await loadNotes();
      loadTimeline();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to record internal note");
    } finally {
      setSubmittingNote(false);
    }
  };

  const handleUpdateNote = async (noteId: string) => {
    if (!editingContent.trim()) return;
    try {
      await hrApi.updateInternalNote(noteId, { content: editingContent.trim() });
      setEditingNoteId(null);
      setEditingContent("");
      await loadNotes();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update note");
    }
  };

  const handleDeleteNote = async (noteId: string) => {
    if (!confirm("Are you sure you want to delete this internal note?")) return;
    try {
      await hrApi.deleteInternalNote(noteId);
      await loadNotes();
      loadTimeline();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete note");
    }
  };

  const handleSubmitReview = async (e: React.FormEvent) => {
    e.preventDefault();
    const appId = candidate?.current_application?.application_id || applicationId;
    if (!appId) {
      alert("No active application found to review.");
      return;
    }
    if (!reviewSummary.trim()) {
      alert("Please provide an evaluation summary.");
      return;
    }
    try {
      setSubmittingReview(true);
      await hrApi.submitReviewFeedback(appId, {
        recommendation,
        overall_rating: overallRating,
        technical_rating: technicalRating,
        communication_rating: communicationRating,
        cultural_rating: culturalRating,
        summary: reviewSummary.trim(),
        pros: reviewPros
          .split(",")
          .map((p) => p.trim())
          .filter(Boolean),
        cons: reviewCons
          .split(",")
          .map((c) => c.trim())
          .filter(Boolean),
      });
      setShowReviewForm(false);
      setReviewSummary("");
      setReviewPros("");
      setReviewCons("");
      await loadReviews(appId);
      loadTimeline();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to submit review scorecard");
    } finally {
      setSubmittingReview(false);
    }
  };

  const handleCreateTask = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!taskTitle.trim()) return;
    try {
      setSubmittingTask(true);
      await hrApi.createRecruitmentTask(candidateId, {
        application_id: applicationId || candidate?.current_application?.application_id || null,
        title: taskTitle.trim(),
        description: taskDescription.trim() || undefined,
        task_type: taskType,
        assignee_id: taskAssigneeId || null,
        due_date: taskDueDate ? new Date(taskDueDate).toISOString() : null,
      });
      setShowTaskForm(false);
      setTaskTitle("");
      setTaskDescription("");
      setTaskAssigneeId("");
      setTaskDueDate("");
      await loadTasks();
      loadTimeline();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to create follow-up task");
    } finally {
      setSubmittingTask(false);
    }
  };

  const handleToggleTask = async (taskId: string, currentCompleted: boolean) => {
    try {
      await hrApi.updateRecruitmentTask(taskId, { is_completed: !currentCompleted });
      await loadTasks();
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to update task");
    }
  };

  if (loading) {
    return (
      <div
        className="p-16 text-center text-xs text-slate-400 space-y-3"
        data-testid="candidate-loading"
      >
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
        <h2 className="text-lg font-bold text-slate-800 dark:text-slate-100">
          Candidate Access Denied or Not Found
        </h2>
        <p className="text-xs text-slate-500 leading-relaxed">
          {error ||
            "You do not have permission to view this candidate profile, or the candidate has not applied to any job within your organization."}
        </p>
        <div className="pt-2">
          <Link
            href="/hr/applicants"
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 transition-colors shadow-sm"
          >
            <ArrowLeft className="w-4 h-4" /> Return to Applicants
          </Link>
        </div>
      </div>
    );
  }

  const appCtx = candidate.current_application;

  const filteredTimelineEvents = (timeline?.events || []).filter((e) => {
    if (timelineFilter === "internal") return e.is_internal;
    if (timelineFilter === "candidate") return !e.is_internal;
    return true;
  });

  return (
    <div className="space-y-6 max-w-7xl mx-auto pb-16">
      {/* Top Navigation */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <Link
          href="/hr/applicants"
          className="inline-flex items-center gap-2 text-xs font-semibold text-slate-500 hover:text-slate-900 dark:hover:text-slate-100 transition-colors"
        >
          <ArrowLeft className="w-4 h-4" />
          <span>Back to Applicants</span>
        </Link>

        <div className="flex items-center gap-2">
          {appCtx?.resume_snapshot_sha256 && (
            <button
              onClick={handleDownloadResume}
              disabled={downloadingResume}
              className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-semibold bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 hover:bg-slate-50 dark:hover:bg-slate-800 transition shadow-sm text-slate-700 dark:text-slate-200 disabled:opacity-60"
            >
              <Download className="w-3.5 h-3.5 text-blue-600" />
              <span>{downloadingResume ? "Generating Link..." : "Download Resume"}</span>
            </button>
          )}

          {appCtx && (
            <Link
              href={`/hr/pipeline?jobId=${appCtx.job_id}`}
              className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 transition shadow-sm"
            >
              <span>View in Pipeline</span>
            </Link>
          )}
        </div>
      </div>

      {/* Header Profile Card */}
      <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          <div className="flex items-start gap-4">
            <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-blue-600 to-indigo-600 text-white flex items-center justify-center font-bold text-xl shadow-md shrink-0">
              {candidate.full_name
                .split(" ")
                .map((n) => n[0])
                .slice(0, 2)
                .join("")
                .toUpperCase()}
            </div>
            <div className="space-y-1">
              <div className="flex items-center gap-2 flex-wrap">
                <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                  {candidate.full_name}
                </h1>
                {appCtx && (
                  <span className="px-2.5 py-0.5 rounded-full text-[10px] font-semibold uppercase tracking-wider bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {appCtx.status.replace(/_/g, " ")}
                  </span>
                )}
                {candidate.bio && (
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
                    <CheckCircle className="w-3 h-3" /> Profile Active
                  </span>
                )}
              </div>

              {candidate.headline && (
                <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
                  {candidate.headline}
                </p>
              )}

              <div className="flex items-center gap-3 text-xs text-slate-500 flex-wrap pt-1">
                {candidate.email && (
                  <span className="flex items-center gap-1">
                    <Mail className="w-3.5 h-3.5 text-slate-400" />
                    {candidate.email}
                  </span>
                )}
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

      {/* Navigation Tabs */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 overflow-x-auto">
        <button
          onClick={() => setActiveTab("profile")}
          data-testid="tab-profile"
          className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition whitespace-nowrap flex items-center gap-2 ${
            activeTab === "profile"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <User className="w-4 h-4" />
          <span>Profile & Background</span>
        </button>

        <button
          onClick={() => setActiveTab("notes")}
          data-testid="tab-notes"
          className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition whitespace-nowrap flex items-center gap-2 ${
            activeTab === "notes"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <MessageSquare className="w-4 h-4" />
          <span>Internal Notes</span>
          <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600">
            {notes.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("scorecards")}
          data-testid="tab-scorecards"
          className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition whitespace-nowrap flex items-center gap-2 ${
            activeTab === "scorecards"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <Star className="w-4 h-4" />
          <span>Evaluations & Scorecards</span>
          <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600">
            {reviews.length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("tasks")}
          data-testid="tab-tasks"
          className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition whitespace-nowrap flex items-center gap-2 ${
            activeTab === "tasks"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <CheckSquare className="w-4 h-4" />
          <span>Recruitment Tasks</span>
          <span className="px-1.5 py-0.2 rounded-full text-[10px] bg-slate-100 dark:bg-slate-800 text-slate-600">
            {tasks.filter((t) => !t.is_completed).length}
          </span>
        </button>

        <button
          onClick={() => setActiveTab("timeline")}
          data-testid="tab-timeline"
          className={`px-4 py-2.5 text-xs font-semibold border-b-2 transition whitespace-nowrap flex items-center gap-2 ${
            activeTab === "timeline"
              ? "border-blue-600 text-blue-600"
              : "border-transparent text-slate-500 hover:text-slate-800 dark:hover:text-slate-200"
          }`}
        >
          <History className="w-4 h-4" />
          <span>Activity Timeline</span>
        </button>
      </div>

      {/* Main Content Layout */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Columns: Active Tab Panel */}
        <div className="lg:col-span-2 space-y-6">
          {/* TAB 1: Profile & Background */}
          {activeTab === "profile" && (
            <div className="space-y-6">
              {/* Bio / Summary */}
              {candidate.bio && (
                <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-2">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-500">
                    Candidate Biography
                  </h3>
                  <p className="text-xs text-slate-700 dark:text-slate-300 leading-relaxed whitespace-pre-line">
                    {candidate.bio}
                  </p>
                </div>
              )}

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

              {/* Projects */}
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
          )}

          {/* TAB 2: Internal Notes */}
          {activeTab === "notes" && (
            <div className="space-y-6">
              {/* Add Note Form */}
              <div
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-4"
                data-testid="add-note-form"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <Lock className="w-4 h-4 text-amber-600" />
                    <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                      Add Internal Note
                    </h3>
                  </div>
                  <span className="text-[11px] text-amber-600 bg-amber-50 dark:bg-amber-950/40 px-2 py-0.5 rounded-full font-medium border border-amber-200 dark:border-amber-900/50">
                    Confidential to Organization
                  </span>
                </div>

                <form onSubmit={handleAddNote} className="space-y-3">
                  <textarea
                    value={newNoteContent}
                    onChange={(e) => setNewNoteContent(e.target.value)}
                    placeholder="Enter confidential internal observations, interview thoughts, or recruiter notes..."
                    rows={3}
                    data-testid="note-content-input"
                    className="w-full text-xs p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-blue-500"
                  />

                  <div className="flex items-center justify-between flex-wrap gap-3">
                    <div className="flex items-center gap-3">
                      <select
                        value={newNoteCategory}
                        onChange={(e) => setNewNoteCategory(e.target.value)}
                        data-testid="note-category-select"
                        className="text-xs px-2.5 py-1.5 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-700 dark:text-slate-300"
                      >
                        <option value="general">General</option>
                        <option value="screening">Screening</option>
                        <option value="interview_feedback">Interview Feedback</option>
                        <option value="compensation">Compensation</option>
                        <option value="reference_check">Reference Check</option>
                      </select>

                      <label className="flex items-center gap-1.5 text-xs text-slate-600 dark:text-slate-300 cursor-pointer">
                        <input
                          type="checkbox"
                          checked={newNoteConfidential}
                          onChange={(e) => setNewNoteConfidential(e.target.checked)}
                          data-testid="note-confidential-checkbox"
                          className="rounded text-blue-600 focus:ring-blue-500"
                        />
                        <span>Admins & Author Only</span>
                      </label>
                    </div>

                    <button
                      type="submit"
                      disabled={submittingNote || !newNoteContent.trim()}
                      data-testid="submit-note-btn"
                      className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 disabled:opacity-50 transition shadow-sm inline-flex items-center gap-1.5"
                    >
                      <Plus className="w-3.5 h-3.5" />
                      <span>{submittingNote ? "Saving..." : "Post Note"}</span>
                    </button>
                  </div>
                </form>
              </div>

              {/* Notes List */}
              <div
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4"
                data-testid="notes-list"
              >
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                    Internal Collaboration Notes ({notes.length})
                  </h3>
                  <span className="text-[11px] text-slate-400">
                    Never visible to candidates
                  </span>
                </div>

                {notesLoading ? (
                  <p className="text-xs text-slate-400 italic">Loading notes...</p>
                ) : notes.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-400 italic">
                    No internal notes recorded yet. Add the first note above.
                  </div>
                ) : (
                  <div className="space-y-3">
                    {notes.map((note) => (
                      <div
                        key={note.id}
                        className="p-4 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/70 dark:bg-slate-800/40 space-y-2 text-xs"
                      >
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-semibold text-slate-800 dark:text-slate-200">
                              {note.author_name}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 capitalize font-mono">
                              {note.author_role.replace("_", " ")}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 capitalize">
                              {note.category.replace("_", " ")}
                            </span>
                            {note.is_confidential && (
                              <span className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded-full bg-rose-50 text-rose-700 border border-rose-200">
                                <Lock className="w-2.5 h-2.5" /> Confidential
                              </span>
                            )}
                          </div>

                          <div className="flex items-center gap-2 text-[11px] text-slate-400">
                            <span>{new Date(note.created_at).toLocaleString()}</span>
                            {note.can_edit && (
                              <div className="flex items-center gap-1 ml-2">
                                <button
                                  onClick={() => {
                                    setEditingNoteId(note.id);
                                    setEditingContent(note.content);
                                  }}
                                  className="p-1 hover:text-blue-600"
                                  title="Edit note"
                                >
                                  <Edit3 className="w-3.5 h-3.5" />
                                </button>
                                <button
                                  onClick={() => handleDeleteNote(note.id)}
                                  className="p-1 hover:text-rose-600"
                                  title="Delete note"
                                >
                                  <Trash2 className="w-3.5 h-3.5" />
                                </button>
                              </div>
                            )}
                          </div>
                        </div>

                        {editingNoteId === note.id ? (
                          <div className="space-y-2 pt-2">
                            <textarea
                              value={editingContent}
                              onChange={(e) => setEditingContent(e.target.value)}
                              rows={2}
                              className="w-full text-xs p-2.5 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-900 text-slate-900 dark:text-slate-100"
                            />
                            <div className="flex items-center gap-2">
                              <button
                                onClick={() => handleUpdateNote(note.id)}
                                className="px-3 py-1 bg-blue-600 text-white rounded text-xs font-semibold"
                              >
                                Save Changes
                              </button>
                              <button
                                onClick={() => setEditingNoteId(null)}
                                className="px-3 py-1 bg-slate-200 text-slate-700 rounded text-xs font-semibold"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        ) : (
                          <p className="text-slate-700 dark:text-slate-300 whitespace-pre-line leading-relaxed">
                            {note.content}
                          </p>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 3: Evaluations & Scorecards */}
          {activeTab === "scorecards" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Application Review Evaluations
                  </h3>
                  <p className="text-xs text-slate-500">
                    Structured hiring manager and recruiter scorecards for candidate appraisal.
                  </p>
                </div>
                <button
                  onClick={() => setShowReviewForm(!showReviewForm)}
                  data-testid="toggle-review-form-btn"
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 transition shadow-sm inline-flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{showReviewForm ? "Close Form" : "Submit Evaluation"}</span>
                </button>
              </div>

              {/* Submit Evaluation Form */}
              {showReviewForm && (
                <form
                  onSubmit={handleSubmitReview}
                  data-testid="submit-scorecard-form"
                  className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4"
                >
                  <h4 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 pb-2 border-b border-slate-100 dark:border-slate-800">
                    Candidate Evaluation Scorecard
                  </h4>

                  {/* Recommendation Selector */}
                  <div className="space-y-1.5">
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Recommendation *
                    </label>
                    <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-xs font-semibold">
                      {(
                        [
                          ["strong_yes", "Strong Yes", "bg-emerald-50 text-emerald-700 border-emerald-300"],
                          ["yes", "Yes", "bg-green-50 text-green-700 border-green-300"],
                          ["neutral", "Neutral", "bg-slate-100 text-slate-700 border-slate-300"],
                          ["no", "No", "bg-amber-50 text-amber-700 border-amber-300"],
                          ["strong_no", "Strong No", "bg-rose-50 text-rose-700 border-rose-300"],
                        ] as const
                      ).map(([val, label, style]) => (
                        <button
                          key={val}
                          type="button"
                          onClick={() => setRecommendation(val)}
                          className={`py-2 px-3 rounded-xl border text-center transition ${
                            recommendation === val
                              ? `${style} ring-2 ring-blue-500 font-bold`
                              : "border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400"
                          }`}
                        >
                          {label}
                        </button>
                      ))}
                    </div>
                  </div>

                  {/* Ratings (1 - 5) */}
                  <div className="grid grid-cols-1 sm:grid-cols-4 gap-4 pt-2">
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Overall Rating (1-5)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={5}
                        value={overallRating}
                        onChange={(e) => setOverallRating(parseInt(e.target.value) || 3)}
                        className="w-full text-xs p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Technical Rating (1-5)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={5}
                        value={technicalRating}
                        onChange={(e) => setTechnicalRating(parseInt(e.target.value) || 3)}
                        className="w-full text-xs p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Communication (1-5)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={5}
                        value={communicationRating}
                        onChange={(e) => setCommunicationRating(parseInt(e.target.value) || 3)}
                        className="w-full text-xs p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                        Cultural Alignment (1-5)
                      </label>
                      <input
                        type="number"
                        min={1}
                        max={5}
                        value={culturalRating}
                        onChange={(e) => setCulturalRating(parseInt(e.target.value) || 3)}
                        className="w-full text-xs p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                  </div>

                  {/* Summary */}
                  <div className="space-y-1 pt-2">
                    <label className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Evaluation Summary & Rationale *
                    </label>
                    <textarea
                      value={reviewSummary}
                      onChange={(e) => setReviewSummary(e.target.value)}
                      rows={3}
                      placeholder="Detailed justification of recommendation and technical assessment..."
                      className="w-full text-xs p-3 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                    />
                  </div>

                  {/* Pros & Cons */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                        Key Strengths / Pros (comma separated)
                      </label>
                      <input
                        type="text"
                        value={reviewPros}
                        onChange={(e) => setReviewPros(e.target.value)}
                        placeholder="Strong system design, clear communicator, domain expertise"
                        className="w-full text-xs p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                    <div className="space-y-1">
                      <label className="text-xs font-semibold text-amber-700 dark:text-amber-400">
                        Key Concerns / Cons (comma separated)
                      </label>
                      <input
                        type="text"
                        value={reviewCons}
                        onChange={(e) => setReviewCons(e.target.value)}
                        placeholder="Limited distributed systems depth, salary expectation high"
                        className="w-full text-xs p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                  </div>

                  <div className="flex justify-end gap-2 pt-2">
                    <button
                      type="button"
                      onClick={() => setShowReviewForm(false)}
                      className="px-4 py-1.5 rounded-xl text-xs font-semibold bg-slate-100 text-slate-700 hover:bg-slate-200"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submittingReview}
                      data-testid="submit-scorecard-btn"
                      className="px-5 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 shadow-sm"
                    >
                      {submittingReview ? "Submitting..." : "Submit Scorecard"}
                    </button>
                  </div>
                </form>
              )}

              {/* Submitted Reviews List */}
              <div
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4"
                data-testid="scorecards-list"
              >
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                    Collaborative Scorecards ({reviews.length})
                  </h3>
                </div>

                {reviewsLoading ? (
                  <p className="text-xs text-slate-400 italic">Loading scorecards...</p>
                ) : reviews.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-400 italic">
                    No evaluation scorecards submitted yet. Click &ldquo;Submit Evaluation&rdquo; above.
                  </div>
                ) : (
                  <div className="space-y-4">
                    {reviews.map((rev) => (
                      <div
                        key={rev.id}
                        className="p-5 rounded-xl border border-slate-100 dark:border-slate-800 bg-slate-50/60 dark:bg-slate-800/40 space-y-3 text-xs"
                      >
                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-900 dark:text-slate-100">
                              {rev.reviewer_name}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-200 dark:bg-slate-700 text-slate-700 dark:text-slate-300 capitalize font-mono">
                              {rev.reviewer_role.replace("_", " ")}
                            </span>
                            <span
                              className={`text-[11px] font-bold px-2.5 py-0.5 rounded-full uppercase border ${
                                rev.recommendation === "strong_yes"
                                  ? "bg-emerald-50 text-emerald-700 border-emerald-300"
                                  : rev.recommendation === "yes"
                                  ? "bg-green-50 text-green-700 border-green-300"
                                  : rev.recommendation === "neutral"
                                  ? "bg-slate-100 text-slate-700 border-slate-300"
                                  : rev.recommendation === "no"
                                  ? "bg-amber-50 text-amber-700 border-amber-300"
                                  : "bg-rose-50 text-rose-700 border-rose-300"
                              }`}
                            >
                              {rev.recommendation.replace("_", " ")}
                            </span>
                          </div>

                          <span className="text-[11px] text-slate-400">
                            {new Date(rev.created_at).toLocaleString()}
                          </span>
                        </div>

                        {/* Ratings Breakdown */}
                        <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-1 font-mono text-[11px]">
                          {rev.overall_rating && (
                            <div className="p-2 rounded bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                              <span className="text-slate-400 block text-[9px] uppercase">Overall</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200">
                                {rev.overall_rating} / 5
                              </span>
                            </div>
                          )}
                          {rev.technical_rating && (
                            <div className="p-2 rounded bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                              <span className="text-slate-400 block text-[9px] uppercase">Technical</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200">
                                {rev.technical_rating} / 5
                              </span>
                            </div>
                          )}
                          {rev.communication_rating && (
                            <div className="p-2 rounded bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                              <span className="text-slate-400 block text-[9px] uppercase">Communication</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200">
                                {rev.communication_rating} / 5
                              </span>
                            </div>
                          )}
                          {rev.cultural_rating && (
                            <div className="p-2 rounded bg-white dark:bg-slate-800 border border-slate-100 dark:border-slate-700">
                              <span className="text-slate-400 block text-[9px] uppercase">Culture</span>
                              <span className="font-bold text-slate-800 dark:text-slate-200">
                                {rev.cultural_rating} / 5
                              </span>
                            </div>
                          )}
                        </div>

                        {/* Summary */}
                        <p className="text-slate-700 dark:text-slate-300 whitespace-pre-line leading-relaxed pt-1">
                          {rev.summary}
                        </p>

                        {/* Pros / Cons Tags */}
                        {((rev.pros && rev.pros.length > 0) || (rev.cons && rev.cons.length > 0)) && (
                          <div className="pt-2 flex flex-wrap gap-4 border-t border-slate-100 dark:border-slate-800 text-[11px]">
                            {rev.pros && rev.pros.length > 0 && (
                              <div className="space-y-1">
                                <span className="font-semibold text-emerald-700 dark:text-emerald-400 flex items-center gap-1">
                                  <ThumbsUp className="w-3 h-3" /> Strengths:
                                </span>
                                <div className="flex flex-wrap gap-1">
                                  {rev.pros.map((p, i) => (
                                    <span
                                      key={i}
                                      className="px-2 py-0.5 rounded bg-emerald-50 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300 border border-emerald-200"
                                    >
                                      {p}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}

                            {rev.cons && rev.cons.length > 0 && (
                              <div className="space-y-1">
                                <span className="font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1">
                                  <ThumbsDown className="w-3 h-3" /> Concerns:
                                </span>
                                <div className="flex flex-wrap gap-1">
                                  {rev.cons.map((c, i) => (
                                    <span
                                      key={i}
                                      className="px-2 py-0.5 rounded bg-amber-50 text-amber-800 dark:bg-amber-950/40 dark:text-amber-300 border border-amber-200"
                                    >
                                      {c}
                                    </span>
                                  ))}
                                </div>
                              </div>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 4: Recruitment Tasks */}
          {activeTab === "tasks" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Recruitment Follow-up Tasks
                  </h3>
                  <p className="text-xs text-slate-500">
                    Track recruiter and hiring manager to-dos, screening calls, and schedule checks.
                  </p>
                </div>
                <button
                  onClick={() => setShowTaskForm(!showTaskForm)}
                  data-testid="toggle-task-form-btn"
                  className="px-3.5 py-1.5 rounded-xl text-xs font-semibold bg-blue-600 text-white hover:bg-blue-700 transition shadow-sm inline-flex items-center gap-1.5"
                >
                  <Plus className="w-3.5 h-3.5" />
                  <span>{showTaskForm ? "Close Form" : "Create Task"}</span>
                </button>
              </div>

              {/* Create Task Form */}
              {showTaskForm && (
                <form
                  onSubmit={handleCreateTask}
                  data-testid="create-task-form"
                  className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3 text-xs"
                >
                  <h4 className="font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300 pb-1 border-b border-slate-100 dark:border-slate-800">
                    New Recruitment Follow-up Task
                  </h4>

                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700 dark:text-slate-300">
                      Task Title *
                    </label>
                    <input
                      type="text"
                      value={taskTitle}
                      onChange={(e) => setTaskTitle(e.target.value)}
                      placeholder="e.g. Conduct 30-min technical phone screen"
                      data-testid="task-title-input"
                      className="w-full p-2.5 rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                    />
                  </div>

                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                    <div className="space-y-1">
                      <label className="font-semibold text-slate-700 dark:text-slate-300">
                        Task Type
                      </label>
                      <select
                        value={taskType}
                        onChange={(e) => setTaskType(e.target.value)}
                        data-testid="task-type-select"
                        className="w-full p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      >
                        <option value="general">General</option>
                        <option value="resume_review">Resume Review</option>
                        <option value="phone_screen">Phone Screen</option>
                        <option value="schedule_interview">Schedule Interview</option>
                        <option value="reference_check">Reference Check</option>
                        <option value="send_offer">Send Offer</option>
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="font-semibold text-slate-700 dark:text-slate-300">
                        Assignee
                      </label>
                      <select
                        value={taskAssigneeId}
                        onChange={(e) => setTaskAssigneeId(e.target.value)}
                        data-testid="task-assignee-select"
                        className="w-full p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      >
                        <option value="">Unassigned</option>
                        {teamMembers.map((m) => (
                          <option key={m.id} value={m.id}>
                            {m.name} ({m.role.replace("_", " ")})
                          </option>
                        ))}
                      </select>
                    </div>

                    <div className="space-y-1">
                      <label className="font-semibold text-slate-700 dark:text-slate-300">
                        Due Date
                      </label>
                      <input
                        type="date"
                        value={taskDueDate}
                        onChange={(e) => setTaskDueDate(e.target.value)}
                        data-testid="task-duedate-input"
                        className="w-full p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                      />
                    </div>
                  </div>

                  <div className="space-y-1">
                    <label className="font-semibold text-slate-700 dark:text-slate-300">
                      Description / Instructions
                    </label>
                    <textarea
                      value={taskDescription}
                      onChange={(e) => setTaskDescription(e.target.value)}
                      rows={2}
                      placeholder="Optional details or preparation checklist..."
                      className="w-full p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-800"
                    />
                  </div>

                  <div className="flex justify-end gap-2 pt-1">
                    <button
                      type="button"
                      onClick={() => setShowTaskForm(false)}
                      className="px-3 py-1 bg-slate-100 text-slate-700 rounded-lg font-semibold"
                    >
                      Cancel
                    </button>
                    <button
                      type="submit"
                      disabled={submittingTask || !taskTitle.trim()}
                      data-testid="submit-task-btn"
                      className="px-4 py-1.5 bg-blue-600 text-white rounded-lg font-semibold hover:bg-blue-700"
                    >
                      {submittingTask ? "Saving..." : "Save Task"}
                    </button>
                  </div>
                </form>
              )}

              {/* Task Checklist */}
              <div
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4"
                data-testid="tasks-list"
              >
                <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
                  <h3 className="text-xs font-bold uppercase tracking-wider text-slate-700 dark:text-slate-300">
                    Candidate Tasks ({tasks.length})
                  </h3>
                </div>

                {tasksLoading ? (
                  <p className="text-xs text-slate-400 italic">Loading tasks...</p>
                ) : tasks.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-400 italic">
                    No follow-up tasks recorded for this candidate.
                  </div>
                ) : (
                  <div className="space-y-2.5">
                    {tasks.map((task) => (
                      <div
                        key={task.id}
                        className={`p-3.5 rounded-xl border flex items-start gap-3 transition ${
                          task.is_completed
                            ? "bg-slate-50/50 dark:bg-slate-900/40 border-slate-100 dark:border-slate-800 opacity-60"
                            : "bg-white dark:bg-slate-800/50 border-slate-200 dark:border-slate-700 shadow-xs"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={task.is_completed}
                          onChange={() => handleToggleTask(task.id, task.is_completed)}
                          data-testid={`task-checkbox-${task.id}`}
                          className="mt-0.5 rounded text-blue-600 focus:ring-blue-500 cursor-pointer"
                        />

                        <div className="flex-1 space-y-1 text-xs">
                          <div className="flex items-center justify-between flex-wrap gap-2">
                            <span
                              className={`font-semibold ${
                                task.is_completed
                                  ? "line-through text-slate-400"
                                  : "text-slate-800 dark:text-slate-200"
                              }`}
                            >
                              {task.title}
                            </span>
                            <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 capitalize">
                              {task.task_type.replace("_", " ")}
                            </span>
                          </div>

                          {task.description && (
                            <p className="text-slate-500 leading-relaxed">{task.description}</p>
                          )}

                          <div className="flex items-center gap-3 text-[11px] text-slate-400 pt-1 flex-wrap">
                            {task.assignee_name && (
                              <span className="flex items-center gap-1 font-medium text-slate-600 dark:text-slate-300">
                                <User className="w-3 h-3 text-blue-500" />
                                {task.assignee_name}
                              </span>
                            )}
                            {task.due_date && (
                              <span className="flex items-center gap-1 font-mono">
                                <Calendar className="w-3 h-3 text-amber-500" />
                                Due: {new Date(task.due_date).toLocaleDateString()}
                              </span>
                            )}
                            <span>Created by {task.creator_name}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* TAB 5: Unified Activity Timeline */}
          {activeTab === "timeline" && (
            <div className="space-y-6">
              <div className="flex items-center justify-between flex-wrap gap-3">
                <div>
                  <h3 className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    Candidate Activity Timeline
                  </h3>
                  <p className="text-xs text-slate-500">
                    Chronological audit trail separating internal collaboration from candidate milestones.
                  </p>
                </div>

                <div className="flex items-center gap-1.5 p-1 rounded-xl bg-slate-100 dark:bg-slate-800 text-xs">
                  <button
                    onClick={() => setTimelineFilter("all")}
                    className={`px-3 py-1 rounded-lg font-semibold transition ${
                      timelineFilter === "all"
                        ? "bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100 shadow-xs"
                        : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    All Events ({timeline?.events.length || 0})
                  </button>
                  <button
                    onClick={() => setTimelineFilter("internal")}
                    className={`px-3 py-1 rounded-lg font-semibold transition ${
                      timelineFilter === "internal"
                        ? "bg-white dark:bg-slate-900 text-amber-600 shadow-xs"
                        : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    Internal Only
                  </button>
                  <button
                    onClick={() => setTimelineFilter("candidate")}
                    className={`px-3 py-1 rounded-lg font-semibold transition ${
                      timelineFilter === "candidate"
                        ? "bg-white dark:bg-slate-900 text-blue-600 shadow-xs"
                        : "text-slate-500 hover:text-slate-700"
                    }`}
                  >
                    Candidate Facing
                  </button>
                </div>
              </div>

              <div
                className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4"
                data-testid="timeline-list"
              >
                {timelineLoading ? (
                  <p className="text-xs text-slate-400 italic">Loading activity timeline...</p>
                ) : filteredTimelineEvents.length === 0 ? (
                  <div className="text-center py-8 text-xs text-slate-400 italic">
                    No timeline events match the selected filter.
                  </div>
                ) : (
                  <div className="relative pl-6 space-y-6 before:absolute before:left-2 before:top-2 before:bottom-2 before:w-0.5 before:bg-slate-200 dark:before:bg-slate-800">
                    {filteredTimelineEvents.map((evt) => (
                      <div key={evt.id} className="relative space-y-1 text-xs">
                        {/* Event Dot */}
                        <div
                          className={`absolute -left-6 top-1 w-3 h-3 rounded-full border-2 border-white dark:border-slate-900 ${
                            evt.is_internal ? "bg-amber-500" : "bg-blue-600"
                          }`}
                        />

                        <div className="flex items-center justify-between flex-wrap gap-2">
                          <div className="flex items-center gap-2">
                            <span className="font-bold text-slate-900 dark:text-slate-100">
                              {evt.title}
                            </span>
                            <span
                              className={`text-[10px] px-2 py-0.5 rounded-full font-semibold border ${
                                evt.is_internal
                                  ? "bg-amber-50 text-amber-800 border-amber-200 dark:bg-amber-950/40 dark:text-amber-300"
                                  : "bg-blue-50 text-blue-700 border-blue-200 dark:bg-blue-950/40 dark:text-blue-300"
                              }`}
                            >
                              {evt.is_internal ? "Internal Action" : "Candidate Milestone"}
                            </span>
                          </div>

                          <span className="text-[11px] font-mono text-slate-400">
                            {new Date(evt.timestamp).toLocaleString()}
                          </span>
                        </div>

                        {evt.description && (
                          <p className="text-slate-600 dark:text-slate-400 leading-relaxed whitespace-pre-line">
                            {evt.description}
                          </p>
                        )}

                        {evt.actor_name && (
                          <div className="text-[11px] text-slate-400 flex items-center gap-1 pt-0.5">
                            <span>By:</span>
                            <span className="font-semibold text-slate-600 dark:text-slate-300">
                              {evt.actor_name}
                            </span>
                            {evt.actor_role && (
                              <span className="capitalize">({evt.actor_role.replace("_", " ")})</span>
                            )}
                          </div>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

        {/* Right Column (1 Col): Application Context & Screening */}
        <div className="space-y-6">
          {/* Current Application Summary */}
          {appCtx && (
            <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3">
              <div className="flex items-center gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
                <Briefcase className="w-4 h-4 text-blue-600" />
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                  Application Context
                </h3>
              </div>

              <div className="space-y-2.5 text-xs">
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
                  <span className="text-slate-500">Stage:</span>
                  <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-blue-50 text-blue-700 border border-blue-200 capitalize">
                    {appCtx.status.replace(/_/g, " ")}
                  </span>
                </div>

                <div className="flex justify-between">
                  <span className="text-slate-500">Applied Date:</span>
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

          {/* AI Screening Assessment Status (No fake scores) */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-2">
            <div className="flex items-center gap-2 pb-2 border-b border-slate-100 dark:border-slate-800">
              <Sparkles className="w-4 h-4 text-purple-600" />
              <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300">
                AI Screening Assessment
              </h3>
            </div>
            <p className="text-xs text-slate-500 leading-relaxed">
              Automated skill matching and semantic screening will execute when AI pipeline inference is activated for this vacancy. No invented match scores are displayed.
            </p>
            <div className="pt-1">
              <span className="inline-flex items-center gap-1 text-[11px] px-2.5 py-1 rounded-lg bg-purple-50 dark:bg-purple-950/40 text-purple-700 dark:text-purple-300 border border-purple-200 dark:border-purple-900/50 font-medium">
                Status: Pending Model Inference
              </span>
            </div>
          </div>

          {/* Candidate Skills */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3">
            <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600 dark:text-slate-300 pb-2 border-b border-slate-100 dark:border-slate-800">
              Verified & Extracted Skills
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {candidate.skills.length === 0 ? (
                <span className="text-xs text-slate-400 italic">No skills extracted.</span>
              ) : (
                candidate.skills.map((skill) => (
                  <span
                    key={skill}
                    className="px-2.5 py-1 rounded-lg text-xs font-medium bg-blue-50 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300 border border-blue-100 dark:border-blue-900/40"
                  >
                    {skill}
                  </span>
                ))
              )}
            </div>
          </div>

          {/* Organization Application History */}
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 p-5 shadow-sm space-y-3">
            <div className="flex items-center justify-between pb-2 border-b border-slate-100 dark:border-slate-800">
              <div className="flex items-center gap-1.5 text-xs font-bold text-slate-700 dark:text-slate-300">
                <History className="w-3.5 h-3.5 text-purple-600" />
                <span>Organization History</span>
              </div>
              <span className="text-[11px] text-slate-400 font-mono">
                {candidate.organization_application_history.length} record(s)
              </span>
            </div>

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
