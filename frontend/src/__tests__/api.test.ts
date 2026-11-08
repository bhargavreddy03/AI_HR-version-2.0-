import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getApiBaseUrl } from "@/lib/api";

describe("getApiBaseUrl discovery", () => {
  const originalEnv = process.env;

  beforeEach(() => {
    process.env = { ...originalEnv };
  });

  afterEach(() => {
    process.env = originalEnv;
    vi.unstubAllGlobals();
  });

  it("returns INTERNAL_API_URL or default in server environment (window undefined)", () => {
    vi.stubGlobal("window", undefined);

    delete process.env.INTERNAL_API_URL;
    expect(getApiBaseUrl()).toBe("http://backend:8000/api/v1");

    process.env.INTERNAL_API_URL = "http://custom-internal-host:8000/api/v1";
    expect(getApiBaseUrl()).toBe("http://custom-internal-host:8000/api/v1");
  });

  it("returns NEXT_PUBLIC_API_URL or default in browser environment (window defined)", () => {
    vi.stubGlobal("window", {});
    delete process.env.NEXT_PUBLIC_API_URL;
    expect(getApiBaseUrl()).toBe("http://localhost:8000/api/v1");

    process.env.NEXT_PUBLIC_API_URL = "https://api.staging.aihr.com/api/v1";
    expect(getApiBaseUrl()).toBe("https://api.staging.aihr.com/api/v1");
  });
});
