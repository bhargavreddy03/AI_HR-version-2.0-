import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import JobDetailPage from "@/app/hr/jobs/[id]/page";
import { hrApi } from "@/lib/hrApi";
import type {
  JobLifecycleHistoryItem,
  JobLifecyclePermittedActionsResponse,
  JobLifecycleTransitionResponse,
  JobRequisition,
} from "@/types/hr";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "11111111-2222-3333-4444-555555555555" }),
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

const mockJob: JobRequisition = {
  id: "11111111-2222-3333-4444-555555555555",
  tenant_id: "tenant-1",
  title: "Staff Cloud Reliability Architect",
  slug: "staff-cloud-reliability-architect-abc12345",
  department: "Platform Engineering",
  location: "Austin, TX",
  country: "United States",
  remote_type: "hybrid",
  employment_type: "full_time",
  experience_level: "principal",
  description: "Architect mission-critical cloud platform resilience.",
  responsibilities: "Scale multi-region Kubernetes clusters.",
  required_qualifications: "8+ years in SRE and Cloud architecture.",
  skills_required: ["Kubernetes", "Terraform", "Go"],
  preferred_skills: ["Rust", "eBPF"],
  salary_min: 190000,
  salary_max: 240000,
  salary_currency: "USD",
  vacancies_count: 1,
  status: "pending_approval",
  approval_status: "pending_approval",
  visibility: "public",
  recruiter_id: "rec-1",
  recruiter_name: "Sarah Jenkins",
  recruiter_email: "sarah@acme.com",
  hiring_manager_id: "hm-1",
  hiring_manager_name: "Alex Vance",
  hiring_manager_email: "alex@acme.com",
  applications_count: 0,
  created_at: "2026-11-01T10:00:00Z",
  updated_at: "2026-11-05T12:00:00Z",
};

const mockPermittedActions: JobLifecyclePermittedActionsResponse = {
  job_id: "11111111-2222-3333-4444-555555555555",
  current_status: "pending_approval",
  approval_status: "pending_approval",
  permitted_actions: ["approve", "request_changes"],
  can_approve: true,
  user_role: "hiring_manager",
  separation_of_duties_active: false,
};

const mockHistory: JobLifecycleHistoryItem[] = [
  {
    id: "hist-1",
    job_id: "11111111-2222-3333-4444-555555555555",
    previous_status: "draft",
    new_status: "pending_approval",
    action: "submit_for_approval",
    actor_id: "rec-1",
    actor_name: "Sarah Jenkins",
    actor_email: "sarah@acme.com",
    actor_role: "recruiter",
    reason: "Submitted for engineering leadership sign-off",
    audit_metadata: {},
    created_at: "2026-11-02T11:00:00Z",
  },
];

