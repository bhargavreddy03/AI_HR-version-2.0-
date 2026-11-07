/**
 * Global application TypeScript interface declarations.
 */

export interface SystemHealthResponse {
  status: "healthy" | "degraded" | "unhealthy";
  environment: string;
  version: string;
}

export interface ApiErrorResponse {
  error: {
    code: string;
    message: string;
    details?: Record<string, unknown>;
  };
}
