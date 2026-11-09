"use client";

import React, { useState } from "react";
import { getApiBaseUrl } from "@/lib/api";

interface LoginFormProps {
  onSuccess?: (user: { email: string; role?: string }) => void;
  redirectOnSuccess?: boolean;
}

export function LoginForm({ onSuccess, redirectOnSuccess = true }: LoginFormProps) {
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [fieldErrors, setFieldErrors] = useState<{ email?: string; password?: string }>({});

  const validate = (): boolean => {
    const errors: { email?: string; password?: string } = {};
    if (!email.trim()) {
      errors.email = "Email is required";
    } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      errors.email = "Invalid email format";
    }

    if (!password) {
      errors.password = "Password is required";
    } else if (password.length < 8) {
      errors.password = "Password must be at least 8 characters";
    }

    setFieldErrors(errors);
    return Object.keys(errors).length === 0;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setErrorMessage(null);

    if (!validate()) {
      return;
    }

    setIsLoading(true);

    try {
      const baseUrl = getApiBaseUrl();
      const res = await fetch(`${baseUrl}/auth/login`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        credentials: "include",
        body: JSON.stringify({ email, password }),
      });

      if (!res.ok) {
        let errorDetail = "Invalid email or password.";
        try {
          const errData = await res.json();
          errorDetail = errData.detail || errData.title || errorDetail;
        } catch {
          // fallback to default errorDetail
        }
        setErrorMessage(errorDetail);
        setIsLoading(false);
        return;
      }

      const data = await res.json();
      setIsLoading(false);

      if (onSuccess) {
        onSuccess(data);
      }

      if (redirectOnSuccess && typeof window !== "undefined") {
        window.location.href = "/dashboard";
      }
    } catch {
      setErrorMessage("Network error: Unable to connect to authentication server.");
      setIsLoading(false);
    }
  };

  return (
    <form
      onSubmit={handleSubmit}
      noValidate
      className="w-full max-w-md space-y-4 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900"
      aria-label="Login Form"
    >
      <div className="space-y-1">
        <h2 className="text-xl font-bold tracking-tight text-slate-900 dark:text-white">
          Sign In
        </h2>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          Enter your credentials to access your recruitment portal
        </p>
      </div>

      {errorMessage && (
        <div
          role="alert"
          aria-live="assertive"
          className="rounded-lg border border-red-200 bg-red-50 p-3 text-xs text-red-700 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
        >
          {errorMessage}
        </div>
      )}

      <div className="space-y-1 text-left">
        <label
          htmlFor="login-email"
          className="block text-xs font-semibold text-slate-700 dark:text-slate-300"
        >
          Email Address
        </label>
        <input
          id="login-email"
          type="email"
          name="email"
          autoComplete="email"
          disabled={isLoading}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          aria-invalid={Boolean(fieldErrors.email)}
          aria-describedby={fieldErrors.email ? "login-email-error" : undefined}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          placeholder="recruiter@enterprise.com"
        />
        {fieldErrors.email && (
          <p id="login-email-error" className="text-xs text-red-600 dark:text-red-400">
            {fieldErrors.email}
          </p>
        )}
      </div>

      <div className="space-y-1 text-left">
        <label
          htmlFor="login-password"
          className="block text-xs font-semibold text-slate-700 dark:text-slate-300"
        >
          Password
        </label>
        <input
          id="login-password"
          type="password"
          name="password"
          autoComplete="current-password"
          disabled={isLoading}
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          aria-invalid={Boolean(fieldErrors.password)}
          aria-describedby={fieldErrors.password ? "login-password-error" : undefined}
          className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm text-slate-900 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 dark:border-slate-700 dark:bg-slate-800 dark:text-white"
          placeholder="••••••••••••"
        />
        {fieldErrors.password && (
          <p id="login-password-error" className="text-xs text-red-600 dark:text-red-400">
            {fieldErrors.password}
          </p>
        )}
      </div>

      <button
        type="submit"
        disabled={isLoading}
        aria-busy={isLoading}
        className="w-full rounded-md bg-blue-600 py-2.5 text-sm font-semibold text-white transition hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-60"
      >
        {isLoading ? "Authenticating..." : "Sign In to Platform"}
      </button>
    </form>
  );
}
