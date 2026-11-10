"use client";

import React from "react";

export function DashboardSkeleton() {
  return (
    <div className="space-y-6 animate-pulse" aria-busy="true" aria-label="Loading candidate dashboard">
      {/* Banner Skeleton */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm">
        <div className="h-7 w-64 bg-slate-200 dark:bg-slate-800 rounded-md mb-2" />
        <div className="h-4 w-96 bg-slate-100 dark:bg-slate-800/60 rounded-md" />
      </div>

      {/* Profile Completeness Skeleton */}
      <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-3">
        <div className="flex justify-between items-center">
          <div className="h-5 w-40 bg-slate-200 dark:bg-slate-800 rounded-md" />
          <div className="h-5 w-12 bg-slate-200 dark:bg-slate-800 rounded-md" />
        </div>
        <div className="h-2.5 w-full bg-slate-100 dark:bg-slate-800 rounded-full" />
      </div>

      {/* Metrics Row Skeleton (5 cards) */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-5 gap-3.5">
        {[1, 2, 3, 4, 5].map((i) => (
          <div
            key={i}
            className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-4 shadow-sm space-y-2"
          >
            <div className="h-3.5 w-20 bg-slate-100 dark:bg-slate-800 rounded" />
            <div className="h-7 w-12 bg-slate-200 dark:bg-slate-800 rounded-md" />
          </div>
        ))}
      </div>

      {/* Two-Column Section Skeleton */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="h-5 w-48 bg-slate-200 dark:bg-slate-800 rounded-md" />
          <div className="space-y-3">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-16 bg-slate-50 dark:bg-slate-800/50 rounded-xl" />
            ))}
          </div>
        </div>
        <div className="bg-white dark:bg-slate-900 border border-slate-200/80 dark:border-slate-800 rounded-2xl p-6 shadow-sm space-y-4">
          <div className="h-5 w-36 bg-slate-200 dark:bg-slate-800 rounded-md" />
          <div className="space-y-3">
            {[1, 2].map((i) => (
              <div key={i} className="h-14 bg-slate-50 dark:bg-slate-800/50 rounded-xl" />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
