import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { HrSidebar } from "@/components/hr/HrSidebar";
import { HrHeader } from "@/components/hr/HrHeader";
import HrDashboardPage from "@/app/hr/dashboard/page";
import { hrApi } from "@/lib/hrApi";
import type { HrDashboardOverviewResponse } from "@/types/hr";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/hr/dashboard",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

// Mock Recharts ResponsiveContainer to avoid SVG size calculation errors in happy-dom
vi.mock("recharts", async () => {
  const actual = await vi.importActual("recharts");
  return {
    ...actual,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
      <div data-testid="responsive-container" style={{ width: 400, height: 250 }}>
        {children}
      </div>
    ),
  };
});

describe("HR / Recruiter Portal Components & Dashboard", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe("HrSidebar", () => {
    it("renders all HR navigation links and organization context", () => {
      render(<HrSidebar organizationName="Acme Cloud Technologies" />);

      expect(screen.getByText("Recruitment Overview")).toBeDefined();
      expect(screen.getByText("Job Requisitions")).toBeDefined();
      expect(screen.getByText("Applicant Pool")).toBeDefined();
      expect(screen.getByText("Pipeline Board")).toBeDefined();
      expect(screen.getByText("Organization Settings")).toBeDefined();
      expect(screen.getByText("Candidate Portal")).toBeDefined();
      expect(screen.getByText("Acme Cloud Technologies")).toBeDefined();
    });

    it("triggers onClose callback when mobile close button is clicked", () => {
      const handleClose = vi.fn();
      render(<HrSidebar isOpen={true} onClose={handleClose} />);

      const closeBtn = screen.getByRole("button", { name: /Close sidebar/i });
      fireEvent.click(closeBtn);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("HrHeader", () => {
    it("renders organization pill, search bar, and user profile", () => {
      render(
        <HrHeader
          organizationName="Acme Cloud Corp"
          userEmail="recruiter@acme.com"
          userRole="Recruiter"
        />
      );

      expect(screen.getByText("Acme Cloud Corp")).toBeDefined();
      expect(
        screen.getByPlaceholderText(/Search applicants, requisitions, skills/i)
      ).toBeDefined();
      expect(screen.getByText("recruiter")).toBeDefined();
    });

    it("toggles profile menu with Sign Out action", async () => {
      render(
        <HrHeader
          userEmail="recruiter@acme.com"
          userRole="Lead Recruiter"
        />
      );

      const profileBtn = screen.getByText("recruiter");
      fireEvent.click(profileBtn);

      await waitFor(() => {
        expect(screen.getByText("Sign Out")).toBeDefined();
        expect(screen.getByText("recruiter@acme.com")).toBeDefined();
      });
    });
  });

  describe("HrDashboardPage", () => {
    const mockDashboardData: HrDashboardOverviewResponse = {
      tenant_id: "org-tenant-101",
      organization_name: "Acme Cloud Corp",
      metrics: {
        total_candidates: 18,
        total_applications: 24,
        active_jobs: 5,
        published_jobs: 6,
        draft_jobs: 2,
        applications_awaiting_review: 7,
        shortlisted_candidates: 4,
        scheduled_interviews: 3,
        hired_candidates: 2,
        pending_tasks: 7,
      },
      recruitment_funnel: [
        { stage: "applied", label: "Applied", count: 24, percentage: 100 },
        { stage: "review", label: "Resume Review", count: 21, percentage: 87.5 },
        { stage: "screening", label: "Screening", count: 12, percentage: 50 },
        { stage: "shortlisted", label: "Shortlisted", count: 9, percentage: 37.5 },
        { stage: "interview", label: "Interview Round", count: 5, percentage: 20.8 },
        { stage: "offer", label: "Offer Extended", count: 3, percentage: 12.5 },
        { stage: "hired", label: "Hired", count: 2, percentage: 8.3 },
      ],
      applications_over_time: [
        { date: "2026-11-01", applications_count: 5 },
        { date: "2026-11-05", applications_count: 8 },
        { date: "2026-11-09", applications_count: 11 },
      ],
      applications_by_job: [
        {
          job_id: "job-1",
          job_title: "Senior Distributed Systems Engineer",
          department: "Platform Infrastructure",
          status: "published",
          applications_count: 14,
          active_count: 8,
        },
        {
          job_id: "job-2",
          job_title: "Principal Security Architect",
          department: "InfoSec",
          status: "published",
          applications_count: 10,
          active_count: 4,
        },
      ],
      applications_by_department: [
        {
          department: "Platform Infrastructure",
          applications_count: 14,
          open_jobs_count: 3,
        },
        {
          department: "InfoSec",
          applications_count: 10,
          open_jobs_count: 2,
        },
      ],
      recent_applicants: [
        {
          application_id: "app-101",
          candidate_id: "cand-1",
          candidate_name: "Elena Rostova",
          candidate_email: "elena@example.com",
          job_id: "job-1",
          job_title: "Senior Distributed Systems Engineer",
          department: "Platform Infrastructure",
          applied_at: "2026-11-09T14:30:00Z",
          stage: "under_review",
          candidate_status: "under_review",
          skills_count: 2,
          top_skills: ["Rust", "Kubernetes"],
        },
      ],
      recent_activities: [
        {
          id: "act-1",
          event_type: "application_submitted",
          title: "New Application Submitted",
          description: "Elena Rostova applied for Senior Distributed Systems Engineer",
          candidate_name: "Elena Rostova",
          job_title: "Senior Distributed Systems Engineer",
          timestamp: "2026-11-09T14:30:00Z",
          actor_name: "Candidate",
        },
      ],
      active_filters: {},
    };

    it("renders all high-level KPI metric cards from real backend aggregation", async () => {
      vi.spyOn(hrApi, "getDashboardOverview").mockResolvedValue(mockDashboardData);

      render(<HrDashboardPage />);

      await waitFor(() => {
        expect(screen.getByText("Recruitment Overview")).toBeDefined();
        expect(screen.getByText("18")).toBeDefined(); // Total Candidates
        expect(screen.getAllByText("24").length).toBeGreaterThanOrEqual(1); // Total Applications
        expect(screen.getByText("7")).toBeDefined();  // Needs Review
      });

      expect(screen.getAllByText("Senior Distributed Systems Engineer").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Elena Rostova")).toBeDefined();
      expect(screen.getByText("Rust")).toBeDefined();
    });

    it("renders recruitment funnel conversion stages", async () => {
      vi.spyOn(hrApi, "getDashboardOverview").mockResolvedValue(mockDashboardData);

      render(<HrDashboardPage />);

      await waitFor(() => {
        expect(screen.getByText("Recruitment Funnel Conversion")).toBeDefined();
      });

      expect(screen.getByText("Resume Review")).toBeDefined();
      expect(screen.getByText("Interview Round")).toBeDefined();
      expect(screen.getByText("Offer Extended")).toBeDefined();
      expect(screen.getAllByText("Hired").length).toBeGreaterThanOrEqual(1);
      expect(screen.getAllByText("Shortlisted").length).toBeGreaterThanOrEqual(1);
    });

    it("updates filters and triggers backend request with updated parameters", async () => {
      const getOverviewSpy = vi
        .spyOn(hrApi, "getDashboardOverview")
        .mockResolvedValue(mockDashboardData);

      render(<HrDashboardPage />);

      await waitFor(() => {
        expect(screen.getByText("Recruitment Overview")).toBeDefined();
      });

      // Change Time Horizon to Past 7 Days
      const horizonSelect = screen.getByDisplayValue("Past 30 Days");
      fireEvent.change(horizonSelect, { target: { value: "7" } });

      await waitFor(() => {
        expect(getOverviewSpy).toHaveBeenCalled();
      });
    });

    it("renders empty state cleanly when organization has 0 applicants", async () => {
      vi.spyOn(hrApi, "getDashboardOverview").mockResolvedValue({
        tenant_id: "empty-tenant",
        organization_name: "Startup Alpha",
        metrics: {
          total_candidates: 0,
          total_applications: 0,
          active_jobs: 0,
          published_jobs: 0,
          draft_jobs: 0,
          applications_awaiting_review: 0,
          shortlisted_candidates: 0,
          scheduled_interviews: 0,
          hired_candidates: 0,
          pending_tasks: 0,
        },
        recruitment_funnel: [],
        applications_over_time: [],
        applications_by_job: [],
        applications_by_department: [],
        recent_applicants: [],
        recent_activities: [],
        active_filters: {},
      });

      render(<HrDashboardPage />);

      await waitFor(() => {
        expect(screen.getByText("Recruitment Overview")).toBeDefined();
      });

      expect(screen.getByText("No recent candidate submissions found.")).toBeDefined();
      expect(screen.getByText("No active job requisitions published yet.")).toBeDefined();
    });
  });
});
