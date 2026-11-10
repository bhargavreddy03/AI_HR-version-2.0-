import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import CandidateDetailPage from "@/app/hr/candidates/[id]/page";
import { hrApi } from "@/lib/hrApi";
import type {
  CandidateActivityTimelineResponse,
  CandidateDetailResponse,
  InternalNoteResponse,
  RecruitmentTaskResponse,
  ReviewFeedbackResponse,
  TeamMemberOption,
} from "@/types/hr";

const mockPush = vi.fn();
vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "cand-1111" }),
  useSearchParams: () => ({
    get: (key: string) => (key === "applicationId" ? "app-1111" : null),
  }),
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

const mockCandidate: CandidateDetailResponse = {
  candidate_id: "cand-1111",
  first_name: "Jane",
  last_name: "Doe",
  full_name: "Jane Doe",
  email: "jane.doe@example.com",
  phone_number: "+1 555-0199",
  headline: "Principal Systems Architect",
  bio: "Experienced distributed systems and cloud infrastructure specialist.",
  location_city: "Seattle",
  location_country: "United States",
  preferred_title: "Staff Engineer",
  work_authorization: "US Citizen",
  portfolio_urls: ["https://janedoe.dev"],
  skills: ["Python", "FastAPI", "Kubernetes", "PostgreSQL"],
  experience_years: 9,
  experiences: [
    {
      id: "exp-1",
      company_name: "CloudTech Systems",
      job_title: "Senior Backend Engineer",
      location: "Seattle, WA",
      start_date: "2021-01",
      end_date: null,
      is_current: true,
      description: "Architected event-driven microservices serving 10M requests daily.",
      skills: ["Python", "Kafka"],
    },
  ],
  educations: [
    {
      id: "edu-1",
      institution: "University of Washington",
      degree: "B.S.",
      field_of_study: "Computer Science",
      start_year: 2012,
      end_year: 2016,
    },
  ],
  certifications: [
    {
      id: "cert-1",
      name: "AWS Certified Solutions Architect",
      issuing_organization: "Amazon Web Services",
      issue_date: "2022-03",
      expiration_date: null,
    },
  ],
  projects: [
    {
      id: "proj-1",
      title: "Distributed Cache Mesh",
      description: "Low-latency in-memory cache proxy written in Rust.",
      role: "Lead Author",
      project_url: "https://github.com/janedoe/cache-mesh",
      skills: ["Rust", "Redis", "Distributed Systems"],
    },
  ],
  languages: [],
  current_application: {
    application_id: "app-1111",
    job_id: "job-101",
    job_title: "Principal Cloud Architect",
    job_department: "Engineering",
    job_location: "Remote, US",
    status: "screening",
    candidate_status: "under_review",
    applied_at: "2026-10-01T10:00:00Z",
    resume_snapshot_sha256: "abc123sha",
    recruiter_name: "Alice Recruiter",
    cover_letter: "Excited to contribute to next-gen cloud services.",
    answers: {},
    internal_timeline: [],
    candidate_timeline: [],
  },
  organization_application_history: [
    {
      application_id: "app-1111",
      job_id: "job-101",
      job_title: "Principal Cloud Architect",
      department: "Engineering",
      status: "screening",
      candidate_status: "under_review",
      applied_at: "2026-10-01T10:00:00Z",
    },
  ],
};

const mockNotes: InternalNoteResponse[] = [
  {
    id: "note-1",
    candidate_id: "cand-1111",
    application_id: "app-1111",
    author_id: "user-rec-1",
    author_name: "Alice Recruiter",
    author_role: "recruiter",
    content: "Strong candidate with comprehensive distributed systems design background.",
    category: "screening",
    is_confidential: false,
    can_edit: true,
    created_at: "2026-10-02T14:30:00Z",
    updated_at: "2026-10-02T14:30:00Z",
  },
  {
    id: "note-2",
    candidate_id: "cand-1111",
    application_id: "app-1111",
    author_id: "user-admin-1",
    author_name: "David Admin",
    author_role: "admin",
    content: "Confidential salary range discussion: candidate expects $190k-$210k base.",
    category: "compensation",
    is_confidential: true,
    can_edit: false,
    created_at: "2026-10-03T09:00:00Z",
    updated_at: "2026-10-03T09:00:00Z",
  },
];

const mockReviews: ReviewFeedbackResponse[] = [
  {
    id: "rev-1",
    application_id: "app-1111",
    reviewer_id: "user-hm-1",
    reviewer_name: "Carol Manager",
    reviewer_role: "hiring_manager",
    recommendation: "strong_yes",
    technical_rating: 5,
    communication_rating: 4,
    cultural_rating: 5,
    overall_rating: 5,
    summary: "Exceptional technical depth on distributed systems consensus and fault tolerance.",
    pros: ["Deep distributed consensus knowledge", "Excellent communication"],
    cons: ["Slightly high compensation expectation"],
    created_at: "2026-10-04T16:00:00Z",
    updated_at: "2026-10-04T16:00:00Z",
  },
];

