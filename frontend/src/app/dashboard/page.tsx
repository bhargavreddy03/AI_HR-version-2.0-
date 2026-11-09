"use client";

import React, { useEffect, useState } from "react";
import { Navigation } from "@/components/Navigation";
import { getApiBaseUrl } from "@/lib/api";

interface UserProfile {
  id: string;
  email: string;
  role: "candidate" | "recruiter" | "admin" | "super_admin";
  organization_id?: string;
}

export default function DashboardPage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    async function loadUser() {
      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(`${baseUrl}/auth/me`, {
          credentials: "include",
          headers: { Accept: "application/json" },
        });

        if (!res.ok) {
          // If unauthenticated, redirect to login
          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
          return;
        }

        const data = await res.json();
        setUser({
          id: data.id || "usr-current",
          email: data.email,
          role: data.role || "recruiter",
          organization_id: data.tenant_id || data.organization_id,
        });
      } catch {
        setError("Failed to fetch session. Please log in again.");
      } finally {
        setIsLoading(false);
      }
    }

    loadUser();
  }, []);

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950">
      <Navigation
        user={user}
        onLogout={() => {
          if (typeof window !== "undefined") {
            window.location.href = "/login";
          }
        }}
      />

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6">
        <div className="rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white">
            Enterprise Recruitment Dashboard
          </h1>

          {isLoading ? (
            <div data-testid="dashboard-loading" className="py-8 text-center text-sm text-slate-500">
              Loading security context...
            </div>
          ) : error ? (
            <div role="alert" className="my-4 rounded-md bg-red-50 p-4 text-sm text-red-700">
              {error}
            </div>
          ) : user ? (
            <div className="mt-4 space-y-4">
              <div className="rounded-lg border border-slate-100 bg-slate-50 p-4 text-xs dark:border-slate-800 dark:bg-slate-950">
                <p>
                  <strong>Authenticated Identity:</strong> {user.email}
                </p>
                <p className="mt-1">
                  <strong>Assigned Role:</strong>{" "}
                  <span className="capitalize">{user.role}</span>
                </p>
                {user.organization_id && (
                  <p className="mt-1">
                    <strong>Tenant ID:</strong> {user.organization_id}
                  </p>
                )}
              </div>

              <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
                <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
                  <h3 className="text-sm font-semibold">Candidates</h3>
                  <p className="mt-1 text-xs text-slate-500">Manage pipeline candidates and resumes</p>
                </div>
                <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
                  <h3 className="text-sm font-semibold">Active Jobs</h3>
                  <p className="mt-1 text-xs text-slate-500">Monitor requisitions and applicant flow</p>
                </div>
                <div className="rounded-lg border border-slate-200 p-4 dark:border-slate-800">
                  <h3 className="text-sm font-semibold">AI Match Score</h3>
                  <p className="mt-1 text-xs text-slate-500">Embeddings-based semantic match queue</p>
                </div>
              </div>
            </div>
          ) : (
            <div className="py-6 text-sm text-slate-500">
              Session expired. Please <a href="/login" className="text-blue-600 underline">sign in</a>.
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
