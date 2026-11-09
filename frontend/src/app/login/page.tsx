"use client";

import React from "react";
import { LoginForm } from "@/components/LoginForm";

export default function LoginPage() {
  return (
    <main className="flex min-h-screen flex-col items-center justify-center p-4">
      <div className="mb-6 text-center">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900 dark:text-white sm:text-3xl">
          AI HR Intelligence Platform
        </h1>
        <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
          Secure Multi-Tenant SaaS Recruitment Portal
        </p>
      </div>

      <LoginForm />

      <p className="mt-4 text-center text-xs text-slate-500 dark:text-slate-400">
        <a href="/" className="hover:underline">
          &larr; Back to Platform Home
        </a>
      </p>
    </main>
  );
}
