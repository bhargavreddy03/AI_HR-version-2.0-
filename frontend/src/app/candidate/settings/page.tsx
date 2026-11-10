"use client";

import React, { useState, useEffect } from "react";
import {
  Shield,
  Lock,
  Download,
  Trash2,
  Bell,
  CheckCircle2,
  AlertTriangle,
  Mail,
  KeyRound,
  FileText,
  Briefcase,
  Eye,
  History,
  AlertCircle,
  HelpCircle,
  Clock,
  X,
  ExternalLink,
} from "lucide-react";
import { candidateApi } from "@/lib/candidateApi";
import type {
  CandidateAccount,
  NotificationPreferences,
  PrivacyPreferences,
  CandidatePreference,
  ConsentHistoryItem,
} from "@/types/candidate";

type SettingsTab = "account" | "notifications" | "career" | "privacy" | "data_rights";

export default function CandidateSettingsPage() {
  const [activeTab, setActiveTab] = useState<SettingsTab>("account");
  const [loading, setLoading] = useState(true);
  const [saveSuccess, setSaveSuccess] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  // Account State
  const [account, setAccount] = useState<CandidateAccount | null>(null);
  const [firstName, setFirstName] = useState("");
  const [lastName, setLastName] = useState("");
  const [phoneNumber, setPhoneNumber] = useState("");

  // Password Change State
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordLoading, setPasswordLoading] = useState(false);

  // Notification Preferences State
  const [notifPrefs, setNotifPrefs] = useState<NotificationPreferences>({
    email_application_updates: true,
    email_interview_alerts: true,
    email_job_recommendations: false,
    in_app_alerts: true,
    digest_frequency: "instant",
  });

  // Privacy Preferences State
  const [privacyPrefs, setPrivacyPrefs] = useState<PrivacyPreferences>({
    profile_visibility: "applied_only",
    allow_ai_matching: true,
    data_retention_months: 24,
  });

  // Career Preferences State
  const [careerPrefs, setCareerPrefs] = useState<CandidatePreference>({
    desired_job_titles: [],
    desired_locations: [],
    remote_preference: "flexible",
    employment_types: ["full_time"],
    minimum_salary: undefined,
    currency: "USD",
  });
  const [titlesInput, setTitlesInput] = useState("");
  const [locationsInput, setLocationsInput] = useState("");

  // Consent History State
  const [consentHistory, setConsentHistory] = useState<ConsentHistoryItem[]>([]);

  // Modals
  const [showCorrectionModal, setShowCorrectionModal] = useState(false);
  const [correctionField, setCorrectionField] = useState("");
  const [correctionValue, setCorrectionValue] = useState("");
  const [correctionReason, setCorrectionReason] = useState("");
  const [correctionLoading, setCorrectionLoading] = useState(false);

  const [showDeletionModal, setShowDeletionModal] = useState(false);
  const [deletionPassword, setDeletionPassword] = useState("");
  const [deletionReason, setDeletionReason] = useState("");
  const [deletionLoading, setDeletionLoading] = useState(false);

  // Verification request status
  const [verificationStatus, setVerificationStatus] = useState<string | null>(null);

  // Load all settings
  useEffect(() => {
    async function loadAllSettings() {
      try {
        setLoading(true);
        setActionError(null);

        const [accRes, notifRes, privRes, careerRes, consentsRes] =
          await Promise.allSettled([
            candidateApi.getAccountInfo(),
            candidateApi.getNotificationPreferences(),
            candidateApi.getPrivacyPreferences(),
            candidateApi.getPreferences(),
            candidateApi.getConsentHistory(),
          ]);

        if (accRes.status === "fulfilled" && accRes.value) {
          setAccount(accRes.value);
          setFirstName(accRes.value.first_name || "");
          setLastName(accRes.value.last_name || "");
          setPhoneNumber(accRes.value.phone_number || "");
        }
        if (notifRes.status === "fulfilled" && notifRes.value) {
          setNotifPrefs(notifRes.value);
        }
        if (privRes.status === "fulfilled" && privRes.value) {
          setPrivacyPrefs(privRes.value);
        }
        if (careerRes.status === "fulfilled" && careerRes.value) {
          setCareerPrefs(careerRes.value);
          setTitlesInput((careerRes.value.desired_job_titles || []).join(", "));
          setLocationsInput((careerRes.value.desired_locations || []).join(", "));
        }
        if (consentsRes.status === "fulfilled" && consentsRes.value) {
          setConsentHistory(consentsRes.value.consents || []);
        }
      } catch (err: unknown) {
        setActionError(err instanceof Error ? err.message : "Failed to load settings");
      } finally {
        setLoading(false);
      }
    }

    loadAllSettings();
  }, []);

  const triggerSuccessToast = (msg: string) => {
    setSaveSuccess(msg);
    setTimeout(() => setSaveSuccess(null), 3500);
  };

  // 1. Account Info Save
  const handleSaveAccountInfo = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    try {
      const updated = await candidateApi.updateAccountInfo({
        first_name: firstName.trim(),
        last_name: lastName.trim(),
        phone_number: phoneNumber.trim(),
      });
      setAccount(updated);
      triggerSuccessToast("Personal contact information updated.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update account");
    }
  };

  // 2. Password Change
  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    if (newPassword !== confirmPassword) {
      setActionError("New password and confirmation do not match.");
      return;
    }
    if (newPassword.length < 8) {
      setActionError("New password must be at least 8 characters long.");
      return;
    }

    setPasswordLoading(true);
    try {
      await candidateApi.changePassword({
        current_password: currentPassword,
        new_password: newPassword,
      });
      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      triggerSuccessToast("Password changed successfully. All other active sessions have been invalidated.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to change password");
    } finally {
      setPasswordLoading(false);
    }
  };

  // 3. Email Verification Request
  const handleRequestVerification = async () => {
    setActionError(null);
    try {
      const res = await candidateApi.requestEmailVerification();
      setVerificationStatus(res.message);
      triggerSuccessToast("Verification link dispatched.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to request verification");
    }
  };

  // 4. Notification Preferences Save
  const handleSaveNotifPrefs = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    try {
      const updated = await candidateApi.updateNotificationPreferences(notifPrefs);
      setNotifPrefs(updated);
      triggerSuccessToast("Notification preferences updated.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update notification preferences");
    }
  };

  // 5. Career Preferences Save
  const handleSaveCareerPrefs = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    try {
      const desired_job_titles = titlesInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);
      const desired_locations = locationsInput
        .split(",")
        .map((s) => s.trim())
        .filter(Boolean);

      const payload: Partial<CandidatePreference> = {
        desired_job_titles,
        desired_locations,
        remote_preference: careerPrefs.remote_preference,
        employment_types: careerPrefs.employment_types,
        minimum_salary: careerPrefs.minimum_salary ? Number(careerPrefs.minimum_salary) : undefined,
        currency: careerPrefs.currency,
      };

      const updated = await candidateApi.updatePreferences(payload);
      setCareerPrefs(updated);
      triggerSuccessToast("Career preferences saved.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update career preferences");
    }
  };

  // 6. Privacy Preferences Save
  const handleSavePrivacyPrefs = async (e: React.FormEvent) => {
    e.preventDefault();
    setActionError(null);
    try {
      const updated = await candidateApi.updatePrivacyPreferences(privacyPrefs);
      setPrivacyPrefs(updated);
      triggerSuccessToast("Privacy preferences updated.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to update privacy preferences");
    }
  };

  // 7. Personal Data Export Download
  const handleDownloadExport = async () => {
    setActionError(null);
    try {
      const data = await candidateApi.getDataExport();
      const blob = new Blob([JSON.stringify(data, null, 2)], {
        type: "application/json",
      });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = `candidate_data_export_${new Date().toISOString().slice(0, 10)}.json`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      triggerSuccessToast("Personal data export (JSON) downloaded successfully.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to compile personal data export");
    }
  };

  // 8. Correction Request Submit
  const handleCorrectionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setCorrectionLoading(true);
    setActionError(null);
    try {
      await candidateApi.submitCorrectionRequest({
        field_name: correctionField.trim(),
        requested_correction: correctionValue.trim(),
        reason: correctionReason.trim(),
      });
      setShowCorrectionModal(false);
      setCorrectionField("");
      setCorrectionValue("");
      setCorrectionReason("");
      triggerSuccessToast("Formal correction request logged for data steward review.");
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Failed to submit correction request");
    } finally {
      setCorrectionLoading(false);
    }
  };

  // 9. Deletion Request Submit
  const handleDeletionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setDeletionLoading(true);
    setActionError(null);
    try {
      const res = await candidateApi.submitDeletionRequest({
        password: deletionPassword,
        reason: deletionReason.trim() || undefined,
      });
      setShowDeletionModal(false);
      setDeletionPassword("");
      triggerSuccessToast(res.message);
      alert(
        `${res.message}\n\nNotice: ${res.disclaimer}`
      );
    } catch (err: unknown) {
      setActionError(err instanceof Error ? err.message : "Account deletion rejected");
    } finally {
      setDeletionLoading(false);
    }
  };

  return (
    <div className="space-y-6 max-w-6xl mx-auto pb-12">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Account Settings & Privacy
          </h1>
          <p className="text-sm text-slate-500 dark:text-slate-400 mt-0.5">
            Manage your global candidate identity, notification channels, career targets, and statutory data rights.
          </p>
        </div>
      </div>

      {/* Global Status Banners */}
      {saveSuccess && (
        <div className="flex items-center gap-2 p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-xs font-semibold text-emerald-800 dark:text-emerald-300 rounded-xl">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
          <span>{saveSuccess}</span>
        </div>
      )}

      {actionError && (
        <div
          role="alert"
          className="flex items-center gap-2 p-3.5 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-800 text-xs font-semibold text-red-800 dark:text-red-300 rounded-xl"
        >
          <AlertCircle className="w-4 h-4 shrink-0 text-red-600" />
          <span>{actionError}</span>
        </div>
      )}

      {/* Tab Navigation */}
      <div className="flex items-center gap-2 border-b border-slate-200 dark:border-slate-800 overflow-x-auto pb-1">
        <button
          type="button"
          onClick={() => setActiveTab("account")}
          className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
            activeTab === "account"
              ? "bg-primary-600 text-white shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          <Shield className="w-3.5 h-3.5" />
          <span>Account & Security</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("notifications")}
          className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
            activeTab === "notifications"
              ? "bg-primary-600 text-white shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          <Bell className="w-3.5 h-3.5" />
          <span>Notifications</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("career")}
          className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
            activeTab === "career"
              ? "bg-primary-600 text-white shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          <Briefcase className="w-3.5 h-3.5" />
          <span>Job Preferences</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("privacy")}
          className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
            activeTab === "privacy"
              ? "bg-primary-600 text-white shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          <Eye className="w-3.5 h-3.5" />
          <span>Privacy & Consents</span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab("data_rights")}
          className={`flex items-center gap-1.5 px-4 py-2 text-xs font-semibold rounded-xl transition-colors whitespace-nowrap ${
            activeTab === "data_rights"
              ? "bg-primary-600 text-white shadow-sm"
              : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800"
          }`}
        >
          <Lock className="w-3.5 h-3.5" />
          <span>Data Subject Rights</span>
        </button>
      </div>

      {/* =================================================================== */}
      {/* TAB 1: Account & Security */}
      {/* =================================================================== */}
      {activeTab === "account" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {/* Identity & Personal Info Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
              <Shield className="w-4 h-4 text-primary-600" />
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Personal Contact Details
              </h2>
            </div>

            <form onSubmit={handleSaveAccountInfo} className="space-y-3.5">
              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    First Name
                  </label>
                  <input
                    type="text"
                    required
                    value={firstName}
                    onChange={(e) => setFirstName(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Last Name
                  </label>
                  <input
                    type="text"
                    required
                    value={lastName}
                    onChange={(e) => setLastName(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                  />
                </div>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Primary Phone Number
                </label>
                <input
                  type="text"
                  value={phoneNumber}
                  onChange={(e) => setPhoneNumber(e.target.value)}
                  placeholder="+1 (555) 000-0000"
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                />
              </div>

              <div className="flex justify-end pt-1">
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                >
                  Save Contact Information
                </button>
              </div>
            </form>
          </div>

          {/* Email Verification Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
              <Mail className="w-4 h-4 text-primary-600" />
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Email Verification Status
              </h2>
            </div>

            <div className="p-3.5 bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800 rounded-xl space-y-2 text-xs">
              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Registered Email:</span>
                <span className="font-semibold text-slate-900 dark:text-white">
                  {account?.email || "candidate@example.com"}
                </span>
              </div>

              <div className="flex items-center justify-between">
                <span className="text-slate-500 font-medium">Status:</span>
                <span className="inline-flex items-center gap-1 font-semibold text-emerald-700 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-950/40 px-2 py-0.5 rounded text-[11px]">
                  <CheckCircle2 className="w-3 h-3" />
                  Verified Account
                </span>
              </div>
            </div>

            {verificationStatus && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400 bg-amber-50 dark:bg-amber-950/30 p-2.5 rounded-lg border border-amber-200 dark:border-amber-800 leading-relaxed">
                {verificationStatus}
              </p>
            )}

            <button
              type="button"
              onClick={handleRequestVerification}
              className="w-full px-4 py-2 bg-slate-100 hover:bg-slate-200 dark:bg-slate-800 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-300 text-xs font-semibold rounded-xl transition-colors"
            >
              Request Verification Email Link
            </button>
          </div>

          {/* Password Change Card (Reauthentication) */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4 md:col-span-2">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <KeyRound className="w-4 h-4 text-primary-600" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                  Change Account Password
                </h2>
              </div>
              <span className="text-[11px] text-slate-400">
                Argon2id Hash Protected
              </span>
            </div>

            <form onSubmit={handleChangePassword} className="space-y-3.5 max-w-xl">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Current Password *
                </label>
                <input
                  type="password"
                  required
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                />
              </div>

              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    New Password *
                  </label>
                  <input
                    type="password"
                    required
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                    Confirm New Password *
                  </label>
                  <input
                    type="password"
                    required
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                  />
                </div>
              </div>

              <div className="flex justify-end pt-1">
                <button
                  type="submit"
                  disabled={passwordLoading || !currentPassword || !newPassword}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                >
                  {passwordLoading ? "Updating..." : "Update Password & Evict Other Sessions"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 2: Notification Preferences */}
      {/* =================================================================== */}
      {activeTab === "notifications" && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Bell className="w-4 h-4 text-primary-600" />
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Notification Delivery Channels
              </h2>
            </div>
            <span className="text-[11px] text-slate-400">
              In-App + Background Queue
            </span>
          </div>

          <form onSubmit={handleSaveNotifPrefs} className="space-y-4">
            <div className="divide-y divide-slate-100 dark:divide-slate-800">
              {/* In-App Alerts */}
              <div className="py-3 flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    In-App Notification Alerts
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Display real-time bell alerts for application status, interview schedules, and system messages.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifPrefs.in_app_alerts}
                  onChange={(e) =>
                    setNotifPrefs({ ...notifPrefs, in_app_alerts: e.target.checked })
                  }
                  className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                />
              </div>

              {/* Email Application Updates */}
              <div className="py-3 flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Application Milestones & Status Updates
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Send email alerts when your submission is reviewed, shortlisted, or advanced by a recruiter.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifPrefs.email_application_updates}
                  onChange={(e) =>
                    setNotifPrefs({
                      ...notifPrefs,
                      email_application_updates: e.target.checked,
                    })
                  }
                  className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                />
              </div>

              {/* Email Interview Alerts */}
              <div className="py-3 flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Interview Invitations & Rescheduling Alerts
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Immediate alerts with calendar details and conference links when interview rounds are scheduled.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifPrefs.email_interview_alerts}
                  onChange={(e) =>
                    setNotifPrefs({
                      ...notifPrefs,
                      email_interview_alerts: e.target.checked,
                    })
                  }
                  className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                />
              </div>

              {/* Email Job Recommendations */}
              <div className="py-3 flex items-center justify-between gap-4">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Matching Job Openings & Career Alerts
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Receive opportunities matched against your verified canonical skills and preferred locations.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={notifPrefs.email_job_recommendations}
                  onChange={(e) =>
                    setNotifPrefs({
                      ...notifPrefs,
                      email_job_recommendations: e.target.checked,
                    })
                  }
                  className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                />
              </div>

              {/* Digest Frequency */}
              <div className="py-3.5 flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    Email Notification Frequency
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Choose how often non-urgent communications and job match digests are delivered.
                  </p>
                </div>
                <select
                  value={notifPrefs.digest_frequency}
                  onChange={(e) =>
                    setNotifPrefs({ ...notifPrefs, digest_frequency: e.target.value })
                  }
                  className="px-3 py-1.5 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent sm:w-44 focus:ring-2 focus:ring-primary-500 focus:outline-none"
                >
                  <option value="instant">Instant Real-time</option>
                  <option value="daily">Daily Digest</option>
                  <option value="weekly">Weekly Digest</option>
                  <option value="none">Mute Non-Urgent</option>
                </select>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
              >
                Save Notification Preferences
              </button>
            </div>
          </form>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 3: Job Preferences */}
      {/* =================================================================== */}
      {activeTab === "career" && (
        <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-5">
          <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
            <div className="flex items-center gap-2">
              <Briefcase className="w-4 h-4 text-primary-600" />
              <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                Career & Role Preferences
              </h2>
            </div>
            <span className="text-[11px] text-slate-400">
              Powers Job Discovery Recommendations
            </span>
          </div>

          <form onSubmit={handleSaveCareerPrefs} className="space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Target Role Titles (Comma-separated)
              </label>
              <input
                type="text"
                value={titlesInput}
                onChange={(e) => setTitlesInput(e.target.value)}
                placeholder="e.g. Principal Cloud Architect, Senior Python Engineer, Engineering Manager"
                className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                Preferred Locations (Comma-separated)
              </label>
              <input
                type="text"
                value={locationsInput}
                onChange={(e) => setLocationsInput(e.target.value)}
                placeholder="e.g. San Francisco CA, New York NY, London UK"
                className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Work Arrangement Preference
                </label>
                <select
                  value={careerPrefs.remote_preference}
                  onChange={(e) =>
                    setCareerPrefs({
                      ...careerPrefs,
                      remote_preference: e.target.value as CandidatePreference["remote_preference"],
                    })
                  }
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none capitalize"
                >
                  <option value="flexible">Flexible / Any Arrangement</option>
                  <option value="remote">Fully Remote</option>
                  <option value="hybrid">Hybrid</option>
                  <option value="onsite">On-site</option>
                </select>
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Minimum Target Annual Salary
                </label>
                <div className="flex gap-2">
                  <select
                    value={careerPrefs.currency}
                    onChange={(e) =>
                      setCareerPrefs({ ...careerPrefs, currency: e.target.value })
                    }
                    className="w-24 px-2 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                  >
                    <option value="USD">USD ($)</option>
                    <option value="EUR">EUR (€)</option>
                    <option value="GBP">GBP (£)</option>
                    <option value="CAD">CAD ($)</option>
                  </select>
                  <input
                    type="number"
                    value={careerPrefs.minimum_salary || ""}
                    onChange={(e) =>
                      setCareerPrefs({
                        ...careerPrefs,
                        minimum_salary: e.target.value ? Number(e.target.value) : undefined,
                      })
                    }
                    placeholder="e.g. 150000"
                    className="flex-1 px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                  />
                </div>
              </div>
            </div>

            <div className="flex justify-end pt-2">
              <button
                type="submit"
                className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
              >
                Save Career Preferences
              </button>
            </div>
          </form>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 4: Privacy Preferences & Consent History */}
      {/* =================================================================== */}
      {activeTab === "privacy" && (
        <div className="space-y-6">
          {/* Privacy Preferences Card */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Eye className="w-4 h-4 text-primary-600" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                  Profile Visibility & Matching Permissions
                </h2>
              </div>
              <span className="text-[11px] text-slate-400">
                Multi-Tenant Isolation Protection
              </span>
            </div>

            <form onSubmit={handleSavePrivacyPrefs} className="space-y-4">
              <div className="space-y-2">
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300">
                  Recruiter Visibility Policy
                </label>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
                  <label
                    className={`p-3.5 border rounded-xl flex items-start gap-3 cursor-pointer transition-all ${
                      privacyPrefs.profile_visibility === "applied_only"
                        ? "border-primary-500 bg-primary-50/20 dark:bg-primary-950/20"
                        : "border-slate-200 dark:border-slate-800"
                    }`}
                  >
                    <input
                      type="radio"
                      name="visibility"
                      value="applied_only"
                      checked={privacyPrefs.profile_visibility === "applied_only"}
                      onChange={() =>
                        setPrivacyPrefs({ ...privacyPrefs, profile_visibility: "applied_only" })
                      }
                      className="mt-0.5 text-primary-600"
                    />
                    <div>
                      <p className="font-semibold text-slate-900 dark:text-white">
                        Applied Organizations Only (Recommended)
                      </p>
                      <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                        Only tenant employers where you explicitly submit a job application can view your profile and resume.
                      </p>
                    </div>
                  </label>

                  <label
                    className={`p-3.5 border rounded-xl flex items-start gap-3 cursor-pointer transition-all ${
                      privacyPrefs.profile_visibility === "discoverable"
                        ? "border-primary-500 bg-primary-50/20 dark:bg-primary-950/20"
                        : "border-slate-200 dark:border-slate-800"
                    }`}
                  >
                    <input
                      type="radio"
                      name="visibility"
                      value="discoverable"
                      checked={privacyPrefs.profile_visibility === "discoverable"}
                      onChange={() =>
                        setPrivacyPrefs({ ...privacyPrefs, profile_visibility: "discoverable" })
                      }
                      className="mt-0.5 text-primary-600"
                    />
                    <div>
                      <p className="font-semibold text-slate-900 dark:text-white">
                        Verified Employer Talent Pool
                      </p>
                      <p className="text-[11px] text-slate-500 mt-0.5 leading-relaxed">
                        Verified enterprise recruiters may discover your self-declared skills and invite you to open roles.
                      </p>
                    </div>
                  </label>
                </div>
              </div>

              <div className="flex items-center justify-between py-2 border-t border-slate-100 dark:border-slate-800">
                <div>
                  <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                    AI Talent Matching & Embedding Evaluation
                  </p>
                  <p className="text-[11px] text-slate-500">
                    Allow platform vector matching to evaluate your resume against published enterprise job requisitions.
                  </p>
                </div>
                <input
                  type="checkbox"
                  checked={privacyPrefs.allow_ai_matching}
                  onChange={(e) =>
                    setPrivacyPrefs({ ...privacyPrefs, allow_ai_matching: e.target.checked })
                  }
                  className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
                />
              </div>

              <div className="flex justify-end pt-2">
                <button
                  type="submit"
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                >
                  Save Privacy Preferences
                </button>
              </div>
            </form>
          </div>

          {/* Consent History Ledger */}
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <History className="w-4 h-4 text-primary-600" />
                <h2 className="text-sm font-bold text-slate-900 dark:text-white">
                  Candidate Consent Ledger
                </h2>
              </div>
              <span className="text-[11px] text-slate-400">
                Official Regulatory Audit History
              </span>
            </div>

            {consentHistory.length === 0 ? (
              <p className="text-xs text-slate-400 text-center py-6">
                No consent records recorded yet.
              </p>
            ) : (
              <div className="divide-y divide-slate-100 dark:divide-slate-800">
                {consentHistory.map((item) => (
                  <div key={item.consent_id} className="py-3 space-y-1">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-900 dark:text-white">
                        {item.title}
                      </span>
                      <span className="text-[10px] text-slate-400 font-mono">
                        {new Date(item.granted_at).toLocaleDateString()}
                      </span>
                    </div>
                    <p className="text-[11px] text-slate-500 leading-relaxed">
                      {item.description}
                    </p>
                    <div className="flex items-center gap-3 text-[10px] text-slate-400">
                      <span>Source: {item.source}</span>
                      {item.ip_address && <span>IP: {item.ip_address}</span>}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* TAB 5: Data Subject Rights (GDPR / CCPA) */}
      {/* =================================================================== */}
      {activeTab === "data_rights" && (
        <div className="space-y-6">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
            <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
              <Lock className="w-5 h-5 text-primary-600" />
              <h2 className="text-base font-bold text-slate-900 dark:text-white">
                Global Data Privacy & Subject Access Rights
              </h2>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              In accordance with international data governance standards (GDPR Art. 15–20, CCPA/CPRA, and statutory fair recruitment policies), you have full access to your candidate record. You may download a machine-readable export, request formal corrections, or initiate account erasure.
            </p>

            <div className="p-3.5 bg-slate-50 dark:bg-slate-800/40 rounded-xl border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400 space-y-1">
              <p className="font-semibold text-slate-800 dark:text-slate-200">
                Statutory Notice on Recruiter Evaluation Trade Secrets:
              </p>
              <p className="text-[11px] leading-relaxed">
                Personal data exports include all candidate-submitted data (profile, resumes, SHA-256 seals, submitted questionnaires, and consent declarations). Confidential internal hiring team notes, interviewer scorecards, and private assessment algorithms constitute proprietary tenant work product protected from applicant disclosure under applicable trade secret laws.
              </p>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 pt-2">
              {/* Export Button */}
              <button
                type="button"
                onClick={handleDownloadExport}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 text-xs font-semibold rounded-xl transition-colors shadow-sm"
              >
                <Download className="w-4 h-4 text-primary-600" />
                <span>Export Personal Data (JSON)</span>
              </button>

              {/* Correction Request Button */}
              <button
                type="button"
                onClick={() => setShowCorrectionModal(true)}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 text-xs font-semibold rounded-xl transition-colors shadow-sm"
              >
                <FileText className="w-4 h-4 text-primary-600" />
                <span>Request Data Correction</span>
              </button>

              {/* Deletion Request Button */}
              <button
                type="button"
                onClick={() => setShowDeletionModal(true)}
                className="inline-flex items-center justify-center gap-2 px-4 py-2.5 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-900/40 text-red-700 dark:text-red-300 text-xs font-semibold rounded-xl border border-red-200 dark:border-red-800 transition-colors shadow-sm"
              >
                <Trash2 className="w-4 h-4 text-red-600" />
                <span>Request Account Erasure</span>
              </button>
            </div>
          </div>

          {/* Statutory Compliance Notice Banner */}
          <div className="p-4 bg-amber-50/60 dark:bg-amber-950/30 border border-amber-200 dark:border-amber-800/60 rounded-xl space-y-1.5 text-xs text-amber-900 dark:text-amber-300">
            <div className="flex items-center gap-2 font-bold">
              <AlertTriangle className="w-4 h-4 text-amber-600" />
              <span>Mandatory Legal Recordkeeping Notice</span>
            </div>
            <p className="text-[11px] leading-relaxed text-amber-800 dark:text-amber-400">
              Do not promise deletion of records that must be retained under applicable policies or legal obligations. In accordance with EEOC 29 C.F.R. § 1602, OFCCP 41 C.F.R. § 60-1.12, and GDPR Art. 17(3)(b), historical job applications, consent declarations, and immutable audit logs will be retained for the legally mandated statutory retention period. Do not claim legal compliance solely because these interfaces exist.
            </p>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 1: Formal Data Correction Request */}
      {/* =================================================================== */}
      {showCorrectionModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-start justify-between">
              <h3 className="text-base font-bold text-slate-900 dark:text-white flex items-center gap-2">
                <FileText className="w-5 h-5 text-primary-600" />
                <span>Request Data Correction</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowCorrectionModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-500 leading-relaxed">
              Submit a formal request to correct inaccurate profile data, historical entries, or contact details. Your request will be logged and reviewed by the data privacy steward.
            </p>

            <form onSubmit={handleCorrectionSubmit} className="space-y-3 pt-1">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Field / Data to Correct *
                </label>
                <input
                  type="text"
                  required
                  value={correctionField}
                  onChange={(e) => setCorrectionField(e.target.value)}
                  placeholder="e.g. phone_number, work_experience, legal_name"
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-primary-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Requested Accurate Value *
                </label>
                <textarea
                  rows={2}
                  required
                  value={correctionValue}
                  onChange={(e) => setCorrectionValue(e.target.value)}
                  placeholder="Enter the accurate information..."
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Reason / Justification *
                </label>
                <textarea
                  rows={2}
                  required
                  value={correctionReason}
                  onChange={(e) => setCorrectionReason(e.target.value)}
                  placeholder="Explain why this correction is necessary..."
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowCorrectionModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={correctionLoading || !correctionField || !correctionValue}
                  className="px-4 py-2 bg-primary-600 hover:bg-primary-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                >
                  {correctionLoading ? "Logging..." : "Submit Correction Request"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* =================================================================== */}
      {/* MODAL 2: Account Erasure Request */}
      {/* =================================================================== */}
      {showDeletionModal && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl max-w-md w-full p-6 space-y-4 shadow-2xl">
            <div className="flex items-start justify-between">
              <h3 className="text-base font-bold text-red-600 flex items-center gap-2">
                <Trash2 className="w-5 h-5 text-red-600" />
                <span>Request Account Erasure</span>
              </h3>
              <button
                type="button"
                onClick={() => setShowDeletionModal(false)}
                className="text-slate-400 hover:text-slate-600"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <p className="text-xs text-slate-600 dark:text-slate-300 leading-relaxed">
              This action disables candidate authentication and revokes active sessions.
            </p>

            <div className="p-3 bg-red-50 dark:bg-red-950/40 border border-red-200 dark:border-red-900 rounded-xl text-[11px] text-red-800 dark:text-red-300 space-y-1">
              <p className="font-bold">Statutory Retention Warning:</p>
              <p className="leading-relaxed">
                Do not promise deletion of records that must be retained under applicable policies or legal obligations. Regulatory records, submitted job applications, and consent declarations are archived in accordance with mandatory EEOC and GDPR retention laws.
              </p>
            </div>

            <form onSubmit={handleDeletionSubmit} className="space-y-3 pt-1">
              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Reauthenticate: Current Password *
                </label>
                <input
                  type="password"
                  required
                  value={deletionPassword}
                  onChange={(e) => setDeletionPassword(e.target.value)}
                  placeholder="Enter your account password"
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent focus:ring-2 focus:ring-red-500 focus:outline-none"
                />
              </div>

              <div>
                <label className="block text-xs font-semibold text-slate-700 dark:text-slate-300 mb-1">
                  Reason for Account Erasure (Optional)
                </label>
                <textarea
                  rows={2}
                  value={deletionReason}
                  onChange={(e) => setDeletionReason(e.target.value)}
                  placeholder="e.g. Leaving the platform, no longer seeking opportunities..."
                  className="w-full px-3 py-2 text-xs border border-slate-200 dark:border-slate-700 rounded-xl bg-transparent"
                />
              </div>

              <div className="flex justify-end gap-2 pt-2">
                <button
                  type="button"
                  onClick={() => setShowDeletionModal(false)}
                  className="px-4 py-2 text-xs font-semibold text-slate-600 hover:text-slate-800"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  disabled={deletionLoading || !deletionPassword}
                  className="px-4 py-2 bg-red-600 hover:bg-red-700 disabled:opacity-50 text-white text-xs font-semibold rounded-xl shadow-sm transition-colors"
                >
                  {deletionLoading ? "Processing..." : "Confirm Account Erasure"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
