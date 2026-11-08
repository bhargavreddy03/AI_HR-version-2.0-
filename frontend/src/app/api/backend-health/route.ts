import { NextResponse } from "next/server";
import { getApiBaseUrl } from "@/lib/api";

export const dynamic = "force-dynamic";

export async function GET() {
  const baseUrl = getApiBaseUrl();

  try {
    const res = await fetch(`${baseUrl}/health/ready`, {
      cache: "no-store",
      headers: {
        Accept: "application/json",
      },
    });

    if (!res.ok) {
      return NextResponse.json(
        {
          status: "degraded",
          backendUrl: baseUrl,
          httpStatus: res.status,
        },
        { status: 502 }
      );
    }

    const data: unknown = await res.json();
    return NextResponse.json({
      status: "connected",
      backendUrl: baseUrl,
      backend: data,
    });
  } catch (error) {
    return NextResponse.json(
      {
        status: "disconnected",
        backendUrl: baseUrl,
        error: error instanceof Error ? error.message : "Backend unreachable",
      },
      { status: 503 }
    );
  }
}
