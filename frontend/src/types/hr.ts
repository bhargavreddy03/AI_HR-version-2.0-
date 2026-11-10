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
  user_role?: string;
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

// ----------------------------------------------------------------------
// Applicant & Candidate Management Interfaces (Step 4.2.5)
// ----------------------------------------------------------------------

export interface ApplicantListItem {
  id: string; // application id
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  candidate_phone?: string | null;
  candidate_headline?: string | null;
  candidate_location?: string | null;
  candidate_avatar_url?: string | null;
  job_id: string;
  job_title: string;
  job_department: string;
  job_location: string;
  status: string;
  candidate_status: string;
  applied_at: string;
  skills: string[];
  experience_years: number;
  current_job_title?: string | null;
  current_company?: string | null;
  resume_available: boolean;
  resume_id?: string | null;
  resume_filename?: string | null;
  resume_snapshot_sha256?: string | null;
  recruiter_id?: string | null;
  recruiter_name?: string | null;
  hiring_manager_id?: string | null;
  hiring_manager_name?: string | null;
  last_activity_at: string;
}

export interface ApplicantListResponse {
  items: ApplicantListItem[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export interface ApplicantFilterParams {
  search?: string;
  job_id?: string;
  department?: string;
  status?: string;
  recruiter_id?: string;
  location?: string;
  skills?: string;
  min_experience_years?: number;
  max_experience_years?: number;
  applied_after?: string;
  applied_before?: string;
  page?: number;
  page_size?: number;
  sort_by?: string;
  sort_order?: string;
}

export interface CandidateDetailExperience {
  id: string;
  job_title: string;
  company_name: string;
  location?: string | null;
  start_date: string;
  end_date?: string | null;
  is_current: boolean;
  description?: string | null;
  skills: string[];
}

export interface CandidateDetailEducation {
  id: string;
  institution: string;
  degree: string;
  field_of_study: string;
  start_year?: number | null;
  end_year?: number | null;
  grade?: string | null;
}

export interface CandidateDetailCertification {
  id: string;
  name: string;
  issuing_organization: string;
  issue_date?: string | null;
  expiration_date?: string | null;
  credential_id?: string | null;
  credential_url?: string | null;
}

export interface CandidateDetailProject {
  id: string;
  title: string;
  description?: string | null;
  role?: string | null;
  project_url?: string | null;
  skills: string[];
}

export interface CandidateDetailLanguage {
  id: string;
  language: string;
  proficiency: string;
}

export interface OrganizationApplicationSummary {
  application_id: string;
  job_id: string;
  job_title: string;
  department: string;
  applied_at: string;
  status: string;
  candidate_status: string;
  withdrawn_at?: string | null;
}

export interface TimelineEventItem {
  status: string;
  changed_at: string;
  note?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  is_internal: boolean;
}

export interface ApplicationDetailContext {
  application_id: string;
  job_id: string;
  job_title: string;
  job_department: string;
  job_location: string;
  recruiter_id?: string | null;
  recruiter_name?: string | null;
  hiring_manager_id?: string | null;
  hiring_manager_name?: string | null;
  status: string;
  candidate_status: string;
  applied_at: string;
  cover_letter?: string | null;
  answers: Record<string, unknown>;
  resume_id?: string | null;
  resume_version_applied?: number | null;
  resume_snapshot_sha256?: string | null;
  resume_filename?: string | null;
  candidate_timeline: TimelineEventItem[];
  internal_timeline: TimelineEventItem[];
}

export interface CandidateDetailResponse {
  candidate_id: string;
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone_number?: string | null;
  avatar_url?: string | null;
  headline?: string | null;
  bio?: string | null;
  location_city?: string | null;
  location_country?: string | null;
  preferred_title?: string | null;
  work_authorization?: string | null;
  portfolio_urls: string[];
  skills: string[];
  experience_years: number;
  experiences: CandidateDetailExperience[];
  educations: CandidateDetailEducation[];
  certifications: CandidateDetailCertification[];
  projects: CandidateDetailProject[];
  languages: CandidateDetailLanguage[];
  current_application?: ApplicationDetailContext | null;
  organization_application_history: OrganizationApplicationSummary[];
}

export interface ResumeSignedUrlResponse {
  application_id: string;
  candidate_id: string;
  resume_id?: string | null;
  filename: string;
  mime_type: string;
  file_size_bytes: number;
  content_sha256: string;
  download_url: string;
  expires_in_seconds: number;
}

export interface CandidateComparisonItem {
  application_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  job_id: string;
  job_title: string;
  status: string;
  applied_at: string;
  experience_years: number;
  current_job_title?: string | null;
  current_company?: string | null;
  highest_education?: string | null;
  skills: string[];
  job_skills_required: string[];
  matching_skills: string[];
  missing_skills: string[];
  match_percentage: number;
  resume_available: boolean;
}

export interface CandidateComparisonRequest {
  application_ids: string[];
}

export interface CandidateComparisonResponse {
  job_id?: string | null;
  job_title?: string | null;
  candidates: CandidateComparisonItem[];
}

export interface BulkRecruiterAssignRequest {
  application_ids: string[];
  recruiter_id: string;
}

export interface BulkRecruiterAssignResponse {
  updated_count: number;
  application_ids: string[];
  recruiter_id: string;
  recruiter_name: string;
}

// ----------------------------------------------------------------------
// Recruitment Pipeline & Stage Management Interfaces (Step 4.2.6)
// ----------------------------------------------------------------------

export interface PipelineStageConfig {
  id: string;
  label: string;
  order: number;
  is_terminal?: boolean;
  color?: string | null;
}

export interface PipelineCardItem {
  application_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_email: string;
  candidate_headline?: string | null;
  candidate_avatar_url?: string | null;
  job_id: string;
  job_title: string;
  job_department: string;
  stage: string;
  stage_version: number;
  applied_at: string;
  last_activity_at: string;
  recruiter_id?: string | null;
  recruiter_name?: string | null;
  skills: string[];
  resume_available: boolean;
}

export interface PipelineStageColumn {
  id: string;
  label: string;
  order: number;
  is_terminal: boolean;
  count: number;
  cards: PipelineCardItem[];
}

export interface PipelineBoardResponse {
  tenant_id: string;
  stages: PipelineStageColumn[];
  total_candidates: number;
  active_filters: Record<string, unknown>;
}

export interface StageTransitionRequest {
  target_stage: string;
  expected_stage_version?: number | null;
  reason?: string | null;
  notes?: string | null;
}

export interface StageTransitionResponse {
  application_id: string;
  previous_stage: string;
  new_stage: string;
  stage_version: number;
  candidate_status: string;
  changed_at: string;
  actor_name?: string | null;
  actor_role?: string | null;
  reason?: string | null;
}

export interface BulkStageMoveRequest {
  application_ids: string[];
  target_stage: string;
  reason?: string | null;
}

export interface BulkStageMoveSkippedItem {
  application_id: string;
  candidate_name?: string | null;
  current_stage: string;
  reason: string;
}

export interface BulkStageMoveResponse {
  target_stage: string;
  total_requested: number;
  updated_count: number;
  updated_ids: string[];
  skipped_count: number;
  skipped: BulkStageMoveSkippedItem[];
}

export interface ApplicationStageHistoryItem {
  id: string;
  application_id: string;
  previous_stage: string;
  new_stage: string;
  actor_id?: string | null;
  actor_name?: string | null;
  actor_role?: string | null;
  reason?: string | null;
  audit_metadata: Record<string, unknown>;
  created_at: string;
}


