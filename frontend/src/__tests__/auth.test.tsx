import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import React from "react";
import { LoginForm } from "@/components/LoginForm";

describe("LoginForm Component", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("renders email, password inputs and submit button", () => {
    render(<LoginForm redirectOnSuccess={false} />);

    expect(screen.getByLabelText(/Email Address/i)).toBeDefined();
    expect(screen.getByLabelText(/Password/i)).toBeDefined();
    expect(screen.getByRole("button", { name: /Sign In to Platform/i })).toBeDefined();
  });

  it("validates empty submission and renders validation errors", async () => {
    render(<LoginForm redirectOnSuccess={false} />);

    const submitBtn = screen.getByRole("button", { name: /Sign In to Platform/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Email is required")).toBeDefined();
      expect(screen.getByText("Password is required")).toBeDefined();
    });
  });

  it("validates invalid email format and short password", async () => {
    render(<LoginForm redirectOnSuccess={false} />);

    const emailInput = screen.getByLabelText(/Email Address/i);
    const passwordInput = screen.getByLabelText(/Password/i);
    const submitBtn = screen.getByRole("button", { name: /Sign In to Platform/i });

    fireEvent.change(emailInput, { target: { value: "not-an-email" } });
    fireEvent.change(passwordInput, { target: { value: "short" } });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(screen.getByText("Invalid email format")).toBeDefined();
      expect(screen.getByText("Password must be at least 8 characters")).toBeDefined();
    });
  });

  it("submits valid credentials and calls onSuccess on HTTP 200", async () => {
    const handleSuccess = vi.fn();
    const mockUser = { id: "usr-1", email: "recruiter@enterprise.com", role: "recruiter" };

    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: true,
          status: 200,
          json: () => Promise.resolve(mockUser),
        } as unknown as Response)
      )
    );

    render(<LoginForm onSuccess={handleSuccess} redirectOnSuccess={false} />);

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: "recruiter@enterprise.com" },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: "ValidPassword123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Sign In to Platform/i }));

    await waitFor(() => {
      expect(handleSuccess).toHaveBeenCalledWith(mockUser);
    });
  });

  it("displays server error message on 401 unauthorized failure", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() =>
        Promise.resolve({
          ok: false,
          status: 401,
          json: () =>
            Promise.resolve({
              code: "UNAUTHORIZED",
              detail: "Invalid email or password credentials provided.",
            }),
        } as unknown as Response)
      )
    );

    render(<LoginForm redirectOnSuccess={false} />);

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: "wrong@enterprise.com" },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: "IncorrectPassword123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Sign In to Platform/i }));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert).toBeDefined();
      expect(alert.textContent).toContain("Invalid email or password credentials provided.");
    });
  });

  it("displays network error message on fetch rejection", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockImplementation(() => Promise.reject(new Error("Connection refused")))
    );

    render(<LoginForm redirectOnSuccess={false} />);

    fireEvent.change(screen.getByLabelText(/Email Address/i), {
      target: { value: "user@enterprise.com" },
    });
    fireEvent.change(screen.getByLabelText(/Password/i), {
      target: { value: "CorrectPassword123!" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Sign In to Platform/i }));

    await waitFor(() => {
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toContain("Network error: Unable to connect");
    });
  });
});
