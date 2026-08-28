import type { NextRequest } from "next/server";

import { forwardRequest } from "@/lib/proxy";

type RouteContext = { params: Promise<{ path: string[] }> };

async function handle(request: NextRequest, context: RouteContext) {
  const { path } = await context.params;
  return forwardRequest(
    request,
    path,
    process.env.AIRSTRONG_AIRLINE_BASE_URL ?? "http://127.0.0.1:4200",
  );
}

export const dynamic = "force-dynamic";
export const GET = handle;
export const POST = handle;
export const OPTIONS = handle;
