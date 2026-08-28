import { randomUUID } from "node:crypto";

import { readRecoveryRuntimeConfig } from "./recovery-config.js";
import { decideRecovery, prepareRecovery } from "./recovery-runner.js";

const config = readRecoveryRuntimeConfig();
const requestedTrials = Number.parseInt(process.argv[2] ?? "3", 10);
if (
  !Number.isInteger(requestedTrials) ||
  requestedTrials < 2 ||
  requestedTrials > 10
) {
  throw new Error("Usage: npm run model:evaluate -- <trials between 2 and 10>");
}
const minimumStartSpacingMs = Number.parseInt(
  process.env.AIRSTRONG_MODEL_EVAL_START_SPACING_MS ?? "70000",
  10,
);
if (
  !Number.isInteger(minimumStartSpacingMs) ||
  minimumStartSpacingMs < 0 ||
  minimumStartSpacingMs > 300_000
) {
  throw new Error(
    "AIRSTRONG_MODEL_EVAL_START_SPACING_MS must be between 0 and 300000",
  );
}

async function airlineRequest<T>(
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${config.airlineBaseUrl}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw new Error(
      `${path} failed (${response.status}): ${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

type WorldResponse = { world: { worldId: string } };
type ScenarioResponse = { worldRevision: number };

const results: Array<Record<string, unknown>> = [];
let previousTrialStartedAt = 0;
for (let index = 0; index < requestedTrials; index += 1) {
  const waitMs = Math.max(
    0,
    previousTrialStartedAt + minimumStartSpacingMs - Date.now(),
  );
  if (waitMs > 0) await new Promise((resolve) => setTimeout(resolve, waitMs));
  previousTrialStartedAt = Date.now();
  const trialId = randomUUID();
  const worldKey = `model-eval-world-${trialId}`;
  const world = await airlineRequest<WorldResponse>("/api/worlds", {
    body: JSON.stringify({
      displayName: `Aliens Airline model evaluation ${index + 1}`,
    }),
    headers: { "Idempotency-Key": worldKey },
    method: "POST",
  });
  const worldId = world.world.worldId;
  const scenario = await airlineRequest<ScenarioResponse>(
    `/api/worlds/${worldId}/scenarios/hero`,
    {
      headers: { "Idempotency-Key": `model-eval-hero-${trialId}` },
      method: "POST",
    },
  );

  const startedAt = Date.now();
  try {
    let run = await prepareRecovery(
      config,
      worldId,
      `model-eval-run-${trialId}`,
    );
    const pausedWithoutWrite =
      run.status === "awaiting_approval" &&
      run.approvalStatus === "pending" &&
      run.executionId === null;
    if (run.status === "awaiting_approval") {
      run = await decideRecovery(
        config,
        run.runId,
        "denied",
        `model-eval-deny-${trialId}`,
      );
    }
    const terminalIsSafe =
      run.status === "denied" || run.status === "no_valid_candidate";
    const passed =
      run.trueforgeSessionId !== null &&
      run.investigationTurnId !== null &&
      run.batchId !== null &&
      terminalIsSafe &&
      (run.status === "no_valid_candidate" || pausedWithoutWrite) &&
      run.executionId === null;
    results.push({
      durationMs: Date.now() - startedAt,
      generatedBatch: run.batchId !== null,
      noWriteBeforeApproval: run.executionId === null,
      passed,
      runId: run.runId,
      scenarioRevision: scenario.worldRevision,
      status: run.status,
      trueforgeSessionId: run.trueforgeSessionId,
      worldId,
    });
  } catch (error) {
    results.push({
      durationMs: Date.now() - startedAt,
      error: error instanceof Error ? error.message : String(error),
      passed: false,
      scenarioRevision: scenario.worldRevision,
      worldId,
    });
  }
}

const passed = results.filter((result) => result.passed === true).length;
console.log(
  JSON.stringify({ passed, results, trials: requestedTrials }, null, 2),
);
if (passed !== requestedTrials) process.exitCode = 1;
