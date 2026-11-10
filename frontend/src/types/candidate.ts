/**
 * Candidate Portal Types and Interfaces
 */

export interface CandidateUserProfile {
  id: string;
  email: string;
  full_name: string;
  is_active: boolean;
  is_verified: boolean;
  avatar_url?: string | null;
  phone?: string | null;
  location_city?: string | null;
  location_country?: string | null;
  preferred_title?: string | null;
  work_authorization?: string | null;
}

export interface CandidateExperience {
  id: string;
  title: string;
  company_name: string;
  location?: string | null;
  is_current: boolean;
  start_date: string;
  end_date?: string | null;
  description?: string | null;
}

export interface CandidateEducation {
  id: string;
  institution_name: string;
  degree: string;
  field_of_study?: string | null;
  start_year?: number | null;
  end_year?: number | null;
  grade?: string | null;
}

export interface CandidateCertification {
  id: string;
  name: string;
  issuing_organization: string;
  issue_date?: string | null;
  expiration_date?: string | null;
  credential_id?: string | null;
  credential_url?: string | null;
}

export interface CandidateProject {
  id: string;
  title: string;
  description?: string | null;
  project_url?: string | null;
  technologies: string[];
}

export interface CandidateLanguage {
  id: string;
  language_code: string;
  proficiency_level: "elementary" | "limited_working" | "professional_working" | "full_professional" | "native";
}

export interface CandidatePreference {
  desired_salary_min?: number | null;
  desired_salary_currency?: string;
  desired_role_levels: string[];
  remote_preference?: "remote" | "hybrid" | "onsite" | "any";
  open_to_relocation: boolean;
  notice_period_days?: number | null;
}

export interface CandidateFullProfile {
  user: CandidateUserProfile;
  headline?: string | null;
  bio?: string | null;
  years_of_experience?: number | null;
  self_declared_skills: string[];
  experiences: CandidateExperience[];
  educations: CandidateEducation[];
  certifications: CandidateCertification[];
  projects: CandidateProject[];
  languages: CandidateLanguage[];
  preference?: CandidatePreference | null;
  profile_completeness_pct: number;
}

export interface CandidateResume {
  id: string;
  file_name: string;
  file_size_bytes: number;
  mime_type: string;
  sha256_hash: string;
  version_number: number;
  is_default: boolean;
  extracted_skills: string[];
  extracted_text_snippet?: string | null;
  uploaded_at: string;
  has_active_applications?: boolean;
}

export interface ExtractedSectionItem {
  title: string;
  organization?: string | null;
  date_range?: string | null;
  description?: string | null;
}

export interface ExtractedProfileData {
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  summary?: string | null;
  skills: string[];
  experience: ExtractedSectionItem[];
  education: ExtractedSectionItem[];
  certifications: string[];
  projects: ExtractedSectionItem[];
}

export interface ResumeExtractionResponse {
  resume_id: string;
  status: string;
  extracted_text?: string | null;
  skills_extracted: string[];
  word_count: number;
  extracted_data?: ExtractedProfileData | null;
  ocr_applied: boolean;
  ocr_provider: string;
  malware_scan_status: string;
}

export interface JobPublicSummary {
  id: string;
  tenant_id: string;
  organization_name?: string | null;
  title: string;
  slug?: string;
  department?: string | null;
  location?: string | null;
  remote_type: "remote" | "hybrid" | "onsite" | string;
  employment_type: "full_time" | "part_time" | "contract" | "internship" | string;
  experience_level?: string | null;
  salary_min?: number | null;
  salary_max?: number | null;
  salary_currency?: string;
  skills_required?: string[];
  required_skills: string[];
  published_at?: string | null;
  created_at?: string;
  application_deadline?: string | null;
  is_saved?: boolean;
  has_applied?: boolean;
  is_expired?: boolean;
}

export interface JobDetail extends JobPublicSummary {
  description: string;
  requirements?: string | null;
  preferred_skills?: string[];
}

export interface JobListResponse {
  jobs: JobPublicSummary[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface SavedJobItem {
  id: string;
  job_id: string;
  saved_at: string;
  job: JobPublicSummary;
}

export type CandidateFacingStatus =
  | "received"
  | "under_review"
  | "shortlisted"
  | "interviewing"
  | "offer"
  | "rejected"
  | "withdrawn";

export interface CandidateApplicationSummary {
  id: string;
  job_id: string;
  tenant_id: string;
  organization_name?: string | null;
  job_title?: string | null;
  job_department?: string | null;
  job_location?: string | null;
  remote_type?: string | null;
  candidate_status: CandidateFacingStatus | string;
  applied_at: string;
  withdrawn_at?: string | null;
  withdrawal_reason?: string | null;
  resume_id?: string | null;
  resume_filename?: string | null;
  resume_version_applied?: number | null;
  resume_snapshot_sha256?: string | null;
  job?: JobPublicSummary;
}

export interface CandidateApplicationDetail extends CandidateApplicationSummary {
  cover_letter?: string | null;
  answers?: Record<string, any> | null;
  consent_records?: Record<string, any> | null;
  timeline: {
    status: CandidateFacingStatus | string;
    changed_at: string;
    note?: string;
  }[];
}

export interface ApplicationSubmitResponse {
  id: string;
  job_id: string;
  candidate_status: string;
  resume_snapshot_sha256?: string;
  resume_version_applied?: number;
  message: string;
  applied_at: string;
}

export interface CandidateNotification {
  id: string;
  title: string;
  body: string;
  notification_type: string;
  link_url?: string | null;
  is_read: boolean;
  created_at: string;
}
