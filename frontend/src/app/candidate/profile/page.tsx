"use client";

import React, { useState, useEffect } from "react";
import {
  User,
  Briefcase,
  GraduationCap,
  Award,
  FolderGit2,
  Globe,
  Sliders,
  Plus,
  Trash2,
  Save,
  CheckCircle2,
  AlertCircle,
  Loader2,
  X,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type {
  CandidateFullProfile,
  CandidateExperience,
  CandidateEducation,
  CandidateCertification,
  CandidateProject,
  CandidateLanguage,
  CandidatePreference,
} from "@/types/candidate";

export default function CandidateProfilePage() {
  const [profile, setProfile] = useState<CandidateFullProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [feedback, setFeedback] = useState<{ type: "success" | "error"; message: string } | null>(null);

  // Form states
  const [personalForm, setPersonalForm] = useState({
    headline: "",
    bio: "",
    years_of_experience: 0,
    phone: "",
    location_city: "",
    location_country: "",
    preferred_title: "",
    work_authorization: "",
  });

  // Skills state
  const [skills, setSkills] = useState<string[]>([]);
  const [skillInput, setSkillInput] = useState("");
  const [skillSuggestions, setSkillSuggestions] = useState<string[]>([]);

  // Preferences state
  const [preferences, setPreferences] = useState<CandidatePreference>({
    desired_salary_min: 0,
    desired_salary_currency: "USD",
    desired_role_levels: [],
    remote_preference: "any",
    open_to_relocation: false,
    notice_period_days: 30,
  });

  // Modals state for items
  const [showExpModal, setShowExpModal] = useState(false);
  const [newExp, setNewExp] = useState({
    title: "",
    company_name: "",
    location: "",
    is_current: false,
    start_date: "",
    end_date: "",
    description: "",
  });

  const [showEduModal, setShowEduModal] = useState(false);
  const [newEdu, setNewEdu] = useState({
    institution_name: "",
    degree: "",
    field_of_study: "",
    start_year: 2020,
    end_year: 2024,
    grade: "",
  });

  useEffect(() => {
    async function loadProfile() {
      try {
        setLoading(true);
        const data = await candidateApi.getProfile();
        setProfile(data);
        setPersonalForm({
          headline: data.headline || "",
          bio: data.bio || "",
          years_of_experience: data.years_of_experience || 0,
          phone: data.user.phone || "",
          location_city: data.user.location_city || "",
          location_country: data.user.location_country || "",
          preferred_title: data.user.preferred_title || "",
          work_authorization: data.user.work_authorization || "",
        });
        setSkills(data.self_declared_skills || []);
        if (data.preference) {
          setPreferences(data.preference);
        }
      } catch (err: unknown) {
        setFeedback({
          type: "error",
          message: err instanceof Error ? err.message : "Failed to load candidate profile",
        });
      } finally {
        setLoading(false);
      }
    }
    loadProfile();
  }, []);

  // Handle skill suggestion search
  useEffect(() => {
    if (!skillInput.trim()) {
      setSkillSuggestions([]);
      return;
    }
    const timer = setTimeout(async () => {
      try {
        const res = await candidateApi.suggestSkills(skillInput);
        setSkillSuggestions(res.suggestions || []);
      } catch {
        setSkillSuggestions([]);
      }
    }, 250);
    return () => clearTimeout(timer);
  }, [skillInput]);

  const handleSavePersonalInfo = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setFeedback(null);
    try {
      const updated = await candidateApi.updateProfile({
        ...personalForm,
        years_of_experience: Number(personalForm.years_of_experience) || 0,
      });
      setProfile(updated);
      setFeedback({ type: "success", message: "Personal information saved successfully." });
    } catch (err: unknown) {
      setFeedback({ type: "error", message: err instanceof Error ? err.message : "Failed to save profile" });
    } finally {
      setSaving(false);
    }
  };

  const handleAddSkill = async (skillToAdd: string) => {
    const trimmed = skillToAdd.trim();
    if (!trimmed || skills.includes(trimmed)) return;
    const updated = [...skills, trimmed];
    setSkills(updated);
    setSkillInput("");
    setSkillSuggestions([]);
    try {
      await candidateApi.updateSkills(updated);
    } catch {
      // rollback or retry
    }
  };

  const handleRemoveSkill = async (skillToRemove: string) => {
    const updated = skills.filter((s) => s !== skillToRemove);
    setSkills(updated);
    try {
      await candidateApi.updateSkills(updated);
    } catch {
      // rollback
    }
  };

  const handleAddExperience = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await candidateApi.addExperience(newExp);
      if (profile) {
        setProfile({ ...profile, experiences: [created, ...profile.experiences] });
      }
      setShowExpModal(false);
      setNewExp({
        title: "",
        company_name: "",
        location: "",
        is_current: false,
        start_date: "",
        end_date: "",
        description: "",
      });
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to add experience");
    }
  };

  const handleDeleteExperience = async (id: string) => {
    if (!confirm("Are you sure you want to delete this experience?")) return;
    try {
      await candidateApi.deleteExperience(id);
      if (profile) {
        setProfile({
          ...profile,
          experiences: profile.experiences.filter((e) => e.id !== id),
        });
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete experience");
    }
  };

  const handleAddEducation = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      const created = await candidateApi.addEducation({
        ...newEdu,
        start_year: Number(newEdu.start_year) || null,
        end_year: Number(newEdu.end_year) || null,
      });
      if (profile) {
        setProfile({ ...profile, educations: [created, ...profile.educations] });
      }
      setShowEduModal(false);
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to add education");
    }
  };

  const handleDeleteEducation = async (id: string) => {
    if (!confirm("Are you sure you want to delete this education entry?")) return;
    try {
      await candidateApi.deleteEducation(id);
      if (profile) {
        setProfile({
          ...profile,
          educations: profile.educations.filter((ed) => ed.id !== id),
        });
      }
    } catch (err: unknown) {
      alert(err instanceof Error ? err.message : "Failed to delete education");
    }
  };

  const handleSavePreferences = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await candidateApi.updatePreferences(preferences);
      setFeedback({ type: "success", message: "Career preferences updated successfully." });
    } catch (err: unknown) {
      setFeedback({ type: "error", message: err instanceof Error ? err.message : "Failed to save preferences" });
    }
  };

  if (loading) {
    return (
      <div className="flex flex-col items-center justify-center py-20 space-y-3">
        <Loader2 className="w-8 h-8 animate-spin text-primary-600" />
        <p className="text-sm text-slate-500">Loading your candidate profile...</p>
      </div>
    );
  }

  return (
    <div className="space-y-8">
      {/* Page Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Candidate Profile
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Manage your global candidate persona, verified skills, and career preferences across organizations.
        </p>
      </div>

      {feedback && (
        <div
          role="alert"
          className={`flex items-center gap-2 p-4 rounded-xl border text-sm ${
            feedback.type === "success"
              ? "bg-emerald-50 dark:bg-emerald-950/40 text-emerald-800 dark:text-emerald-300 border-emerald-200 dark:border-emerald-800"
              : "bg-red-50 dark:bg-red-950/40 text-red-800 dark:text-red-300 border-red-200 dark:border-red-800"
          }`}
        >
          {feedback.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
          ) : (
            <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          )}
          <span>{feedback.message}</span>
        </div>
      )}

      {/* Section 1: Basic Information */}
      <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-6">
        <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
          <User className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Personal & Contact Details
          </h2>
        </div>

        <form onSubmit={handleSavePersonalInfo} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Full Name (Global Identity)
              </label>
              <input
                type="text"
                disabled
                value={profile?.user.full_name || ""}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 rounded-lg text-slate-500 cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Email Address
              </label>
              <input
                type="email"
                disabled
                value={profile?.user.email || ""}
                className="w-full px-3 py-2 text-sm bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-800 rounded-lg text-slate-500 cursor-not-allowed"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Phone Number
              </label>
              <input
                type="tel"
                value={personalForm.phone}
                onChange={(e) => setPersonalForm({ ...personalForm, phone: e.target.value })}
                placeholder="+1 (555) 012-3456"
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Preferred Job Title
              </label>
              <input
                type="text"
                value={personalForm.preferred_title}
                onChange={(e) => setPersonalForm({ ...personalForm, preferred_title: e.target.value })}
                placeholder="Senior Full Stack Engineer"
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Location (City)
              </label>
              <input
                type="text"
                value={personalForm.location_city}
                onChange={(e) => setPersonalForm({ ...personalForm, location_city: e.target.value })}
                placeholder="San Francisco"
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Location (Country)
              </label>
              <input
                type="text"
                value={personalForm.location_country}
                onChange={(e) => setPersonalForm({ ...personalForm, location_country: e.target.value })}
                placeholder="United States"
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Work Authorization
              </label>
              <input
                type="text"
                value={personalForm.work_authorization}
                onChange={(e) => setPersonalForm({ ...personalForm, work_authorization: e.target.value })}
                placeholder="US Citizen / Green Card / EU Citizen"
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Total Years of Professional Experience
              </label>
              <input
                type="number"
                min="0"
                max="60"
                value={personalForm.years_of_experience}
                onChange={(e) => setPersonalForm({ ...personalForm, years_of_experience: Number(e.target.value) })}
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Headline
            </label>
            <input
              type="text"
              value={personalForm.headline}
              onChange={(e) => setPersonalForm({ ...personalForm, headline: e.target.value })}
              placeholder="e.g. Senior AI Systems Engineer specializing in Distributed Systems & FastAPI"
              className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>

          <div>
            <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
              Professional Bio
            </label>
            <textarea
              rows={4}
              value={personalForm.bio}
              onChange={(e) => setPersonalForm({ ...personalForm, bio: e.target.value })}
              placeholder="Describe your career highlights, architectural specialties, and what you're looking for..."
              className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              disabled={saving}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
            >
              {saving ? <Loader2 className="w-4 h-4 animate-spin" /> : <Save className="w-4 h-4" />}
              Save Personal Info
            </button>
          </div>
        </form>
      </section>

      {/* Section 2: Canonical Skill Registry Tagging */}
      <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Award className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              Self-Declared Skills (Taxonomy Normalized)
            </h2>
          </div>
          <span className="text-xs text-slate-500">
            {skills.length} skills added
          </span>
        </div>

        <p className="text-xs text-slate-500 dark:text-slate-400">
          Type to search our enterprise canonical skills registry. Skills are verified and mapped against 500+ standard industry taxonomies.
        </p>

        {/* Skill Input with suggestions */}
        <div className="relative">
          <div className="flex gap-2">
            <input
              type="text"
              value={skillInput}
              onChange={(e) => setSkillInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter") {
                  e.preventDefault();
                  handleAddSkill(skillInput);
                }
              }}
              placeholder="e.g. Python, FastAPI, Docker, PostgreSQL, React..."
              className="flex-1 px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
            />
            <button
              type="button"
              onClick={() => handleAddSkill(skillInput)}
              className="px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-sm font-medium rounded-lg text-slate-700 dark:text-slate-200 transition-colors"
            >
              Add Skill
            </button>
          </div>

          {skillSuggestions.length > 0 && (
            <div className="absolute z-10 left-0 right-0 mt-1 bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-xl shadow-lg p-2 max-h-48 overflow-y-auto">
              <p className="text-[10px] uppercase font-bold text-slate-400 px-2 py-1">
                Suggested Canonical Skills
              </p>
              {skillSuggestions.map((s) => (
                <button
                  key={s}
                  type="button"
                  onClick={() => handleAddSkill(s)}
                  className="w-full text-left px-3 py-1.5 text-xs text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700 rounded-md transition-colors"
                >
                  + {s}
                </button>
              ))}
            </div>
          )}
        </div>

        {/* Active Skills Badges */}
        <div className="flex flex-wrap gap-2 pt-2">
          {skills.map((skill) => (
            <span
              key={skill}
              className="inline-flex items-center gap-1.5 px-3 py-1 text-xs font-semibold bg-primary-50 dark:bg-primary-950/50 text-primary-700 dark:text-primary-300 border border-primary-200 dark:border-primary-800 rounded-full"
            >
              {skill}
              <button
                type="button"
                onClick={() => handleRemoveSkill(skill)}
                className="hover:text-red-500 focus:outline-none"
                aria-label={`Remove skill ${skill}`}
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </span>
          ))}
          {skills.length === 0 && (
            <p className="text-xs text-slate-400 italic">No skills added yet.</p>
          )}
        </div>
      </section>

      {/* Section 3: Experience */}
      <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <Briefcase className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              Work Experience
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setShowExpModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary-50 dark:bg-primary-950/40 text-primary-700 dark:text-primary-300 hover:bg-primary-100 text-xs font-semibold rounded-lg transition-colors"
          >
            <Plus className="w-3.5 h-3.5" /> Add Experience
          </button>
        </div>

        <div className="space-y-3">
          {profile?.experiences && profile.experiences.length > 0 ? (
            profile.experiences.map((exp) => (
              <div
                key={exp.id}
                className="p-4 border border-slate-100 dark:border-slate-800 rounded-xl flex items-start justify-between gap-4"
              >
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    {exp.title}
                  </h3>
                  <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
                    {exp.company_name} {exp.location ? `&bull; ${exp.location}` : ""}
                  </p>
                  <p className="text-xs text-slate-400">
                    {exp.start_date} &ndash; {exp.is_current ? "Present" : exp.end_date || "Present"}
                  </p>
                  {exp.description && (
                    <p className="text-xs text-slate-600 dark:text-slate-300 pt-1 whitespace-pre-line">
                      {exp.description}
                    </p>
                  )}
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteExperience(exp.id)}
                  className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                  aria-label="Delete experience"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))
          ) : (
            <p className="text-xs text-slate-400 py-3 italic">No work experiences listed.</p>
          )}
        </div>
      </section>

      {/* Section 4: Education */}
      <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
          <div className="flex items-center gap-2">
            <GraduationCap className="w-5 h-5 text-primary-600 dark:text-primary-400" />
            <h2 className="text-lg font-bold text-slate-900 dark:text-white">
              Education
            </h2>
          </div>
          <button
            type="button"
            onClick={() => setShowEduModal(true)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-primary-50 dark:bg-primary-950/40 text-primary-700 dark:text-primary-300 hover:bg-primary-100 text-xs font-semibold rounded-lg transition-colors"
          >
            <Plus className="w-3.5 h-3.5" /> Add Education
          </button>
        </div>

        <div className="space-y-3">
          {profile?.educations && profile.educations.length > 0 ? (
            profile.educations.map((edu) => (
              <div
                key={edu.id}
                className="p-4 border border-slate-100 dark:border-slate-800 rounded-xl flex items-start justify-between gap-4"
              >
                <div className="space-y-1">
                  <h3 className="text-sm font-bold text-slate-900 dark:text-white">
                    {edu.degree} {edu.field_of_study ? `in ${edu.field_of_study}` : ""}
                  </h3>
                  <p className="text-xs font-medium text-slate-600 dark:text-slate-400">
                    {edu.institution_name}
                  </p>
                  <p className="text-xs text-slate-400">
                    {edu.start_year || ""} &ndash; {edu.end_year || ""}
                  </p>
                </div>
                <button
                  type="button"
                  onClick={() => handleDeleteEducation(edu.id)}
                  className="p-1.5 text-slate-400 hover:text-red-500 rounded-lg hover:bg-red-50 dark:hover:bg-red-950/30 transition-colors"
                  aria-label="Delete education"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))
          ) : (
            <p className="text-xs text-slate-400 py-3 italic">No education history listed.</p>
          )}
        </div>
      </section>

      {/* Section 5: Preferences */}
      <section className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
          <Sliders className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <h2 className="text-lg font-bold text-slate-900 dark:text-white">
            Career Preferences
          </h2>
        </div>

        <form onSubmit={handleSavePreferences} className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Minimum Desired Salary
              </label>
              <input
                type="number"
                min="0"
                value={preferences.desired_salary_min || 0}
                onChange={(e) => setPreferences({ ...preferences, desired_salary_min: Number(e.target.value) })}
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Remote Work Preference
              </label>
              <select
                value={preferences.remote_preference || "any"}
                onChange={(e) => setPreferences({ ...preferences, remote_preference: e.target.value as CandidatePreference["remote_preference"] })}
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              >
                <option value="any">Any (Remote, Hybrid, Onsite)</option>
                <option value="remote">Fully Remote Only</option>
                <option value="hybrid">Hybrid</option>
                <option value="onsite">On-Site Only</option>
              </select>
            </div>
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Notice Period (Days)
              </label>
              <input
                type="number"
                min="0"
                value={preferences.notice_period_days || 0}
                onChange={(e) => setPreferences({ ...preferences, notice_period_days: Number(e.target.value) })}
                className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>
          </div>

          <div className="flex items-center gap-2 pt-2">
            <input
              type="checkbox"
              id="openToRelo"
              checked={preferences.open_to_relocation || false}
              onChange={(e) => setPreferences({ ...preferences, open_to_relocation: e.target.checked })}
              className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
            />
            <label htmlFor="openToRelo" className="text-xs font-medium text-slate-700 dark:text-slate-300">
              Open to relocation for the right enterprise opportunity
            </label>
          </div>

          <div className="flex justify-end pt-2">
            <button
              type="submit"
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-semibold rounded-xl shadow-sm transition-colors"
            >
              <Save className="w-4 h-4" /> Save Career Preferences
            </button>
          </div>
        </form>
      </section>

      {/* Add Experience Modal */}
      {showExpModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">Add Work Experience</h3>
              <button onClick={() => setShowExpModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleAddExperience} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Job Title *</label>
                <input
                  type="text"
                  required
                  value={newExp.title}
                  onChange={(e) => setNewExp({ ...newExp, title: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Company Name *</label>
                <input
                  type="text"
                  required
                  value={newExp.company_name}
                  onChange={(e) => setNewExp({ ...newExp, company_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Start Date *</label>
                  <input
                    type="date"
                    required
                    value={newExp.start_date}
                    onChange={(e) => setNewExp({ ...newExp, start_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">End Date</label>
                  <input
                    type="date"
                    disabled={newExp.is_current}
                    value={newExp.end_date}
                    onChange={(e) => setNewExp({ ...newExp, end_date: e.target.value })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent disabled:opacity-50"
                  />
                </div>
              </div>
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="expCurrent"
                  checked={newExp.is_current}
                  onChange={(e) => setNewExp({ ...newExp, is_current: e.target.checked })}
                  className="h-4 w-4 rounded border-slate-300 text-primary-600"
                />
                <label htmlFor="expCurrent" className="text-xs text-slate-700 dark:text-slate-300">
                  I currently work here
                </label>
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Description</label>
                <textarea
                  rows={3}
                  value={newExp.description}
                  onChange={(e) => setNewExp({ ...newExp, description: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowExpModal(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 text-white text-sm font-semibold rounded-lg hover:bg-primary-700"
                >
                  Add Experience
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Add Education Modal */}
      {showEduModal && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-xl">
            <div className="flex items-center justify-between">
              <h3 className="text-lg font-bold text-slate-900 dark:text-white">Add Education</h3>
              <button onClick={() => setShowEduModal(false)} className="text-slate-400 hover:text-slate-600">
                <X className="w-5 h-5" />
              </button>
            </div>
            <form onSubmit={handleAddEducation} className="space-y-3">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Institution *</label>
                <input
                  type="text"
                  required
                  value={newEdu.institution_name}
                  onChange={(e) => setNewEdu({ ...newEdu, institution_name: e.target.value })}
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Degree *</label>
                <input
                  type="text"
                  required
                  value={newEdu.degree}
                  onChange={(e) => setNewEdu({ ...newEdu, degree: e.target.value })}
                  placeholder="e.g. Bachelor of Science"
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Field of Study</label>
                <input
                  type="text"
                  value={newEdu.field_of_study}
                  onChange={(e) => setNewEdu({ ...newEdu, field_of_study: e.target.value })}
                  placeholder="e.g. Computer Science"
                  className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                />
              </div>
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">Start Year</label>
                  <input
                    type="number"
                    value={newEdu.start_year}
                    onChange={(e) => setNewEdu({ ...newEdu, start_year: Number(e.target.value) })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">End Year</label>
                  <input
                    type="number"
                    value={newEdu.end_year}
                    onChange={(e) => setNewEdu({ ...newEdu, end_year: Number(e.target.value) })}
                    className="w-full px-3 py-2 text-sm border border-slate-200 dark:border-slate-700 rounded-lg bg-transparent"
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowEduModal(false)}
                  className="px-4 py-2 text-sm text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 text-white text-sm font-semibold rounded-lg hover:bg-primary-700"
                >
                  Add Education
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
