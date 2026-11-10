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
import CandidateResumesPage from "@/app/candidate/resumes/page";
import CandidateJobsPage from "@/app/candidate/jobs/page";
import CandidateJobDetailPage from "@/app/candidate/jobs/[id]/page";
import CandidateSavedJobsPage from "@/app/candidate/saved-jobs/page";
import { candidateApi } from "@/lib/candidateApi";

// Mock next/navigation
vi.mock("next/navigation", () => ({
  usePathname: () => "/candidate/dashboard",
  useParams: () => ({ id: "job-101" }),
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
      vi.spyOn(candidateApi, "searchJobs").mockResolvedValue({
        jobs: [],
        total: 0,
        page: 1,
        page_size: 20,
        total_pages: 1,
      });

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

  describe("CandidateResumesPage", () => {
    const mockResumes = [
      {
        id: "res-1",
        file_name: "jane_doe_lead_engineer.pdf",
        file_size_bytes: 1048576,
        mime_type: "application/pdf",
        sha256_hash: "a1b2c3d4e5f67890abcdef1234567890abcdef12",
        version_number: 2,
        is_default: true,
        extracted_skills: ["Python", "FastAPI", "PostgreSQL"],
        extracted_text_snippet: "Jane Doe Senior Python Architect...",
        uploaded_at: new Date().toISOString(),
        has_active_applications: true,
      },
      {
        id: "res-2",
        file_name: "jane_doe_initial.docx",
        file_size_bytes: 524288,
        mime_type: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        sha256_hash: "f6e5d4c3b2a10987fedcba0987654321fedcba09",
        version_number: 1,
        is_default: false,
        extracted_skills: ["Python", "Flask"],
        extracted_text_snippet: "Jane Doe Software Developer...",
        uploaded_at: new Date().toISOString(),
        has_active_applications: false,
      },
    ];

    it("renders resume documents with version badges and defensibility notices", async () => {
      vi.spyOn(candidateApi, "getResumes").mockResolvedValue(mockResumes);

      render(<CandidateResumesPage />);

      await waitFor(() => {
        expect(screen.getByText("jane_doe_lead_engineer.pdf")).toBeDefined();
      });

      expect(screen.getByText("v2")).toBeDefined();
      expect(screen.getByText("v1")).toBeDefined();
      expect(screen.getByText("Default")).toBeDefined();
      expect(screen.getByText("Application Retained")).toBeDefined();
      expect(screen.getByText(/Processing Pipeline Status & Capabilities/i)).toBeDefined();
    });

    it("opens application retention protection modal when deleting retained resume", async () => {
      vi.spyOn(candidateApi, "getResumes").mockResolvedValue(mockResumes);

      render(<CandidateResumesPage />);

      await waitFor(() => {
        expect(screen.getByText("jane_doe_lead_engineer.pdf")).toBeDefined();
      });

      // Find delete button for the retained resume (res-1)
      const deleteButtons = screen.getAllByTitle(/Protected by Application Retention|Delete Resume/i);
      expect(deleteButtons.length).toBe(2);

      // Click first delete button (retained resume)
      fireEvent.click(deleteButtons[0]);

      // Retention modal appears
      expect(screen.getByText("Application Retention Protection")).toBeDefined();
      expect(screen.getByText(/Under compliance, audit defensibility, and record retention requirements/i)).toBeDefined();

      // Close modal
      fireEvent.click(screen.getByRole("button", { name: "Understood" }));
      expect(screen.queryByText("Application Retention Protection")).toBeNull();
    });

    it("opens review extraction modal and allows editing skills", async () => {
      vi.spyOn(candidateApi, "getResumes").mockResolvedValue(mockResumes);
      vi.spyOn(candidateApi, "getResumeExtraction").mockResolvedValue({
        resume_id: "res-1",
        status: "COMPLETED",
        skills_extracted: ["Python", "FastAPI", "PostgreSQL"],
        word_count: 150,
        ocr_applied: false,
        ocr_provider: "null_ocr_unconfigured",
        malware_scan_status: "passed_development_mode",
        extracted_data: {
          name: "Jane Doe",
          email: "jane.doe@example.com",
          phone: "+1 555-0199",
          summary: "Lead Python Architect with 10+ years experience",
          skills: ["Python", "FastAPI", "PostgreSQL"],
          experience: [{ title: "Lead Architect", organization: "Cloud Corp" }],
          education: [{ title: "B.S. CS", organization: "MIT" }],
          certifications: ["AWS Certified"],
          projects: [{ title: "AI Pipeline" }],
        },
      });

      render(<CandidateResumesPage />);

      await waitFor(() => {
        expect(screen.getByText("jane_doe_lead_engineer.pdf")).toBeDefined();
      });

      const reviewButtons = screen.getAllByRole("button", { name: /Review Skills/i });
      fireEvent.click(reviewButtons[0]);

      await waitFor(() => {
        expect(screen.getByText("Candidate Extraction Review & Verification")).toBeDefined();
      });

      expect(screen.getByText("Jane Doe")).toBeDefined();
      expect(screen.getByText("jane.doe@example.com")).toBeDefined();
      expect(screen.getByRole("button", { name: /Apply to Verified Profile/i })).toBeDefined();
      expect(screen.getByRole("button", { name: /Save Resume Skills/i })).toBeDefined();
    });
  });

  describe("CandidateJobsPage", () => {
    const mockJobsResponse = {
      jobs: [
        {
          id: "job-101",
          tenant_id: "tenant-1",
          organization_name: "Acme Corp",
          title: "Principal Cloud Architect",
          department: "Engineering",
          location: "San Francisco, CA",
          remote_type: "remote",
          employment_type: "full_time",
          experience_level: "Senior",
          salary_min: 180000,
          salary_max: 220000,
          salary_currency: "USD",
          required_skills: ["AWS", "Kubernetes", "Terraform"],
          published_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
          application_deadline: new Date(Date.now() + 864000000).toISOString(),
          is_saved: false,
          has_applied: false,
          is_expired: false,
        },
        {
          id: "job-102",
          tenant_id: "tenant-2",
          organization_name: "Nexus AI",
          title: "Senior Python Backend Engineer",
          department: "AI Platforms",
          location: "New York, NY",
          remote_type: "hybrid",
          employment_type: "full_time",
          experience_level: "Senior",
          salary_min: 160000,
          salary_max: 200000,
          salary_currency: "USD",
          required_skills: ["Python", "FastAPI", "PostgreSQL"],
          published_at: new Date().toISOString(),
          created_at: new Date().toISOString(),
          application_deadline: new Date(Date.now() + 864000000).toISOString(),
          is_saved: true,
          has_applied: true,
          is_expired: false,
        },
      ],
      total: 2,
      page: 1,
      page_size: 12,
      total_pages: 1,
    };

    it("renders job search input and published opportunity cards", async () => {
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([
        {
          id: "saved-1",
          job_id: "job-102",
          saved_at: new Date().toISOString(),
          job: mockJobsResponse.jobs[1],
        },
      ]);
      vi.spyOn(candidateApi, "searchJobs").mockResolvedValue(mockJobsResponse);

      render(<CandidateJobsPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
        expect(screen.getByText("Senior Python Backend Engineer")).toBeDefined();
      });

      expect(screen.getByText("Acme Corp")).toBeDefined();
      expect(screen.getByText("Nexus AI")).toBeDefined();
      expect(screen.getByText("Applied")).toBeDefined();
    });

    it("allows toggling save/bookmark on a job", async () => {
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([]);
      vi.spyOn(candidateApi, "searchJobs").mockResolvedValue(mockJobsResponse);
      const saveSpy = vi.spyOn(candidateApi, "saveJob").mockResolvedValue({
        id: "saved-101",
        job_id: "job-101",
        saved_at: new Date().toISOString(),
        job: mockJobsResponse.jobs[0],
      });

      render(<CandidateJobsPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
      });

      const saveButtons = screen.getAllByRole("button", { name: /Save job/i });
      fireEvent.click(saveButtons[0]);

      await waitFor(() => {
        expect(saveSpy).toHaveBeenCalledWith("job-101");
      });
    });

    it("submits search query and triggers filtered reload", async () => {
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([]);
      const searchSpy = vi.spyOn(candidateApi, "searchJobs").mockResolvedValue(mockJobsResponse);

      render(<CandidateJobsPage />);

      const searchInput = screen.getByPlaceholderText(/Search by role title/i);
      fireEvent.change(searchInput, { target: { value: "Cloud" } });

      const searchBtn = screen.getByRole("button", { name: /^Search$/i });
      fireEvent.click(searchBtn);

      await waitFor(() => {
        expect(searchSpy).toHaveBeenCalled();
      });
    });
  });

  describe("CandidateJobDetailPage", () => {
    const mockDetail = {
      id: "job-101",
      tenant_id: "tenant-1",
      organization_name: "Acme Corp",
      title: "Principal Cloud Architect",
      department: "Engineering",
      location: "San Francisco, CA",
      remote_type: "remote",
      employment_type: "full_time",
      experience_level: "Senior",
      salary_min: 180000,
      salary_max: 220000,
      salary_currency: "USD",
      required_skills: ["AWS", "Kubernetes", "Terraform"],
      preferred_skills: ["Golang", "Rust"],
      description: "We are seeking a Principal Cloud Architect to scale our cloud platforms.",
      requirements: "10+ years of cloud architecture experience.",
      published_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
      application_deadline: new Date(Date.now() + 864000000).toISOString(),
      is_saved: false,
      has_applied: false,
      is_expired: false,
    };

    it("renders job requisition details and skills tags", async () => {
      vi.spyOn(candidateApi, "getJob").mockResolvedValue(mockDetail);
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([]);

      render(<CandidateJobDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
        expect(screen.getByText("Acme Corp")).toBeDefined();
      });

      expect(screen.getByText("We are seeking a Principal Cloud Architect to scale our cloud platforms.")).toBeDefined();
      expect(screen.getByText("10+ years of cloud architecture experience.")).toBeDefined();
      expect(screen.getByText("AWS")).toBeDefined();
      expect(screen.getByText("Kubernetes")).toBeDefined();
      expect(screen.getByText("Terraform")).toBeDefined();
      expect(screen.getByText("Golang")).toBeDefined();
    });

    it("displays position closed banner when job is expired", async () => {
      vi.spyOn(candidateApi, "getJob").mockResolvedValue({
        ...mockDetail,
        is_expired: true,
      });
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([]);

      render(<CandidateJobDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/Position Closed:/i)).toBeDefined();
        expect(screen.getByText("Applications Closed")).toBeDefined();
      });
    });

    it("displays applied banner when candidate has already applied", async () => {
      vi.spyOn(candidateApi, "getJob").mockResolvedValue({
        ...mockDetail,
        has_applied: true,
      });
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue([]);

      render(<CandidateJobDetailPage />);

      await waitFor(() => {
        expect(screen.getByText(/You have already submitted an application/i)).toBeDefined();
        expect(screen.getByText("View Application")).toBeDefined();
      });
    });
  });

  describe("CandidateSavedJobsPage", () => {
    const mockSavedJobs = [
      {
        id: "saved-1",
        job_id: "job-101",
        saved_at: new Date().toISOString(),
        job: {
          id: "job-101",
          tenant_id: "tenant-1",
          organization_name: "Acme Corp",
          title: "Principal Cloud Architect",
          department: "Engineering",
          location: "San Francisco, CA",
          remote_type: "remote",
          employment_type: "full_time",
          required_skills: ["AWS"],
          is_saved: true,
          has_applied: false,
          is_expired: false,
        },
      },
      {
        id: "saved-2",
        job_id: "job-102",
        saved_at: new Date().toISOString(),
        job: {
          id: "job-102",
          tenant_id: "tenant-2",
          organization_name: "Nexus AI",
          title: "Senior AI Researcher",
          department: "Research",
          location: "New York, NY",
          remote_type: "onsite",
          employment_type: "full_time",
          required_skills: ["PyTorch"],
          is_saved: true,
          has_applied: true,
          is_expired: true,
        },
      },
    ];

    it("renders saved jobs list with expired and applied indicators", async () => {
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue(mockSavedJobs);

      render(<CandidateSavedJobsPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
        expect(screen.getByText("Senior AI Researcher")).toBeDefined();
      });

      expect(screen.getByText("Applied")).toBeDefined();
      expect(screen.getByText("Position Closed / Expired")).toBeDefined();
    });

    it("allows removing a saved job", async () => {
      vi.spyOn(candidateApi, "getSavedJobs").mockResolvedValue(mockSavedJobs);
      const unsaveSpy = vi.spyOn(candidateApi, "unsaveJob").mockResolvedValue(undefined);

      render(<CandidateSavedJobsPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
      });

      const removeBtns = screen.getAllByRole("button", { name: /Remove saved job/i });
      fireEvent.click(removeBtns[0]);

      await waitFor(() => {
        expect(unsaveSpy).toHaveBeenCalledWith("job-101");
      });
    });
  });
});
