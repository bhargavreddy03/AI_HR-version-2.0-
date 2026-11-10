"use client";

import React, { useState, useEffect } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import {
  Briefcase,
  ArrowLeft,
  Save,
  Send,
  Eye,
  Plus,
  X,
  AlertCircle,
  RotateCw,
  Search,
  Check,
} from "lucide-react";
import { z } from "zod";
import { hrApi } from "@/lib/hrApi";
import type {
  TeamMemberOption,
  CanonicalSkillSuggestion,
  JobRequisitionCreateInput,
} from "@/types/hr";

const requisitionSchema = z
  .object({
    title: z.string().min(2, "Title must be at least 2 characters").max(255),
    department: z.string().min(1, "Department is required"),
    location: z.string().min(1, "Location is required"),
    country: z.string().optional(),
    remote_type: z.enum(["onsite", "hybrid", "remote"]),
    employment_type: z.enum(["full_time", "part_time", "contract", "internship"]),
    experience_level: z.enum(["entry", "mid", "senior", "lead", "executive"]),
    description: z.string().min(10, "Description must be at least 10 characters"),
    responsibilities: z.string().optional(),
    required_qualifications: z.string().optional(),
    experience_requirements: z.string().optional(),
    education_requirements: z.string().optional(),
    salary_min: z.number().nullable().optional(),
    salary_max: z.number().nullable().optional(),
    salary_currency: z.string().default("USD"),
    vacancies_count: z.number().min(1, "Must have at least 1 vacancy").max(1000),
    application_deadline: z.string().optional(),
    recruiter_id: z.string().optional(),
    hiring_manager_id: z.string().optional(),
    visibility: z.enum(["public", "internal", "unlisted"]),
  })
  .refine(
    (data) => {
      if (
        data.salary_min !== null &&
        data.salary_min !== undefined &&
        data.salary_max !== null &&
        data.salary_max !== undefined
      ) {
        return data.salary_min <= data.salary_max;
      }
      return true;
    },
    {
      message: "Minimum salary cannot be greater than maximum salary",
      path: ["salary_max"],
    }
  );

