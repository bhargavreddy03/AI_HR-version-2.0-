import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { Navigation } from "@/components/Navigation";

describe("Navigation Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders public sign in link when unauthenticated", () => {
    render(<Navigation user={null} />);

    expect(screen.getByRole("link", { name: /Sign In/i })).toBeDefined();
    expect(screen.queryByRole("button", { name: /Log Out/i })).toBeNull();
  });

  it("renders candidate navigation links when authenticated as candidate", () => {
    const candidateUser = {
      email: "candidate@example.com",
      role: "candidate" as const,
    };

    render(<Navigation user={candidateUser} />);

    expect(screen.getByRole("link", { name: /My Profile/i })).toBeDefined();
    expect(screen.getByRole("link", { name: /Applications/i })).toBeDefined();

    // Does NOT render recruiter or admin links
    expect(screen.queryByRole("link", { name: /Job Postings/i })).toBeNull();
    expect(screen.queryByRole("link", { name: /Security Audit/i })).toBeNull();
  });

  it("renders recruiter navigation links when authenticated as recruiter", () => {
    const recruiterUser = {
      email: "recruiter@enterprise.com",
      role: "recruiter" as const,
    };

    render(<Navigation user={recruiterUser} />);

    expect(screen.getByRole("link", { name: /Candidates/i })).toBeDefined();
    expect(screen.getByRole("link", { name: /Job Postings/i })).toBeDefined();
    expect(screen.getByRole("link", { name: /AI Screening/i })).toBeDefined();

    // Does NOT render admin links
    expect(screen.queryByRole("link", { name: /Security Audit/i })).toBeNull();
  });

  it("renders admin navigation links when authenticated as admin", () => {
    const adminUser = {
      email: "admin@enterprise.com",
      role: "admin" as const,
    };

    render(<Navigation user={adminUser} />);

    expect(screen.getByRole("link", { name: /Organization/i })).toBeDefined();
    expect(screen.getByRole("link", { name: /Security Audit/i })).toBeDefined();
  });

  it("triggers logout request and callback on clicking logout button", async () => {
    const handleLogout = vi.fn();
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve({ message: "Logged out" }),
        } as unknown as Response)
      )
    );

    render(
      <Navigation
        user={{ email: "user@enterprise.com", role: "recruiter" }}
        onLogout={handleLogout}
      />
    );

    const logoutBtn = screen.getByRole("button", { name: /Log Out/i });
    fireEvent.click(logoutBtn);

    await waitFor(() => {
      expect(handleLogout).toHaveBeenCalled();
    });
  });
});
