import { TrueForge, type TrueForgeApi } from "@truefoundry/trueforge-sdk";

import type { RecoveryRuntimeConfig } from "./recovery-config.js";
import {
  analyzeRecoveryEvidence,
  type RecoveryEvidence,
} from "./recovery-evidence.js";

const AGENT_NAME = "airstrong-recovery";
const MCP_NAME = "airstrong-airline";
const MODEL_NAME = "google-gemini/gemini-3-5-flash-lite";

interface EvaluationResponse {
  batch: {
    candidates: Array<{
      candidateId: string;
      recommended: boolean;
      valid: boolean;
      violations: unknown[];
    }>;
  };
  batchId: string;
  lineage: { artifactHash: string };
}

export interface DurableRecoveryRun {
  approvalActions: Array<Record<string, unknown>> | null;
  approvalContinuationTurnId: string | null;
  approvalId: string | null;
  approvalStatus: "approved" | "consumed" | "denied" | "pending" | null;
  approvalSummary: Record<string, number> | null;
  appliedWorldRevision: number | null;
  batchId: string | null;
  executionId: string | null;
  executionTurnId: string | null;
  expectedWorldRevision: number | null;
  investigationTurnId: string | null;
  planHash: string | null;
  recommendedCandidateId: string | null;
  runId: string;
  snapshotHash: string;
  startedWorldRevision: number;
  status:
    | "approved"
    | "awaiting_approval"
    | "candidates_ranked"
    | "computing"
    | "denied"
    | "executing"
    | "failed"
    | "investigating"
    | "no_valid_candidate"
    | "stale"
    | "verified"
    | "verifying";
  trueforgeApprovalEventId: string | null;
  trueforgeSessionId: string | null;
  trueforgeThreadId: string | null;
  trueforgeToolCallId: string | null;
  verificationValid: boolean | null;
  worldId: string;
}

interface RunResponse {
  replayed?: boolean;
  run: DurableRecoveryRun;
}

export async function configureRecoveryAgent(
  client: TrueForge,
  config: RecoveryRuntimeConfig,
): Promise<void> {
  await client.settings.modelProviders.createOrUpdate({
    manifest: {
      auth: { apiKey: config.geminiApiKey },
      models: [
        {
          modelId: "gemini-3.5-flash-lite",
          name: "gemini-3-5-flash-lite",
          properties: {
            contextLength: 1_048_576,
            maxOutputTokens: 65_536,
            reasoningEfforts: ["minimal", "low", "medium", "high"],
          },
        },
      ],
      type: "google-gemini",
    },
  });
  await client.settings.mcpServers.createOrUpdate({
    manifest: {
      description: "Airstrong authoritative synthetic airline operations",
      name: MCP_NAME,
      type: "remote",
      url: config.airlineMcpUrl,
    },
  });
  await client.settings.sandboxProviders.createOrUpdate({
    manifest: {
      auth: { apiKey: config.daytonaApiKey },
      autoArchiveIntervalInMinutes: 30,
      autoDeleteIntervalInMinutes: 120,
      autoStopIntervalInMinutes: 5,
      execTimeoutMs: 120_000,
      type: "daytona",
    },
  });

  const manifest: TrueForgeApi.AgentSpec = {
    config: {
      askUserQuestions: { enabled: false },
      contextManagement: {
        compaction: { enabled: true },
        largeToolResponse: { enabled: true },
      },
      dynamicSubAgents: { enabled: true },
      generativeUi: { enabled: false },
      iterationLimit: 48,
      sandbox: { enabled: true, fileDownloads: false },
    },
    instructions: [
      "You coordinate factual airline recovery computation for Airstrong.",
      "Never invent operational facts, tools, candidate actions, metrics, violations, or outcomes.",
      "Use exactly three dynamic subagents for the initial investigation: Aircraft, Crew, and Passenger.",
      "The model must never select or label a winning plan. The authoritative digital twin and deterministic ranker decide.",
      "Generated code may read the immutable snapshot and use the trusted solver bundle, but it must never mutate live airline state.",
      "Do not predict that any candidate will pass, fail, or win.",
      "Do not use exec for exploration. One exec call must write and run the complete generated artifact; only one repair exec is allowed after a failure.",
      "Only the backend deterministic ranker may select the recommended candidate.",
      "When explicitly given the backend-selected candidate and approval identifiers, call airline_apply_recovery exactly once with those exact values. After its real response, call airline_verify_recovery exactly once using the returned executionId.",
    ].join(" "),
    mcpServers: [
      {
        name: MCP_NAME,
        preload: true,
        requireApprovalForTools: ["airline_apply_recovery"],
      },
    ],
    model: {
      name: MODEL_NAME,
      params: {
        maxTokens: 18_000,
        reasoningEffort: "low",
        temperature: 0,
      },
    },
  };
  const agents = await client.agents.list();
  const existing = agents.data.find((agent) => agent.name === AGENT_NAME);
  if (existing) {
    await client.agents.update(existing.id, { manifest });
  } else {
    await client.agents.create({ name: AGENT_NAME, manifest });
  }
}

