import { expect, test } from "@playwright/test";

test.describe("AI HR Platform E2E Authentication & Navigation Flows", () => {
  test("Home page loads successfully and exposes architectural health metadata", async ({
    page,
  }) => {
    await page.goto("/");
    await expect(page).toHaveTitle(/AI HR/i);
    await expect(
      page.getByRole("heading", { name: /AI HR Intelligence Platform/i })
    ).toBeVisible();
    await expect(page.getByText(/Frontend Core:/i)).toBeVisible();
    await expect(page.getByText(/Backend API:/i)).toBeVisible();
  });

  test("Login page client-side validation enforces required email and password", async ({
    page,
  }) => {
    await page.goto("/login");
    await expect(page.getByRole("heading", { name: /Sign In/i })).toBeVisible();

    const submitBtn = page.getByRole("button", { name: /Sign In to Platform/i });
    await submitBtn.click();

    await expect(page.getByText("Email is required")).toBeVisible();
    await expect(page.getByText("Password is required")).toBeVisible();

    // Partial input validation
    await page.getByLabel("Email Address").fill("invalid-email-address");
    await page.getByLabel("Password").fill("short");
    await submitBtn.click();

    await expect(page.getByText("Invalid email format")).toBeVisible();
    await expect(page.getByText("Password must be at least 8 characters")).toBeVisible();
  });

  test("Login rejects invalid credentials with RFC 7807 error banner", async ({
    page,
  }) => {
    await page.goto("/login");

    await page.getByLabel("Email Address").fill("nonexistent@enterprise.com");
    await page.getByLabel("Password").fill("IncorrectPassword123!");
    await page.getByRole("button", { name: /Sign In to Platform/i }).click();

    // Wait for the alert banner
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
  });

  test("Unauthenticated access to /dashboard redirects to /login", async ({ page }) => {
    await page.goto("/dashboard");
    // Next.js client redirects to /login if /auth/me returns 401
    await page.waitForURL("**/login");
    await expect(page.getByRole("heading", { name: /Sign In/i })).toBeVisible();
  });
});
