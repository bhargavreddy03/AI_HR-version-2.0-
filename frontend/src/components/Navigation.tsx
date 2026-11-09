"use client";

import React from "react";
import { getApiBaseUrl } from "@/lib/api";

export interface NavigationProps {
  user?: {
    email: string;
    role: "candidate" | "recruiter" | "admin" | "super_admin";
    organization?: string;
  } | null;
  onLogout?: () => void;
}

export function Navigation({ user, onLogout }: NavigationProps) {
  const handleLogout = async () => {
    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Proceed with client logout even if network request fails
    }

    if (onLogout) {
      onLogout();
    } else if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  };

  return (
    <header className="w-full border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto flex max-w-7xl items-center justify-between px-4 py-3 sm:px-6">
        <div className="flex items-center space-x-6">
          <a
            href="/"
            className="text-base font-bold text-slate-900 dark:text-white"
            aria-label="AI HR Intelligence Home"
          >
            AI HR Platform
          </a>

          {user && (
            <nav aria-label="Main Navigation" className="hidden space-x-4 md:flex">
              {/* Common Links */}
              <a
                href="/dashboard"
                className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300 dark:hover:text-blue-400"
              >
                Dashboard
              </a>

              {/* Candidate-specific links */}
              {user.role === "candidate" && (
                <>
                  <a
                    href="/dashboard/profile"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    My Profile
                  </a>
                  <a
                    href="/dashboard/applications"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    Applications
                  </a>
                </>
              )}

              {/* Recruiter-specific links */}
              {(user.role === "recruiter" || user.role === "admin" || user.role === "super_admin") && (
                <>
                  <a
                    href="/dashboard/candidates"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    Candidates
                  </a>
                  <a
                    href="/dashboard/jobs"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    Job Postings
                  </a>
                  <a
                    href="/dashboard/screening"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    AI Screening
                  </a>
                </>
              )}

              {/* Admin-only links */}
              {(user.role === "admin" || user.role === "super_admin") && (
                <>
                  <a
                    href="/dashboard/organization"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    Organization
                  </a>
                  <a
                    href="/dashboard/audit"
                    className="text-xs font-medium text-slate-600 hover:text-blue-600 dark:text-slate-300"
                  >
                    Security Audit
                  </a>
                </>
              )}
            </nav>
          )}
        </div>

        <div className="flex items-center space-x-3">
          {user ? (
            <>
              <span className="hidden text-xs text-slate-600 sm:inline dark:text-slate-300">
                {user.email}
              </span>
              <span
                data-testid="user-role-badge"
                className="rounded-full bg-slate-100 px-2.5 py-0.5 text-xs font-medium capitalize text-slate-700 dark:bg-slate-800 dark:text-slate-300"
              >
                {user.role}
              </span>
              <button
                type="button"
                onClick={handleLogout}
                aria-label="Log Out"
                className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 dark:border-slate-700 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Log Out
              </button>
            </>
          ) : (
            <a
              href="/login"
              className="rounded-md bg-blue-600 px-3.5 py-1.5 text-xs font-semibold text-white hover:bg-blue-700"
            >
              Sign In
            </a>
          )}
        </div>
      </div>
    </header>
  );
}