function initialPrompt(worldId: string): string {
  return `Recover authoritative Airstrong world ${worldId} from its current incident.

Follow this exact workflow:
1. Call airline_world_snapshot with world_id ${worldId}. Treat the returned revision and facts as immutable for this computation.
2. Create exactly three dynamic subagents and no others:
   - Aircraft must call airline_aircraft_investigation for ${worldId} and report factual aircraft and rotation constraints.
   - Crew must call airline_crew_investigation for ${worldId} and report factual qualification and duty constraints.
   - Passenger must call airline_passenger_investigation for ${worldId} and report factual itinerary dependencies.
   Wait for all three reports.
3. Formulate this incident's recovery problem from those facts. Derive six meaningfully different strategy parameter proposals. The trusted solver will use those proposals as the starting points for bounded incident-specific parameter exploration and retain the first three distinct action sets. Strategy IDs are opaque identifiers with no A/B/C meaning. Do not predict any result.
   Each dictionary must contain exactly: strategy_id, max_cancellations, max_delay_minutes, allow_aircraft_substitution, cancellation_weight, passenger_preservation_weight, delay_weight, aircraft_reassignment_weight, stabilization_weight. All counts, limits, and weights must use integer literals. Delay limits are non-negative multiples of 15. Weights are non-negative and not all zero.
4. Enter Code Mode. Do not inspect tools or data with exploratory exec calls. Your first and only normal exec call must use a quoted heredoc to create the complete new recovery_problem.py and then run python3 recovery_problem.py. The Python must:
   - import asyncio, base64, hashlib, json, pathlib, subprocess, sys, and call_tool from mcp_client;
   - call airline_solver_bundle from ${MCP_NAME}; its files field is a mapping of relative path to source text and requirements is a list of pinned packages; recompute SHA-256 over the sorted mapping using the exact canonical sequence name + "\\0" + source + "\\0" and stop unless it equals bundleHash; then write every mapping entry under generated_lib and install only those exact requirements with subprocess.check_call;
   - call airline_world_snapshot for ${worldId};
   - derive non-empty scope_flight_ids from operationalImpacts entries whose entityType equals flight, using entityId, then sort and deduplicate them;
   - define the six incident-specific strategy dictionaries in the generated source using the trusted StrategyParameters field names;
   - hash its own exact source bytes with SHA-256;
   - import solve_recovery_problem from airstrong_airline.sandbox_runtime and execute the real OR-Tools-backed trusted primitives;
   - set solve_result = solve_recovery_problem(snapshot, scope_flight_ids, strategies, artifact_hash), then print exactly one final line beginning AIRSTRONG_RESULT= followed by compact JSON with artifactHash, artifactSourceBase64, bundleHash set to the verified computed bundle digest, snapshotHash set to every candidate's identical snapshotHash, worldRevision set to snapshot["worldRevision"], and candidates set to solve_result["candidates"] (the candidates field must be an array, not the solve_result object).
   call_tool is async and must be awaited with body={}. Add generated_lib to sys.path before importing the trusted runtime. Use this exact positional call: solve_recovery_problem(snapshot, scope_flight_ids, strategies, artifact_hash). Use asyncio.run(main()).
5. A single repair exec of recovery_problem.py is allowed only if that complete execution fails. After success, stop. Do not call airline_recovery_candidates, rank candidates, call recovery writes, request approval, or claim a winner.`;
}

