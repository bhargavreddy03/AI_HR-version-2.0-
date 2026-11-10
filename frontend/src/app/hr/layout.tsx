"use client";

import React, { useState, useEffect } from "react";
import { HrSidebar } from "@/components/hr/HrSidebar";
import { HrHeader } from "@/components/hr/HrHeader";
import { getApiBaseUrl } from "@/lib/api";

interface UserSessionInfo {
  email: string;
  role: string;
  organization_name?: string;
}

export default function HrLayout({ children }: { children: React.ReactNode }) {
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [session, setSession] = useState<UserSessionInfo>({
    email: "recruiter@example.com",
    role: "recruiter",
    organization_name: "Acme Cloud Corp",
  });

  useEffect(() => {
    async function loadSession() {
      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(`${baseUrl}/auth/me`, {
          credentials: "include",
          headers: { Accept: "application/json" },
        });
        if (res.ok) {
          const data = await res.json();
          setSession({
            email: data.email || "recruiter@example.com",
            role: data.role || "recruiter",
            organization_name: data.organization_name || data.tenant_name || "Acme Cloud Corp",
          });
        }
      } catch {
        // Fallback session state
      }
    }

    loadSession();
  }, []);

  return (
    <div className="min-h-screen bg-slate-50/50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col">
      {/* Sidebar Navigation */}
      <HrSidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        organizationName={session.organization_name}
      />

      {/* Main Content Area */}
      <div className="lg:pl-64 flex flex-col flex-1 min-w-0">
        <HrHeader
          onMenuClick={() => setSidebarOpen(true)}
          organizationName={session.organization_name}
          userEmail={session.email}
          userRole={session.role}
        />

        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl mx-auto w-full">
          {children}
        </main>
      </div>
    </div>
  );
}
