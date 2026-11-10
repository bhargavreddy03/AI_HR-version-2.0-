"use client";

import React, { useState } from "react";
import Link from "next/link";
import {
  Menu,
  Bell,
  Search,
  LogOut,
  User,
  ShieldCheck,
  Building2,
} from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";

interface HrHeaderProps {
  onMenuClick?: () => void;
  organizationName?: string;
  userEmail?: string;
  userRole?: string;
}

export function HrHeader({
  onMenuClick,
  organizationName = "Employer Workspace",
  userEmail = "recruiter@example.com",
  userRole = "Recruiter",
}: HrHeaderProps) {
  const [showProfileMenu, setShowProfileMenu] = useState(false);

  const handleLogout = async () => {
    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Ignored
    } finally {
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
  };

  return (
    <header className="h-16 bg-white dark:bg-slate-900 border-b border-slate-200 dark:border-slate-800 sticky top-0 z-30 flex items-center justify-between px-4 sm:px-6">
      <div className="flex items-center gap-3">
        {onMenuClick && (
          <button
            type="button"
            onClick={onMenuClick}
            aria-label="Open sidebar"
            className="p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 lg:hidden"
          >
            <Menu className="w-5 h-5" />
          </button>
        )}

        {/* Global Search Bar */}
        <div className="hidden sm:flex items-center gap-2 px-3 py-1.5 bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700 rounded-xl w-64 md:w-80 text-xs">
          <Search className="w-3.5 h-3.5 text-slate-400 shrink-0" />
          <input
            type="text"
            placeholder="Search applicants, requisitions, skills..."
            className="bg-transparent border-none outline-none w-full text-slate-800 dark:text-slate-200 placeholder:text-slate-400"
          />
        </div>
      </div>

      {/* Right Actions */}
      <div className="flex items-center gap-3">
        {/* Organization Badge */}
        <div className="hidden md:flex items-center gap-1.5 px-3 py-1 bg-primary-50 dark:bg-primary-950/40 border border-primary-100 dark:border-primary-900/50 rounded-lg text-xs font-semibold text-primary-700 dark:text-primary-300">
          <Building2 className="w-3.5 h-3.5" />
          <span>{organizationName}</span>
        </div>

        {/* Notifications Icon */}
        <button
          type="button"
          aria-label="View notifications"
          className="p-2 rounded-xl text-slate-500 hover:text-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 relative transition-colors"
        >
          <Bell className="w-4 h-4" />
          <span className="absolute top-1.5 right-1.5 w-2 h-2 rounded-full bg-primary-600 ring-2 ring-white dark:ring-slate-900" />
        </button>

        {/* User Account Menu */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowProfileMenu(!showProfileMenu)}
            className="flex items-center gap-2 p-1.5 rounded-xl hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors text-xs font-semibold text-slate-700 dark:text-slate-200"
          >
            <div className="w-7 h-7 rounded-lg bg-indigo-50 dark:bg-indigo-950/60 border border-indigo-200 dark:border-indigo-800 flex items-center justify-center text-primary-600">
              <User className="w-3.5 h-3.5" />
            </div>
            <span className="hidden sm:inline font-medium max-w-[120px] truncate">
              {userEmail.split("@")[0]}
            </span>
          </button>

          {showProfileMenu && (
            <div className="absolute right-0 mt-2 w-56 bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-xl py-2 z-50 text-xs">
              <div className="px-4 py-2 border-b border-slate-100 dark:border-slate-800 space-y-0.5">
                <p className="font-semibold text-slate-900 dark:text-white truncate">
                  {userEmail}
                </p>
                <div className="flex items-center gap-1 text-[11px] text-slate-500">
                  <ShieldCheck className="w-3 h-3 text-emerald-600" />
                  <span className="capitalize">{userRole}</span>
                </div>
              </div>

              <Link
                href="/hr/settings"
                onClick={() => setShowProfileMenu(false)}
                className="flex items-center gap-2 px-4 py-2 hover:bg-slate-50 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300"
              >
                <span>Organization Settings</span>
              </Link>

              <button
                type="button"
                onClick={handleLogout}
                className="w-full flex items-center gap-2 px-4 py-2 hover:bg-red-50 dark:hover:bg-red-950/40 text-red-600 dark:text-red-400 text-left border-t border-slate-100 dark:border-slate-800 mt-1"
              >
                <LogOut className="w-3.5 h-3.5" />
                <span>Sign Out</span>
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