async function airlineRequest<T>(
  config: RecoveryRuntimeConfig,
  path: string,
  init: RequestInit = {},
): Promise<T> {
  const response = await fetch(`${config.airlineBaseUrl}${path}`, {
    ...init,
    headers: {
      Authorization: `Bearer ${config.airlineRuntimeToken}`,
      "Content-Type": "application/json",
      ...init.headers,
    },
  });
  if (!response.ok) {
    throw new Error(
      `Airline runtime request ${path} failed (${response.status}): ${await response.text()}`,
    );
  }
  return (await response.json()) as T;
}

async function createDurableRun(
  config: RecoveryRuntimeConfig,
  worldId: string,
  idempotencyKey: string,
): Promise<DurableRecoveryRun> {
  const response = await airlineRequest<RunResponse>(
    config,
    `/api/worlds/${worldId}/recovery/runs`,
    {
      headers: { "Idempotency-Key": idempotencyKey },
      method: "POST",
    },
  );
  return response.run;
}

export async function getDurableRun(
  config: RecoveryRuntimeConfig,
  runId: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(config, `/api/recovery/runs/${runId}`)
  ).run;
}

async function linkInvestigationTurn(
  config: RecoveryRuntimeConfig,
  runId: string,
  sessionId: string,
  turnId: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(
      config,
      `/api/recovery/runs/${runId}/trueforge/investigation`,
      {
        body: JSON.stringify({
          investigationTurnId: turnId,
          trueforgeSessionId: sessionId,
        }),
        method: "POST",
      },
    )
  ).run;
}

async function linkExecutionTurn(
  config: RecoveryRuntimeConfig,
  runId: string,
  turnId: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(
      config,
      `/api/recovery/runs/${runId}/trueforge/execution`,
      {
        body: JSON.stringify({ executionTurnId: turnId }),
        method: "POST",
      },
    )
  ).run;
}

async function linkApprovalEvent(
  config: RecoveryRuntimeConfig,
  runId: string,
  turnId: string,
  approval: TrueForgeApi.ToolApprovalRequiredEvent,
  toolCallId: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(
      config,
      `/api/recovery/runs/${runId}/approval/trueforge`,
      {
        body: JSON.stringify({
          approvalEventId: approval.id,
          executionTurnId: turnId,
          threadId: approval.threadId,
          toolCallId,
        }),
        method: "POST",
      },
    )
  ).run;
}

async function linkContinuationTurn(
  config: RecoveryRuntimeConfig,
  runId: string,
  turnId: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(
      config,
      `/api/recovery/runs/${runId}/trueforge/continuation`,
      {
        body: JSON.stringify({ continuationTurnId: turnId }),
        method: "POST",
      },
    )
  ).run;
}

async function requestApproval(
  config: RecoveryRuntimeConfig,
  runId: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(
      config,
      `/api/recovery/runs/${runId}/approval`,
      { method: "POST" },
    )
  ).run;
}

async function decideApproval(
  config: RecoveryRuntimeConfig,
  runId: string,
  decision: "approved" | "denied",
  idempotencyKey: string,
): Promise<DurableRecoveryRun> {
  return (
    await airlineRequest<RunResponse>(
      config,
      `/api/recovery/runs/${runId}/approval/decision`,
      {
        body: JSON.stringify({ decision }),
        headers: { "Idempotency-Key": idempotencyKey },
        method: "POST",
      },
    )
  ).run;
}

