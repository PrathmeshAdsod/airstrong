import {
  createServer,
  type IncomingMessage,
  type ServerResponse,
} from "node:http";

import { readRecoveryRuntimeConfig } from "./recovery-config.js";
import {
  decideRecovery,
  ensureDurableRun,
  getDurableRun,
  prepareRecovery,
  reportRecoveryFailure,
} from "./recovery-runner.js";

const config = readRecoveryRuntimeConfig();
const port = Number.parseInt(process.env.PORT ?? "4300", 10);
const allowedOrigins = new Set(
  (process.env.AIRSTRONG_WEB_ORIGINS ?? "http://localhost:3000")
    .split(",")
    .map((value) => value.trim())
    .filter(Boolean),
);
const activeTasks = new Map<string, Promise<void>>();

function send(
  response: ServerResponse,
  status: number,
  payload: Record<string, unknown>,
): void {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(JSON.stringify(payload));
}

function stringValue(value: unknown): string {
  if (typeof value === "string") {
    return value;
  }
  if (Array.isArray(value) && typeof value[0] === "string") {
    return value[0];
  }
  return "";
}

async function body(
  request: IncomingMessage,
): Promise<Record<string, unknown>> {
  const chunks: Buffer[] = [];
  let size = 0;
  for await (const chunk of request) {
    const value = Buffer.from(chunk as Uint8Array);
    size += value.length;
    if (size > 64 * 1024) {
      throw new Error("Request body exceeds 64 KiB");
    }
    chunks.push(value);
  }
  if (chunks.length === 0) {
    return {};
  }
  const parsed = JSON.parse(Buffer.concat(chunks).toString("utf8")) as unknown;
  if (typeof parsed !== "object" || parsed === null || Array.isArray(parsed)) {
    throw new Error("Request body must be a JSON object");
  }
  return parsed as Record<string, unknown>;
}

function startPreparation(
  worldId: string,
  runId: string,
  idempotencyKey: string,
): void {
  if (activeTasks.has(runId)) {
    return;
  }
  const task = prepareRecovery(config, worldId, idempotencyKey)
    .then(() => undefined)
    .catch(async (error: unknown) => {
      try {
        await reportRecoveryFailure(config, runId, "prepare", error);
      } catch (reportError) {
        console.error(
          "Failed to persist recovery preparation failure",
          reportError,
        );
      }
    })
    .finally(() => activeTasks.delete(runId));
  activeTasks.set(runId, task);
}

function startDecision(
  runId: string,
  decision: "approved" | "denied",
  idempotencyKey: string,
): void {
  if (activeTasks.has(runId)) {
    return;
  }
  const task = decideRecovery(config, runId, decision, idempotencyKey)
    .then(() => undefined)
    .catch(async (error: unknown) => {
      try {
        await reportRecoveryFailure(config, runId, "decision", error);
      } catch (reportError) {
        console.error(
          "Failed to persist recovery decision failure",
          reportError,
        );
      }
    })
    .finally(() => activeTasks.delete(runId));
  activeTasks.set(runId, task);
}

async function handleRequest(
  request: IncomingMessage,
  response: ServerResponse,
): Promise<void> {
  const origin = request.headers.origin;
  if (origin && allowedOrigins.has(origin)) {
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Vary", "Origin");
  }
  response.setHeader(
    "Access-Control-Allow-Headers",
    "Content-Type, Idempotency-Key",
  );
  response.setHeader("Access-Control-Allow-Methods", "GET, POST, OPTIONS");
  if (request.method === "OPTIONS") {
    response.writeHead(204);
    response.end();
    return;
  }

  try {
    const url = new URL(request.url ?? "/", "http://runtime.local");
    if (request.method === "GET" && url.pathname === "/health") {
      send(response, 200, { status: "ok" });
      return;
    }
    const startMatch = url.pathname.match(
      /^\/api\/worlds\/([0-9a-f-]{36})\/recovery$/,
    );
    if (request.method === "POST" && startMatch) {
      const worldId = startMatch[1]!;
      const payload = await body(request);
      const idempotencyKey = stringValue(
        request.headers["idempotency-key"] ?? payload.idempotencyKey ?? "",
      );
      const run = await ensureDurableRun(config, worldId, idempotencyKey);
      startPreparation(worldId, run.runId, idempotencyKey);
      send(response, 202, { run });
      return;
    }
    const runMatch = url.pathname.match(
      /^\/api\/recovery\/runs\/([0-9a-f-]{36})$/,
    );
    if (request.method === "GET" && runMatch) {
      send(response, 200, { run: await getDurableRun(config, runMatch[1]!) });
      return;
    }
    const decisionMatch = url.pathname.match(
      /^\/api\/recovery\/runs\/([0-9a-f-]{36})\/decision$/,
    );
    if (request.method === "POST" && decisionMatch) {
      const runId = decisionMatch[1]!;
      const payload = await body(request);
      const decision = payload.decision;
      if (decision !== "approved" && decision !== "denied") {
        throw new Error("decision must be approved or denied");
      }
      const idempotencyKey = stringValue(
        request.headers["idempotency-key"] ?? payload.idempotencyKey ?? "",
      );
      const run = await getDurableRun(config, runId);
      startDecision(runId, decision, idempotencyKey);
      send(response, 202, { run });
      return;
    }
    send(response, 404, { error: "not_found" });
  } catch (error) {
    send(response, 400, {
      error: "invalid_request",
      detail: error instanceof Error ? error.message : String(error),
    });
  }
}

const server = createServer((request, response) => {
  void handleRequest(request, response);
});

server.listen(port, "0.0.0.0", () => {
  console.log(JSON.stringify({ port, service: "airstrong-agent-runtime" }));
});
