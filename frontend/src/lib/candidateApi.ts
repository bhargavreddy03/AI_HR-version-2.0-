import { getApiBaseUrl } from "./api";
import type {
  CandidateFullProfile,
  CandidateExperience,
  CandidateEducation,
  CandidateCertification,
  CandidateProject,
  CandidateLanguage,
  CandidatePreference,
  CandidateResume,
  ResumeExtractionResponse,
  JobPublicSummary,
  JobDetail,
  JobListResponse,
  SavedJobItem,
  CandidateApplicationSummary,
  CandidateApplicationDetail,
  ApplicationSubmitResponse,
  CandidateNotification,
  CandidateAccount,
  NotificationPreferences,
  PrivacyPreferences,
  CandidateInterview,
  PersonalDataExport,
  CorrectionRequestPayload,
  CorrectionRequestResponse,
  DeletionRequestPayload,
  DeletionRequestResponse,
  ConsentHistoryItem,
} from "@/types/candidate";

async function fetchWithAuth<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const url = `${baseUrl}${endpoint}`;

  const headers: Record<string, string> = {
    Accept: "application/json",
    ...(options.headers as Record<string, string>),
  };

  // If body is not FormData, add Content-Type: application/json
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }

  // Support local token fallback if available in localStorage
  if (typeof window !== "undefined") {
    const token = localStorage.getItem("token") || localStorage.getItem("access_token");
    if (token && !headers["Authorization"]) {
      headers["Authorization"] = `Bearer ${token}`;
    }
  }

  const response = await fetch(url, {
    ...options,
    headers,
    credentials: "include",
  });

  if (!response.ok) {
    let errorDetail = `Request failed with status ${response.status}`;
    try {
      const errJson = await response.json();
      errorDetail = errJson.detail || errJson.message || errorDetail;
    } catch {
      // fallback
    }
    throw new Error(errorDetail);
  }

  if (response.status === 204) {
    return null as T;
  }

  return response.json();
}