async function collectTurn(
  client: TrueForge,
  sessionId: string,
  turnId: string,
): Promise<TrueForgeApi.TurnStreamingEvent[]> {
  const persisted = await client.sessions.listTurnEvents(sessionId, turnId, {
    limit: 100,
  });
  const events: TrueForgeApi.TurnStreamingEvent[] = [...persisted.data];
  const persistedDone = events.find(
    (event): event is TrueForgeApi.TurnDoneEvent => event.type === "turn.done",
  );
  if (persistedDone) {
    if (persistedDone.state.status === "error") {
      throw new Error(
        `TrueForge recovery turn failed: ${JSON.stringify(persistedDone.state)}`,
      );
    }
    return events;
  }
  const known = new Set(events.map((event) => event.id));
  const stream = await client.sessions.subscribeToTurn(sessionId, turnId);
  for await (const event of stream) {
    if (!known.has(event.id)) {
      events.push(event);
      known.add(event.id);
    }
    if (event.type === "turn.done") {
      if (event.state.status === "error") {
        throw new Error(
          `TrueForge recovery turn failed: ${JSON.stringify(event.state)}`,
        );
      }
      break;
    }
  }
  return events;
}

function executionPrompt(run: DurableRecoveryRun): string {
  if (
    !run.approvalId ||
    !run.recommendedCandidateId ||
    run.expectedWorldRevision === null ||
    !run.planHash
  ) {
    throw new Error("Durable recovery run is missing approval lineage");
  }
  const idempotencyKey = `apply-${run.runId}-${run.planHash.slice(0, 16)}`;
  return `The Airstrong backend has completed authoritative twin validation and deterministic ranking for run ${run.runId}. The backend-selected recommendation is ${run.recommendedCandidateId}. You did not select it and must not compare or relabel candidates.

Call airline_apply_recovery exactly once with these exact arguments:
- world_id: ${run.worldId}
- run_id: ${run.runId}
- approval_id: ${run.approvalId}
- candidate_id: ${run.recommendedCandidateId}
- expected_world_revision: ${run.expectedWorldRevision}
- idempotency_key: ${idempotencyKey}

This consequential call must pause for TrueForge human approval. Do not claim it ran while approval is pending. After approval and the real tool response, read executionId from that response and call airline_verify_recovery exactly once with world_id ${run.worldId}, run_id ${run.runId}, and that execution_id. Report only the factual verification response.`;
}

function parsedToolArguments(
  call: TrueForgeApi.ToolCall,
): Record<string, unknown> {
  const value = JSON.parse(call.function.arguments) as unknown;
  if (typeof value !== "object" || value === null) {
    throw new Error("Consequential tool arguments were not an object");
  }
  return value as Record<string, unknown>;
}

function analyzeExecutionApproval(
  events: TrueForgeApi.TurnStreamingEvent[],
  run: DurableRecoveryRun,
): {
  approval: TrueForgeApi.ToolApprovalRequiredEvent;
  toolCallId: string;
} {
  const approval = events.find(
    (event): event is TrueForgeApi.ToolApprovalRequiredEvent =>
      event.type === "tool.approval_required",
  );
  if (!approval) {
    throw new Error("TrueForge did not pause the recovery write for approval");
  }
  const calls = events
    .filter(
      (event): event is TrueForgeApi.ModelMessageEvent =>
        event.type === "model.message",
    )
    .flatMap((event) => event.toolCalls ?? [])
    .filter((call) => call.toolInfo.name === "airline_apply_recovery");
  if (calls.length !== 1) {
    throw new Error(
      `Expected exactly one airline_apply_recovery call; saw ${calls.length}`,
    );
  }
  const call = calls[0]!;
  const args = parsedToolArguments(call);
  const expected = {
    approval_id: run.approvalId,
    candidate_id: run.recommendedCandidateId,
    expected_world_revision: run.expectedWorldRevision,
    run_id: run.runId,
    world_id: run.worldId,
  };
  for (const [key, value] of Object.entries(expected)) {
    if (args[key] !== value) {
      throw new Error(`TrueForge recovery write changed authoritative ${key}`);
    }
  }
  if (
    typeof args.idempotency_key !== "string" ||
    !args.idempotency_key.startsWith(`apply-${run.runId}-`)
  ) {
    throw new Error(
      "TrueForge recovery write used an unsupported idempotency key",
    );
  }
  if (!approval.toolCalls.some((item) => item.id === call.id)) {
    throw new Error(
      "The recovery write did not enter the TrueForge approval gate",
    );
  }
  return { approval, toolCallId: call.id };
}