export default function NewJobRequisitionPage() {
  const router = useRouter();

  // Form State
  const [title, setTitle] = useState("");
  const [department, setDepartment] = useState("Engineering");
  const [location, setLocation] = useState("");
  const [country, setCountry] = useState("United States");
  const [remoteType, setRemoteType] = useState<"onsite" | "hybrid" | "remote">("hybrid");
  const [employmentType, setEmploymentType] = useState<
    "full_time" | "part_time" | "contract" | "internship"
  >("full_time");
  const [experienceLevel, setExperienceLevel] = useState<
    "entry" | "mid" | "senior" | "lead" | "executive"
  >("mid");
  const [description, setDescription] = useState("");
  const [responsibilities, setResponsibilities] = useState("");
  const [requiredQualifications, setRequiredQualifications] = useState("");
  const [experienceRequirements, setExperienceRequirements] = useState("");
  const [educationRequirements, setEducationRequirements] = useState("");
  const [salaryMin, setSalaryMin] = useState<number | "">("");
  const [salaryMax, setSalaryMax] = useState<number | "">("");
  const [salaryCurrency, setSalaryCurrency] = useState("USD");
  const [vacanciesCount, setVacanciesCount] = useState(1);
  const [applicationDeadline, setApplicationDeadline] = useState("");
  const [visibility, setVisibility] = useState<"public" | "internal" | "unlisted">("public");
  const [recruiterId, setRecruiterId] = useState("");
  const [hiringManagerId, setHiringManagerId] = useState("");

  // Skills
  const [skillsRequired, setSkillsRequired] = useState<string[]>([]);
  const [preferredSkills, setPreferredSkills] = useState<string[]>([]);
  const [reqSkillInput, setReqSkillInput] = useState("");
  const [prefSkillInput, setPrefSkillInput] = useState("");
  const [reqSuggestions, setReqSuggestions] = useState<CanonicalSkillSuggestion[]>([]);
  const [prefSuggestions, setPrefSuggestions] = useState<CanonicalSkillSuggestion[]>([]);

  // Team members
  const [teamMembers, setTeamMembers] = useState<TeamMemberOption[]>([]);

  // UI state
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});
  const [showPreviewModal, setShowPreviewModal] = useState(false);

  useEffect(() => {
    async function loadMembers() {
      try {
        const members = await hrApi.getTeamMembers();
        setTeamMembers(members);
      } catch {
        // Continue without members list if not loaded
      }
    }
    loadMembers();
  }, []);

  // Canonical skill search for Required Skills
  useEffect(() => {
    if (!reqSkillInput.trim()) {
      setReqSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const results = await hrApi.autocompleteSkills(reqSkillInput, 8);
        setReqSuggestions(results);
      } catch {
        setReqSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [reqSkillInput]);

  // Canonical skill search for Preferred Skills
  useEffect(() => {
    if (!prefSkillInput.trim()) {
      setPrefSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const results = await hrApi.autocompleteSkills(prefSkillInput, 8);
        setPrefSuggestions(results);
      } catch {
        setPrefSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [prefSkillInput]);

  const addRequiredSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (trimmed && !skillsRequired.some((s) => s.toLowerCase() === trimmed.toLowerCase())) {
      setSkillsRequired([...skillsRequired, trimmed]);
    }
    setReqSkillInput("");
    setReqSuggestions([]);
  };

  const removeRequiredSkill = (skill: string) => {
    setSkillsRequired(skillsRequired.filter((s) => s !== skill));
  };

  const addPreferredSkill = (skill: string) => {
    const trimmed = skill.trim();
    if (trimmed && !preferredSkills.some((s) => s.toLowerCase() === trimmed.toLowerCase())) {
      setPreferredSkills([...preferredSkills, trimmed]);
    }
    setPrefSkillInput("");
    setPrefSuggestions([]);
  };

  const removePreferredSkill = (skill: string) => {
    setPreferredSkills(preferredSkills.filter((s) => s !== skill));
  };

  const handleSubmit = async (submitStatus: "draft" | "pending_approval") => {
    setError(null);
    setFieldErrors({});

    const formData = {
      title,
      department,
      location,
      country: country || undefined,
      remote_type: remoteType,
      employment_type: employmentType,
      experience_level: experienceLevel,
      description,
      responsibilities: responsibilities || undefined,
      required_qualifications: requiredQualifications || undefined,
      experience_requirements: experienceRequirements || undefined,
      education_requirements: educationRequirements || undefined,
      salary_min: salaryMin === "" ? null : Number(salaryMin),
      salary_max: salaryMax === "" ? null : Number(salaryMax),
      salary_currency: salaryCurrency,
      vacancies_count: Number(vacanciesCount),
      application_deadline: applicationDeadline || undefined,
      recruiter_id: recruiterId || undefined,
      hiring_manager_id: hiringManagerId || undefined,
      visibility,
    };

    const parseResult = requisitionSchema.safeParse(formData);
    if (!parseResult.success) {
      const errMap: Record<string, string> = {};
      parseResult.error.issues.forEach((err) => {
        if (err.path[0]) {
          errMap[String(err.path[0])] = err.message;
        }
      });
      setFieldErrors(errMap);
      setError("Please resolve the highlighted validation errors.");
      return;
    }

    try {
      setLoading(true);
      const payload: JobRequisitionCreateInput = {
        ...parseResult.data,
        skills_required: skillsRequired,
        preferred_skills: preferredSkills,
        status: submitStatus,
      };

      const created = await hrApi.createJob(payload);
      router.push(`/hr/jobs/${created.id}`);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to create requisition";
      setError(msg);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="p-4 sm:p-6 lg:p-8 max-w-5xl mx-auto space-y-6">
      {/* Top Navigation */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-3">
          <Link
            href="/hr/jobs"
            className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
          >
            <ArrowLeft className="w-4 h-4" />
          </Link>
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
              Create Job Requisition
            </h1>
            <p className="text-xs text-slate-500 mt-0.5">
              Draft a new vacancy requisition with skill specifications and team assignments.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => setShowPreviewModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
          >
            <Eye className="w-3.5 h-3.5" />
            Preview
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => handleSubmit("draft")}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
            data-testid="save-draft-button"
          >
            <Save className="w-3.5 h-3.5" />
            Save Draft
          </button>
          <button
            type="button"
            disabled={loading}
            onClick={() => handleSubmit("pending_approval")}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors"
            data-testid="submit-approval-button"
          >
            {loading ? <RotateCw className="w-3.5 h-3.5 animate-spin" /> : <Send className="w-3.5 h-3.5" />}
            Submit for Approval
          </button>
        </div>
      </div>

      {/* Global Error Banner */}
      {error && (
        <div className="p-4 rounded-xl border border-rose-200 bg-rose-50 text-rose-700 text-sm flex items-center gap-2">
          <AlertCircle className="w-5 h-5 flex-shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {/* Form Grid */}
      <div className="space-y-6">
        {/* Section 1: Basic Information */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 pb-2 border-b border-slate-100 dark:border-slate-800">
            1. Role & Placement
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Job Title <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. Senior Distributed Systems Engineer"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
                className={`w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
                  fieldErrors.title ? "border-rose-400 bg-rose-50/20" : "border-slate-200 dark:border-slate-700"
                }`}
                data-testid="input-title"
              />
              {fieldErrors.title && (
                <p className="mt-1 text-xs text-rose-500">{fieldErrors.title}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Department <span className="text-rose-500">*</span>
              </label>
              <select
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                data-testid="select-department"
              >
                <option value="Engineering">Engineering</option>
                <option value="Product">Product</option>
                <option value="Design">Design</option>
                <option value="Data & AI">Data & AI</option>
                <option value="Marketing">Marketing</option>
                <option value="Sales">Sales</option>
                <option value="Human Resources">Human Resources</option>
                <option value="Finance">Finance</option>
                <option value="Operations">Operations</option>
                <option value="Legal">Legal</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Location (City, State / Region) <span className="text-rose-500">*</span>
              </label>
              <input
                type="text"
                placeholder="e.g. San Francisco, CA or Austin, TX"
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className={`w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
                  fieldErrors.location ? "border-rose-400" : "border-slate-200 dark:border-slate-700"
                }`}
                data-testid="input-location"
              />
              {fieldErrors.location && (
                <p className="mt-1 text-xs text-rose-500">{fieldErrors.location}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Country
              </label>
              <input
                type="text"
                placeholder="e.g. United States"
                value={country}
                onChange={(e) => setCountry(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Work Arrangement
              </label>
              <select
                value={remoteType}
                onChange={(e) => setRemoteType(e.target.value as "onsite" | "hybrid" | "remote")}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <option value="onsite">On-site</option>
                <option value="hybrid">Hybrid</option>
                <option value="remote">Fully Remote</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Employment Type
              </label>
              <select
                value={employmentType}
                onChange={(e) =>
                  setEmploymentType(
                    e.target.value as "full_time" | "part_time" | "contract" | "internship"
                  )
                }
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <option value="full_time">Full-time</option>
                <option value="part_time">Part-time</option>
                <option value="contract">Contract</option>
                <option value="internship">Internship</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Experience Level
              </label>
              <select
                value={experienceLevel}
                onChange={(e) =>
                  setExperienceLevel(
                    e.target.value as "entry" | "mid" | "senior" | "lead" | "executive"
                  )
                }
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <option value="entry">Entry Level</option>
                <option value="mid">Mid Level</option>
                <option value="senior">Senior</option>
                <option value="lead">Lead / Principal</option>
                <option value="executive">Executive</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Target Vacancies Count
              </label>
              <input
                type="number"
                min={1}
                max={1000}
                value={vacanciesCount}
                onChange={(e) => setVacanciesCount(Number(e.target.value))}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
          </div>
        </div>

        {/* Section 2: Compensation & Visibility */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 pb-2 border-b border-slate-100 dark:border-slate-800">
            2. Compensation, Visibility & Deadlines
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Minimum Annual Salary
              </label>
              <input
                type="number"
                placeholder="e.g. 120000"
                value={salaryMin}
                onChange={(e) => setSalaryMin(e.target.value === "" ? "" : Number(e.target.value))}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                data-testid="input-salary-min"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Maximum Annual Salary
              </label>
              <input
                type="number"
                placeholder="e.g. 160000"
                value={salaryMax}
                onChange={(e) => setSalaryMax(e.target.value === "" ? "" : Number(e.target.value))}
                className={`w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 ${
                  fieldErrors.salary_max ? "border-rose-400" : "border-slate-200 dark:border-slate-700"
                }`}
                data-testid="input-salary-max"
              />
              {fieldErrors.salary_max && (
                <p className="mt-1 text-xs text-rose-500">{fieldErrors.salary_max}</p>
              )}
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Currency
              </label>
              <select
                value={salaryCurrency}
                onChange={(e) => setSalaryCurrency(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <option value="USD">USD ($)</option>
                <option value="EUR">EUR (€)</option>
                <option value="GBP">GBP (£)</option>
                <option value="CAD">CAD ($)</option>
                <option value="AUD">AUD ($)</option>
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Visibility Setting
              </label>
              <select
                value={visibility}
                onChange={(e) => setVisibility(e.target.value as "public" | "internal" | "unlisted")}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              >
                <option value="public">Public (Visible on careers portal)</option>
                <option value="internal">Internal Only (Organization employees)</option>
                <option value="unlisted">Unlisted (Accessible only via direct link)</option>
              </select>
            </div>

            <div className="md:col-span-2">
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Application Deadline
              </label>
              <input
                type="datetime-local"
                value={applicationDeadline}
                onChange={(e) => setApplicationDeadline(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
              />
            </div>
          </div>
        </div>

        {/* Section 3: Skill Taxonomy Specification */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
          <div className="pb-2 border-b border-slate-100 dark:border-slate-800">
            <h2 className="text-base font-bold text-slate-900 dark:text-slate-100">
              3. Canonical Skill Registry Specification
            </h2>
            <p className="text-xs text-slate-500 mt-0.5">
              Powered by Step 3.10 Canonical Skills Taxonomy. Autocomplete automatically maps aliases into standardized competencies.
            </p>
          </div>

          {/* Required Skills */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Required Technical Competencies
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {skillsRequired.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-blue-50 text-blue-700 border border-blue-200"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => removeRequiredSkill(skill)}
                    className="hover:text-rose-600 ml-1"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>

            <div className="relative">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Search canonical skill or type custom (e.g. Python, Docker, Kubernetes)..."
                    value={reqSkillInput}
                    onChange={(e) => setReqSkillInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        if (reqSkillInput) addRequiredSkill(reqSkillInput);
                      }
                    }}
                    className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                    data-testid="input-required-skills"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (reqSkillInput) addRequiredSkill(reqSkillInput);
                  }}
                  className="px-3 py-2 text-xs font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700"
                >
                  Add
                </button>
              </div>

              {/* Autocomplete Dropdown */}
              {reqSuggestions.length > 0 && (
                <div className="absolute z-20 mt-1 w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-lg max-h-48 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
                  {reqSuggestions.map((sug) => (
                    <button
                      key={sug.skill_id}
                      type="button"
                      onClick={() => addRequiredSkill(sug.canonical_name)}
                      className="w-full text-left px-3 py-2 text-xs hover:bg-blue-50 dark:hover:bg-blue-950/40 flex items-center justify-between transition-colors"
                    >
                      <span className="font-semibold text-slate-900 dark:text-slate-100">
                        {sug.canonical_name}
                      </span>
                      <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                        {sug.category}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>

          {/* Preferred Skills */}
          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Preferred / Nice-to-have Skills
            </label>
            <div className="flex flex-wrap gap-1.5 mb-2">
              {preferredSkills.map((skill) => (
                <span
                  key={skill}
                  className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200"
                >
                  {skill}
                  <button
                    type="button"
                    onClick={() => removePreferredSkill(skill)}
                    className="hover:text-rose-600 ml-1"
                  >
                    <X className="w-3 h-3" />
                  </button>
                </span>
              ))}
            </div>

            <div className="relative">
              <div className="flex gap-2">
                <div className="relative flex-1">
                  <Search className="w-4 h-4 text-slate-400 absolute left-3 top-1/2 -translate-y-1/2" />
                  <input
                    type="text"
                    placeholder="Search preferred skill (e.g. GraphQL, Terraform)..."
                    value={prefSkillInput}
                    onChange={(e) => setPrefSkillInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        if (prefSkillInput) addPreferredSkill(prefSkillInput);
                      }
                    }}
                    className="w-full pl-9 pr-4 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                  />
                </div>
                <button
                  type="button"
                  onClick={() => {
                    if (prefSkillInput) addPreferredSkill(prefSkillInput);
                  }}
                  className="px-3 py-2 text-xs font-semibold bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 rounded-lg border border-slate-200 dark:border-slate-700"
                >
                  Add
                </button>
              </div>

              {prefSuggestions.length > 0 && (
                <div className="absolute z-20 mt-1 w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl shadow-lg max-h-48 overflow-y-auto divide-y divide-slate-100 dark:divide-slate-800">
                  {prefSuggestions.map((sug) => (
                    <button
                      key={sug.skill_id}
                      type="button"
                      onClick={() => addPreferredSkill(sug.canonical_name)}
                      className="w-full text-left px-3 py-2 text-xs hover:bg-emerald-50 dark:hover:bg-emerald-950/40 flex items-center justify-between transition-colors"
                    >
                      <span className="font-semibold text-slate-900 dark:text-slate-100">
                        {sug.canonical_name}
                      </span>
                      <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-slate-100 dark:bg-slate-800 text-slate-500">
                        {sug.category}
                      </span>
                    </button>
                  ))}
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Section 4: Detailed Descriptions & Requirements */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 pb-2 border-b border-slate-100 dark:border-slate-800">
            4. Job Description & Specifications
          </h2>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Job Description Overview <span className="text-rose-500">*</span>
            </label>
            <textarea
              rows={5}
              placeholder="Provide a comprehensive role overview, mission, and company context..."
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              className={`w-full p-3 text-sm bg-slate-50 dark:bg-slate-800/50 border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 font-sans ${
                fieldErrors.description ? "border-rose-400" : "border-slate-200 dark:border-slate-700"
              }`}
              data-testid="input-description"
            />
            {fieldErrors.description && (
              <p className="mt-1 text-xs text-rose-500">{fieldErrors.description}</p>
            )}
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Core Responsibilities
            </label>
            <textarea
              rows={4}
              placeholder="• Architect and maintain high-throughput distributed microservices&#10;• Lead sprint design reviews and cross-functional engineering alignment"
              value={responsibilities}
              onChange={(e) => setResponsibilities(e.target.value)}
              className="w-full p-3 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 font-sans"
            />
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Required Qualifications & Experience
              </label>
              <textarea
                rows={4}
                placeholder="• 5+ years building backend systems in Python/Go&#10;• Experience with Docker and Kubernetes"
                value={requiredQualifications}
                onChange={(e) => setRequiredQualifications(e.target.value)}
                className="w-full p-3 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 font-sans"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Education & Certification Requirements
              </label>
              <textarea
                rows={4}
                placeholder="• B.S. or M.S. in Computer Science or equivalent practical experience&#10;• AWS Certified Solutions Architect (optional)"
                value={educationRequirements}
                onChange={(e) => setEducationRequirements(e.target.value)}
                className="w-full p-3 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20 font-sans"
              />
            </div>
          </div>
        </div>

        {/* Section 5: Team Assignments */}
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-6 shadow-sm space-y-4">
          <h2 className="text-base font-bold text-slate-900 dark:text-slate-100 pb-2 border-b border-slate-100 dark:border-slate-800">
            5. Internal Recruitment Team Assignments
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Lead Recruiter Assignment
              </label>
              <select
                value={recruiterId}
                onChange={(e) => setRecruiterId(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                data-testid="select-recruiter"
              >
                <option value="">Unassigned (Assign later)</option>
                {teamMembers.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name} ({member.role}) — {member.email}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Hiring Manager Assignment
              </label>
              <select
                value={hiringManagerId}
                onChange={(e) => setHiringManagerId(e.target.value)}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500/20"
                data-testid="select-hiring-manager"
              >
                <option value="">Unassigned (Assign later)</option>
                {teamMembers.map((member) => (
                  <option key={member.id} value={member.id}>
                    {member.name} ({member.role}) — {member.email}
                  </option>
                ))}
              </select>
            </div>
          </div>
        </div>
      </div>

      {/* Requisition Preview Modal */}
      {showPreviewModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/50 backdrop-blur-sm p-4 overflow-y-auto">
          <div className="bg-white dark:bg-slate-900 rounded-2xl border border-slate-200 dark:border-slate-800 max-w-3xl w-full shadow-2xl overflow-hidden my-8">
            <div className="p-6 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
              <div>
                <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-blue-50 text-blue-700 border border-blue-200">
                  Candidate View Preview
                </span>
                <h3 className="text-xl font-bold text-slate-900 dark:text-slate-100 mt-1">
                  {title || "Untitled Job Opening"}
                </h3>
                <p className="text-xs text-slate-500">
                  {department} • {location || "Location not set"} • {remoteType} • {employmentType}
                </p>
              </div>
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                className="p-2 text-slate-400 hover:text-slate-700 rounded-lg"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-6 space-y-6 max-h-[70vh] overflow-y-auto text-sm text-slate-700 dark:text-slate-300">
              <div>
                <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                  About the Role
                </h4>
                <p className="whitespace-pre-line text-slate-800 dark:text-slate-200">
                  {description || "No description provided."}
                </p>
              </div>

              {responsibilities && (
                <div>
                  <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                    Key Responsibilities
                  </h4>
                  <p className="whitespace-pre-line text-slate-800 dark:text-slate-200">
                    {responsibilities}
                  </p>
                </div>
              )}

              {skillsRequired.length > 0 && (
                <div>
                  <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                    Required Technical Skills
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {skillsRequired.map((s) => (
                      <span
                        key={s}
                        className="px-2.5 py-1 text-xs rounded-md bg-blue-50 text-blue-700 border border-blue-200 font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {preferredSkills.length > 0 && (
                <div>
                  <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                    Preferred Skills
                  </h4>
                  <div className="flex flex-wrap gap-1.5">
                    {preferredSkills.map((s) => (
                      <span
                        key={s}
                        className="px-2.5 py-1 text-xs rounded-md bg-emerald-50 text-emerald-700 border border-emerald-200 font-medium"
                      >
                        {s}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {requiredQualifications && (
                <div>
                  <h4 className="text-xs uppercase font-semibold text-slate-500 tracking-wider mb-2">
                    Qualifications & Experience
                  </h4>
                  <p className="whitespace-pre-line text-slate-800 dark:text-slate-200">
                    {requiredQualifications}
                  </p>
                </div>
              )}

              {(salaryMin || salaryMax) && (
                <div className="p-4 rounded-xl bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 flex items-center justify-between">
                  <span className="text-xs text-slate-500">Estimated Annual Base Range</span>
                  <span className="text-sm font-bold text-slate-900 dark:text-slate-100">
                    {salaryMin ? `${salaryCurrency} ${Number(salaryMin).toLocaleString()}` : ""}
                    {salaryMin && salaryMax ? " - " : ""}
                    {salaryMax ? `${salaryCurrency} ${Number(salaryMax).toLocaleString()}` : ""}
                  </span>
                </div>
              )}
            </div>

            <div className="p-4 border-t border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950 flex justify-end">
              <button
                type="button"
                onClick={() => setShowPreviewModal(false)}
                className="px-4 py-2 text-xs font-semibold text-slate-700 dark:text-slate-200 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg hover:bg-slate-100"
              >
                Close Preview
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
