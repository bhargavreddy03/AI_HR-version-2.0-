"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  Briefcase,
  Users,
  Kanban,
  UserCheck,
  Settings,
  X,
  ExternalLink,
  ShieldCheck,
  Building2,
} from "lucide-react";

interface HrSidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
  organizationName?: string;
}

const navItems = [
  {
    name: "Recruitment Overview",
    href: "/hr/dashboard",
    icon: LayoutDashboard,
  },
  {
    name: "Job Requisitions",
    href: "/hr/jobs",
    icon: Briefcase,
  },
  {
    name: "Applicant Pool",
    href: "/hr/applicants",
    icon: Users,
  },
  {
    name: "Pipeline Board",
    href: "/hr/pipeline",
    icon: Kanban,
  },
  {
    name: "Team & Assignments",
    href: "/hr/assignments",
    icon: UserCheck,
  },
  {
    name: "Organization Settings",
    href: "/hr/settings",
    icon: Settings,
  },
];

export function HrSidebar({
  isOpen = false,
  onClose,
  organizationName = "Employer Workspace",
}: HrSidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/40 backdrop-blur-sm lg:hidden transition-opacity"
          onClick={onClose}
        />
      )}

      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 w-64 bg-white dark:bg-slate-900 border-r border-slate-200 dark:border-slate-800 transition-transform duration-200 ease-in-out lg:translate-x-0 ${
          isOpen ? "translate-x-0" : "-translate-x-full"
        }`}
      >
        <div className="flex flex-col h-full">
          {/* Header & Logo */}
          <div className="h-16 flex items-center justify-between px-6 border-b border-slate-100 dark:border-slate-800">
            <Link href="/hr/dashboard" className="flex items-center gap-2.5">
              <div className="w-8 h-8 rounded-xl bg-gradient-to-tr from-primary-600 to-indigo-600 flex items-center justify-center text-white shadow-sm">
                <ShieldCheck className="w-4 h-4" />
              </div>
              <div className="flex flex-col">
                <span className="font-bold text-sm tracking-tight text-slate-900 dark:text-white">
                  AI HR Intelligence
                </span>
                <span className="text-[10px] text-primary-600 dark:text-primary-400 font-semibold tracking-wider uppercase">
                  Recruiter Portal
                </span>
              </div>
            </Link>

            {onClose && (
              <button
                type="button"
                onClick={onClose}
                aria-label="Close sidebar"
                className="p-1 rounded-lg text-slate-400 hover:text-slate-600 hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
              >
                <X className="w-5 h-5" />
              </button>
            )}
          </div>

          {/* Active Organization Context Card */}
          <div className="px-4 py-3 mx-4 my-3 bg-slate-50 dark:bg-slate-800/40 border border-slate-200/80 dark:border-slate-800 rounded-xl">
            <div className="flex items-center gap-2 text-xs">
              <Building2 className="w-3.5 h-3.5 text-primary-600 shrink-0" />
              <div className="truncate">
                <p className="text-[10px] uppercase font-bold text-slate-400 tracking-wider">
                  Active Tenant
                </p>
                <p className="font-semibold text-slate-900 dark:text-white truncate">
                  {organizationName}
                </p>
              </div>
            </div>
          </div>

          {/* Nav List */}
          <nav className="flex-1 px-4 py-2 space-y-1 overflow-y-auto">
            {navItems.map((item) => {
              const isActive =
                item.href === "/hr/dashboard"
                  ? pathname === item.href
                  : pathname.startsWith(item.href);
              const Icon = item.icon;

              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onClose}
                  className={`flex items-center gap-3 px-3.5 py-2.5 rounded-xl text-xs font-semibold transition-colors ${
                    isActive
                      ? "bg-primary-50 dark:bg-primary-950/40 text-primary-700 dark:text-primary-300 font-bold border border-primary-100 dark:border-primary-900/50"
                      : "text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-white hover:bg-slate-50 dark:hover:bg-slate-800/50"
                  }`}
                >
                  <Icon
                    className={`w-4 h-4 transition-colors ${
                      isActive
                        ? "text-primary-600 dark:text-primary-400"
                        : "text-slate-400 group-hover:text-slate-600"
                    }`}
                  />
                  <span>{item.name}</span>
                </Link>
              );
            })}
          </nav>

          {/* Candidate Portal Switcher & Footer */}
          <div className="p-4 border-t border-slate-100 dark:border-slate-800 space-y-2">
            <Link
              href="/candidate/dashboard"
              className="flex items-center justify-between px-3.5 py-2.5 rounded-xl text-xs font-medium text-slate-600 dark:text-slate-400 hover:text-slate-900 hover:bg-slate-50 dark:hover:bg-slate-800 transition-colors border border-slate-200/60 dark:border-slate-800"
            >
              <div className="flex items-center gap-2">
                <Users className="w-3.5 h-3.5 text-primary-500" />
                <span>Candidate Portal</span>
              </div>
              <ExternalLink className="w-3.5 h-3.5 text-slate-400" />
            </Link>

            <div className="px-2 pt-1">
              <span className="text-[10px] text-slate-400 block">
                Multi-Tenant Enterprise SaaS v2.0
              </span>
            </div>
          </div>
        </div>
      </aside>
    </>
  );
}
