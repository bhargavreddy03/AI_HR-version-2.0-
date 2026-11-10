import { getApiBaseUrl } from "./api";
import type {
  CanonicalSkillSuggestion,
  HrDashboardFilterParams,
  HrDashboardOverviewResponse,
  JobRequisition,
  JobRequisitionCreateInput,
  JobRequisitionFilterParams,
  JobRequisitionListResponse,
  JobRequisitionUpdateInput,
  TeamMemberOption,
} from "@/types/hr";

async function fetchWithAuth<T>(
  endpoint: string,
  options: RequestInit = {}
): Promise<T> {
  const baseUrl = getApiBaseUrl();
  const res = await fetch(`${baseUrl}${endpoint}`, {
    ...options,
    credentials: "include",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
  });

  if (!res.ok) {
    let errorDetail = `Request failed with status ${res.status}`;
    try {
      const data = await res.json();
      errorDetail = data.detail || data.title || data.message || errorDetail;
    } catch {
      // Non-JSON response
    }
    throw new Error(errorDetail);
  }

  return res.json() as Promise<T>;
}

export const hrApi = {
  /**
   * Fetch organization-scoped HR dashboard metrics and analytics.
   */
  async getDashboardOverview(
    filters: HrDashboardFilterParams = {}
  ): Promise<HrDashboardOverviewResponse> {
    const params = new URLSearchParams();
    if (filters.start_date) params.append("start_date", filters.start_date);
    if (filters.end_date) params.append("end_date", filters.end_date);
    if (filters.department) params.append("department", filters.department);
    if (filters.job_id) params.append("job_id", filters.job_id);
    if (filters.location) params.append("location", filters.location);
    if (filters.employment_type) params.append("employment_type", filters.employment_type);
    if (filters.stage) params.append("stage", filters.stage);

    const queryString = params.toString() ? `?${params.toString()}` : "";
    return fetchWithAuth<HrDashboardOverviewResponse>(`/hr/dashboard/overview${queryString}`);
  },

  /**
   * List organization-scoped job requisitions.
   */
  async listJobs(
    filters: JobRequisitionFilterParams = {}
  ): Promise<JobRequisitionListResponse> {
    const params = new URLSearchParams();
    if (filters.search) params.append("search", filters.search);
    if (filters.department) params.append("department", filters.department);
    if (filters.status) params.append("status", filters.status);
    if (filters.recruiter_id) params.append("recruiter_id", filters.recruiter_id);
    if (filters.hiring_manager_id) params.append("hiring_manager_id", filters.hiring_manager_id);
    if (filters.page) params.append("page", String(filters.page));
    if (filters.page_size) params.append("page_size", String(filters.page_size));
    if (filters.sort_by) params.append("sort_by", filters.sort_by);
    if (filters.sort_order) params.append("sort_order", filters.sort_order);

    const queryString = params.toString() ? `?${params.toString()}` : "";
    return fetchWithAuth<JobRequisitionListResponse>(`/hr/jobs${queryString}`);
  },

  /**
   * Get job requisition details by UUID.
   */
  async getJob(jobId: string): Promise<JobRequisition> {
    return fetchWithAuth<JobRequisition>(`/hr/jobs/${jobId}`);
  },

  /**
   * Create a new job requisition draft or pending approval.
   */
  async createJob(input: JobRequisitionCreateInput): Promise<JobRequisition> {
    return fetchWithAuth<JobRequisition>("/hr/jobs", {
      method: "POST",
      body: JSON.stringify(input),
    });
  },

  /**
   * Update an existing job requisition.
   */
  async updateJob(
    jobId: string,
    input: JobRequisitionUpdateInput
  ): Promise<JobRequisition> {
    return fetchWithAuth<JobRequisition>(`/hr/jobs/${jobId}`, {
      method: "PUT",
      body: JSON.stringify(input),
    });
  },

  /**
   * Delete a draft job requisition with no applications.
   */
  async deleteJob(jobId: string): Promise<void> {
    const baseUrl = getApiBaseUrl();
    const res = await fetch(`${baseUrl}/hr/jobs/${jobId}`, {
      method: "DELETE",
      credentials: "include",
      headers: {
        Accept: "application/json",
      },
    });
    if (!res.ok) {
      let errorDetail = `Failed to delete job requisition (${res.status})`;
      try {
        const data = await res.json();
        errorDetail = data.detail || data.title || errorDetail;
      } catch {
        // Non-JSON
      }
      throw new Error(errorDetail);
    }
  },

  /**
   * Retrieve active team members for recruiter/hiring manager assignments.
   */
  async getTeamMembers(): Promise<TeamMemberOption[]> {
    return fetchWithAuth<TeamMemberOption[]>("/hr/jobs/team-members");
  },

  /**
   * Search Canonical Skill Registry for autocomplete.
   */
  async autocompleteSkills(
    query: string = "",
    limit: number = 15
  ): Promise<CanonicalSkillSuggestion[]> {
    const params = new URLSearchParams();
    if (query) params.append("q", query);
    params.append("limit", String(limit));
    return fetchWithAuth<CanonicalSkillSuggestion[]>(
      `/hr/jobs/skills-autocomplete?${params.toString()}`
    );
  },
};
