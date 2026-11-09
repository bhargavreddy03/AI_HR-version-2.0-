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

  test("Login rejects invalid credentials with verified backend 401 response and alert banner", async ({
    page,
  }) => {
    await page.goto("/login");

    await page.getByLabel("Email Address").fill("nonexistent@enterprise.com");
    await page.getByLabel("Password").fill("IncorrectPassword123!");

    // Await actual network response from backend to prevent false positives from UI glitches or route mismatches
    const responsePromise = page.waitForResponse(
      (response) =>
        response.url().includes("/auth/login") &&
        response.request().method() === "POST",
      { timeout: 10000 }
    );

    await page.getByRole("button", { name: /Sign In to Platform/i }).click();

    const response = await responsePromise;
    expect(response.status()).toBe(401);

    const errorJson = await response.json();
    expect(errorJson).toBeTruthy();
    expect(errorJson.detail || errorJson.code || errorJson.title).toBeTruthy();

    // Assert UI surfaces accessible alert
    const alert = page.getByRole("alert");
    await expect(alert).toBeVisible();
    await expect(alert).toContainText(/invalid/i);
  });

  test("Unauthenticated access to /dashboard redirects to /login", async ({ page }) => {
    await page.goto("/dashboard");
    // Next.js client redirects to /login if session check returns unauthenticated
    await page.waitForURL("**/login");
    await expect(page.getByRole("heading", { name: /Sign In/i })).toBeVisible();
  });

  test("Protected backend API resources reject unauthenticated requests directly with HTTP 401", async ({
    request,
  }) => {
    // Verifies backend server-level defense, independent of browser client redirect logic
    const backendBase = process.env.BACKEND_BASE_URL || "http://127.0.0.1:8000/api/v1";
    const response = await request.get(`${backendBase}/auth/me`, {
      headers: {
        Accept: "application/json",
      },
    });

    expect(response.status()).toBe(401);
    const body = await response.json();
    expect(body.status || response.status()).toBe(401);
    expect(body.code || body.detail || body.title).toBeTruthy();
  });
});
