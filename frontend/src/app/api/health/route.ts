import { NextResponse } from "next/server";

export async function GET() {
  return NextResponse.json({
    status: "healthy",
    framework: "Next.js 14 (App Router)",
    timestamp: new Date().toISOString(),
  });
}
