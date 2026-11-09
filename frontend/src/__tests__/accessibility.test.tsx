import { describe, expect, it } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import React from "react";
import { LoginForm } from "@/components/LoginForm";
import { Navigation } from "@/components/Navigation";

describe("Frontend Accessibility Verification", () => {
  it("LoginForm implements accessible form landmark and label associations", () => {
    render(<LoginForm redirectOnSuccess={false} />);

    // Form landmark has accessible name
    const form = screen.getByRole("form", { name: /Login Form/i });
    expect(form).toBeDefined();

    // Inputs have explicit labels
    const emailInput = screen.getByLabelText(/Email Address/i);
    const passwordInput = screen.getByLabelText(/Password/i);
    expect(emailInput.getAttribute("id")).toBe("login-email");
    expect(passwordInput.getAttribute("id")).toBe("login-password");
  });

  it("LoginForm sets aria-invalid and aria-describedby upon validation failure", () => {
    render(<LoginForm redirectOnSuccess={false} />);

    const submitBtn = screen.getByRole("button", { name: /Sign In to Platform/i });
    fireEvent.click(submitBtn);

    const emailInput = screen.getByLabelText(/Email Address/i);
    const passwordInput = screen.getByLabelText(/Password/i);

    expect(emailInput.getAttribute("aria-invalid")).toBe("true");
    expect(emailInput.getAttribute("aria-describedby")).toBe("login-email-error");

    expect(passwordInput.getAttribute("aria-invalid")).toBe("true");
    expect(passwordInput.getAttribute("aria-describedby")).toBe("login-password-error");
  });

  it("Navigation component implements accessible landmark and button semantics", () => {
    render(
      <Navigation
        user={{ email: "auditor@enterprise.com", role: "admin" }}
      />
    );

    // Nav element has aria-label
    const nav = screen.getByRole("navigation", { name: /Main Navigation/i });
    expect(nav).toBeDefined();

    // Logout button has accessible name
    const logoutBtn = screen.getByRole("button", { name: /Log Out/i });
    expect(logoutBtn.getAttribute("aria-label")).toBe("Log Out");
  });
});
