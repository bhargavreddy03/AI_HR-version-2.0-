/**
 * TypeScript interfaces for the HR / Recruiter Portal and Analytics.
 * Conforms to Step 4.2 architecture specifications.
 */

export interface HrDashboardMetrics {
  total_candidates: number;
  total_applications: number;
  active_jobs: number;
  published_jobs: number;
  draft_jobs: number;
  applications_awaiting_review: number;
  shortlisted_candidates: number;
  scheduled_interviews: number;
  hired_candidates: number;
  pending_tasks: number;
}

export interface FunnelStageCount {
  stage: string;
  label: string;
  count: number;
  percentage: number;
}

export interface ApplicationsOverTimePoint {
  date: string;
  applications_count: number;
}

export interface JobApplicationCount {
  job_id: string;
  job_title: string;
  department: string;
  status: string;
  applications_count: number;
  active_count: number;
}

export interface DepartmentApplicationCount {
  department: string;
  applications_count: number;
  open_jobs_count: number;
}

export interface RecentApplicantItem {
  application_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  job_id: string;
  job_title: string;
  department: string;
  applied_at: string;
  stage: string;
  candidate_status: string;
  resume_snapshot_sha256?: string | null;
  skills_count: number;
  top_skills: string[];
}

export interface RecentActivityItem {
  id: string;
  event_type: string;
  title: string;
  description: string;
  candidate_name?: string | null;
  job_title?: string | null;
  timestamp: string;
  actor_name?: string | null;
}

export interface HrDashboardOverviewResponse {
  tenant_id: string;
  organization_name: string;
  metrics: HrDashboardMetrics;
  recruitment_funnel: FunnelStageCount[];
  applications_over_time: ApplicationsOverTimePoint[];
  applications_by_job: JobApplicationCount[];
  applications_by_department: DepartmentApplicationCount[];
  recent_applicants: RecentApplicantItem[];
  recent_activities: RecentActivityItem[];
  active_filters: Record<string, unknown>;
}

export interface HrDashboardFilterParams {
  start_date?: string;
  end_date?: string;
  department?: string;
  job_id?: string;
  location?: string;
  employment_type?: string;
  stage?: string;
}
