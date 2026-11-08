import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { GET as healthGet } from "@/app/api/health/route";
import { GET as backendHealthGet } from "@/app/api/backend-health/route";

describe("Route Handlers", () => {
  describe("Health API Route (/api/health)", () => {
    it("returns 200 OK with healthy status and metadata", async () => {
      const response = await healthGet();
      expect(response.status).toBe(200);

      const json = await response.json();
      expect(json.status).toBe("healthy");
      expect(json.framework).toContain("Next.js 14");
      expect(json.timestamp).toBeDefined();
    });
  });

  describe("Backend Health API Route (/api/backend-health)", () => {
    beforeEach(() => {
      vi.restoreAllMocks();
    });

    afterEach(() => {
      vi.restoreAllMocks();
      vi.unstubAllGlobals();
    });

    it("returns connected status when upstream backend responds healthy", async () => {
      const mockBackendData = {
        status: "healthy",
        dependencies: { database: "healthy", redis: "healthy" },
      };

      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: true,
          status: 200,
          json: async () => mockBackendData,
        })
      );

      const response = await backendHealthGet();
      expect(response.status).toBe(200);

      const json = await response.json();
      expect(json.status).toBe("connected");
      expect(json.backend).toEqual(mockBackendData);
    });

    it("returns degraded status (502) when upstream backend returns non-200", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockResolvedValue({
          ok: false,
          status: 503,
        })
      );

      const response = await backendHealthGet();
      expect(response.status).toBe(502);

      const json = await response.json();
      expect(json.status).toBe("degraded");
      expect(json.httpStatus).toBe(503);
    });

    it("returns disconnected status (503) when backend fetch throws network error", async () => {
      vi.stubGlobal(
        "fetch",
        vi.fn().mockRejectedValue(new Error("Connection refused"))
      );

      const response = await backendHealthGet();
      expect(response.status).toBe(503);

      const json = await response.json();
      expect(json.status).toBe("disconnected");
      expect(json.error).toBe("Connection refused");
    });
  });
});
