import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import HrPipelinePage from "@/app/hr/pipeline/page";
import { hrApi } from "@/lib/hrApi";
import type {
  ApplicationStageHistoryItem,
  JobRequisition,
  PipelineBoardResponse,
  PipelineStageConfig,
  TeamMemberOption,
} from "@/types/hr";

const mockStages: PipelineStageConfig[] = [
  { id: "applied", label: "Applied", order: 1, is_terminal: false },
  { id: "resume_review", label: "Resume Review", order: 2, is_terminal: false },
  { id: "screening", label: "Screening", order: 3, is_terminal: false },
  { id: "shortlisted", label: "Shortlisted", order: 4, is_terminal: false },
  { id: "assessment", label: "Assessment", order: 5, is_terminal: false },
  { id: "interview", label: "Interview", order: 6, is_terminal: false },
  { id: "final_interview", label: "Final Interview", order: 7, is_terminal: false },
  { id: "offer", label: "Offer", order: 8, is_terminal: false },
  { id: "hired", label: "Hired", order: 9, is_terminal: true },
  { id: "rejected", label: "Rejected", order: 10, is_terminal: true },
  { id: "withdrawn", label: "Withdrawn", order: 11, is_terminal: true },
];

const mockJobs: JobRequisition[] = [
  {
    id: "job-1111",
    tenant_id: "org-1",
    title: "Senior Python Platform Engineer",
    department: "Engineering",
    description: "Build robust distributed backend systems.",
    employment_type: "full_time",
    work_arrangement: "remote",
    status: "published",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  },
];

const mockTeam: TeamMemberOption[] = [
  {
    id: "rec-1",
    name: "Alice Recruiter",
    email: "alice@example.com",
    role: "recruiter",
  },
];

const mockBoardResponse: PipelineBoardResponse = {
  tenant_id: "org-1",
  total_candidates: 2,
  active_filters: {},
  stages: [
    {
      id: "applied",
      label: "Applied",
      order: 1,
      is_terminal: false,
      count: 1,
      cards: [
        {
          application_id: "app-101",
          candidate_id: "cand-101",
          candidate_name: "Jane Cloud",
          candidate_email: "jane.cloud@example.com",
          candidate_headline: "Senior Cloud Architect",
          job_id: "job-1111",
          job_title: "Senior Python Platform Engineer",
          job_department: "Engineering",
          stage: "applied",
          stage_version: 1,
          applied_at: "2026-11-05T10:00:00Z",
          last_activity_at: "2026-11-05T10:00:00Z",
          recruiter_id: "rec-1",
          recruiter_name: "Alice Recruiter",
          skills: ["Python", "FastAPI", "Kubernetes"],
          resume_available: true,
        },
      ],
    },
    {
      id: "screening",
      label: "Screening",
      order: 3,
      is_terminal: false,
      count: 1,
      cards: [
        {
          application_id: "app-102",
          candidate_id: "cand-102",
          candidate_name: "Bob Builder",
          candidate_email: "bob.builder@example.com",
          candidate_headline: "DevOps Engineer",
          job_id: "job-1111",
          job_title: "Senior Python Platform Engineer",
          job_department: "Engineering",
          stage: "screening",
          stage_version: 2,
          applied_at: "2026-11-04T12:00:00Z",
          last_activity_at: "2026-11-06T14:00:00Z",
          recruiter_id: null,
          recruiter_name: null,
          skills: ["Docker", "Terraform"],
          resume_available: true,
        },
      ],
    },
    {
      id: "rejected",
      label: "Rejected",
      order: 10,
      is_terminal: true,
      count: 0,
      cards: [],
    },
  ],
};

const mockHistoryResponse: ApplicationStageHistoryItem[] = [
  {
    id: "hist-1",
    application_id: "app-101",
    previous_stage: "applied",
    new_stage: "screening",
    actor_id: "user-recruiter-1",
    actor_name: "Alice Recruiter",
    actor_role: "recruiter",
    reason: "Passed initial resume review",
    audit_metadata: {},
    created_at: "2026-11-06T11:00:00Z",
  },
];