describe("HR Job Publishing and Lifecycle Management (Frontend)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hrApi, "getJob").mockResolvedValue({ ...mockJob });
    vi.spyOn(hrApi, "getJobLifecycleHistory").mockResolvedValue([...mockHistory]);
    vi.spyOn(hrApi, "getPermittedLifecycleActions").mockResolvedValue({ ...mockPermittedActions });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders lifecycle status stepper and permitted workflow action buttons", async () => {
    render(<JobDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Staff Cloud Reliability Architect")).toBeDefined();
    });

    // Workflow lifecycle header
    expect(screen.getByText("Publication & Approval Lifecycle")).toBeDefined();

    // Stepper stages
    expect(screen.getAllByText("Pending Approval").length).toBeGreaterThanOrEqual(1);

    // Permitted action buttons
    expect(screen.getByRole("button", { name: /approve requisition/i })).toBeDefined();
    expect(screen.getByRole("button", { name: /request changes/i })).toBeDefined();
  });

  it("displays separation of duties warning banner when active", async () => {
    vi.spyOn(hrApi, "getPermittedLifecycleActions").mockResolvedValue({
      job_id: mockJob.id,
      current_status: "pending_approval",
      approval_status: "pending_approval",
      permitted_actions: ["request_changes"], // approve excluded due to separation of duties
      can_approve: false,
      user_role: "recruiter",
      separation_of_duties_active: true,
    });

    render(<JobDetailPage />);

    await waitFor(() => {
      expect(screen.getByText(/Separation of Duties Policy Active:/i)).toBeDefined();
    });

    expect(
      screen.getByText(/You are assigned as the lead recruiter for this job requisition/i)
    ).toBeDefined();
    expect(screen.queryByRole("button", { name: /approve requisition/i })).toBeNull();
  });

  it("handles approve action directly", async () => {
    const executeSpy = vi.spyOn(hrApi, "executeLifecycleAction").mockResolvedValue({
      job: { ...mockJob, status: "approved", approval_status: "approved" },
      transition: {
        id: "hist-2",
        job_id: mockJob.id,
        previous_status: "pending_approval",
        new_status: "approved",
        action: "approve",
        actor_id: "hm-1",
        actor_name: "Alex Vance",
        actor_role: "hiring_manager",
        audit_metadata: {},
        created_at: "2026-11-03T09:00:00Z",
      },
      permitted_next_actions: ["publish", "return_to_draft"],
    });

    render(<JobDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /approve requisition/i })).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /approve requisition/i }));

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalledWith(mockJob.id, {
        action: "approve",
        reason: undefined,
      });
    });
  });

  it("handles request changes modal with mandatory reason", async () => {
    const executeSpy = vi.spyOn(hrApi, "executeLifecycleAction").mockResolvedValue({
      job: {
        ...mockJob,
        status: "draft",
        approval_status: "draft",
        change_request_reason: "Please update the required qualifications to include Kubernetes.",
      },
      transition: {
        id: "hist-2",
        job_id: mockJob.id,
        previous_status: "pending_approval",
        new_status: "draft",
        action: "request_changes",
        actor_id: "hm-1",
        actor_name: "Alex Vance",
        actor_role: "hiring_manager",
        reason: "Please update the required qualifications to include Kubernetes.",
        audit_metadata: {},
        created_at: "2026-11-03T09:00:00Z",
      },
      permitted_next_actions: ["submit_for_approval"],
    });

    render(<JobDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /request changes/i })).toBeDefined();
    });

    // Click to open modal
    fireEvent.click(screen.getByRole("button", { name: /request changes/i }));

    expect(screen.getByText("Request Requisition Changes")).toBeDefined();

    // Type change reason into textarea
    const textarea = screen.getByTestId("textarea-changes-reason");
    fireEvent.change(textarea, {
      target: { value: "Please update the required qualifications to include Kubernetes." },
    });

    // Click confirm submit in modal
    const confirmBtn = screen.getByTestId("btn-confirm-request-changes");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalledWith(mockJob.id, {
        action: "request_changes",
        reason: "Please update the required qualifications to include Kubernetes.",
      });
    });
  });

  it("handles publish modal confirmation when job is approved", async () => {
    vi.spyOn(hrApi, "getJob").mockResolvedValue({
      ...mockJob,
      status: "approved",
      approval_status: "approved",
    });
    vi.spyOn(hrApi, "getPermittedLifecycleActions").mockResolvedValue({
      job_id: mockJob.id,
      current_status: "approved",
      approval_status: "approved",
      permitted_actions: ["publish", "return_to_draft"],
      can_approve: true,
      user_role: "recruiter",
      separation_of_duties_active: false,
    });

    const executeSpy = vi.spyOn(hrApi, "executeLifecycleAction").mockResolvedValue({
      job: { ...mockJob, status: "published", approval_status: "approved", published_at: "2026-11-04T10:00:00Z" },
      transition: {
        id: "hist-3",
        job_id: mockJob.id,
        previous_status: "approved",
        new_status: "published",
        action: "publish",
        actor_id: "rec-1",
        actor_name: "Sarah Jenkins",
        actor_role: "recruiter",
        audit_metadata: {},
        created_at: "2026-11-04T10:00:00Z",
      },
      permitted_next_actions: ["pause", "close"],
    });

    render(<JobDetailPage />);

    await waitFor(() => {
      expect(screen.getByRole("button", { name: /publish to careers site/i })).toBeDefined();
    });

    fireEvent.click(screen.getByRole("button", { name: /publish to careers site/i }));

    expect(screen.getByText("Publish Job to Career Site")).toBeDefined();

    const confirmBtn = screen.getByTestId("btn-confirm-publish");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(executeSpy).toHaveBeenCalledWith(mockJob.id, {
        action: "publish",
        reason: undefined,
      });
    });
  });

  it("renders lifecycle audit timeline with actors, transitions and reasons", async () => {
    render(<JobDetailPage />);

    await waitFor(() => {
      expect(screen.getByText("Lifecycle Audit History")).toBeDefined();
    });

    expect(screen.getAllByText("Sarah Jenkins").length).toBeGreaterThanOrEqual(1);
    expect(screen.getByText("recruiter")).toBeDefined();
    expect(screen.getByText("draft → pending_approval")).toBeDefined();
    expect(screen.getByText("Submitted for engineering leadership sign-off")).toBeDefined();
  });
});