const mockTasks: RecruitmentTaskResponse[] = [
  {
    id: "task-1",
    candidate_id: "cand-1111",
    application_id: "app-1111",
    creator_id: "user-rec-1",
    creator_name: "Alice Recruiter",
    assignee_id: "user-hm-1",
    assignee_name: "Carol Manager",
    title: "Conduct 45-min system design panel interview",
    description: "Focus on Kubernetes scaling and multi-region failover",
    task_type: "schedule_interview",
    due_date: "2026-10-10T18:00:00Z",
    is_completed: false,
    completed_at: null,
    created_at: "2026-10-02T15:00:00Z",
    updated_at: "2026-10-02T15:00:00Z",
  },
];

const mockTimeline: CandidateActivityTimelineResponse = {
  candidate_id: "cand-1111",
  application_id: "app-1111",
  events: [
    {
      id: "evt-1",
      event_type: "application_submitted",
      title: "Application Submitted",
      description: "Submitted application for Principal Cloud Architect (Engineering)",
      actor_name: "Candidate",
      actor_role: "candidate",
      is_internal: false,
      timestamp: "2026-10-01T10:00:00Z",
    },
    {
      id: "evt-2",
      event_type: "stage_transition",
      title: "Stage Advanced to Screening",
      description: "Moved from Applied to Screening. Reason: Met technical qualifications",
      actor_name: "Alice Recruiter",
      actor_role: "recruiter",
      is_internal: false,
      timestamp: "2026-10-02T11:00:00Z",
    },
    {
      id: "evt-3",
      event_type: "note_added",
      title: "Internal Note Added (Screening)",
      description: "Strong candidate with comprehensive distributed systems design background.",
      actor_name: "Alice Recruiter",
      actor_role: "recruiter",
      is_internal: true,
      timestamp: "2026-10-02T14:30:00Z",
    },
  ],
  total_events: 3,
};

const mockTeamMembers: TeamMemberOption[] = [
  { id: "user-rec-1", name: "Alice Recruiter", email: "alice@acme.com", role: "recruiter" },
  { id: "user-hm-1", name: "Carol Manager", email: "carol@acme.com", role: "hiring_manager" },
];

