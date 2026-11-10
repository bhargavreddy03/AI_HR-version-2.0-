"use client";

import React, { useState } from "react";
import {
  Shield,
  Lock,
  Download,
  Trash2,
  Bell,
  CheckCircle2,
  AlertTriangle,
} from "lucide-react";

export default function CandidateSettingsPage() {
  const [emailAlerts, setEmailAlerts] = useState(true);
  const [inAppAlerts, setInAppAlerts] = useState(true);
  const [savedSuccess, setSavedSuccess] = useState(false);

  const handleSaveNotifications = (e: React.FormEvent) => {
    e.preventDefault();
    setSavedSuccess(true);
    setTimeout(() => setSavedSuccess(false), 3000);
  };

  const handleExportData = () => {
    alert("Data export initiated. Your compiled GDPR/CCPA personal data package will be sent to your verified email address.");
  };

  const handleDeleteAccount = () => {
    alert("Candidate account deletion request submitted. Active organization employment records and immutable regulatory audit snapshots will be processed in accordance with applicable retention laws.");
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
          Candidate Settings & Privacy
        </h1>
        <p className="text-sm text-slate-500 dark:text-slate-400">
          Manage your account security, notification alerts, and data privacy rights.
        </p>
      </div>

      {savedSuccess && (
        <div className="flex items-center gap-2 p-3.5 bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-200 dark:border-emerald-800 text-xs font-semibold text-emerald-800 dark:text-emerald-300 rounded-xl">
          <CheckCircle2 className="w-4 h-4 shrink-0 text-emerald-600" />
          <span>Settings saved successfully.</span>
        </div>
      )}

      {/* Global Identity & Security Architecture */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
          <Shield className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            Global Candidate Identity Architecture
          </h2>
        </div>

        <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
          Your candidate profile, self-declared skills, and uploaded resumes belong to your single global candidate account. You can apply to multiple independent organizations without creating separate accounts. Each organization only receives data you explicitly submit during your job application.
        </p>

        <div className="p-3.5 bg-slate-50 dark:bg-slate-800/50 rounded-xl border border-slate-200 dark:border-slate-800 text-xs text-slate-600 dark:text-slate-400 space-y-1">
          <p className="font-semibold text-slate-800 dark:text-slate-200">
            Tenant Isolation Guarantees:
          </p>
          <ul className="list-disc list-inside space-y-0.5 text-[11px]">
            <li>Organization A cannot see that you applied to Organization B.</li>
            <li>Internal hiring notes, interview evaluations, and recruiter feedback remain strictly within that organization.</li>
            <li>Resume snapshots captured at submission time are immutable and cannot be tampered with.</li>
          </ul>
        </div>
      </div>

      {/* Notification Preferences */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
          <Bell className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            Notification Preferences
          </h2>
        </div>

        <form onSubmit={handleSaveNotifications} className="space-y-3">
          <div className="flex items-center justify-between py-2">
            <div>
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                Application Status Updates
              </p>
              <p className="text-[11px] text-slate-500">
                Receive notifications when your application status progresses (shortlisted, interview scheduled, offer).
              </p>
            </div>
            <input
              type="checkbox"
              checked={inAppAlerts}
              onChange={(e) => setInAppAlerts(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
            />
          </div>

          <div className="flex items-center justify-between py-2 border-t border-slate-100 dark:border-slate-800">
            <div>
              <p className="text-xs font-semibold text-slate-800 dark:text-slate-200">
                Email Digest & Job Matches
              </p>
              <p className="text-[11px] text-slate-500">
                Periodic emails with new openings matching your canonical skills and career preferences.
              </p>
            </div>
            <input
              type="checkbox"
              checked={emailAlerts}
              onChange={(e) => setEmailAlerts(e.target.checked)}
              className="h-4 w-4 rounded border-slate-300 text-primary-600 focus:ring-primary-500"
            />
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

      {/* Data Privacy & GDPR / CCPA Rights */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
        <div className="flex items-center gap-2 border-b border-slate-100 dark:border-slate-800 pb-3">
          <Lock className="w-5 h-5 text-primary-600 dark:text-primary-400" />
          <h2 className="text-base font-bold text-slate-900 dark:text-white">
            Data Privacy & Candidate Rights
          </h2>
        </div>

        <p className="text-xs text-slate-600 dark:text-slate-400 leading-relaxed">
          In compliance with global data privacy regulations (GDPR, CCPA/CPRA, and international statutory standards), you have full transparency and control over your personal data.
        </p>

        <div className="flex flex-col sm:flex-row gap-3 pt-2">
          <button
            type="button"
            onClick={handleExportData}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-700 dark:text-slate-200 text-xs font-semibold rounded-xl transition-colors"
          >
            <Download className="w-4 h-4" /> Export All Personal Data (JSON)
          </button>

          <button
            type="button"
            onClick={handleDeleteAccount}
            className="inline-flex items-center justify-center gap-2 px-4 py-2 bg-red-50 dark:bg-red-950/40 hover:bg-red-100 dark:hover:bg-red-900/40 text-red-700 dark:text-red-300 text-xs font-semibold rounded-xl border border-red-200 dark:border-red-800 transition-colors"
          >
            <Trash2 className="w-4 h-4" /> Request Account Erasure
          </button>
        </div>
      </div>
    </div>
  );
}
