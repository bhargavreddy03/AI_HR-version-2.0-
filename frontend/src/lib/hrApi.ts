import { getApiBaseUrl } from "./api";
import type {
  ApplicantFilterParams,
  ApplicantListResponse,
  ApplicationStageHistoryItem,
  BulkRecruiterAssignRequest,
  BulkRecruiterAssignResponse,
  BulkStageMoveRequest,
  BulkStageMoveResponse,
  CandidateComparisonRequest,
  CandidateComparisonResponse,
  CandidateDetailResponse,
  CanonicalSkillSuggestion,
  HrDashboardFilterParams,
  HrDashboardOverviewResponse,
  JobLifecycleActionRequest,
  JobLifecycleHistoryItem,
  JobLifecyclePermittedActionsResponse,
  JobLifecycleTransitionResponse,
  JobRequisition,
  JobRequisitionCreateInput,
  JobRequisitionFilterParams,
  JobRequisitionListResponse,
  JobRequisitionUpdateInput,
  PipelineBoardResponse,
  PipelineStageConfig,
  ResumeSignedUrlResponse,
  StageTransitionRequest,
  StageTransitionResponse,
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

  /**
   * Execute a lifecycle state transition action (submit, approve, request changes, publish, pause, reopen, close, archive).
   */
  async executeLifecycleAction(
    jobId: string,
    request: JobLifecycleActionRequest
  ): Promise<JobLifecycleTransitionResponse> {
    return fetchWithAuth<JobLifecycleTransitionResponse>(
      `/hr/jobs/${jobId}/lifecycle`,
      {
        method: "POST",
        body: JSON.stringify(request),
      }
    );
  },

  /**
   * Retrieve immutable lifecycle audit history for a job requisition.
   */
  async getJobLifecycleHistory(
    jobId: string
  ): Promise<JobLifecycleHistoryItem[]> {
    return fetchWithAuth<JobLifecycleHistoryItem[]>(
      `/hr/jobs/${jobId}/lifecycle/history`
    );
  },

  /**
   * Evaluate permitted lifecycle actions for the active user on this requisition.
   */
  async getPermittedLifecycleActions(
    jobId: string
  ): Promise<JobLifecyclePermittedActionsResponse> {
    return fetchWithAuth<JobLifecyclePermittedActionsResponse>(
      `/hr/jobs/${jobId}/lifecycle/permitted-actions`
    );
  },

  /**
   * List applicants with server-side filtering, search, and pagination.
   */
  async listApplicants(
    params: ApplicantFilterParams = {}
  ): Promise<ApplicantListResponse> {
    const sp = new URLSearchParams();
    if (params.search) sp.append("search", params.search);
    if (params.job_id) sp.append("job_id", params.job_id);
    if (params.department) sp.append("department", params.department);
    if (params.status) sp.append("status", params.status);
    if (params.recruiter_id) sp.append("recruiter_id", params.recruiter_id);
    if (params.location) sp.append("location", params.location);
    if (params.skills) sp.append("skills", params.skills);
    if (params.min_experience_years !== undefined)
      sp.append("min_experience_years", params.min_experience_years.toString());
    if (params.max_experience_years !== undefined)
      sp.append("max_experience_years", params.max_experience_years.toString());
    if (params.applied_after) sp.append("applied_after", params.applied_after);
    if (params.applied_before) sp.append("applied_before", params.applied_before);
    if (params.page) sp.append("page", params.page.toString());
    if (params.page_size) sp.append("page_size", params.page_size.toString());
    if (params.sort_by) sp.append("sort_by", params.sort_by);
    if (params.sort_order) sp.append("sort_order", params.sort_order);

    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return fetchWithAuth<ApplicantListResponse>(`/hr/applicants${qs}`);
  },

  /**
   * Retrieve complete candidate profile scoped strictly to organization context.
   */
  async getCandidateDetails(
    candidateId: string,
    applicationId?: string
  ): Promise<CandidateDetailResponse> {
    const qs = applicationId ? `?application_id=${applicationId}` : "";
    return fetchWithAuth<CandidateDetailResponse>(
      `/hr/candidates/${candidateId}${qs}`
    );
  },

  /**
   * Generate short-lived presigned URL for secure resume download with audit logging.
   */
  async getApplicationResumeUrl(
    applicationId: string
  ): Promise<ResumeSignedUrlResponse> {
    return fetchWithAuth<ResumeSignedUrlResponse>(
      `/hr/applications/${applicationId}/resume`
    );
  },

  /**
   * Prepare side-by-side comparative matrix for selected candidates.
   */
  async compareCandidates(
    applicationIds: string[]
  ): Promise<CandidateComparisonResponse> {
    return fetchWithAuth<CandidateComparisonResponse>("/hr/candidates/compare", {
      method: "POST",
      body: JSON.stringify({ application_ids: applicationIds }),
    });
  },

  /**
   * Bulk assign recruiter to multiple selected applications.
   */
  async bulkAssignRecruiter(
    applicationIds: string[],
    recruiterId: string
  ): Promise<BulkRecruiterAssignResponse> {
    return fetchWithAuth<BulkRecruiterAssignResponse>(
      "/hr/applicants/bulk-assign",
      {
        method: "POST",
        body: JSON.stringify({
          application_ids: applicationIds,
          recruiter_id: recruiterId,
        }),
      }
    );
  },

  /**
   * Retrieve configured recruitment pipeline stages for the organization.
   */
  async getPipelineStages(): Promise<PipelineStageConfig[]> {
    return fetchWithAuth<PipelineStageConfig[]>("/hr/pipeline/stages");
  },

  /**
   * Retrieve recruitment pipeline Kanban board grouped by stage with optional filters.
   */
  async getPipelineBoard(params?: {
    job_id?: string;
    recruiter_id?: string;
    search?: string;
    limit_per_stage?: number;
  }): Promise<PipelineBoardResponse> {
    const sp = new URLSearchParams();
    if (params?.job_id) sp.append("job_id", params.job_id);
    if (params?.recruiter_id) sp.append("recruiter_id", params.recruiter_id);
    if (params?.search) sp.append("search", params.search);
    if (params?.limit_per_stage)
      sp.append("limit_per_stage", params.limit_per_stage.toString());

    const qs = sp.toString() ? `?${sp.toString()}` : "";
    return fetchWithAuth<PipelineBoardResponse>(`/hr/pipeline/board${qs}`);
  },

  /**
   * Move an individual application to a permitted pipeline stage with optimistic concurrency.
   */
  async transitionApplicationStage(
    applicationId: string,
    payload: StageTransitionRequest
  ): Promise<StageTransitionResponse> {
    return fetchWithAuth<StageTransitionResponse>(
      `/hr/applications/${applicationId}/stage`,
      {
        method: "POST",
        body: JSON.stringify(payload),
      }
    );
  },

  /**
   * Bulk move selected applications to target stage with validation.
   */
  async bulkStageMove(
    payload: BulkStageMoveRequest
  ): Promise<BulkStageMoveResponse> {
    return fetchWithAuth<BulkStageMoveResponse>("/hr/pipeline/bulk-stage-move", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  },

  /**
   * Retrieve complete audit trail of stage transitions for an application.
   */
  async getApplicationStageHistory(
    applicationId: string
  ): Promise<ApplicationStageHistoryItem[]> {
    return fetchWithAuth<ApplicationStageHistoryItem[]>(
      `/hr/applications/${applicationId}/stage/history`
    );
  },
};
