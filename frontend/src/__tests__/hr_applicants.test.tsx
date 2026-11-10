import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import HrApplicantsPage from "@/app/hr/applicants/page";
import CandidateDetailPage from "@/app/hr/candidates/[id]/page";
import { hrApi } from "@/lib/hrApi";
import type {
  ApplicantListItem,
  ApplicantListResponse,
  CandidateComparisonResponse,
  CandidateDetailResponse,
  JobRequisition,
  ResumeSignedUrlResponse,
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

const mockApplicants: ApplicantListItem[] = [
  {
    id: "app-1111",
    candidate_id: "cand-1111",
    candidate_name: "Jane Doe",
    candidate_email: "jane.doe@example.com",
    candidate_phone: "+1-555-0100",
    candidate_headline: "Senior Cloud Engineer",
    candidate_location: "Austin, TX",
    job_id: "job-1111",
    job_title: "Senior Python Platform Engineer",
    job_department: "Engineering",
    job_location: "Austin, TX",
    status: "in_screening",
    candidate_status: "under_review",
    applied_at: "2026-11-01T10:00:00Z",
    skills: ["Python", "FastAPI", "Docker", "PostgreSQL"],
    experience_years: 4.5,
    current_job_title: "Backend Engineer",
    current_company: "CloudScale Inc",
    resume_available: true,
    resume_id: "res-1111",
    resume_filename: "Jane_Doe_Resume.pdf",
    recruiter_id: "rec-1",
    recruiter_name: "Alice Recruiter",
    hiring_manager_id: "hm-1",
    hiring_manager_name: "Bob Manager",
    last_activity_at: "2026-11-02T12:00:00Z",
  },
  {
    id: "app-2222",
    candidate_id: "cand-2222",
    candidate_name: "John Smith",
    candidate_email: "john.smith@example.com",
    candidate_headline: "Full Stack Developer",
    candidate_location: "San Francisco, CA",
    job_id: "job-1111",
    job_title: "Senior Python Platform Engineer",
    job_department: "Engineering",
    job_location: "Austin, TX",
    status: "submitted",
    candidate_status: "submitted",
    applied_at: "2026-11-03T14:00:00Z",
    skills: ["Python", "React", "AWS"],
    experience_years: 3.0,
    current_job_title: "Full Stack Dev",
    current_company: "DevCorp",
    resume_available: false,
    last_activity_at: "2026-11-03T14:00:00Z",
  },
];

const mockListResponse: ApplicantListResponse = {
  items: mockApplicants,
  total: 2,
  page: 1,
  page_size: 20,
  pages: 1,
};

const mockJobs: JobRequisition[] = [
  {
    id: "job-1111",
    tenant_id: "tenant-1",
    title: "Senior Python Platform Engineer",
    slug: "sr-python-platform-eng",
    department: "Engineering",
    location: "Austin, TX",
    remote_type: "hybrid",
    employment_type: "full_time",
    experience_level: "senior",
    description: "Build scalable cloud platform.",
    skills_required: ["Python", "FastAPI", "Docker"],
    preferred_skills: ["Kubernetes"],
    vacancies_count: 1,
    salary_currency: "USD",
    status: "published",
    approval_status: "approved",
    visibility: "public",
    applications_count: 2,
    created_at: "2026-10-20T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
  },
];

const mockTeamMembers: TeamMemberOption[] = [
  {
    id: "rec-1",
    name: "Alice Recruiter",
    email: "alice@acme.com",
    role: "recruiter",
  },
];

const mockCandidateDetails: CandidateDetailResponse = {
  candidate_id: "cand-1111",
  first_name: "Jane",
  last_name: "Doe",
  full_name: "Jane Doe",
  email: "jane.doe@example.com",
  phone_number: "+1-555-0100",
  headline: "Senior Cloud Engineer",
  bio: "Experienced cloud infrastructure engineer.",
  location_city: "Austin",
  location_country: "United States",
  preferred_title: "Staff Engineer",
  work_authorization: "US Citizen",
  portfolio_urls: ["https://janedoe.dev"],
  skills: ["Python", "FastAPI", "Docker", "PostgreSQL"],
  experience_years: 4.5,
  experiences: [
    {
      id: "exp-1",
      job_title: "Backend Engineer",
      company_name: "CloudScale Inc",
      location: "Austin, TX",
      start_date: "2022-01",
      end_date: null,
      is_current: true,
      description: "Scaled backend services to 10k RPS.",
      skills: ["Python", "FastAPI"],
    },
  ],
  educations: [
    {
      id: "edu-1",
      institution: "University of Texas at Austin",
      degree: "B.S. Computer Science",
      field_of_study: "Computer Science",
      start_year: 2017,
      end_year: 2021,
      grade: "3.9 GPA",
    },
  ],
  certifications: [
    {
      id: "cert-1",
      name: "AWS Solutions Architect Associate",
      issuing_organization: "Amazon Web Services",
      issue_date: "2023",
    },
  ],
  projects: [
    {
      id: "proj-1",
      title: "Distributed Scheduler",
      description: "Fault tolerant scheduler in Python.",
      role: "Lead Author",
      project_url: "https://github.com/janedoe/scheduler",
      skills: ["Python", "Redis"],
    },
  ],
  languages: [
    {
      id: "lang-1",
      language: "English",
      proficiency: "native",
    },
  ],
  current_application: {
    application_id: "app-1111",
    job_id: "job-1111",
    job_title: "Senior Python Platform Engineer",
    job_department: "Engineering",
    job_location: "Austin, TX",
    recruiter_name: "Alice Recruiter",
    hiring_manager_name: "Bob Manager",
    status: "in_screening",
    candidate_status: "under_review",
    applied_at: "2026-11-01T10:00:00Z",
    cover_letter: "Excited to join Acme Cloud and scale backend infrastructure.",
    answers: {},
    resume_id: "res-1111",
    resume_filename: "Jane_Doe_Resume.pdf",
    candidate_timeline: [
      {
        status: "submitted",
        changed_at: "2026-11-01T10:00:00Z",
        note: "Application received",
        is_internal: false,
      },
    ],
    internal_timeline: [
      {
        status: "in_screening",
        changed_at: "2026-11-02T12:00:00Z",
        note: "Moved candidate to technical screening stage",
        is_internal: true,
      },
    ],
  },
  organization_application_history: [
    {
      application_id: "app-1111",
      job_id: "job-1111",
      job_title: "Senior Python Platform Engineer",
      department: "Engineering",
      applied_at: "2026-11-01T10:00:00Z",
      status: "in_screening",
      candidate_status: "under_review",
    },
  ],
};

const mockComparisonResponse: CandidateComparisonResponse = {
  job_id: "job-1111",
  job_title: "Senior Python Platform Engineer",
  candidates: [
    {
      application_id: "app-1111",
      candidate_id: "cand-1111",
      candidate_name: "Jane Doe",
      candidate_email: "jane.doe@example.com",
      job_id: "job-1111",
      job_title: "Senior Python Platform Engineer",
      status: "in_screening",
      applied_at: "2026-11-01T10:00:00Z",
      experience_years: 4.5,
      current_job_title: "Backend Engineer",
      current_company: "CloudScale Inc",
      highest_education: "B.S. Computer Science",
      skills: ["Python", "FastAPI", "Docker", "PostgreSQL"],
      job_skills_required: ["Python", "FastAPI", "Docker"],
      matching_skills: ["Python", "FastAPI", "Docker"],
      missing_skills: [],
      match_percentage: 100.0,
      resume_available: true,
    },
    {
      application_id: "app-2222",
      candidate_id: "cand-2222",
      candidate_name: "John Smith",
      candidate_email: "john.smith@example.com",
      job_id: "job-1111",
      job_title: "Senior Python Platform Engineer",
      status: "submitted",
      applied_at: "2026-11-03T14:00:00Z",
      experience_years: 3.0,
      current_job_title: "Full Stack Dev",
      current_company: "DevCorp",
      highest_education: "B.A.",
      skills: ["Python", "React", "AWS"],
      job_skills_required: ["Python", "FastAPI", "Docker"],
      matching_skills: ["Python"],
      missing_skills: ["FastAPI", "Docker"],
      match_percentage: 33.3,
      resume_available: false,
    },
  ],
};

describe("HR Applicant and Candidate Management (Frontend)", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
    vi.spyOn(hrApi, "listApplicants").mockResolvedValue({ ...mockListResponse });
    vi.spyOn(hrApi, "listJobs").mockResolvedValue({
      items: mockJobs,
      total: 1,
      page: 1,
      page_size: 100,
      pages: 1,
    });
    vi.spyOn(hrApi, "getTeamMembers").mockResolvedValue(mockTeamMembers);
    vi.spyOn(hrApi, "getCandidateDetails").mockResolvedValue({ ...mockCandidateDetails });
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("renders applicant pool page with candidate rows, status badges, and skills", async () => {
    render(<HrApplicantsPage />);

    await waitFor(() => {
      expect(screen.getByText("Applicant Pool & Candidates")).toBeDefined();
      expect(screen.getByText("Jane Doe")).toBeDefined();
      expect(screen.getByText("John Smith")).toBeDefined();
    });

    // Experience badges
    expect(screen.getByText("4.5 yrs exp")).toBeDefined();
    expect(screen.getByText("3 yrs exp")).toBeDefined();

    // Stage badges
    expect(screen.getByText("in screening")).toBeDefined();
    expect(screen.getByText("submitted")).toBeDefined();
  });

  it("triggers filter and search reloads on input change", async () => {
    const listSpy = vi.spyOn(hrApi, "listApplicants").mockResolvedValue(mockListResponse);

    render(<HrApplicantsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("applicant-search-input")).toBeDefined();
    });

    fireEvent.change(screen.getByTestId("applicant-search-input"), {
      target: { value: "Jane" },
    });

    await waitFor(() => {
      expect(listSpy).toHaveBeenCalledWith(
        expect.objectContaining({
          search: "Jane",
        })
      );
    });
  });

  it("handles multi-select and opens candidate comparison matrix", async () => {
    vi.spyOn(hrApi, "compareCandidates").mockResolvedValue(mockComparisonResponse);

    render(<HrApplicantsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("checkbox-app-1111")).toBeDefined();
    });

    // Select two candidates
    fireEvent.click(screen.getByTestId("checkbox-app-1111"));
    fireEvent.click(screen.getByTestId("checkbox-app-2222"));

    // Compare button should appear and be enabled
    const compareBtn = screen.getByTestId("btn-compare-candidates");
    expect(compareBtn).toBeDefined();

    fireEvent.click(compareBtn);

    await waitFor(() => {
      expect(screen.getByText("Candidate Comparison Matrix")).toBeDefined();
      expect(screen.getByText("100%")).toBeDefined();
      expect(screen.getByText("33.3%")).toBeDefined();
    });
  });

  it("handles bulk recruiter assignment modal and submission", async () => {
    const assignSpy = vi.spyOn(hrApi, "bulkAssignRecruiter").mockResolvedValue({
      updated_count: 1,
      application_ids: ["app-1111"],
      recruiter_id: "rec-1",
      recruiter_name: "Alice Recruiter",
    });

    render(<HrApplicantsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("checkbox-app-1111")).toBeDefined();
    });

    // Select candidate
    fireEvent.click(screen.getByTestId("checkbox-app-1111"));

    // Click assign recruiter
    const assignBtn = screen.getByTestId("btn-bulk-assign-recruiter");
    fireEvent.click(assignBtn);

    expect(screen.getAllByText("Assign Recruiter").length).toBeGreaterThanOrEqual(2);

    // Select recruiter
    const selectRecruiter = screen.getByTestId("select-assign-recruiter");
    fireEvent.change(selectRecruiter, { target: { value: "rec-1" } });

    // Submit
    const confirmBtn = screen.getByTestId("btn-confirm-bulk-assign");
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(assignSpy).toHaveBeenCalledWith(["app-1111"], "rec-1");
    });
  });

  it("handles resume download presigned URL generation", async () => {
    const resumeSpy = vi.spyOn(hrApi, "getApplicationResumeUrl").mockResolvedValue({
      application_id: "app-1111",
      candidate_id: "cand-1111",
      filename: "Jane_Doe_Resume.pdf",
      mime_type: "application/pdf",
      file_size_bytes: 1048576,
      content_sha256: "sha256_mock_hash",
      download_url: "https://s3.mock.domain/resume.pdf?sig=valid",
      expires_in_seconds: 900,
    });

    const windowSpy = vi.spyOn(window, "open").mockImplementation(() => null);

    render(<HrApplicantsPage />);

    await waitFor(() => {
      expect(screen.getByTestId("btn-download-resume-app-1111")).toBeDefined();
    });

    fireEvent.click(screen.getByTestId("btn-download-resume-app-1111"));

    await waitFor(() => {
      expect(resumeSpy).toHaveBeenCalledWith("app-1111");
      expect(windowSpy).toHaveBeenCalledWith(
        "https://s3.mock.domain/resume.pdf?sig=valid",
        "_blank",
        "noopener,noreferrer"
      );
    });
  });

  it("renders CandidateDetailPage with full profile, portfolio, and separated timelines", async () => {
    render(<CandidateDetailPage />);

    await waitFor(() => {
      expect(screen.getAllByText("Jane Doe").length).toBeGreaterThanOrEqual(1);
    });

    // Profile summary
    expect(screen.getByText("Senior Cloud Engineer")).toBeDefined();
    expect(screen.getByText("Experienced cloud infrastructure engineer.")).toBeDefined();
    expect(screen.getByText("US Citizen")).toBeDefined();

    // Experience
    expect(screen.getByText("Backend Engineer")).toBeDefined();
    expect(screen.getByText("CloudScale Inc • Austin, TX")).toBeDefined();

    // Education
    expect(screen.getByText("B.S. Computer Science in Computer Science")).toBeDefined();
    expect(screen.getByText("University of Texas at Austin")).toBeDefined();

    // Timeline separation
    expect(screen.getByText("Internal HR Activity & Notes")).toBeDefined();
    expect(screen.getByText("Moved candidate to technical screening stage")).toBeDefined();

    expect(screen.getByText("Candidate-Facing Journey")).toBeDefined();
    expect(screen.getByText("Application received")).toBeDefined();

    // Organization application history
    expect(screen.getByText("Organization Application History")).toBeDefined();
  });
});