describe("Step 4.2.8 — Candidate Review & HR Collaboration Workspace", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.spyOn(hrApi, "getCandidateDetails").mockResolvedValue(mockCandidate);
    vi.spyOn(hrApi, "getInternalNotes").mockResolvedValue(mockNotes);
    vi.spyOn(hrApi, "getApplicationReviews").mockResolvedValue(mockReviews);
    vi.spyOn(hrApi, "listRecruitmentTasks").mockResolvedValue(mockTasks);
    vi.spyOn(hrApi, "getCandidateTimeline").mockResolvedValue(mockTimeline);
    vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue(mockTeamMembers);
    vi.spyOn(hrApi, "addInternalNote").mockResolvedValue({
      id: "note-new",
      candidate_id: "cand-1111",
      application_id: "app-1111",
      author_id: "user-rec-1",
      author_name: "Alice Recruiter",
      author_role: "recruiter",
      content: "Fresh recruiter note recorded during screen.",
      category: "screening",
      is_confidential: false,
      can_edit: true,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    vi.spyOn(hrApi, "submitReviewFeedback").mockResolvedValue({
      id: "rev-new",
      application_id: "app-1111",
      reviewer_id: "user-rec-1",
      reviewer_name: "Alice Recruiter",
      reviewer_role: "recruiter",
      recommendation: "strong_yes",
      overall_rating: 5,
      summary: "High hire confidence.",
      pros: ["Quick turnaround"],
      cons: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    vi.spyOn(hrApi, "updateRecruitmentTask").mockResolvedValue({
      ...mockTasks[0],
      is_completed: true,
      completed_at: new Date().toISOString(),
    });
    vi.spyOn(hrApi, "createRecruitmentTask").mockResolvedValue({
      id: "task-new",
      candidate_id: "cand-1111",
      application_id: "app-1111",
      creator_name: "Alice Recruiter",
      title: "Send offer letter package",
      task_type: "send_offer",
      is_completed: false,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders candidate header, profile background and honest AI screening notice without fake scores", async () => {
    render(<CandidateDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Jane Doe")).toBeDefined();
    });

    expect(screen.getByText("Principal Systems Architect")).toBeDefined();
    expect(screen.getByText("Seattle, United States")).toBeDefined();
    expect(screen.getByText("US Citizen")).toBeDefined();
    expect(screen.getByText("9")).toBeDefined(); // Years experience
    expect(screen.getByText("Senior Backend Engineer")).toBeDefined();
    expect(screen.getByText("AWS Certified Solutions Architect")).toBeDefined();

    // Verify AI screening honest reporting (no invented scores)
    expect(screen.getByText("AI Screening Assessment")).toBeDefined();
    expect(
      screen.getByText(/Automated skill matching and semantic screening will execute when AI pipeline inference is activated/i)
    ).toBeDefined();
  });

  it("switches to Internal Notes tab, displays confidential notes and submits a new note", async () => {
    render(<CandidateDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("tab-notes")).toBeDefined();
    });

    // Click Notes Tab
    fireEvent.click(screen.getByTestId("tab-notes"));

    await waitFor(() => {
      expect(screen.getByTestId("notes-list")).toBeDefined();
    });

    // Verify existing notes and confidentiality badges
    expect(screen.getByText(/Strong candidate with comprehensive distributed systems design/i)).toBeDefined();
    expect(screen.getByText(/Confidential salary range discussion/i)).toBeDefined();
    expect(screen.getByText("Confidential")).toBeDefined();

    // Fill and submit new note
    const input = screen.getByTestId("note-content-input");
    fireEvent.change(input, { target: { value: "Candidate demonstrated strong Kubernetes architecture." } });
    fireEvent.click(screen.getByTestId("submit-note-btn"));

    await waitFor(() => {
      expect(hrApi.addInternalNote).toHaveBeenCalledWith("cand-1111", {
        application_id: "app-1111",
        content: "Candidate demonstrated strong Kubernetes architecture.",
        category: "general",
        is_confidential: false,
      });
    });
  });

  it("switches to Evaluations & Scorecards tab, displays scorecards and submits review", async () => {
    render(<CandidateDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("tab-scorecards")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("tab-scorecards"));

    await waitFor(() => {
      expect(screen.getByTestId("scorecards-list")).toBeDefined();
    });

    // Verify existing review
    expect(screen.getByText("Carol Manager")).toBeDefined();
    expect(screen.getByText(/Exceptional technical depth on distributed systems/i)).toBeDefined();
    expect(screen.getAllByText("5 / 5").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("Deep distributed consensus knowledge")).toBeDefined();

    // Toggle Review Form
    fireEvent.click(screen.getByTestId("toggle-review-form-btn"));
    await waitFor(() => {
      expect(screen.getByTestId("submit-scorecard-form")).toBeDefined();
    });

    // Enter summary and submit
    const summaryInput = screen.getByPlaceholderText(/Detailed justification of recommendation/i);
    fireEvent.change(summaryInput, { target: { value: "Exceeds all technical qualifications for the role." } });
    fireEvent.click(screen.getByTestId("submit-scorecard-btn"));

    await waitFor(() => {
      expect(hrApi.submitReviewFeedback).toHaveBeenCalledWith(
        "app-1111",
        expect.objectContaining({
          recommendation: "yes",
          summary: "Exceeds all technical qualifications for the role.",
        })
      );
    });
  });

  it("switches to Recruitment Tasks tab and toggles completion", async () => {
    render(<CandidateDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("tab-tasks")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("tab-tasks"));

    await waitFor(() => {
      expect(screen.getByTestId("tasks-list")).toBeDefined();
    });

    expect(screen.getByText("Conduct 45-min system design panel interview")).toBeDefined();
    expect(screen.getByText("Carol Manager")).toBeDefined();

    // Toggle task completed
    const checkbox = screen.getByTestId("task-checkbox-task-1");
    fireEvent.click(checkbox);

    await waitFor(() => {
      expect(hrApi.updateRecruitmentTask).toHaveBeenCalledWith("task-1", { is_completed: true });
    });
  });

  it("switches to Activity Timeline tab and displays separated internal and candidate events", async () => {
    render(<CandidateDetailPage />);

    await waitFor(() => {
      expect(screen.getByTestId("tab-timeline")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("tab-timeline"));

    await waitFor(() => {
      expect(screen.getByTestId("timeline-list")).toBeDefined();
    });

    expect(screen.getByText("Application Submitted")).toBeDefined();
    expect(screen.getByText("Stage Advanced to Screening")).toBeDefined();
    expect(screen.getByText("Internal Note Added (Screening)")).toBeDefined();

    // Filter to Candidate Facing
    fireEvent.click(screen.getByText(/Candidate Facing/i));
    expect(screen.getByText("Application Submitted")).toBeDefined();
    expect(screen.queryByText("Internal Note Added (Screening)")).toBeNull();

    // Filter to Internal Only
    fireEvent.click(screen.getByText(/Internal Only/i));
    expect(screen.getByText("Internal Note Added (Screening)")).toBeDefined();
    expect(screen.queryByText("Application Submitted")).toBeNull();
  });
});
