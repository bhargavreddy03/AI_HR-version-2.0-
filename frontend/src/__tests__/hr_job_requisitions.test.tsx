import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import HrJobsPage from "@/app/hr/jobs/page";
import NewJobRequisitionPage from "@/app/hr/jobs/new/page";
import JobDetailPage from "@/app/hr/jobs/[id]/page";
import EditJobRequisitionPage from "@/app/hr/jobs/[id]/edit/page";
import { hrApi } from "@/lib/hrApi";
import type { JobRequisition, JobRequisitionListResponse } from "@/types/hr";

const mockPush = vi.fn();

vi.mock("next/navigation", () => ({
  useParams: () => ({ id: "11111111-2222-3333-4444-555555555555" }),
  useRouter: () => ({
    push: mockPush,
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

const mockJobs: JobRequisition[] = [
  {
    id: "11111111-2222-3333-4444-555555555555",
    tenant_id: "tenant-1",
    title: "Senior Distributed Systems Engineer",
    slug: "senior-distributed-systems-engineer-abc12345",
    department: "Engineering",
    location: "San Francisco, CA",
    country: "United States",
    remote_type: "hybrid",
    employment_type: "full_time",
    experience_level: "senior",
    description: "Build robust distributed backend infrastructure.",
    responsibilities: "Architect fault-tolerant microservices.",
    required_qualifications: "5+ years distributed systems experience.",
    skills_required: ["Go", "PostgreSQL", "Kafka"],
    preferred_skills: ["Kubernetes", "gRPC"],
    salary_min: 160000,
    salary_max: 210000,
    salary_currency: "USD",
    vacancies_count: 2,
    status: "published",
    approval_status: "approved",
    visibility: "public",
    recruiter_id: "rec-1",
    recruiter_name: "Sarah Jenkins",
    recruiter_email: "sarah@acme.com",
    hiring_manager_id: "hm-1",
    hiring_manager_name: "Alex Vance",
    hiring_manager_email: "alex@acme.com",
    applications_count: 14,
    created_at: "2026-11-01T10:00:00Z",
    updated_at: "2026-11-05T12:00:00Z",
  },
  {
    id: "22222222-3333-4444-5555-666666666666",
    tenant_id: "tenant-1",
    title: "Product Marketing Manager",
    slug: "product-marketing-manager-def67890",
    department: "Marketing",
    location: "New York, NY",
    country: "United States",
    remote_type: "remote",
    employment_type: "full_time",
    experience_level: "mid",
    description: "Lead developer tooling product marketing campaigns.",
    skills_required: ["Product Marketing", "Content Strategy"],
    preferred_skills: ["SEO"],
    salary_min: 110000,
    salary_max: 140000,
    salary_currency: "USD",
    vacancies_count: 1,
    status: "draft",
    approval_status: "draft",
    visibility: "internal",
    applications_count: 0,
    created_at: "2026-11-08T15:00:00Z",
    updated_at: "2026-11-08T15:00:00Z",
  },
];

const mockListResponse: JobRequisitionListResponse = {
  items: mockJobs,
  total: 2,
  page: 1,
  page_size: 10,
  pages: 1,
};

describe("Step 4.2.3 — Job Requisition Management Frontend", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    mockPush.mockReset();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("HrJobsPage (Listing)", () => {
    it("renders job requisition listing with table rows and status badges", async () => {
      vi.spyOn(hrApi, "listJobs").mockResolvedValue(mockListResponse);

      render(<HrJobsPage />);

      await waitFor(() => {
        expect(screen.getByText("Job Requisitions")).toBeDefined();
        expect(screen.getByText("Senior Distributed Systems Engineer")).toBeDefined();
        expect(screen.getByText("Product Marketing Manager")).toBeDefined();
      });

      // Badges
      expect(screen.getAllByText("Published").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Draft")).toBeDefined();
      // Applicant count badge
      expect(screen.getByText("14")).toBeDefined();
    });

    it("triggers filter reload on search input change", async () => {
      const listSpy = vi.spyOn(hrApi, "listJobs").mockResolvedValue(mockListResponse);

      render(<HrJobsPage />);

      await waitFor(() => {
        expect(screen.getByTestId("job-search-input")).toBeDefined();
      });

      fireEvent.change(screen.getByTestId("job-search-input"), {
        target: { value: "Distributed" },
      });

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            search: "Distributed",
          })
        );
      });
    });

    it("triggers status tab filter when clicked", async () => {
      const listSpy = vi.spyOn(hrApi, "listJobs").mockResolvedValue(mockListResponse);

      render(<HrJobsPage />);

      await waitFor(() => {
        expect(screen.getByText("Drafts")).toBeDefined();
      });

      fireEvent.click(screen.getByText("Drafts"));

      await waitFor(() => {
        expect(listSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            status: "draft",
          })
        );
      });
    });
  });

  describe("NewJobRequisitionPage (Creation)", () => {
    it("renders all form sections, validates input, and enforces salary_min <= salary_max", async () => {
      vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue([
        { id: "u-1", name: "Sarah Jenkins", email: "sarah@acme.com", role: "recruiter" },
      ]);
      vi.spyOn(hrApi, "autocompleteSkills").mockResolvedValue([
        { canonical_name: "Python", category: "Language", skill_id: "python" },
      ]);

      render(<NewJobRequisitionPage />);

      // Title input
      expect(screen.getByTestId("input-title")).toBeDefined();
      expect(screen.getByTestId("input-location")).toBeDefined();

      // Submit without fields -> validation errors shown
      fireEvent.click(screen.getByTestId("save-draft-button"));

      await waitFor(() => {
        expect(screen.getByText("Title must be at least 2 characters")).toBeDefined();
        expect(screen.getByText("Location is required")).toBeDefined();
      });

      // Fill in salary_min > salary_max -> validation error
      fireEvent.change(screen.getByTestId("input-title"), { target: { value: "QA Lead" } });
      fireEvent.change(screen.getByTestId("input-location"), { target: { value: "Remote" } });
      fireEvent.change(screen.getByTestId("input-description"), {
        target: { value: "Lead the Quality Assurance team across platform services." },
      });
      fireEvent.change(screen.getByTestId("input-salary-min"), { target: { value: "190000" } });
      fireEvent.change(screen.getByTestId("input-salary-max"), { target: { value: "150000" } });

      fireEvent.click(screen.getByTestId("save-draft-button"));

      await waitFor(() => {
        expect(
          screen.getByText("Minimum salary cannot be greater than maximum salary")
        ).toBeDefined();
      });
    });

    it("successfully creates requisition with canonical skills and redirects", async () => {
      vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue([]);
      const createSpy = vi.spyOn(hrApi, "createJob").mockResolvedValue(mockJobs[0]);

      render(<NewJobRequisitionPage />);

      fireEvent.change(screen.getByTestId("input-title"), {
        target: { value: "Senior Distributed Systems Engineer" },
      });
      fireEvent.change(screen.getByTestId("input-location"), {
        target: { value: "San Francisco, CA" },
      });
      fireEvent.change(screen.getByTestId("input-description"), {
        target: { value: "Build robust distributed backend infrastructure." },
      });
      fireEvent.change(screen.getByTestId("input-salary-min"), { target: { value: "160000" } });
      fireEvent.change(screen.getByTestId("input-salary-max"), { target: { value: "210000" } });

      // Add required skill
      fireEvent.change(screen.getByTestId("input-required-skills"), {
        target: { value: "Go" },
      });
      fireEvent.keyDown(screen.getByTestId("input-required-skills"), {
        key: "Enter",
        code: "Enter",
      });

      fireEvent.click(screen.getByTestId("save-draft-button"));

      await waitFor(() => {
        expect(createSpy).toHaveBeenCalledWith(
          expect.objectContaining({
            title: "Senior Distributed Systems Engineer",
            location: "San Francisco, CA",
            status: "draft",
            skills_required: ["Go"],
          })
        );
        expect(mockPush).toHaveBeenCalledWith(`/hr/jobs/${mockJobs[0].id}`);
      });
    });
  });

  describe("JobDetailPage (Details & Actions)", () => {
    it("renders complete requisition specifications, assignments, and opens candidate view preview", async () => {
      vi.spyOn(hrApi, "getJob").mockResolvedValue(mockJobs[0]);

      render(<JobDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Senior Distributed Systems Engineer")).toBeDefined();
        expect(screen.getByText("Sarah Jenkins")).toBeDefined();
        expect(screen.getByText("Alex Vance")).toBeDefined();
        expect(screen.getByText("Build robust distributed backend infrastructure.")).toBeDefined();
      });

      // Click Candidate Preview button
      fireEvent.click(screen.getByTestId("preview-candidate-view-button"));

      await waitFor(() => {
        expect(screen.getByText("Public Candidate View Preview")).toBeDefined();
        expect(screen.getAllByText("Role Overview").length).toBeGreaterThanOrEqual(1);
      });
    });
  });

  describe("EditJobRequisitionPage (Editing)", () => {
    it("pre-populates existing data and saves changes", async () => {
      vi.spyOn(hrApi, "getJob").mockResolvedValue(mockJobs[0]);
      vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue([]);
      const updateSpy = vi.spyOn(hrApi, "updateJob").mockResolvedValue(mockJobs[0]);

      render(<EditJobRequisitionPage />);

      await waitFor(() => {
        expect(screen.getByDisplayValue("Senior Distributed Systems Engineer")).toBeDefined();
        expect(screen.getByDisplayValue("San Francisco, CA")).toBeDefined();
      });

      fireEvent.change(screen.getByTestId("input-edit-title"), {
        target: { value: "Staff Distributed Systems Engineer" },
      });

      fireEvent.click(screen.getByTestId("save-changes-button"));

      await waitFor(() => {
        expect(updateSpy).toHaveBeenCalledWith(
          mockJobs[0].id,
          expect.objectContaining({
            title: "Staff Distributed Systems Engineer",
          })
        );
        expect(mockPush).toHaveBeenCalledWith(`/hr/jobs/${mockJobs[0].id}`);
      });
    });
  });
});