export const candidateApi = {
  // Profile
  getProfile: () => fetchWithAuth<CandidateFullProfile>("/candidates/me"),
  updateProfile: (data: {
    headline?: string;
    bio?: string;
    years_of_experience?: number;
    phone?: string;
    location_city?: string;
    location_country?: string;
    preferred_title?: string;
    work_authorization?: string;
  }) =>
    fetchWithAuth<CandidateFullProfile>("/candidates/me", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Skills
  updateSkills: (skills: string[]) =>
    fetchWithAuth<{ skills: string[] }>("/candidates/me/skills", {
      method: "PUT",
      body: JSON.stringify({ skills }),
    }),
  suggestSkills: (q: string) =>
    fetchWithAuth<{ suggestions: string[] }>(`/candidates/skills/suggest?q=${encodeURIComponent(q)}`),

  // Experiences
  addExperience: (data: Omit<CandidateExperience, "id">) =>
    fetchWithAuth<CandidateExperience>("/candidates/me/experiences", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteExperience: (id: string) =>
    fetchWithAuth<void>(`/candidates/me/experiences/${id}`, {
      method: "DELETE",
    }),

  // Education
  addEducation: (data: Omit<CandidateEducation, "id">) =>
    fetchWithAuth<CandidateEducation>("/candidates/me/education", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteEducation: (id: string) =>
    fetchWithAuth<void>(`/candidates/me/education/${id}`, {
      method: "DELETE",
    }),

  // Certifications
  addCertification: (data: Omit<CandidateCertification, "id">) =>
    fetchWithAuth<CandidateCertification>("/candidates/me/certifications", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteCertification: (id: string) =>
    fetchWithAuth<void>(`/candidates/me/certifications/${id}`, {
      method: "DELETE",
    }),

  // Projects
  addProject: (data: Omit<CandidateProject, "id">) =>
    fetchWithAuth<CandidateProject>("/candidates/me/projects", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteProject: (id: string) =>
    fetchWithAuth<void>(`/candidates/me/projects/${id}`, {
      method: "DELETE",
    }),

  // Languages
  addLanguage: (data: Omit<CandidateLanguage, "id">) =>
    fetchWithAuth<CandidateLanguage>("/candidates/me/languages", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  deleteLanguage: (id: string) =>
    fetchWithAuth<void>(`/candidates/me/languages/${id}`, {
      method: "DELETE",
    }),

  // Preferences
  getPreferences: () =>
    fetchWithAuth<CandidatePreference>("/candidates/me/preferences"),
  updatePreferences: (data: Partial<CandidatePreference>) =>
    fetchWithAuth<CandidatePreference>("/candidates/me/preferences", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Resumes
  getResumes: () => fetchWithAuth<CandidateResume[]>("/resumes/me"),
  uploadResume: (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    return fetchWithAuth<CandidateResume>("/resumes/me/upload", {
      method: "POST",
      body: formData,
    });
  },
  setDefaultResume: (id: string) =>
    fetchWithAuth<CandidateResume>(`/resumes/me/${id}/set-default`, {
      method: "PUT",
    }),
  deleteResume: (id: string) =>
    fetchWithAuth<void>(`/resumes/me/${id}`, {
      method: "DELETE",
    }),
  getResumeDownloadUrl: (id: string) =>
    fetchWithAuth<{ download_url: string; expires_in_seconds: number }>(`/resumes/me/${id}/download`),
  getResumeExtraction: (id: string) =>
    fetchWithAuth<ResumeExtractionResponse>(`/resumes/me/${id}/extraction`),
  updateResumeSkills: (id: string, skills: string[]) =>
    fetchWithAuth<CandidateResume>(`/resumes/me/${id}/skills`, {
      method: "PUT",
      body: JSON.stringify({ skills }),
    }),
  syncResumeSkillsToProfile: (id: string) =>
    fetchWithAuth<{ skills: string[] }>(`/resumes/${id}/sync-profile`, {
      method: "POST",
    }),

  // Jobs
  searchJobs: (params?: {
    query?: string;
    department?: string;
    location?: string;
    remote_type?: string;
    employment_type?: string;
    experience_level?: string;
    skills?: string | string[];
    min_salary?: number;
    max_salary?: number;
    posted_within_days?: number;
    sort_by?: "recent" | "closing_soon" | "salary_high" | string;
    page?: number;
    page_size?: number;
    limit?: number;
    offset?: number;
  }) => {
    const searchParams = new URLSearchParams();
    if (params) {
      if (params.query) searchParams.append("query", params.query);
      if (params.department) searchParams.append("department", params.department);
      if (params.location) searchParams.append("location", params.location);
      if (params.remote_type) searchParams.append("remote_type", params.remote_type);
      if (params.employment_type) searchParams.append("employment_type", params.employment_type);
      if (params.experience_level) searchParams.append("experience_level", params.experience_level);
      if (params.skills) {
        if (Array.isArray(params.skills)) {
          params.skills.forEach((s) => searchParams.append("skills", s));
        } else {
          searchParams.append("skills", params.skills);
        }
      }
      if (params.min_salary !== undefined && params.min_salary !== null) {
        searchParams.append("min_salary", params.min_salary.toString());
      }
      if (params.max_salary !== undefined && params.max_salary !== null) {
        searchParams.append("max_salary", params.max_salary.toString());
      }
      if (params.posted_within_days !== undefined && params.posted_within_days !== null) {
        searchParams.append("posted_within_days", params.posted_within_days.toString());
      }
      if (params.sort_by) searchParams.append("sort_by", params.sort_by);
      if (params.page) searchParams.append("page", params.page.toString());
      if (params.page_size) searchParams.append("page_size", params.page_size.toString());
      if (params.limit) searchParams.append("limit", params.limit.toString());
      if (params.offset) searchParams.append("offset", params.offset.toString());
    }
    const qs = searchParams.toString();
    return fetchWithAuth<JobListResponse>(`/jobs/search${qs ? `?${qs}` : ""}`);
  },
  getJob: (id: string) => fetchWithAuth<JobDetail>(`/jobs/${id}`),
  getSavedJobs: () => fetchWithAuth<SavedJobItem[]>("/jobs/saved"),
  saveJob: (jobId: string) =>
    fetchWithAuth<SavedJobItem>(`/jobs/${jobId}/save`, {
      method: "POST",
    }),
  unsaveJob: (jobId: string) =>
    fetchWithAuth<void>(`/jobs/${jobId}/save`, {
      method: "DELETE",
    }),

  // Applications
  applyJob: (
    jobId: string,
    data: {
      resume_id?: string;
      cover_letter?: string;
      answers?: Record<string, any>;
      consent_records?: Record<string, any>;
      idempotency_key?: string;
    }
  ) =>
    fetchWithAuth<ApplicationSubmitResponse>(`/jobs/${jobId}/apply`, {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getMyApplications: () => fetchWithAuth<CandidateApplicationSummary[]>("/jobs/applications/me"),
  getApplicationDetail: (applicationId: string) =>
    fetchWithAuth<CandidateApplicationDetail>(`/jobs/applications/me/${applicationId}`),
  withdrawApplication: (applicationId: string, withdrawal_reason: string) =>
    fetchWithAuth<CandidateApplicationDetail>(`/jobs/applications/me/${applicationId}/withdraw`, {
      method: "POST",
      body: JSON.stringify({ withdrawal_reason, reason: withdrawal_reason }),
    }),

  // Notifications
  getNotifications: (params?: { category?: string; is_read?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.category) qs.append("category", params.category);
    if (params?.is_read !== undefined) qs.append("is_read", String(params.is_read));
    const query = qs.toString();
    return fetchWithAuth<CandidateNotification[]>(`/candidates/me/notifications${query ? `?${query}` : ""}`);
  },
  getUnreadNotificationCount: () =>
    fetchWithAuth<{ unread_count: number }>("/candidates/me/notifications/unread-count"),
  markNotificationRead: (id: string) =>
    fetchWithAuth<void>(`/candidates/me/notifications/${id}/read`, {
      method: "PATCH",
    }),
  markAllNotificationsRead: () =>
    fetchWithAuth<void>("/candidates/me/notifications/read-all", {
      method: "POST",
    }),

  // Account & Security Settings
  getAccountInfo: () =>
    fetchWithAuth<CandidateAccount>("/candidates/me/account"),
  updateAccountInfo: (data: { first_name?: string; last_name?: string; phone_number?: string }) =>
    fetchWithAuth<CandidateAccount>("/candidates/me/account", {
      method: "PATCH",
      body: JSON.stringify(data),
    }),
  changePassword: (data: { current_password: string; new_password: string }) =>
    fetchWithAuth<{ message: string }>("/auth/password/change", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  requestEmailVerification: () =>
    fetchWithAuth<{ status: string; email: string; message: string; email_service_configured: boolean }>(
      "/candidates/me/request-email-verification",
      { method: "POST" }
    ),

  // Notification Preferences
  getNotificationPreferences: () =>
    fetchWithAuth<NotificationPreferences>("/candidates/me/notification-preferences"),
  updateNotificationPreferences: (data: Partial<NotificationPreferences>) =>
    fetchWithAuth<NotificationPreferences>("/candidates/me/notification-preferences", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Privacy Preferences
  getPrivacyPreferences: () =>
    fetchWithAuth<PrivacyPreferences>("/candidates/me/privacy-preferences"),
  updatePrivacyPreferences: (data: Partial<PrivacyPreferences>) =>
    fetchWithAuth<PrivacyPreferences>("/candidates/me/privacy-preferences", {
      method: "PUT",
      body: JSON.stringify(data),
    }),

  // Candidate Interview Visibility
  getInterviews: () =>
    fetchWithAuth<{ interviews: CandidateInterview[]; total: number }>("/candidates/me/interviews"),

  // Data Privacy Subject Rights (GDPR / CCPA)
  getDataExport: () =>
    fetchWithAuth<PersonalDataExport>("/candidates/me/privacy/export"),
  submitCorrectionRequest: (data: CorrectionRequestPayload) =>
    fetchWithAuth<CorrectionRequestResponse>("/candidates/me/privacy/correction-request", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  submitDeletionRequest: (data: DeletionRequestPayload) =>
    fetchWithAuth<DeletionRequestResponse>("/candidates/me/privacy/deletion-request", {
      method: "POST",
      body: JSON.stringify(data),
    }),
  getConsentHistory: () =>
    fetchWithAuth<{ consents: ConsentHistoryItem[]; total: number }>("/candidates/me/privacy/consent-history"),
};
