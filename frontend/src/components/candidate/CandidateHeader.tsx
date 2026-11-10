"use client";

import React, { useState, useEffect, useRef } from "react";
import { Menu, Bell, Check, ExternalLink, LogOut, User as UserIcon } from "lucide-react";
import { getApiBaseUrl } from "@/lib/api";

interface NotificationItem {
  id: string;
  title: string;
  message: string;
  category: string;
  is_read: boolean;
  action_url?: string | null;
  created_at: string;
}

interface CandidateHeaderProps {
  onMenuClick?: () => void;
  userEmail?: string;
  userName?: string;
}

export function CandidateHeader({
  onMenuClick,
  userEmail = "candidate@example.com",
  userName = "Candidate",
}: CandidateHeaderProps) {
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [isNotifOpen, setIsNotifOpen] = useState(false);
  const [isUserMenuOpen, setIsUserMenuOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    async function loadNotifications() {
      try {
        const baseUrl = getApiBaseUrl();
        const res = await fetch(`${baseUrl}/candidates/me/notifications`, {
          credentials: "include",
        });
        if (res.ok) {
          const data = await res.json();
          const items = Array.isArray(data) ? data : (data.notifications || []);
          setNotifications(items);
          setUnreadCount(items.filter((item: NotificationItem) => !item.is_read).length);
        }
      } catch {
        // Graceful fallback for offline / mock testing
      }
    }
    loadNotifications();
  }, []);

  const handleMarkAllRead = async () => {
    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/candidates/me/notifications/read-all`, {
        method: "POST",
        credentials: "include",
      });
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    } catch {
      setNotifications((prev) => prev.map((n) => ({ ...n, is_read: true })));
      setUnreadCount(0);
    }
  };

  const handleMarkOneRead = async (id: string) => {
    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/candidates/me/notifications/${id}/read`, {
        method: "PATCH",
        credentials: "include",
      });
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    } catch {
      setNotifications((prev) =>
        prev.map((n) => (n.id === id ? { ...n, is_read: true } : n))
      );
      setUnreadCount((prev) => Math.max(0, prev - 1));
    }
  };

  const handleLogout = async () => {
    try {
      const baseUrl = getApiBaseUrl();
      await fetch(`${baseUrl}/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // Proceed with redirect
    }
    if (typeof window !== "undefined") {
      window.location.href = "/login";
    }
  };

  return (
    <header className="sticky top-0 z-30 flex h-16 w-full items-center justify-between border-b border-slate-200 bg-white/90 px-4 backdrop-blur-md dark:border-slate-800 dark:bg-slate-900/90 sm:px-6">
      {/* Left: Mobile hamburger */}
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={onMenuClick}
          className="rounded-lg p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 lg:hidden dark:text-slate-300 dark:hover:bg-slate-800"
          aria-label="Open sidebar"
        >
          <Menu className="h-5 w-5" />
        </button>
        <span className="hidden text-sm font-medium text-slate-500 sm:inline dark:text-slate-400">
          Welcome back, <strong className="text-slate-800 dark:text-slate-200">{userName}</strong>
        </span>
      </div>

      {/* Right: Notifications & User profile */}
      <div className="flex items-center gap-3" ref={dropdownRef}>
        {/* Notifications Dropdown */}
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setIsNotifOpen(!isNotifOpen);
              setIsUserMenuOpen(false);
            }}
            className="relative rounded-full p-2 text-slate-600 hover:bg-slate-100 hover:text-slate-900 dark:text-slate-300 dark:hover:bg-slate-800"
            aria-label="Notifications"
          >
            <Bell className="h-5 w-5" />
            {unreadCount > 0 && (
              <span className="absolute top-1 right-1 flex h-4 min-w-[1rem] items-center justify-center rounded-full bg-blue-600 px-1 text-[10px] font-bold text-white ring-2 ring-white dark:ring-slate-900">
                {unreadCount > 9 ? "9+" : unreadCount}
              </span>
            )}
          </button>

          {isNotifOpen && (
            <div className="absolute right-0 mt-2 w-80 rounded-xl border border-slate-200 bg-white shadow-xl dark:border-slate-800 dark:bg-slate-900 sm:w-96">
              <div className="flex items-center justify-between border-b border-slate-100 p-3 dark:border-slate-800">
                <span className="text-xs font-bold text-slate-900 dark:text-white">
                  Notifications
                </span>
                {unreadCount > 0 && (
                  <button
                    type="button"
                    onClick={handleMarkAllRead}
                    className="flex items-center gap-1 text-[11px] font-medium text-blue-600 hover:underline dark:text-blue-400"
                  >
                    <Check className="h-3 w-3" />
                    Mark all as read
                  </button>
                )}
              </div>

              <div className="max-h-72 divide-y divide-slate-100 overflow-y-auto dark:divide-slate-800">
                {notifications.length === 0 ? (
                  <div className="py-8 text-center text-xs text-slate-500">
                    No new notifications
                  </div>
                ) : (
                  notifications.map((notif) => (
                    <div
                      key={notif.id}
                      onClick={() => !notif.is_read && handleMarkOneRead(notif.id)}
                      className={`p-3 text-xs transition-colors cursor-pointer ${
                        notif.is_read
                          ? "bg-white opacity-70 dark:bg-slate-900"
                          : "bg-blue-50/50 dark:bg-blue-950/20 hover:bg-blue-50"
                      }`}
                    >
                      <p className="font-semibold text-slate-900 dark:text-white">
                        {notif.title}
                      </p>
                      <p className="mt-0.5 text-slate-600 dark:text-slate-300">
                        {notif.message}
                      </p>
                      {notif.action_url && (
                        <a
                          href={notif.action_url}
                          className="mt-1.5 inline-flex items-center gap-1 font-medium text-blue-600 hover:underline dark:text-blue-400"
                        >
                          View Details <ExternalLink className="h-3 w-3" />
                        </a>
                      )}
                    </div>
                  ))
                )}
              </div>
            </div>
          )}
        </div>

        {/* User Avatar Menu */}
        <div className="relative">
          <button
            type="button"
            onClick={() => {
              setIsUserMenuOpen(!isUserMenuOpen);
              setIsNotifOpen(false);
            }}
            className="flex items-center gap-2 rounded-full p-1 hover:ring-2 hover:ring-blue-500/20"
            aria-label="User profile menu"
          >
            <div className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-200 text-xs font-bold text-slate-700 dark:bg-slate-700 dark:text-slate-200">
              {userName.slice(0, 2).toUpperCase()}
            </div>
          </button>

          {isUserMenuOpen && (
            <div className="absolute right-0 mt-2 w-56 rounded-xl border border-slate-200 bg-white py-1.5 shadow-xl dark:border-slate-800 dark:bg-slate-900">
              <div className="border-b border-slate-100 px-3.5 py-2 dark:border-slate-800">
                <p className="text-xs font-bold text-slate-900 dark:text-white">{userName}</p>
                <p className="truncate text-[11px] text-slate-500">{userEmail}</p>
              </div>

              <a
                href="/candidate/profile"
                className="flex items-center gap-2 px-3.5 py-2 text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                <UserIcon className="h-3.5 w-3.5" />
                Profile & Skills
              </a>

              <a
                href="/candidate/settings"
                className="flex items-center gap-2 px-3.5 py-2 text-xs text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
              >
                Account Settings
              </a>

              <button
                type="button"
                onClick={handleLogout}
                className="flex w-full items-center gap-2 px-3.5 py-2 text-xs font-medium text-rose-600 hover:bg-rose-50 dark:text-rose-400 dark:hover:bg-rose-950/20"
              >
                <LogOut className="h-3.5 w-3.5" />
                Sign Out
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
