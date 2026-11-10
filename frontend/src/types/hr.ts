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

export interface JobRequisition {
  id: string;
  tenant_id: string;
  title: string;
  slug: string;
  department: string;
  location: string;
  country?: string | null;
  remote_type: string;
  employment_type: string;
  experience_level: string;
  description: string;
  responsibilities?: string | null;
  required_qualifications?: string | null;
  requirements?: string | null;
  skills_required: string[];
  preferred_skills: string[];
  experience_requirements?: string | null;
  education_requirements?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency: string;
  vacancies_count: number;
  status: string;
  approval_status: string;
  visibility: string;
  recruiter_id?: string | null;
  recruiter_name?: string | null;
  recruiter_email?: string | null;
  hiring_manager_id?: string | null;
  hiring_manager_name?: string | null;
  hiring_manager_email?: string | null;
  applications_count: number;
  published_at?: string | null;
  closed_at?: string | null;
  reopened_at?: string | null;
  change_request_reason?: string | null;
  application_deadline?: string | null;
  created_at: string;
  updated_at: string;
}

export interface JobRequisitionCreateInput {
  title: string;
  department: string;
  location: string;
  country?: string | null;
  remote_type: string;
  employment_type: string;
  experience_level: string;
  description: string;
  responsibilities?: string | null;
  required_qualifications?: string | null;
  skills_required: string[];
  preferred_skills: string[];
  experience_requirements?: string | null;
  education_requirements?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency: string;
  vacancies_count: number;
  application_deadline?: string | null;
  recruiter_id?: string | null;
  hiring_manager_id?: string | null;
  visibility: string;
  status: string;
}

export interface JobRequisitionUpdateInput {
  title?: string;
  department?: string;
  location?: string;
  country?: string | null;
  remote_type?: string;
  employment_type?: string;
  experience_level?: string;
  description?: string;
  responsibilities?: string | null;
  required_qualifications?: string | null;
  skills_required?: string[];
  preferred_skills?: string[];
  experience_requirements?: string | null;
  education_requirements?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string;
  vacancies_count?: number;
  application_deadline?: string | null;
  recruiter_id?: string | null;
  hiring_manager_id?: string | null;
  visibility?: string;
  status?: string;
}

export interface JobRequisitionListResponse {
  items: JobRequisition[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface TeamMemberOption {
  id: string;
  name: string;
  email: string;
  role: string;
}

export interface CanonicalSkillSuggestion {
  canonical_name: string;
  category: string;
  skill_id: string;
}

export interface JobLifecycleActionRequest {
  action: string;
  reason?: string | null;
  audit_metadata?: Record<string, unknown>;
}

export interface JobLifecycleHistoryItem {
  id: string;
  job_id: string;
  previous_status: string;
  new_status: string;
  action: string;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_email?: string | null;
  actor_role?: string | null;
  reason?: string | null;
  audit_metadata: Record<string, unknown>;
  created_at: string;
}

export interface JobLifecyclePermittedActionsResponse {
  job_id: string;
  current_status: string;
  approval_status: string;
  permitted_actions: string[];
  can_approve: boolean;
  separation_of_duties_active: boolean;
}

export interface JobLifecycleTransitionResponse {
  job: JobRequisition;
  transition: JobLifecycleHistoryItem;
  permitted_next_actions: string[];
}

export interface JobRequisitionFilterParams {
  search?: string;
  department?: string;
  status?: string;
  recruiter_id?: string;
  hiring_manager_id?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: string;
}
