"use client";

import React, { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import {
  Kanban,
  Search,
  Filter,
  RefreshCw,
  ArrowRight,
  History,
  CheckSquare,
  Square,
  AlertCircle,
  Clock,
  Sparkles,
  User,
  Briefcase,
  X,
  ExternalLink,
  ChevronRight,
  ShieldAlert,
  Info,
} from "lucide-react";
import { hrApi } from "@/lib/hrApi";
import type {
  ApplicationStageHistoryItem,
  JobRequisition,
  PipelineBoardResponse,
  PipelineCardItem,
  PipelineStageColumn,
  PipelineStageConfig,
  TeamMemberOption,
} from "@/types/hr";

// Permitted transition rules matching backend FSM
const PIPELINE_TRANSITION_RULES: Record<string, string[]> = {
  applied: ["resume_review", "screening", "rejected", "withdrawn"],
  resume_review: ["screening", "shortlisted", "rejected", "withdrawn"],
  screening: ["shortlisted", "assessment", "interview", "rejected", "withdrawn"],
  shortlisted: ["assessment", "interview", "offer", "rejected", "withdrawn"],
  assessment: ["interview", "final_interview", "shortlisted", "rejected", "withdrawn"],
  interview: ["final_interview", "assessment", "offer", "rejected", "withdrawn"],
  final_interview: ["offer", "interview", "rejected", "withdrawn"],
  offer: ["hired", "rejected", "withdrawn"],
  hired: [],
  withdrawn: [],
  rejected: ["screening", "resume_review", "shortlisted"],
};

export default function HrPipelinePage() {
  const [boardData, setBoardData] = useState<PipelineBoardResponse | null>(null);
  const [stagesConfig, setStagesConfig] = useState<PipelineStageConfig[]>([]);
  const [jobs, setJobs] = useState<JobRequisition[]>([]);
  const [teamMembers, setTeamMembers] = useState<TeamMemberOption[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedJobId, setSelectedJobId] = useState<string>("");
  const [selectedRecruiterId, setSelectedRecruiterId] = useState<string>("");
  const [search, setSearch] = useState<string>("");

  // Bulk Mode & Selection
  const [bulkMode, setBulkMode] = useState(false);
  const [selectedAppIds, setSelectedAppIds] = useState<string[]>([]);
  const [showBulkModal, setShowBulkModal] = useState(false);
  const [bulkTargetStage, setBulkTargetStage] = useState("");
  const [bulkReason, setBulkReason] = useState("");
  const [bulkSubmitting, setBulkSubmitting] = useState(false);
  const [bulkResult, setBulkResult] = useState<{
    updated_count: number;
    skipped_count: number;
    skipped: { candidate_name?: string | null; reason: string }[];
  } | null>(null);

  // Single Move Modal
  const [activeCard, setActiveCard] = useState<PipelineCardItem | null>(null);
  const [targetStage, setTargetStage] = useState("");
  const [moveReason, setMoveReason] = useState("");
  const [moveNotes, setMoveNotes] = useState("");
  const [moving, setMoving] = useState(false);
  const [moveError, setMoveError] = useState<string | null>(null);

  // History Drawer/Modal
  const [historyCard, setHistoryCard] = useState<PipelineCardItem | null>(null);
  const [stageHistory, setStageHistory] = useState<ApplicationStageHistoryItem[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [historyError, setHistoryError] = useState<string | null>(null);

  // Load initial dropdown options
  useEffect(() => {
    async function loadInitial() {
      try {
        const [jobsRes, membersRes, stagesRes] = await Promise.all([
          hrApi.listJobs({ page_size: 100 }),
          hrApi.getTeamMembers().catch(() => []),
          hrApi.getPipelineStages().catch(() => []),
        ]);
        setJobs(jobsRes.items || []);
        setTeamMembers(membersRes || []);
        setStagesConfig(stagesRes || []);
      } catch {
        // Fallback gracefully
      }
    }
    loadInitial();
  }, []);

  // Fetch Board
  const loadBoard = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await hrApi.getPipelineBoard({
        job_id: selectedJobId || undefined,
        recruiter_id: selectedRecruiterId || undefined,
        search: search.trim() || undefined,
        limit_per_stage: 50,
      });
      setBoardData(res);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load recruitment pipeline");
    } finally {
      setLoading(false);
    }
  }, [selectedJobId, selectedRecruiterId, search]);

  useEffect(() => {
    loadBoard();
  }, [loadBoard]);

  // Handle single move modal open
  const openMoveModal = (card: PipelineCardItem) => {
    setActiveCard(card);
    const validNext = PIPELINE_TRANSITION_RULES[card.stage] || [];
    setTargetStage(validNext[0] || "");
    setMoveReason("");
    setMoveNotes("");
    setMoveError(null);
  };

  // Execute single transition
  const handleStageTransition = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!activeCard || !targetStage) return;

    if (targetStage === "rejected" && !moveReason.trim()) {
      setMoveError("A rejection reason is mandatory when rejecting a candidate.");
      return;
    }

    try {
      setMoving(true);
      setMoveError(null);
      await hrApi.transitionApplicationStage(activeCard.application_id, {
        target_stage: targetStage,
        expected_stage_version: activeCard.stage_version,
        reason: moveReason.trim() || null,
        notes: moveNotes.trim() || null,
      });
      setActiveCard(null);
      await loadBoard();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to transition candidate stage";
      setMoveError(msg);
    } finally {
      setMoving(false);
    }
  };

  // Open Stage History
  const openHistory = async (card: PipelineCardItem) => {
    setHistoryCard(card);
    setHistoryLoading(true);
    setHistoryError(null);
    try {
      const history = await hrApi.getApplicationStageHistory(card.application_id);
      setStageHistory(history);
    } catch (err) {
      setHistoryError(err instanceof Error ? err.message : "Failed to load stage history");
    } finally {
      setHistoryLoading(false);
    }
  };

  // Bulk Selection
  const toggleSelectCard = (appId: string) => {
    setSelectedAppIds((prev) =>
      prev.includes(appId) ? prev.filter((id) => id !== appId) : [...prev, appId]
    );
  };

  const handleBulkMoveSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!bulkTargetStage || selectedAppIds.length === 0) return;

    if (bulkTargetStage === "rejected" && !bulkReason.trim()) {
      alert("A rejection reason is mandatory when bulk-rejecting candidates.");
      return;
    }

    try {
      setBulkSubmitting(true);
      const res = await hrApi.bulkStageMove({
        application_ids: selectedAppIds,
        target_stage: bulkTargetStage,
        reason: bulkReason.trim() || null,
      });
      setBulkResult({
        updated_count: res.updated_count,
        skipped_count: res.skipped_count,
        skipped: res.skipped || [],
      });
      setSelectedAppIds([]);
      await loadBoard();
    } catch (err) {
      alert(err instanceof Error ? err.message : "Failed to perform bulk stage move");
    } finally {
      setBulkSubmitting(false);
    }
  };

  // Stage name lookup
  const getStageLabel = (stageId: string): string => {
    const config = stagesConfig.find((s) => s.id === stageId);
    if (config) return config.label;
    const fromBoard = boardData?.stages.find((s) => s.id === stageId);
    if (fromBoard) return fromBoard.label;
    return stageId
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
              Recruitment Pipeline
            </h1>
            <span className="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-indigo-50 dark:bg-indigo-950/60 text-indigo-700 dark:text-indigo-300 border border-indigo-200/50 dark:border-indigo-800">
              {boardData?.total_candidates ?? 0} Active Candidates
            </span>
          </div>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
            Kanban workflow board with finite state machine validation, optimistic locking, and audit trails.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={() => {
              setBulkMode(!bulkMode);
              setSelectedAppIds([]);
            }}
            className={`inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg border transition-colors shadow-sm ${
              bulkMode
                ? "bg-indigo-50 border-indigo-300 text-indigo-700 dark:bg-indigo-950/50 dark:border-indigo-700 dark:text-indigo-200"
                : "bg-white border-slate-300 text-slate-700 hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700"
            }`}
          >
            <CheckSquare className="w-4 h-4 text-indigo-500" />
            {bulkMode ? "Exit Bulk Mode" : "Bulk Select"}
          </button>

          <button
            type="button"
            onClick={() => loadBoard()}
            disabled={loading}
            className="inline-flex items-center gap-2 px-3.5 py-2 text-sm font-medium rounded-lg bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 dark:bg-slate-800 dark:border-slate-700 dark:text-slate-200 dark:hover:bg-slate-700 shadow-sm"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      {/* Filter Toolbar */}
      <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-4 shadow-sm space-y-3">
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          {/* Candidate Search */}
          <div className="relative">
            <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400" />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search candidate name, role..."
              className="w-full pl-9 pr-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 placeholder:text-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500"
            />
          </div>

          {/* Job Requisition Filter */}
          <div className="relative">
            <Briefcase className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <select
              value={selectedJobId}
              onChange={(e) => setSelectedJobId(e.target.value)}
              className="w-full pl-9 pr-8 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 appearance-none"
            >
              <option value="">All Job Requisitions</option>
              {jobs.map((job) => (
                <option key={job.id} value={job.id}>
                  {job.title} ({job.department})
                </option>
              ))}
            </select>
          </div>

          {/* Recruiter Filter */}
          <div className="relative">
            <User className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-slate-400 pointer-events-none" />
            <select
              value={selectedRecruiterId}
              onChange={(e) => setSelectedRecruiterId(e.target.value)}
              className="w-full pl-9 pr-8 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500 appearance-none"
            >
              <option value="">All Recruiters</option>
              {teamMembers.map((member) => (
                <option key={member.id} value={member.id}>
                  {member.name} ({member.email})
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Bulk Action Bar (when active) */}
        {bulkMode && (
          <div className="pt-3 border-t border-slate-100 dark:border-slate-800 flex items-center justify-between">
            <span className="text-sm font-medium text-slate-700 dark:text-slate-300">
              {selectedAppIds.length} candidate{selectedAppIds.length === 1 ? "" : "s"} selected
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                disabled={selectedAppIds.length === 0}
                onClick={() => {
                  setBulkTargetStage("screening");
                  setBulkReason("");
                  setBulkResult(null);
                  setShowBulkModal(true);
                }}
                className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-sm"
              >
                Move Selected Candidates ({selectedAppIds.length})
              </button>
              {selectedAppIds.length > 0 && (
                <button
                  type="button"
                  onClick={() => setSelectedAppIds([])}
                  className="px-2 py-1 text-xs text-slate-500 hover:text-slate-700 dark:text-slate-400"
                >
                  Clear Selection
                </button>
              )}
            </div>
          </div>
        )}
      </div>

      {/* Error state */}
      {error && (
        <div className="p-4 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-800 dark:text-rose-200 flex items-center gap-3">
          <AlertCircle className="w-5 h-5 flex-shrink-0 text-rose-600 dark:text-rose-400" />
          <p className="text-sm">{error}</p>
        </div>
      )}

      {/* Kanban Board Canvas */}
      <div className="overflow-x-auto pb-6">
        <div className="inline-flex gap-4 min-w-full items-start">
          {loading && !boardData ? (
            <div className="w-full py-16 text-center text-slate-500 dark:text-slate-400">
              <RefreshCw className="w-6 h-6 animate-spin mx-auto mb-2 text-indigo-600" />
              Loading recruitment pipeline board...
            </div>
          ) : boardData?.stages && boardData.stages.length > 0 ? (
            boardData.stages.map((column: PipelineStageColumn) => (
              <div
                key={column.id}
                className="w-80 flex-shrink-0 bg-slate-100/70 dark:bg-slate-900/60 rounded-xl border border-slate-200 dark:border-slate-800 flex flex-col max-h-[calc(100vh-280px)]"
              >
                {/* Column Header */}
                <div className="p-3.5 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-white dark:bg-slate-900 rounded-t-xl">
                  <div className="flex items-center gap-2">
                    <span
                      className={`w-2.5 h-2.5 rounded-full ${
                        column.id === "hired"
                          ? "bg-emerald-500"
                          : column.id === "rejected" || column.id === "withdrawn"
                          ? "bg-rose-500"
                          : column.id === "offer"
                          ? "bg-purple-500"
                          : "bg-indigo-500"
                      }`}
                    />
                    <h3 className="text-sm font-semibold text-slate-900 dark:text-white">
                      {column.label}
                    </h3>
                  </div>
                  <span className="px-2 py-0.5 rounded-full text-xs font-semibold bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-300">
                    {column.count}
                  </span>
                </div>

                {/* Card List */}
                <div className="p-2 space-y-2.5 overflow-y-auto flex-1">
                  {column.cards.length === 0 ? (
                    <div className="py-8 text-center text-xs text-slate-400 dark:text-slate-500">
                      No applications in this stage
                    </div>
                  ) : (
                    column.cards.map((card) => {
                      const isSelected = selectedAppIds.includes(card.application_id);
                      const isTerminal =
                        card.stage === "hired" || card.stage === "withdrawn";

                      return (
                        <div
                          key={card.application_id}
                          className={`bg-white dark:bg-slate-800/90 rounded-lg p-3 border shadow-sm transition-all hover:shadow hover:border-indigo-300 dark:hover:border-indigo-700 ${
                            isSelected
                              ? "border-indigo-500 ring-2 ring-indigo-500/20 bg-indigo-50/20 dark:bg-indigo-950/20"
                              : "border-slate-200 dark:border-slate-700/80"
                          }`}
                        >
                          {/* Card Top Row: Checkbox or Stage Version & History */}
                          <div className="flex items-center justify-between mb-2">
                            {bulkMode ? (
                              <button
                                type="button"
                                disabled={isTerminal}
                                onClick={() => toggleSelectCard(card.application_id)}
                                className={`text-slate-400 hover:text-indigo-600 ${
                                  isTerminal ? "opacity-30 cursor-not-allowed" : ""
                                }`}
                              >
                                {isSelected ? (
                                  <CheckSquare className="w-4 h-4 text-indigo-600" />
                                ) : (
                                  <Square className="w-4 h-4" />
                                )}
                              </button>
                            ) : (
                              <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-700/70 text-slate-500 dark:text-slate-400">
                                v{card.stage_version}
                              </span>
                            )}

                            <div className="flex items-center gap-1">
                              <button
                                type="button"
                                onClick={() => openHistory(card)}
                                title="View transition audit history"
                                className="p-1 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200 rounded hover:bg-slate-100 dark:hover:bg-slate-700"
                              >
                                <History className="w-3.5 h-3.5" />
                              </button>
                            </div>
                          </div>

                          {/* Candidate Link & Info */}
                          <Link
                            href={`/hr/candidates/${card.candidate_id}?applicationId=${card.application_id}`}
                            className="block group"
                          >
                            <h4 className="text-sm font-semibold text-slate-900 dark:text-white group-hover:text-indigo-600 dark:group-hover:text-indigo-400 transition-colors flex items-center justify-between">
                              <span>{card.candidate_name}</span>
                              <ChevronRight className="w-3.5 h-3.5 text-slate-300 group-hover:text-indigo-500 opacity-0 group-hover:opacity-100 transition-all" />
                            </h4>
                          </Link>

                          {card.candidate_headline && (
                            <p className="text-xs text-slate-500 dark:text-slate-400 truncate mt-0.5">
                              {card.candidate_headline}
                            </p>
                          )}

                          {/* Job & Department */}
                          <div className="mt-2 text-xs font-medium text-slate-700 dark:text-slate-300 bg-slate-50 dark:bg-slate-800 px-2 py-1 rounded flex items-center justify-between">
                            <span className="truncate">{card.job_title}</span>
                            <span className="text-[10px] text-slate-400 ml-1">
                              {card.job_department}
                            </span>
                          </div>

                          {/* Skills Pills */}
                          {card.skills && card.skills.length > 0 && (
                            <div className="flex flex-wrap gap-1 mt-2">
                              {card.skills.slice(0, 3).map((skill) => (
                                <span
                                  key={skill}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-50 dark:bg-indigo-950/50 text-indigo-700 dark:text-indigo-300 font-medium"
                                >
                                  {skill}
                                </span>
                              ))}
                              {card.skills.length > 3 && (
                                <span className="text-[10px] text-slate-400 self-center">
                                  +{card.skills.length - 3}
                                </span>
                              )}
                            </div>
                          )}

                          {/* Card Footer: Recruiter & Action */}
                          <div className="mt-3 pt-2.5 border-t border-slate-100 dark:border-slate-700/60 flex items-center justify-between text-xs">
                            <div className="text-[11px] text-slate-500 dark:text-slate-400 truncate max-w-[140px]">
                              {card.recruiter_name ? (
                                <span className="flex items-center gap-1">
                                  <User className="w-3 h-3 text-slate-400" />
                                  {card.recruiter_name}
                                </span>
                              ) : (
                                <span className="text-slate-400 italic">Unassigned</span>
                              )}
                            </div>

                            {!isTerminal ? (
                              <button
                                type="button"
                                onClick={() => openMoveModal(card)}
                                className="inline-flex items-center gap-1 px-2 py-1 text-xs font-medium text-indigo-600 hover:text-indigo-700 dark:text-indigo-400 hover:bg-indigo-50 dark:hover:bg-indigo-950/40 rounded transition-colors"
                              >
                                <span>Move</span>
                                <ArrowRight className="w-3 h-3" />
                              </button>
                            ) : (
                              <span className="text-[10px] font-semibold text-slate-400 uppercase tracking-wider">
                                {card.stage}
                              </span>
                            )}
                          </div>
                        </div>
                      );
                    })
                  )}
                </div>
              </div>
            ))
          ) : (
            <div className="w-full py-16 text-center text-slate-500 dark:text-slate-400">
              No pipeline columns found for this organization.
            </div>
          )}
        </div>
      </div>

      {/* SINGLE STAGE TRANSITION MODAL */}
      {activeCard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-md w-full border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white">
                  Move Application Stage
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {activeCard.candidate_name} &bull; {activeCard.job_title}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setActiveCard(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <form noValidate onSubmit={handleStageTransition} className="p-5 space-y-4">
              {/* Current Stage Banner */}
              <div className="p-3 bg-slate-50 dark:bg-slate-800 rounded-xl text-xs flex items-center justify-between">
                <span className="text-slate-500 dark:text-slate-400">Current Stage:</span>
                <span className="font-semibold text-slate-800 dark:text-slate-200 uppercase">
                  {getStageLabel(activeCard.stage)} (v{activeCard.stage_version})
                </span>
              </div>

              {/* Target Stage Selector */}
              <div>
                <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                  Target Stage *
                </label>
                <select
                  data-testid="target-stage-select"
                  value={targetStage}
                  onChange={(e) => setTargetStage(e.target.value)}
                  className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                >
                  {stagesConfig.map((stage) => {
                    const isPermitted = (PIPELINE_TRANSITION_RULES[activeCard.stage] || []).includes(
                      stage.id
                    );
                    return (
                      <option key={stage.id} value={stage.id}>
                        {stage.label} {isPermitted ? "(Permitted)" : "(Transition Restricted)"}
                      </option>
                    );
                  })}
                </select>
              </div>

              {/* Authority Notice for Offer/Hired */}
              {(targetStage === "offer" || targetStage === "hired") && (
                <div className="p-3 rounded-lg bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 text-amber-800 dark:text-amber-300 text-xs flex items-start gap-2">
                  <ShieldAlert className="w-4 h-4 flex-shrink-0 mt-0.5 text-amber-600 dark:text-amber-400" />
                  <span>
                    Moving to <strong>Offer</strong> or <strong>Hired</strong> requires Hiring Manager or Organization Admin authority.
                  </span>
                </div>
              )}

              {/* Mandatory Rejection Reason */}
              {targetStage === "rejected" && (
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-rose-600 dark:text-rose-400 mb-1.5">
                    Rejection Reason * (Mandatory)
                  </label>
                  <textarea
                    rows={3}
                    required
                    value={moveReason}
                    onChange={(e) => setMoveReason(e.target.value)}
                    placeholder="Provide specific feedback or qualification reason for this rejection..."
                    className="w-full px-3 py-2 text-sm rounded-lg border border-rose-300 dark:border-rose-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-rose-500"
                  />
                  <p className="text-[11px] text-slate-400 mt-1">
                    Internal record. The candidate will see status &quot;Not Selected&quot; without confidential feedback.
                  </p>
                </div>
              )}

              {/* Optional Notes */}
              {targetStage !== "rejected" && (
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                    Internal Stage Notes (Optional)
                  </label>
                  <textarea
                    rows={2}
                    value={moveNotes}
                    onChange={(e) => setMoveNotes(e.target.value)}
                    placeholder="Optional notes for recruiter team or hiring manager..."
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  />
                </div>
              )}

              {/* Error Alert */}
              {moveError && (
                <div className="p-3 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-800 text-rose-700 dark:text-rose-300 text-xs flex items-center gap-2">
                  <AlertCircle className="w-4 h-4 flex-shrink-0 text-rose-500" />
                  <span>{moveError}</span>
                </div>
              )}

              {/* Form Buttons */}
              <div className="flex items-center justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setActiveCard(null)}
                  className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 dark:text-slate-300"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={moving || !targetStage}
                  className="px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 disabled:cursor-not-allowed shadow-sm flex items-center gap-2"
                >
                  {moving ? (
                    <>
                      <RefreshCw className="w-4 h-4 animate-spin" />
                      Updating...
                    </>
                  ) : (
                    <>
                      Confirm Transition
                      <ArrowRight className="w-4 h-4" />
                    </>
                  )}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* BULK STAGE MOVE MODAL */}
      {showBulkModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white">
                  Bulk Move Applications
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  Safely transitioning {selectedAppIds.length} candidate applications
                </p>
              </div>
              <button
                type="button"
                onClick={() => {
                  setShowBulkModal(false);
                  setBulkResult(null);
                }}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {bulkResult ? (
              <div className="p-5 space-y-4">
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800 text-xs space-y-2">
                  <div className="flex items-center justify-between font-semibold">
                    <span>Successfully Moved:</span>
                    <span className="text-emerald-600 dark:text-emerald-400 text-sm">
                      {bulkResult.updated_count}
                    </span>
                  </div>
                  <div className="flex items-center justify-between font-semibold">
                    <span>Skipped / Ineligible:</span>
                    <span className="text-amber-600 dark:text-amber-400 text-sm">
                      {bulkResult.skipped_count}
                    </span>
                  </div>
                </div>

                {bulkResult.skipped.length > 0 && (
                  <div className="space-y-1.5 max-h-48 overflow-y-auto">
                    <h5 className="text-xs font-semibold text-slate-700 dark:text-slate-300">
                      Skipped Details:
                    </h5>
                    {bulkResult.skipped.map((s, idx) => (
                      <div
                        key={idx}
                        className="p-2 rounded bg-amber-50 dark:bg-amber-950/30 text-amber-900 dark:text-amber-200 text-xs flex justify-between"
                      >
                        <span className="font-medium">{s.candidate_name || "Applicant"}</span>
                        <span className="text-[11px] opacity-80">{s.reason}</span>
                      </div>
                    ))}
                  </div>
                )}

                <div className="pt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={() => {
                      setShowBulkModal(false);
                      setBulkResult(null);
                    }}
                    className="px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 text-white hover:bg-indigo-700"
                  >
                    Done
                  </button>
                </div>
              </div>
            ) : (
              <form onSubmit={handleBulkMoveSubmit} className="p-5 space-y-4">
                <div>
                  <label className="block text-xs font-semibold uppercase tracking-wider text-slate-500 dark:text-slate-400 mb-1.5">
                    Target Pipeline Stage *
                  </label>
                  <select
                    data-testid="bulk-stage-select"
                    value={bulkTargetStage}
                    onChange={(e) => setBulkTargetStage(e.target.value)}
                    className="w-full px-3 py-2 text-sm rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-indigo-500"
                  >
                    {stagesConfig.map((stage) => (
                      <option key={stage.id} value={stage.id}>
                        {stage.label}
                      </option>
                    ))}
                  </select>
                </div>

                {bulkTargetStage === "rejected" && (
                  <div>
                    <label className="block text-xs font-semibold uppercase tracking-wider text-rose-600 dark:text-rose-400 mb-1.5">
                      Rejection Reason * (Mandatory for Bulk Rejection)
                    </label>
                    <textarea
                      rows={3}
                      required
                      value={bulkReason}
                      onChange={(e) => setBulkReason(e.target.value)}
                      placeholder="Explain reasons for batch candidate rejection..."
                      className="w-full px-3 py-2 text-sm rounded-lg border border-rose-300 dark:border-rose-700 bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 focus:outline-none focus:ring-2 focus:ring-rose-500"
                    />
                  </div>
                )}

                <div className="p-3 bg-blue-50 dark:bg-blue-950/40 rounded-xl text-xs text-blue-800 dark:text-blue-300 flex items-start gap-2">
                  <Info className="w-4 h-4 flex-shrink-0 mt-0.5" />
                  <span>
                    Each selected application is verified against FSM rules. Ineligible candidates (e.g. withdrawn, terminal, or invalid transitions) are automatically skipped safely.
                  </span>
                </div>

                <div className="flex items-center justify-end gap-2 pt-2">
                  <button
                    type="button"
                    onClick={() => setShowBulkModal(false)}
                    className="px-4 py-2 text-sm font-medium text-slate-600 hover:text-slate-800 dark:text-slate-300"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={bulkSubmitting || !bulkTargetStage}
                    className="px-4 py-2 text-sm font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-700 text-white disabled:opacity-50 disabled:cursor-not-allowed shadow-sm flex items-center gap-2"
                  >
                    {bulkSubmitting ? (
                      <>
                        <RefreshCw className="w-4 h-4 animate-spin" />
                        Processing...
                      </>
                    ) : (
                      `Move ${selectedAppIds.length} Applications`
                    )}
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* STAGE HISTORY AUDIT DRAWER / MODAL */}
      {historyCard && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/50 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-white dark:bg-slate-900 rounded-2xl max-w-lg w-full border border-slate-200 dark:border-slate-800 shadow-xl overflow-hidden">
            <div className="p-5 border-b border-slate-100 dark:border-slate-800 flex items-center justify-between">
              <div>
                <h3 className="font-semibold text-slate-900 dark:text-white flex items-center gap-2">
                  <History className="w-4 h-4 text-indigo-500" />
                  Stage Transition Audit History
                </h3>
                <p className="text-xs text-slate-500 dark:text-slate-400 mt-0.5">
                  {historyCard.candidate_name} &bull; {historyCard.job_title}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setHistoryCard(null)}
                className="text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 max-h-96 overflow-y-auto">
              {historyLoading ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  <RefreshCw className="w-5 h-5 animate-spin mx-auto mb-2 text-indigo-600" />
                  Loading transition audit logs...
                </div>
              ) : historyError ? (
                <div className="p-3 text-xs text-rose-600 bg-rose-50 dark:bg-rose-950/40 rounded-lg">
                  {historyError}
                </div>
              ) : stageHistory.length === 0 ? (
                <div className="py-8 text-center text-xs text-slate-400">
                  No historical stage transitions recorded for this application yet.
                </div>
              ) : (
                <div className="space-y-4">
                  {stageHistory.map((entry) => (
                    <div
                      key={entry.id}
                      className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-800/40 text-xs space-y-1.5"
                    >
                      <div className="flex items-center justify-between text-slate-500 dark:text-slate-400">
                        <span className="flex items-center gap-1 font-mono text-[11px]">
                          <Clock className="w-3 h-3" />
                          {new Date(entry.created_at).toLocaleString()}
                        </span>
                        <span className="font-medium text-slate-700 dark:text-slate-300">
                          {entry.actor_name || "System"} ({entry.actor_role || "recruiter"})
                        </span>
                      </div>

                      <div className="flex items-center gap-2 font-semibold">
                        <span className="text-slate-600 dark:text-slate-400">
                          {getStageLabel(entry.previous_stage)}
                        </span>
                        <ArrowRight className="w-3.5 h-3.5 text-slate-400" />
                        <span className="text-indigo-600 dark:text-indigo-400">
                          {getStageLabel(entry.new_stage)}
                        </span>
                      </div>

                      {entry.reason && (
                        <p className="text-slate-600 dark:text-slate-300 pt-1 border-t border-slate-200/60 dark:border-slate-700/60">
                          <span className="font-medium text-slate-500">Reason:</span>{" "}
                          {entry.reason}
                        </p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-100 dark:border-slate-800 bg-slate-50 dark:bg-slate-900 flex justify-end">
              <button
                type="button"
                onClick={() => setHistoryCard(null)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-white border border-slate-300 dark:bg-slate-800 dark:border-slate-700 text-slate-700 dark:text-slate-200 hover:bg-slate-50"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
