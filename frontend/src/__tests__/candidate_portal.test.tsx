import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { ApplicationStatusBadge } from "@/components/candidate/ApplicationStatusBadge";
import { CandidateSidebar } from "@/components/candidate/CandidateSidebar";
import { CandidateHeader } from "@/components/candidate/CandidateHeader";
import { ResumeUploadDropzone } from "@/components/candidate/ResumeUploadDropzone";
import { DashboardSkeleton } from "@/components/candidate/DashboardSkeleton";
import CandidateLayout from "@/app/candidate/layout";
import CandidateDashboardPage from "@/app/candidate/dashboard/page";
import { candidateApi } from "@/lib/candidateApi";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/candidate/dashboard",
  useRouter: () => ({
    push: vi.fn(),
    replace: vi.fn(),
    prefetch: vi.fn(),
  }),
}));

describe("Candidate Portal Components", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  describe("ApplicationStatusBadge", () => {
    it("renders received status accurately with badge text", () => {
      render(<ApplicationStatusBadge status="received" />);
      expect(screen.getByText("Application Received")).toBeDefined();
    });

    it("renders under_review status accurately", () => {
      render(<ApplicationStatusBadge status="under_review" />);
      expect(screen.getByText("Under Review")).toBeDefined();
    });

    it("renders shortlisted status accurately", () => {
      render(<ApplicationStatusBadge status="shortlisted" />);
      expect(screen.getByText("Shortlisted")).toBeDefined();
    });

    it("renders interviewing status accurately", () => {
      render(<ApplicationStatusBadge status="interviewing" />);
      expect(screen.getByText("Interviewing")).toBeDefined();
    });

    it("renders offer status accurately", () => {
      render(<ApplicationStatusBadge status="offer" />);
      expect(screen.getByText("Offer Extended")).toBeDefined();
    });

    it("renders rejected status accurately", () => {
      render(<ApplicationStatusBadge status="rejected" />);
      expect(screen.getByText("Not Selected")).toBeDefined();
    });

    it("renders withdrawn status accurately", () => {
      render(<ApplicationStatusBadge status="withdrawn" />);
      expect(screen.getByText("Withdrawn")).toBeDefined();
    });
  });

  describe("CandidateSidebar", () => {
    it("renders all candidate navigation links", () => {
      render(<CandidateSidebar />);

      expect(screen.getByText("Dashboard")).toBeDefined();
      expect(screen.getByText("My Profile")).toBeDefined();
      expect(screen.getByText("Resumes")).toBeDefined();
      expect(screen.getByText("Find Jobs")).toBeDefined();
      expect(screen.getByText("Saved Jobs")).toBeDefined();
      expect(screen.getByText("My Applications")).toBeDefined();
      expect(screen.getByText("Settings & Privacy")).toBeDefined();
    });

    it("calls onClose when close button clicked in mobile view", () => {
      const handleClose = vi.fn();
      render(<CandidateSidebar isOpen={true} onClose={handleClose} />);

      const closeBtn = screen.getByRole("button", { name: /Close sidebar/i });
      fireEvent.click(closeBtn);
      expect(handleClose).toHaveBeenCalledTimes(1);
    });
  });

  describe("CandidateHeader", () => {
    it("renders candidate header with welcome message and candidate name", () => {
      render(
        <CandidateHeader
          userName="Alice Smith"
          userEmail="alice@example.com"
        />
      );

      expect(screen.getByText(/Welcome back/i)).toBeDefined();
      expect(screen.getByText("Alice Smith")).toBeDefined();
    });

    it("toggles notification dropdown when bell clicked", () => {
      render(<CandidateHeader />);

      const bellBtn = screen.getByRole("button", { name: /Notifications/i });
      fireEvent.click(bellBtn);

      expect(screen.getByText("Notifications")).toBeDefined();
    });
  });

  describe("ResumeUploadDropzone", () => {
    it("renders upload instructions and file guidelines", () => {
      render(<ResumeUploadDropzone />);

      expect(screen.getByText("Click or drag resume here to upload")).toBeDefined();
      expect(
        screen.getByText(/Supports PDF or DOCX up to 15MB/i)
      ).toBeDefined();
    });

    it("shows error when unsupported file type dropped or selected", async () => {
      render(<ResumeUploadDropzone />);

      const dropzone = screen.getByRole("button", { name: /Upload Resume File/i });

      const fakeFile = new File(["fake"], "notes.txt", { type: "text/plain" });
      fireEvent.drop(dropzone, {
        dataTransfer: {
          files: [fakeFile],
        },
      });

      expect(screen.getByText("Only PDF and DOCX files are supported.")).toBeDefined();
    });
  });

  describe("DashboardSkeleton", () => {
    it("renders skeleton loader with accessible aria-busy attribute", () => {
      render(<DashboardSkeleton />);
      const skeleton = screen.getByLabelText("Loading candidate dashboard");
      expect(skeleton).toBeDefined();
      expect(skeleton.getAttribute("aria-busy")).toBe("true");
    });
  });

  describe("CandidateLayout", () => {
    it("renders accessible breadcrumbs navigation", async () => {
      render(
        <CandidateLayout>
          <div>Dashboard Content</div>
        </CandidateLayout>
      );

      expect(screen.getByLabelText("Breadcrumb")).toBeDefined();
      expect(screen.getByText("Portal")).toBeDefined();
      expect(screen.getByText("Dashboard Content")).toBeDefined();
    });
  });

  describe("CandidateDashboardPage", () => {
    it("loads and renders candidate dashboard with live data metrics", async () => {
      vi.spyOn(candidateApi, "getProfile").mockResolvedValue({
        user: {
          id: "usr-1",
          email: "jane@candidate.io",
          full_name: "Jane Doe",
          is_active: true,
          is_verified: true,
        },
        headline: "Staff Cloud Engineer",
        bio: "Specializing in microservices",
        self_declared_skills: ["Go", "FastAPI"],
        experiences: [],
        educations: [],
        certifications: [],
        projects: [],
        languages: [],
        profile_completeness_pct: 85,
      });

      vi.spyOn(candidateApi, "getMyApplications").mockResolvedValue([
        {
          id: "app-1",
          job_id: "job-1",
          tenant_id: "org-1",
          candidate_status: "under_review",
          applied_at: new Date().toISOString(),
          job: {
            id: "job-1",
            tenant_id: "org-1",
            title: "Senior Backend Developer",
            department: "Engineering",
            location: "Remote",
            remote_type: "remote",
            employment_type: "full_time",
            required_skills: ["Go"],
            created_at: new Date().toISOString(),
          },
        },
      ]);

      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([]);
      vi.spyOn(candidateApi, "getResumes").mockResolvedValue([]);
      vi.spyOn(candidateApi, "getNotifications").mockResolvedValue([]);
      vi.spyOn(candidateApi, "searchJobs").mockResolvedValue([]);

      render(<CandidateDashboardPage />);

      await waitFor(() => {
        expect(screen.getByText("Welcome back, Jane Doe")).toBeDefined();
      });

      // Metric checks
      expect(screen.getByText("85%")).toBeDefined();
      expect(screen.getByText("Senior Backend Developer")).toBeDefined();
      expect(screen.getByText("Total Apps")).toBeDefined();
      expect(screen.getAllByText("Under Review").length).toBeGreaterThanOrEqual(1);
      expect(screen.getByText("Shortlisted")).toBeDefined();
      expect(screen.getByText("Interviews")).toBeDefined();
      expect(screen.getByText("Saved Jobs")).toBeDefined();
    });
  });
});
