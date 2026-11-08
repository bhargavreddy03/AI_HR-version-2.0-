/**
 * Client and server API URL discovery.
 *
 * - In containerized SSR (Node.js runtime inside Docker):
 *   Uses INTERNAL_API_URL (defaults to "http://backend:8000/api/v1") to communicate
 *   over the private Docker network using service names without localhost.
 * - In browser runtime (host machine):
 *   Uses NEXT_PUBLIC_API_URL (defaults to "http://localhost:8000/api/v1") so the user's
 *   browser connects to the published host port.
 */
export function getApiBaseUrl(): string {
  if (typeof window === "undefined") {
    return process.env.INTERNAL_API_URL || "http://backend:8000/api/v1";
  }
  return process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000/api/v1";
}
