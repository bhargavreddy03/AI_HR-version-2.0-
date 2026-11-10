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
import CandidateApplicationsPage from "@/app/candidate/applications/page";
import CandidateApplicationDetailPage from "@/app/candidate/applications/[id]/page";
import CandidateSettingsPage from "@/app/candidate/settings/page";
import CandidateInterviewsPage from "@/app/candidate/interviews/page";
import { ApplicationSubmitModal } from "@/components/candidate/ApplicationSubmitModal";
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
      expect(screen.getByText("Interviews")).toBeDefined();
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
      expect(screen.getAllByText("Applied").length).toBeGreaterThanOrEqual(1);
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

  describe("ApplicationSubmitModal", () => {
    const mockJobDetail = {
      id: "job-200",
      tenant_id: "tenant-1",
      organization_name: "Acme Cloud",
      title: "Staff Site Reliability Engineer",
      slug: "staff-sre",
      department: "Infrastructure",
      location: "San Francisco, CA",
      remote_type: "remote",
      employment_type: "full_time",
      description: "Scale high-throughput kubernetes clusters.",
      required_skills: ["Kubernetes", "Go", "Terraform"],
      published_at: new Date().toISOString(),
      created_at: new Date().toISOString(),
    };

    const mockResumes = [
      {
        id: "res-101",
        file_name: "staff_sre_resume.pdf",
        file_size_bytes: 120400,
        mime_type: "application/pdf",
        sha256_hash: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        version_number: 1,
        is_default: true,
        extracted_skills: ["Kubernetes", "Go"],
        uploaded_at: new Date().toISOString(),
      },
    ];

    it("guides candidate through multi-step application workflow and submits with consent", async () => {
      vi.spyOn(candidateApi, "getResumes").mockResolvedValue(mockResumes);
      const applySpy = vi.spyOn(candidateApi, "applyJob").mockResolvedValue({
        id: "app-301",
        job_id: "job-200",
        candidate_status: "submitted",
        resume_snapshot_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        resume_version_applied: 1,
        message: "Application submitted successfully",
        applied_at: new Date().toISOString(),
      });

      const handleClose = vi.fn();
      const handleSuccess = vi.fn();

      render(
        <ApplicationSubmitModal
          job={mockJobDetail}
          onClose={handleClose}
          onSuccess={handleSuccess}
        />
      );

      // Step 1: Requisition Overview
      expect(screen.getByText(/Staff Site Reliability Engineer/i)).toBeDefined();
      expect(screen.getByText("Acme Cloud")).toBeDefined();

      const continueBtn = screen.getByRole("button", { name: /Continue/i });
      fireEvent.click(continueBtn);

      // Step 2: Resume Selection
      await waitFor(() => {
        expect(screen.getByText("staff_sre_resume.pdf")).toBeDefined();
      });
      fireEvent.click(continueBtn);

      // Step 3: Application Questionnaire
      await waitFor(() => {
        expect(screen.getByText("Application Questionnaire")).toBeDefined();
      });
      const coverLetterInput = screen.getByPlaceholderText(/Highlight your relevant experience/i);
      fireEvent.change(coverLetterInput, {
        target: { value: "Experienced SRE with 8+ years scaling production clusters." },
      });
      fireEvent.click(continueBtn);

      // Step 4: Review & Legal Consents
      await waitFor(() => {
        expect(screen.getByText("Review & Confirm Submission")).toBeDefined();
      });

      // Check both checkboxes
      const checkboxes = screen.getAllByRole("checkbox");
      expect(checkboxes.length).toBe(2);
      fireEvent.click(checkboxes[0]);
      fireEvent.click(checkboxes[1]);

      const submitBtn = screen.getByRole("button", { name: /Confirm & Submit Application/i });
      fireEvent.click(submitBtn);

      await waitFor(() => {
        expect(applySpy).toHaveBeenCalledWith(
          "job-200",
          expect.objectContaining({
            resume_id: "res-101",
            cover_letter: "Experienced SRE with 8+ years scaling production clusters.",
            answers: expect.objectContaining({
              work_authorization: "authorized",
            }),
            consent_records: expect.objectContaining({
              data_processing_consent: true,
              accuracy_certified: true,
            }),
          })
        );
      });

      await waitFor(() => {
        expect(screen.getByText("Application Submitted Successfully!")).toBeDefined();
      });
      expect(handleSuccess).toHaveBeenCalledTimes(1);
    });
  });

  describe("CandidateApplicationsPage", () => {
    const mockApps = [
      {
        id: "app-1",
        job_id: "job-101",
        tenant_id: "tenant-1",
        organization_name: "Acme Corp",
        job_title: "Principal Cloud Architect",
        job_department: "Engineering",
        job_location: "San Francisco, CA",
        remote_type: "remote",
        candidate_status: "under_review",
        applied_at: new Date().toISOString(),
        resume_version_applied: 2,
        resume_snapshot_sha256: "sha256_mock_hash",
      },
      {
        id: "app-2",
        job_id: "job-102",
        tenant_id: "tenant-2",
        organization_name: "Nexus AI",
        job_title: "Senior AI Engineer",
        job_department: "Research",
        job_location: "New York, NY",
        remote_type: "hybrid",
        candidate_status: "withdrawn",
        applied_at: new Date().toISOString(),
        withdrawn_at: new Date().toISOString(),
        withdrawal_reason: "Accepted another role",
        resume_version_applied: 1,
        resume_snapshot_sha256: "sha256_mock_hash_2",
      },
    ];

    it("renders applications history with status badges and sealed evidence", async () => {
      vi.spyOn(candidateApi, "getMyApplications").mockResolvedValue(mockApps);

      render(<CandidateApplicationsPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
        expect(screen.getByText("Senior AI Engineer")).toBeDefined();
      });

      expect(screen.getByText("Acme Corp")).toBeDefined();
      expect(screen.getByText("Nexus AI")).toBeDefined();
      expect(screen.getByText("Resume v2")).toBeDefined();
      expect(screen.getAllByText(/SHA-256 Sealed/i).length).toBeGreaterThanOrEqual(1);
    });

    it("allows candidate to withdraw an eligible application with reason", async () => {
      vi.spyOn(candidateApi, "getMyApplications").mockResolvedValue(mockApps);
      const withdrawSpy = vi.spyOn(candidateApi, "withdrawApplication").mockResolvedValue({
        ...mockApps[0],
        candidate_status: "withdrawn",
        withdrawn_at: new Date().toISOString(),
        withdrawal_reason: "Personal circumstances",
        timeline: [],
      });

      render(<CandidateApplicationsPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
      });

      const withdrawBtn = screen.getByRole("button", { name: /^Withdraw$/i });
      fireEvent.click(withdrawBtn);

      await waitFor(() => {
        expect(screen.getByText("Confirm Application Withdrawal")).toBeDefined();
      });

      const reasonInput = screen.getByPlaceholderText(/Accepted another/i);
      fireEvent.change(reasonInput, { target: { value: "Personal circumstances" } });

      const confirmBtn = screen.getByRole("button", { name: /Confirm Withdrawal/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(withdrawSpy).toHaveBeenCalledWith("app-1", "Personal circumstances");
      });
    });
  });

  describe("CandidateApplicationDetailPage", () => {
    const mockAppDetail = {
      id: "app-1",
      job_id: "job-101",
      tenant_id: "tenant-1",
      organization_name: "Acme Corp",
      job_title: "Principal Cloud Architect",
      job_department: "Engineering",
      job_location: "San Francisco, CA",
      remote_type: "remote",
      candidate_status: "under_review",
      applied_at: new Date().toISOString(),
      resume_version_applied: 2,
      resume_filename: "principal_cloud_architect.pdf",
      resume_snapshot_sha256: "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
      cover_letter: "Excited to apply for this leadership role.",
      answers: {
        work_authorization: "authorized",
        visa_sponsorship_required: false,
        earliest_start_date: "2 weeks notice",
      },
      consent_records: {
        data_processing_consent: true,
        accuracy_certified: true,
      },
      timeline: [
        {
          status: "submitted",
          changed_at: new Date(Date.now() - 86400000).toISOString(),
          note: "Application submitted and evidence sealed.",
        },
        {
          status: "under_review",
          changed_at: new Date().toISOString(),
          note: "Application under hiring team review.",
        },
      ],
    };

    it("renders detailed application overview, timeline events, and questionnaire responses", async () => {
      vi.spyOn(candidateApi, "getApplicationDetail").mockResolvedValue(mockAppDetail);

      render(<CandidateApplicationDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
        expect(screen.getByText("Acme Corp")).toBeDefined();
      });

      expect(screen.getByText("Excited to apply for this leadership role.")).toBeDefined();
      expect(screen.getByText("Application under hiring team review.")).toBeDefined();
      expect(screen.getByText("principal_cloud_architect.pdf")).toBeDefined();
      expect(screen.getByText("2 weeks notice")).toBeDefined();
      expect(screen.getByText("SHA-256 Verified")).toBeDefined();
    });

    it("opens withdrawal dialog from detail view and updates candidate status", async () => {
      vi.spyOn(candidateApi, "getApplicationDetail").mockResolvedValue(mockAppDetail);
      const withdrawSpy = vi.spyOn(candidateApi, "withdrawApplication").mockResolvedValue({
        ...mockAppDetail,
        candidate_status: "withdrawn",
        withdrawn_at: new Date().toISOString(),
        withdrawal_reason: "Timing not aligned",
      });

      render(<CandidateApplicationDetailPage />);

      await waitFor(() => {
        expect(screen.getByText("Principal Cloud Architect")).toBeDefined();
      });

      const withdrawBtn = screen.getByRole("button", { name: /Withdraw Application/i });
      fireEvent.click(withdrawBtn);

      await waitFor(() => {
        expect(screen.getByText(/Are you sure you wish to withdraw/i)).toBeDefined();
      });

      const reasonInput = screen.getByPlaceholderText(/Accepted another/i);
      fireEvent.change(reasonInput, { target: { value: "Timing not aligned" } });

      const confirmBtn = screen.getByRole("button", { name: /Confirm Withdrawal/i });
      fireEvent.click(confirmBtn);

      await waitFor(() => {
        expect(withdrawSpy).toHaveBeenCalledWith("app-1", "Timing not aligned");
      });
    });
  });

  describe("CandidateInterviewsPage", () => {
    it("renders empty state cleanly when no interviews are scheduled", async () => {
      vi.spyOn(candidateApi, "getInterviews").mockResolvedValue({
        interviews: [],
        total: 0,
      });

      render(<CandidateInterviewsPage />);

      await waitFor(() => {
        expect(screen.getByText("No Scheduled Interviews")).toBeDefined();
        expect(screen.getByText(/scheduled sessions, video conference links/i)).toBeDefined();
      });
    });

    it("renders scheduled interviews with date, type badge, interviewer, and meeting link", async () => {
      vi.spyOn(candidateApi, "getInterviews").mockResolvedValue({
        interviews: [
          {
            id: "int-1",
            application_id: "app-101",
            job_title: "Staff Platform Engineer",
            organization_name: "Acme Cloud Corp",
            interview_type: "technical",
            scheduled_at: "2026-11-20T14:00:00Z",
            duration_minutes: 60,
            timezone: "America/New_York",
            status: "scheduled",
            meeting_url: "https://meet.example.com/interview-123",
            meeting_instructions: "Please join with webcam enabled and repo ready.",
            interviewer_name: "Sarah Chen, VP Engineering",
            interviewer_role: "VP Engineering",
            rescheduled_reason: null,
            cancellation_reason: null,
          },
        ],
        total: 1,
      });

      render(<CandidateInterviewsPage />);

      await waitFor(() => {
        expect(screen.getByText("Staff Platform Engineer")).toBeDefined();
        expect(screen.getByText("Acme Cloud Corp")).toBeDefined();
      });

      expect(screen.getByText("technical")).toBeDefined();
      expect(screen.getByText(/Sarah Chen, VP Engineering/i)).toBeDefined();
      expect(screen.getByText(/Please join with webcam enabled/i)).toBeDefined();
      expect(screen.getByRole("link", { name: /Join Video Call/i })).toBeDefined();
    });
  });

  describe("CandidateSettingsPage", () => {
    const mockAccount = {
      id: "usr-candidate-1",
      email: "candidate@example.com",
      first_name: "Alex",
      last_name: "Rivera",
      phone_number: "+1 555-0199",
      email_verified: true,
      last_login_at: "2026-11-09T10:00:00Z",
      mfa_enabled: false,
    };

    const mockNotifPrefs = {
      in_app_alerts: true,
      email_application_updates: true,
      email_interview_alerts: true,
      email_job_recommendations: false,
      digest_frequency: "instant" as const,
    };

    const mockPrivacyPrefs = {
      profile_visibility: "applied_only" as const,
      allow_ai_matching: true,
      data_retention_months: 24,
    };

    const mockCareerPrefs = {
      desired_job_titles: ["Lead Backend Engineer"],
      desired_locations: ["Remote", "New York, NY"],
      remote_preference: "remote" as const,
      employment_types: ["full_time"],
      minimum_salary: 175000,
      currency: "USD",
    };

    const mockConsentHistory = {
      consents: [
        {
          consent_type: "terms_of_service",
          granted: true,
          recorded_at: "2026-11-01T09:00:00Z",
          ip_address: "192.168.1.1",
          version: "v2.0",
        },
      ],
      total: 1,
    };

    it("renders account information and email verification status", async () => {
      vi.spyOn(candidateApi, "getAccountInfo").mockResolvedValue(mockAccount);
      vi.spyOn(candidateApi, "getNotificationPreferences").mockResolvedValue(mockNotifPrefs);
      vi.spyOn(candidateApi, "getPrivacyPreferences").mockResolvedValue(mockPrivacyPrefs);
      vi.spyOn(candidateApi, "getPreferences").mockResolvedValue(mockCareerPrefs);
      vi.spyOn(candidateApi, "getConsentHistory").mockResolvedValue(mockConsentHistory);

      render(<CandidateSettingsPage />);

      await waitFor(() => {
        expect(screen.getByText("candidate@example.com")).toBeDefined();
        expect(screen.getByText("Verified Account")).toBeDefined();
      });

      expect(screen.getByDisplayValue("Alex")).toBeDefined();
      expect(screen.getByDisplayValue("Rivera")).toBeDefined();
    });

    it("switches to Notification Preferences tab and saves changes", async () => {
      vi.spyOn(candidateApi, "getAccountInfo").mockResolvedValue(mockAccount);
      vi.spyOn(candidateApi, "getNotificationPreferences").mockResolvedValue(mockNotifPrefs);
      vi.spyOn(candidateApi, "getPrivacyPreferences").mockResolvedValue(mockPrivacyPrefs);
      vi.spyOn(candidateApi, "getPreferences").mockResolvedValue(mockCareerPrefs);
      vi.spyOn(candidateApi, "getConsentHistory").mockResolvedValue(mockConsentHistory);
      const updateNotifSpy = vi.spyOn(candidateApi, "updateNotificationPreferences").mockResolvedValue({
        ...mockNotifPrefs,
        email_job_recommendations: true,
      });

      render(<CandidateSettingsPage />);

      await waitFor(() => {
        expect(screen.getByText("candidate@example.com")).toBeDefined();
      });

      const notifTab = screen.getByRole("button", { name: /Notifications/i });
      fireEvent.click(notifTab);

      await waitFor(() => {
        expect(screen.getByText("In-App Notification Alerts")).toBeDefined();
      });

      const saveBtn = screen.getByRole("button", { name: /Save Notification Preferences/i });
      fireEvent.click(saveBtn);

      await waitFor(() => {
        expect(updateNotifSpy).toHaveBeenCalled();
      });
    });

    it("displays statutory retention warnings on account erasure section", async () => {
      vi.spyOn(candidateApi, "getAccountInfo").mockResolvedValue(mockAccount);
      vi.spyOn(candidateApi, "getNotificationPreferences").mockResolvedValue(mockNotifPrefs);
      vi.spyOn(candidateApi, "getPrivacyPreferences").mockResolvedValue(mockPrivacyPrefs);
      vi.spyOn(candidateApi, "getPreferences").mockResolvedValue(mockCareerPrefs);
      vi.spyOn(candidateApi, "getConsentHistory").mockResolvedValue(mockConsentHistory);

      render(<CandidateSettingsPage />);

      await waitFor(() => {
        expect(screen.getByText("candidate@example.com")).toBeDefined();
      });

      const rightsTab = screen.getByRole("button", { name: /Data Subject Rights/i });
      fireEvent.click(rightsTab);

      await waitFor(() => {
        expect(screen.getByText("Mandatory Legal Recordkeeping Notice")).toBeDefined();
        expect(screen.getByText(/EEOC/i)).toBeDefined();
        expect(screen.getByText("Request Account Erasure")).toBeDefined();
      });
    });
  });
});
