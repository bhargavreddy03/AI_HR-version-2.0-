import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import HrAssignmentsPage from "@/app/hr/assignments/page";
import { hrApi } from "@/lib/hrApi";
import type {
  AssignedVacanciesResponse,
  JobAssignmentHistoryItem,
  JobRequisition,
  TeamMemberOption,
  TeamWorkloadResponse,
} from "@/types/hr";

const mockWorkloadResponse: TeamWorkloadResponse = {
  tenant_id: "org-1",
  summary: {
    total_team_members: 3,
    total_assigned_jobs: 4,
    total_unassigned_jobs: 1,
    total_active_applications: 18,
  },
  recruiters: [
    {
      user_id: "rec-1",
      name: "Alice Recruiter",
      email: "alice@acme.com",
      role: "recruiter",
      assigned_jobs_count: 3,
      active_jobs_count: 2,
      total_applications_count: 12,
      pending_reviews_count: 9,
      active_interviews_count: 3,
      workload_status: "high",
    },
    {
      user_id: "rec-2",
      name: "Bob Talent",
      email: "bob@acme.com",
      role: "recruiter",
      assigned_jobs_count: 1,
      active_jobs_count: 1,
      total_applications_count: 4,
      pending_reviews_count: 2,
      active_interviews_count: 1,
      workload_status: "balanced",
    },
  ],
  hiring_managers: [
    {
      user_id: "hm-1",
      name: "Carol Manager",
      email: "carol@acme.com",
      role: "hiring_manager",
      assigned_jobs_count: 2,
      active_jobs_count: 2,
      total_applications_count: 10,
      pending_reviews_count: 4,
      active_interviews_count: 2,
      workload_status: "balanced",
    },
  ],
};

const mockMyVacancies: AssignedVacanciesResponse = {
  tenant_id: "org-1",
  total: 1,
  vacancies: [
    {
      id: "job-101",
      title: "Senior Cloud Infrastructure Engineer",
      department: "Platform Engineering",
      status: "published",
      work_arrangement: "remote",
      vacancies: 2,
      active_applications_count: 12,
      pending_reviews_count: 5,
      scheduled_interviews_count: 2,
      recruiter_id: "rec-1",
      recruiter_name: "Alice Recruiter",
      hiring_manager_id: "hm-1",
      hiring_manager_name: "Carol Manager",
      created_at: "2026-11-01T00:00:00Z",
    },
  ],
};

const mockJobs = [
  {
    id: "job-101",
    tenant_id: "org-1",
    title: "Senior Cloud Infrastructure Engineer",
    department: "Platform Engineering",
    description: "Cloud lead",
    employment_type: "full_time",
    remote_type: "remote",
    status: "published",
    created_at: "2026-11-01T00:00:00Z",
    updated_at: "2026-11-01T00:00:00Z",
  },
] as unknown as JobRequisition[];

const mockTeam: TeamMemberOption[] = [
  { id: "rec-1", name: "Alice Recruiter", email: "alice@acme.com", role: "recruiter" },
  { id: "rec-2", name: "Bob Talent", email: "bob@acme.com", role: "recruiter" },
  { id: "hm-1", name: "Carol Manager", email: "carol@acme.com", role: "hiring_manager" },
];

const mockHistory: JobAssignmentHistoryItem[] = [
  {
    id: "hist-1",
    job_id: "job-101",
    assignment_type: "recruiter",
    actor_id: "user-admin",
    actor_name: "Admin Boss",
    previous_user_id: null,
    previous_user_name: null,
    new_user_id: "rec-1",
    new_user_name: "Alice Recruiter",
    reason: "Assigned lead recruiter for Q4 opening",
    created_at: "2026-11-02T10:00:00Z",
  },
];

