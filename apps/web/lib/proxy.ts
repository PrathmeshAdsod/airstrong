import type { NextRequest } from "next/server";

const forwardedHeaders = [
  "accept",
  "content-type",
  "idempotency-key",
  "last-event-id",
] as const;

export async function forwardRequest(
  request: NextRequest,
  path: string[],
  baseUrl: string,
): Promise<Response> {
  const encodedPath = path
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const upstreamUrl = new URL(
    `/${encodedPath}`,
    `${baseUrl.replace(/\/$/, "")}/`,
  );
  upstreamUrl.search = request.nextUrl.search;

  const headers = new Headers();
  for (const name of forwardedHeaders) {
    const value = request.headers.get(name);
    if (value) headers.set(name, value);
  }

  const hasBody = request.method !== "GET" && request.method !== "HEAD";
  const upstream = await fetch(upstreamUrl, {
    method: request.method,
    headers,
    body: hasBody ? await request.arrayBuffer() : undefined,
    cache: "no-store",
    redirect: "manual",
  });

  const responseHeaders = new Headers();
  for (const name of ["cache-control", "content-type", "x-accel-buffering"]) {
    const value = upstream.headers.get(name);
    if (value) responseHeaders.set(name, value);
  }

  return new Response(upstream.body, {
    status: upstream.status,
    headers: responseHeaders,
  });
}
