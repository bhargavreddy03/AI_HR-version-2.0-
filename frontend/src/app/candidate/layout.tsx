"use client";

import React, { useState, useEffect } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { ChevronRight, Home } from "lucide-react";
import { CandidateSidebar } from "@/components/candidate/CandidateSidebar";
import { CandidateHeader } from "@/components/candidate/CandidateHeader";
import { candidateApi } from "@/lib/candidateApi";

const ROUTE_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  profile: "My Profile",
  resumes: "My Resumes",
  jobs: "Find Jobs",
  "saved-jobs": "Saved Jobs",
  applications: "My Applications",
  settings: "Account Settings & Privacy",
};

export default function CandidateLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [candidateName, setCandidateName] = useState<string>("Candidate");
  const [candidateEmail, setCandidateEmail] = useState<string>("candidate@example.com");
  const pathname = usePathname();

  useEffect(() => {
    async function loadUser() {
      try {
        const prof = await candidateApi.getProfile();
        if (prof?.user?.full_name) {
          setCandidateName(prof.user.full_name);
        }
        if (prof?.user?.email) {
          setCandidateEmail(prof.user.email);
        }
      } catch {
        // Fallback for unauthenticated preview
      }
    }
    loadUser();
  }, []);

  // Generate breadcrumb items from current pathname
  const segments = (pathname || "")
    .split("/")
    .filter(Boolean)
    .filter((s) => s !== "candidate");

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex">
      {/* Sidebar Navigation */}
      <CandidateSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
      />

      {/* Main Content Area */}
      <div className="flex-1 flex flex-col min-w-0">
        <CandidateHeader
          onMenuClick={() => setSidebarOpen(true)}
          userName={candidateName}
          userEmail={candidateEmail}
        />

        {/* Semantic Accessible Breadcrumb Navigation */}
        <nav
          aria-label="Breadcrumb"
          className="border-b border-slate-200/60 dark:border-slate-800/80 bg-white/50 dark:bg-slate-900/50 px-4 sm:px-6 lg:px-8 py-2 text-xs text-slate-500 backdrop-blur-sm"
        >
          <ol className="flex items-center space-x-1.5 max-w-7xl mx-auto">
            <li>
              <Link
                href="/candidate/dashboard"
                className="hover:text-indigo-600 dark:hover:text-indigo-400 flex items-center gap-1 transition-colors"
              >
                <Home className="w-3.5 h-3.5" />
                <span>Portal</span>
              </Link>
            </li>
            {segments.map((segment, index) => {
              const href = `/candidate/${segments.slice(0, index + 1).join("/")}`;
              const isLast = index === segments.length - 1;
              const label = ROUTE_LABELS[segment] || segment.replace(/-/g, " ");

              return (
                <li key={segment} className="flex items-center space-x-1.5">
                  <ChevronRight className="w-3 h-3 text-slate-400 shrink-0" aria-hidden="true" />
                  {isLast ? (
                    <span
                      aria-current="page"
                      className="font-semibold text-slate-800 dark:text-slate-200 capitalize"
                    >
                      {label}
                    </span>
                  ) : (
                    <Link
                      href={href}
                      className="hover:text-indigo-600 dark:hover:text-indigo-400 capitalize transition-colors"
                    >
                      {label}
                    </Link>
                  )}
                </li>
              );
            })}
          </ol>
        </nav>

        <main className="flex-1 p-4 md:p-6 lg:p-8 max-w-7xl w-full mx-auto focus:outline-none">
          {children}
        </main>
      </div>
    </div>
  );
}