async function collectUntilApproval(
  client: TrueForge,
  sessionId: string,
  turnId: string,
): Promise<TrueForgeApi.TurnStreamingEvent[]> {
  const persisted = await client.sessions.listTurnEvents(sessionId, turnId, {
    limit: 100,
  });
  if (persisted.data.some((event) => event.type === "tool.approval_required")) {
    return persisted.data;
  }
  const events: TrueForgeApi.TurnStreamingEvent[] = [...persisted.data];
  const known = new Set(events.map((event) => event.id));
  const stream = await client.sessions.subscribeToTurn(sessionId, turnId);
  for await (const event of stream) {
    if (!known.has(event.id)) {
      events.push(event);
      known.add(event.id);
    }
    if (event.type === "tool.approval_required") {
      return events;
    }
    if (event.type === "turn.done") {
      throw new Error(
        `TrueForge execution request ended before approval: ${JSON.stringify(event.state)}`,
      );
    }
  }
  throw new Error("TrueForge execution stream ended before approval");
}

async function submitEvidence(
  config: RecoveryRuntimeConfig,
  worldId: string,
  runId: string,
  sessionId: string,
  turnId: string,
  evidence: RecoveryEvidence,
): Promise<EvaluationResponse> {
  const response = await fetch(
    `${config.airlineBaseUrl}/api/worlds/${worldId}/recovery/evaluate`,
    {
      body: JSON.stringify({
        sandboxId: evidence.sandboxId,
        sandboxResult: evidence.sandboxResult,
        runId,
        source: evidence.artifactSource,
        expectedSnapshotHash: evidence.sandboxResult.snapshotHash,
        expectedWorldRevision: evidence.sandboxResult.worldRevision,
        trueforgeSessionId: sessionId,
        trueforgeTurnId: turnId,
      }),
      headers: {
        Authorization: `Bearer ${config.airlineRuntimeToken}`,
        "Content-Type": "application/json",
      },
      method: "POST",
    },
  );
  if (!response.ok) {
    throw new Error(
      `Authoritative twin rejected generated artifact (${response.status}): ${await response.text()}`,
    );
  }
  return (await response.json()) as EvaluationResponse;
}

async function requireRecoveryTools(client: TrueForge): Promise<void> {
  const tools = await client.mcpServers.listTools(MCP_NAME);
  const names = new Set(tools.data.map((tool) => tool.name));
  for (const required of [
    "airline_world_snapshot",
    "airline_aircraft_investigation",
    "airline_crew_investigation",
    "airline_passenger_investigation",
    "airline_solver_bundle",
    "airline_apply_recovery",
    "airline_verify_recovery",
  ]) {
    if (!names.has(required)) {
      throw new Error(`Airline MCP did not expose required tool ${required}`);
    }
  }
}