describe("HrAssignmentsPage Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hrApi, "getTeamWorkload").mockResolvedValue(mockWorkloadResponse);
    vi.spyOn(hrApi, "getMyAssignedVacancies").mockResolvedValue(mockMyVacancies);
    vi.spyOn(hrApi, "listJobs").mockResolvedValue({
      items: mockJobs,
      total: 1,
      page: 1,
      page_size: 100,
      pages: 1,
    });
    vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue(mockTeam);
    vi.spyOn(hrApi, "updateJobAssignments").mockResolvedValue({
      job_id: "job-101",
      job_title: "Senior Cloud Infrastructure Engineer",
      recruiter_id: "rec-2",
      recruiter_name: "Bob Talent",
      hiring_manager_id: "hm-1",
      hiring_manager_name: "Carol Manager",
      updated_at: "2026-11-10T12:00:00Z",
      message: "Recruiter assignment successfully updated to Bob Talent.",
    });
    vi.spyOn(hrApi, "getJobAssignmentHistory").mockResolvedValue(mockHistory);
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders recruitment team workload dashboard and summary metrics", async () => {
    render(<HrAssignmentsPage />);

    expect(screen.getByText("Recruitment Team & Assignments")).toBeDefined();

    await waitFor(() => {
      expect(screen.getByText("Alice Recruiter")).toBeDefined();
      expect(screen.getByText("Bob Talent")).toBeDefined();
      expect(screen.getByText("Carol Manager")).toBeDefined();
    });

    // Check summary numbers
    expect(screen.getAllByText("4").length).toBeGreaterThanOrEqual(1); // total assigned
    expect(screen.getByText("18")).toBeDefined(); // total active apps
    expect(screen.getByText("Near Capacity")).toBeDefined(); // workload status for Alice
  });

  it("filters team members via search input", async () => {
    render(<HrAssignmentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Recruiter")).toBeDefined();
    });

    const searchInput = screen.getByPlaceholderText("Search team member...");
    fireEvent.change(searchInput, { target: { value: "Bob" } });

    await waitFor(() => {
      expect(screen.queryByText("Alice Recruiter")).toBeNull();
      expect(screen.getByText("Bob Talent")).toBeDefined();
    });
  });

  it("switches to 'My Assigned Vacancies' tab and renders assigned vacancy cards", async () => {
    render(<HrAssignmentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Recruiter")).toBeDefined();
    });

    const tabBtn = screen.getByRole("button", { name: /My Assigned Vacancies/i });
    fireEvent.click(tabBtn);

    await waitFor(() => {
      expect(screen.getByText("Senior Cloud Infrastructure Engineer")).toBeDefined();
      expect(screen.getByText("Platform Engineering • remote • 2 open positions")).toBeDefined();
      expect(screen.getByText("Open Pipeline")).toBeDefined();
    });
  });

  it("opens reassign vacancy modal, selects new recruiter, and submits assignment update", async () => {
    render(<HrAssignmentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Recruiter")).toBeDefined();
    });

    // Open Assign Vacancy modal
    const assignBtn = screen.getByRole("button", { name: /Assign Vacancy/i });
    fireEvent.click(assignBtn);

    await waitFor(() => {
      expect(screen.getByText("Assign Vacancy Leads")).toBeDefined();
    });

    // Select Bob Talent as recruiter
    const recruiterSelect = screen.getByTestId("reassign-recruiter-select");
    fireEvent.change(recruiterSelect, { target: { value: "rec-2" } });

    // Submit form
    const saveBtn = screen.getByRole("button", { name: /Save Assignment/i });
    fireEvent.click(saveBtn);

    await waitFor(() => {
      expect(hrApi.updateJobAssignments).toHaveBeenCalledWith(
        "job-101",
        expect.objectContaining({
          recruiter_id: "rec-2",
          update_recruiter: true,
          update_hiring_manager: false,
        })
      );
      expect(
        screen.getByText("Job recruitment assignments updated successfully.")
      ).toBeDefined();
    });
  });

  it("opens assignment audit history modal and displays past transitions", async () => {
    render(<HrAssignmentsPage />);

    await waitFor(() => {
      expect(screen.getByText("Alice Recruiter")).toBeDefined();
    });

    // Switch to My Vacancies tab
    const tabBtn = screen.getByRole("button", { name: /My Assigned Vacancies/i });
    fireEvent.click(tabBtn);

    await waitFor(() => {
      expect(screen.getByText("Senior Cloud Infrastructure Engineer")).toBeDefined();
    });

    // Click History button
    const historyBtn = screen.getByTitle("View assignment audit history");
    fireEvent.click(historyBtn);

    await waitFor(() => {
      expect(screen.getByText("Assignment History")).toBeDefined();
      expect(screen.getByText("Assigned lead recruiter for Q4 opening")).toBeDefined();
      expect(screen.getByText("Admin Boss")).toBeDefined();
    });
  });
});
