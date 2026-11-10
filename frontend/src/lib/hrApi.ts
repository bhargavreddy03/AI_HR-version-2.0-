import { getApiBaseUrl } from "./api";
import type {
  HrDashboardFilterParams,
  HrDashboardOverviewResponse,
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
};