export async function prepareRecovery(
  config: RecoveryRuntimeConfig,
  worldId: string,
  idempotencyKey: string,
): Promise<DurableRecoveryRun> {
  let run = await createDurableRun(config, worldId, idempotencyKey);
  if (
    [
      "approved",
      "awaiting_approval",
      "denied",
      "failed",
      "no_valid_candidate",
      "stale",
      "verified",
      "verifying",
    ].includes(run.status) &&
    (run.status !== "awaiting_approval" || run.trueforgeToolCallId !== null)
  ) {
    return run;
  }

  const client = new TrueForge({ baseUrl: config.trueforgeBaseUrl });
  await configureRecoveryAgent(client, config);
  await requireRecoveryTools(client);

  if (run.batchId === null) {
    let sessionId = run.trueforgeSessionId;
    let turnId = run.investigationTurnId;
    if (sessionId === null || turnId === null) {
      const session = await client.sessions.create({
        agent: { name: AGENT_NAME },
      });
      const turn = await client.sessions.createTurn(session.data.id, {
        input: [{ type: "user.message", content: initialPrompt(worldId) }],
      });
      sessionId = session.data.id;
      turnId = turn.data.id;
      run = await linkInvestigationTurn(config, run.runId, sessionId, turnId);
    }
    await collectTurn(client, sessionId, turnId);
    const persistedEvents = await client.sessions.listTurnEvents(
      sessionId,
      turnId,
      { limit: 100 },
    );
    const evidence = analyzeRecoveryEvidence(persistedEvents.data, {
      requireSubagents: true,
    });
    await submitEvidence(
      config,
      worldId,
      run.runId,
      sessionId,
      turnId,
      evidence,
    );
    run = await getDurableRun(config, run.runId);
  }

  if (run.status === "no_valid_candidate") {
    return run;
  }
  if (run.approvalId === null) {
    run = await requestApproval(config, run.runId);
  }
  const sessionId = run.trueforgeSessionId;
  if (sessionId === null) {
    throw new Error("Recovery run lost its persisted TrueForge session");
  }
  let executionTurnId = run.executionTurnId;
  if (executionTurnId === null) {
    const turn = await client.sessions.createTurn(sessionId, {
      input: [{ type: "user.message", content: executionPrompt(run) }],
    });
    executionTurnId = turn.data.id;
    run = await linkExecutionTurn(config, run.runId, executionTurnId);
  }
  await collectUntilApproval(client, sessionId, executionTurnId);
  const persistedApprovalEvents = await client.sessions.listTurnEvents(
    sessionId,
    executionTurnId,
    { limit: 100 },
  );
  const completeEvents: TrueForgeApi.TurnStreamingEvent[] = [
    ...persistedApprovalEvents.data,
  ];
  while (persistedApprovalEvents.hasNextPage()) {
    await persistedApprovalEvents.getNextPage();
    completeEvents.push(...persistedApprovalEvents.data);
  }
  const approvalEvidence = analyzeExecutionApproval(
    completeEvents,
    run,
  );
  if (run.trueforgeToolCallId === null) {
    run = await linkApprovalEvent(
      config,
      run.runId,
      executionTurnId,
      approvalEvidence.approval,
      approvalEvidence.toolCallId,
    );
  }
  return run;
}

export async function decideRecovery(
  config: RecoveryRuntimeConfig,
  runId: string,
  decision: "approved" | "denied",
  idempotencyKey: string,
): Promise<DurableRecoveryRun> {
  let run = await getDurableRun(config, runId);
  if (run.status === "verified" || run.status === "denied") {
    return run;
  }
  if (
    !run.trueforgeSessionId ||
    !run.trueforgeThreadId ||
    !run.trueforgeToolCallId
  ) {
    throw new Error("Recovery run has no durable TrueForge approval request");
  }
  const sessionId = run.trueforgeSessionId;
  const threadId = run.trueforgeThreadId;
  const toolCallId = run.trueforgeToolCallId;
  if (run.approvalStatus === "pending") {
    run = await decideApproval(config, runId, decision, idempotencyKey);
  } else if (decision === "denied" ? run.approvalStatus !== "denied" : false) {
    throw new Error("Recovery approval was already decided differently");
  }

  const client = new TrueForge({ baseUrl: config.trueforgeBaseUrl });
  await configureRecoveryAgent(client, config);
  let continuationTurnId = run.approvalContinuationTurnId;
  if (continuationTurnId === null) {
    const continuation = await client.sessions.createTurn(sessionId, {
      input: [
        {
          type: "user.tool_approval",
          approval: { status: decision === "approved" ? "allow" : "deny" },
          threadId,
          toolCallId,
        },
      ],
    });
    continuationTurnId = continuation.data.id;
    run = await linkContinuationTurn(config, runId, continuationTurnId);
  }
  await collectTurn(client, sessionId, continuationTurnId);
  run = await getDurableRun(config, runId);
  if (decision === "approved" && run.status !== "verified") {
    throw new Error(
      `Approved recovery did not complete authoritative verification; status is ${run.status}`,
    );
  }
  if (decision === "denied" && run.executionId !== null) {
    throw new Error("Denied recovery produced an operational execution");
  }
  return run;
}

export async function runRecovery(
  config: RecoveryRuntimeConfig,
  worldId: string,
): Promise<DurableRecoveryRun> {
  return prepareRecovery(config, worldId, `recovery-${worldId}`);
}