describe("HrPipelinePage Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hrApi, "listJobs").mockResolvedValue({
      items: mockJobs,
      total: 1,
      page: 1,
      page_size: 100,
      pages: 1,
    });
    vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue(mockTeam);
    vi.spyOn(hrApi, "getPipelineStages").mockResolvedValue(mockStages);
    vi.spyOn(hrApi, "getPipelineBoard").mockResolvedValue(mockBoardResponse);
    vi.spyOn(hrApi, "transitionApplicationStage").mockResolvedValue({
      application_id: "app-101",
      previous_stage: "applied",
      new_stage: "resume_review",
      stage_version: 2,
      candidate_status: "in_review",
      changed_at: "2026-11-10T12:00:00Z",
      actor_name: "Alice Recruiter",
      actor_role: "recruiter",
    });
    vi.spyOn(hrApi, "bulkStageMove").mockResolvedValue({
      target_stage: "screening",
      total_requested: 1,
      updated_count: 1,
      updated_ids: ["app-101"],
      skipped_count: 0,
      skipped: [],
    });
    vi.spyOn(hrApi, "getApplicationStageHistory").mockResolvedValue(mockHistoryResponse);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders pipeline board with column headers and candidate cards", async () => {
    render(<HrPipelinePage />);

    expect(screen.getByText("Recruitment Pipeline")).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
      expect(screen.getByText("Bob Builder")).toBeDefined();
    });

    // Check skills
    expect(screen.getByText("Python")).toBeDefined();
    expect(screen.getByText("Kubernetes")).toBeDefined();

    // Check columns
    expect(screen.getAllByText("Applied").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Screening").length).toBeGreaterThanOrEqual(1);
    expect(screen.getAllByText("Rejected").length).toBeGreaterThanOrEqual(1);
  });

  it("filters board by candidate search query", async () => {
    render(<HrPipelinePage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
    });

    const searchInput = screen.getByPlaceholderText("Search candidate name, role...");
    fireEvent.change(searchInput, { target: { value: "Jane" } });

    await waitFor(() => {
      expect(hrApi.getPipelineBoard).toHaveBeenCalledWith(
        expect.objectContaining({ search: "Jane" })
      );
    });
  });

  it("opens stage transition modal and validates mandatory rejection reason", async () => {
    render(<HrPipelinePage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
    });

    // Click Move button on Jane Cloud's card
    const moveButtons = screen.getAllByRole("button", { name: /Move/i });
    fireEvent.click(moveButtons[0]);

    // Modal should be open
    await waitFor(() => {
      expect(screen.getByText("Move Application Stage")).toBeDefined();
    });

    // Select Rejected as target stage
    const select = screen.getByTestId("target-stage-select");
    fireEvent.change(select, { target: { value: "rejected" } });

    // Try submitting without reason
    const submitBtn = screen.getByRole("button", { name: /Confirm Transition/i });
    fireEvent.click(submitBtn);

    // Rejection reason error should show
    await waitFor(() => {
      expect(
        screen.getByText(/A rejection reason is mandatory when rejecting a candidate/i)
      ).toBeDefined();
    });
    expect(hrApi.transitionApplicationStage).not.toHaveBeenCalled();
  });

  it("executes valid stage transition with optimistic locking version", async () => {
    render(<HrPipelinePage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
    });

    const moveButtons = screen.getAllByRole("button", { name: /Move/i });
    fireEvent.click(moveButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Move Application Stage")).toBeDefined();
    });

    // Target stage is resume_review by default or select resume_review
    const select = screen.getByTestId("target-stage-select");
    fireEvent.change(select, { target: { value: "resume_review" } });

    const submitBtn = screen.getByRole("button", { name: /Confirm Transition/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(hrApi.transitionApplicationStage).toHaveBeenCalledWith(
        "app-101",
        expect.objectContaining({
          target_stage: "resume_review",
          expected_stage_version: 1,
        })
      );
    });
  });

  it("handles optimistic concurrency conflict error", async () => {
    vi.spyOn(hrApi, "transitionApplicationStage").mockRejectedValueOnce(
      new Error("Application stage was updated concurrently by another user.")
    );

    render(<HrPipelinePage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
    });

    const moveButtons = screen.getAllByRole("button", { name: /Move/i });
    fireEvent.click(moveButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Move Application Stage")).toBeDefined();
    });

    const submitBtn = screen.getByRole("button", { name: /Confirm Transition/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(
        screen.getByText(/Application stage was updated concurrently by another user/i)
      ).toBeDefined();
    });
  });

  it("opens bulk selection mode, selects cards, and performs bulk stage move", async () => {
    render(<HrPipelinePage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
    });

    // Enter bulk mode
    const bulkToggle = screen.getByRole("button", { name: /Bulk Select/i });
    fireEvent.click(bulkToggle);

    expect(screen.getByText("Exit Bulk Mode")).toBeDefined();

    // Find and click Jane Cloud's checkbox
    const checkboxes = screen.getAllByRole("button").filter((b) =>
      b.querySelector("svg")
    );
    // Click card checkbox
    const cardCheckbox = checkboxes.find(
      (b) => !b.textContent?.includes("Bulk") && !b.textContent?.includes("Refresh")
    );
    if (cardCheckbox) {
      fireEvent.click(cardCheckbox);
    }

    await waitFor(() => {
      expect(screen.getByText(/1 candidate selected/i)).toBeDefined();
    });

    // Open bulk move modal
    const bulkMoveBtn = screen.getByRole("button", {
      name: /Move Selected Candidates/i,
    });
    fireEvent.click(bulkMoveBtn);

    await waitFor(() => {
      expect(screen.getByText("Bulk Move Applications")).toBeDefined();
    });

    // Submit bulk move
    const confirmBulkBtn = screen.getByRole("button", {
      name: /Move 1 Applications/i,
    });
    fireEvent.click(confirmBulkBtn);

    await waitFor(() => {
      expect(hrApi.bulkStageMove).toHaveBeenCalledWith({
        application_ids: ["app-101"],
        target_stage: "screening",
        reason: null,
      });
      expect(screen.getByText("Successfully Moved:")).toBeDefined();
    });
  });

  it("opens audit history drawer and displays stage transitions", async () => {
    render(<HrPipelinePage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Cloud")).toBeDefined();
    });

    const historyButtons = screen.getAllByTitle("View transition audit history");
    fireEvent.click(historyButtons[0]);

    await waitFor(() => {
      expect(screen.getByText("Stage Transition Audit History")).toBeDefined();
      expect(screen.getByText("Passed initial resume review")).toBeDefined();
    });
  });
});
