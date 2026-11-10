"use client";

import React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  LayoutDashboard,
  User,
  FileText,
  Briefcase,
  Bookmark,
  SendHorizontal,
  Calendar,
  Settings,
  X,
} from "lucide-react";

interface CandidateSidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
}

const NAV_ITEMS = [
  {
    name: "Dashboard",
    href: "/candidate/dashboard",
    icon: LayoutDashboard,
  },
  {
    name: "My Profile",
    href: "/candidate/profile",
    icon: User,
  },
  {
    name: "Resumes",
    href: "/candidate/resumes",
    icon: FileText,
  },
  {
    name: "Find Jobs",
    href: "/candidate/jobs",
    icon: Briefcase,
  },
  {
    name: "Saved Jobs",
    href: "/candidate/saved-jobs",
    icon: Bookmark,
  },
  {
    name: "My Applications",
    href: "/candidate/applications",
    icon: SendHorizontal,
  },
  {
    name: "Interviews",
    href: "/candidate/interviews",
    icon: Calendar,
  },
  {
    name: "Settings & Privacy",
    href: "/candidate/settings",
    icon: Settings,
  },
];

export function CandidateSidebar({ isOpen, onClose }: CandidateSidebarProps) {
  const pathname = usePathname();

  return (
    <>
      {/* Mobile backdrop */}
      {isOpen && (
        <div
          className="fixed inset-0 z-40 bg-slate-900/60 backdrop-blur-sm lg:hidden"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      {/* Sidebar Container */}
      <aside
        className={`fixed top-0 bottom-0 left-0 z-50 flex w-64 flex-col border-r border-slate-200 bg-white shadow-lg transition-transform duration-200 ease-in-out dark:border-slate-800 dark:bg-slate-900 lg:static lg:z-0 lg:shadow-none ${
          isOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        }`}
        aria-label="Candidate Navigation Sidebar"
      >
        {/* Brand Header */}
        <div className="flex h-16 items-center justify-between border-b border-slate-200 px-6 dark:border-slate-800">
          <Link
            href="/candidate/dashboard"
            className="flex items-center gap-2 text-base font-bold text-slate-900 dark:text-white"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-lg bg-blue-600 text-white font-black text-sm">
              AI
            </div>
            <span>Candidate Portal</span>
          </Link>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="rounded-lg p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-700 lg:hidden dark:text-slate-400 dark:hover:bg-slate-800"
              aria-label="Close sidebar"
            >
              <X className="h-5 w-5" />
            </button>
          )}
        </div>

        {/* Navigation Links */}
        <nav className="flex-1 space-y-1.5 overflow-y-auto px-4 py-4">
          {NAV_ITEMS.map((item) => {
            const Icon = item.icon;
            const isActive =
              pathname === item.href ||
              (item.href !== "/candidate/dashboard" && pathname?.startsWith(item.href));

            return (
              <Link
                key={item.name}
                href={item.href}
                onClick={onClose}
                className={`group flex items-center gap-3 rounded-lg px-3.5 py-2.5 text-sm font-medium transition-colors ${
                  isActive
                    ? "bg-blue-50 text-blue-700 dark:bg-blue-950/40 dark:text-blue-300"
                    : "text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-400 dark:hover:bg-slate-800 dark:hover:text-slate-200"
                }`}
              >
                <Icon
                  className={`h-4 w-4 shrink-0 transition-colors ${
                    isActive
                      ? "text-blue-600 dark:text-blue-400"
                      : "text-slate-400 group-hover:text-slate-600 dark:text-slate-500 dark:group-hover:text-slate-300"
                  }`}
                />
                <span>{item.name}</span>
              </Link>
            );
          })}
        </nav>

        {/* Footer Identity Hint */}
        <div className="border-t border-slate-200 p-4 dark:border-slate-800">
          <div className="rounded-lg bg-slate-50 p-3 text-xs text-slate-600 dark:bg-slate-800/60 dark:text-slate-400">
            <p className="font-semibold text-slate-900 dark:text-slate-200">
              Global Identity
            </p>
            <p className="mt-0.5 text-[11px] leading-relaxed">
              One candidate account connects you to all partner organizations.
            </p>
          </div>
        </div>
      </aside>
    </>
  );
}
