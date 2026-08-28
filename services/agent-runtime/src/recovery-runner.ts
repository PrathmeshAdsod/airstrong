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

export interface RecoveryRunResult {
  batchId: string;
  recommendedCandidateId: string | null;
  sessionId: string;
  status: "candidates_ranked" | "no_valid_candidate";
  turnId: string;
  validCandidateCount: number;
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
    ].join(" "),
    mcpServers: [{ name: MCP_NAME, preload: true }],
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
   - call airline_solver_bundle from ${MCP_NAME}; its files field is a mapping of relative path to source text and requirements is a list of pinned packages; write every mapping entry under generated_lib and install only those exact requirements with subprocess.check_call;
   - call airline_world_snapshot for ${worldId};
   - derive non-empty scope_flight_ids from operationalImpacts entries whose entityType equals flight, using entityId, then sort and deduplicate them;
   - define the six incident-specific strategy dictionaries in the generated source using the trusted StrategyParameters field names;
   - hash its own exact source bytes with SHA-256;
   - import solve_recovery_problem from airstrong_airline.sandbox_runtime and execute the real OR-Tools-backed trusted primitives;
   - set solve_result = solve_recovery_problem(snapshot, scope_flight_ids, strategies, artifact_hash), then print exactly one final line beginning AIRSTRONG_RESULT= followed by compact JSON with artifactHash, artifactSourceBase64, snapshotHash set to every candidate's identical snapshotHash, worldRevision set to snapshot["worldRevision"], and candidates set to solve_result["candidates"] (the candidates field must be an array, not the solve_result object).
   call_tool is async and must be awaited with body={}. Add generated_lib to sys.path before importing the trusted runtime. Use this exact positional call: solve_recovery_problem(snapshot, scope_flight_ids, strategies, artifact_hash). Use asyncio.run(main()).
5. A single repair exec of recovery_problem.py is allowed only if that complete execution fails. After success, stop. Do not call airline_recovery_candidates, rank candidates, call recovery writes, request approval, or claim a winner.`;
}

async function collectTurn(
  client: TrueForge,
  sessionId: string,
  turnId: string,
): Promise<TrueForgeApi.TurnStreamingEvent[]> {
  const events: TrueForgeApi.TurnStreamingEvent[] = [];
  const stream = await client.sessions.subscribeToTurn(sessionId, turnId);
  for await (const event of stream) {
    events.push(event);
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

async function submitEvidence(
  config: RecoveryRuntimeConfig,
  worldId: string,
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

function resultFromEvaluation(
  sessionId: string,
  turnId: string,
  evaluation: EvaluationResponse,
): RecoveryRunResult {
  const valid = evaluation.batch.candidates.filter(
    (candidate) => candidate.valid,
  );
  const recommended = evaluation.batch.candidates.find(
    (candidate) => candidate.recommended,
  );
  return {
    batchId: evaluation.batchId,
    recommendedCandidateId: recommended?.candidateId ?? null,
    sessionId,
    status: valid.length ? "candidates_ranked" : "no_valid_candidate",
    turnId,
    validCandidateCount: valid.length,
  };
}

export async function runRecovery(
  config: RecoveryRuntimeConfig,
  worldId: string,
): Promise<RecoveryRunResult> {
  const client = new TrueForge({ baseUrl: config.trueforgeBaseUrl });
  await configureRecoveryAgent(client, config);
  const tools = await client.mcpServers.listTools(MCP_NAME);
  const names = new Set(tools.data.map((tool) => tool.name));
  for (const required of [
    "airline_world_snapshot",
    "airline_aircraft_investigation",
    "airline_crew_investigation",
    "airline_passenger_investigation",
    "airline_solver_bundle",
  ]) {
    if (!names.has(required)) {
      throw new Error(`Airline MCP did not expose required tool ${required}`);
    }
  }
  const session = await client.sessions.create({ agent: { name: AGENT_NAME } });
  const turn = await client.sessions.createTurn(session.data.id, {
    input: [{ type: "user.message", content: initialPrompt(worldId) }],
  });
  await collectTurn(client, session.data.id, turn.data.id);
  const persistedEvents = await client.sessions.listTurnEvents(
    session.data.id,
    turn.data.id,
    { limit: 100 },
  );
  const completeEvents: TrueForgeApi.TurnStreamingEvent[] = [];
  for await (const event of persistedEvents) completeEvents.push(event);
  const evidence = analyzeRecoveryEvidence(completeEvents, {
    requireSubagents: true,
  });
  const evaluation = await submitEvidence(
    config,
    worldId,
    session.data.id,
    turn.data.id,
    evidence,
  );
  return resultFromEvaluation(session.data.id, turn.data.id, evaluation);
}
