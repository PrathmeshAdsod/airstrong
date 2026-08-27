import { mkdir, writeFile } from "node:fs/promises";
import { dirname } from "node:path";
import { randomUUID } from "node:crypto";

import { TrueForge, type TrueForgeApi } from "@truefoundry/trueforge-sdk";

import { readCompatibilityConfig } from "./config.js";
import { readAuditState } from "./database.js";
import {
  analyzeEvidence,
  assertReconnectHasNoOverlap,
} from "./event-evidence.js";

interface PersistedCompatibilityState {
  approvalTurnId: string;
  idempotencyKey: string;
  sessionId: string;
}

const AGENT_NAME = "airstrong-sponsor-compatibility";
const MCP_NAME = "airstrong-compatibility";
const MODEL_NAME = "google-gemini/gemini-3-5-flash-lite";

async function configureTrueForge(
  client: TrueForge,
  geminiApiKey: string,
  daytonaApiKey: string,
): Promise<void> {
  await client.settings.modelProviders.createOrUpdate({
    manifest: {
      auth: { apiKey: geminiApiKey },
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
      description: "Airstrong real PostgreSQL compatibility tools",
      name: MCP_NAME,
      type: "remote",
      url: "http://compatibility-mcp:4100/mcp",
    },
  });
  await client.settings.sandboxProviders.createOrUpdate({
    manifest: {
      auth: { apiKey: daytonaApiKey },
      autoArchiveIntervalInMinutes: 30,
      autoDeleteIntervalInMinutes: 120,
      autoStopIntervalInMinutes: 5,
      execTimeoutMs: 60_000,
      type: "daytona",
    },
  });
}

function agentManifest(): TrueForgeApi.AgentSpec {
  return {
    config: {
      askUserQuestions: { enabled: false },
      contextManagement: {
        compaction: { enabled: true },
        largeToolResponse: { enabled: true },
      },
      dynamicSubAgents: { enabled: true },
      generativeUi: { enabled: false },
      iterationLimit: 45,
      sandbox: { enabled: true, fileDownloads: false },
    },
    instructions: [
      "You are running a strict Airstrong sponsor-stack compatibility check.",
      "Never invent tool results. Never skip a required operation.",
      "Use exactly three dynamic subagents, and do not create any other subagent.",
      "Only the root thread may call the consequential compatibility_commit tool.",
      "Do not retry compatibility_commit while it is awaiting approval.",
    ].join(" "),
    mcpServers: [
      {
        name: MCP_NAME,
        preload: true,
        requireApprovalForTools: ["compatibility_commit"],
      },
    ],
    model: {
      name: MODEL_NAME,
      params: {
        maxTokens: 12_000,
        reasoningEffort: "low",
        temperature: 0,
      },
    },
  };
}

async function upsertAgent(client: TrueForge): Promise<void> {
  const agents = await client.agents.list();
  const existing = agents.data.find((agent) => agent.name === AGENT_NAME);
  if (existing) {
    await client.agents.update(existing.id, { manifest: agentManifest() });
    return;
  }
  await client.agents.create({ name: AGENT_NAME, manifest: agentManifest() });
}

function prompt(idempotencyKey: string): string {
  return `Run this compatibility check exactly:
1. Call compatibility_snapshot from the configured MCP server and retain its factual fields.
2. Create exactly three dynamic subagents named Aircraft, Crew, and Passenger. Each subagent must independently call compatibility_snapshot, then return only one factual check of the service name, probe values, or write count. Wait for all three real subagents.
3. After receiving all three reports, enter TrueForge Code Mode. Use the exec tool to generate a new Python file at runtime. The file must import call_tool from mcp_client, call compatibility_snapshot, compute the sum and count of probe_values, and print only a compact JSON object with those computed values. Write the file before executing it. This code must be generated during this run, not copied from a repository artifact.
4. After the generated Python has executed successfully, call compatibility_commit exactly once with idempotency_key ${idempotencyKey} and payload sponsor-stack-proof. This consequential call must pause for approval.
5. After approval and the real tool response, state only the factual result. Do not create or call unsupported tools.`;
}

function parseSequenceNumber(id: string | undefined): number {
  if (id === undefined) {
    throw new Error(
      "TrueForge resumable SSE event did not include a sequence cursor",
    );
  }
  const sequenceNumber = Number(id);
  if (!Number.isSafeInteger(sequenceNumber) || sequenceNumber < 1) {
    throw new Error(`TrueForge returned an invalid SSE sequence cursor: ${id}`);
  }
  return sequenceNumber;
}

async function collectUntilApprovalWithReconnect(
  baseUrl: string,
  client: TrueForge,
  sessionId: string,
  turnId: string,
): Promise<TrueForgeApi.TurnStreamingEvent[]> {
  const beforeDisconnect: TrueForgeApi.TurnStreamingEvent[] = [];
  const beforeSequenceNumbers: number[] = [];
  const initialStream = await client.sessions.subscribeToTurn(
    sessionId,
    turnId,
  );
  for await (const item of initialStream.withMetadata()) {
    beforeDisconnect.push(item.data);
    beforeSequenceNumbers.push(parseSequenceNumber(item.id));
    if (beforeDisconnect.length >= 4) {
      break;
    }
  }

  const resumeCursor = beforeSequenceNumbers.at(-1);
  if (resumeCursor === undefined) {
    throw new Error(
      "TrueForge emitted no events before the deliberate disconnect",
    );
  }

  const reconnectedClient = new TrueForge({ baseUrl });
  const afterReconnect: TrueForgeApi.TurnStreamingEvent[] = [];
  const afterSequenceNumbers: number[] = [];
  const resumedStream = await reconnectedClient.sessions.subscribeToTurn(
    sessionId,
    turnId,
    {
      afterSequenceNumber: resumeCursor,
    },
  );
  for await (const item of resumedStream.withMetadata()) {
    const event = item.data;
    afterReconnect.push(event);
    afterSequenceNumbers.push(parseSequenceNumber(item.id));
    if (event.type === "tool.approval_required") {
      break;
    }
    if (event.type === "turn.done" && event.state.status === "error") {
      throw new Error(
        `TrueForge turn failed before approval: ${JSON.stringify(event.state)}`,
      );
    }
  }
  assertReconnectHasNoOverlap(beforeSequenceNumbers, afterSequenceNumbers);
  return [...beforeDisconnect, ...afterReconnect];
}

async function main(): Promise<void> {
  const config = readCompatibilityConfig();
  const client = new TrueForge({ baseUrl: config.trueforgeBaseUrl });
  await configureTrueForge(client, config.geminiApiKey, config.daytonaApiKey);

  const tools = await client.mcpServers.listTools(MCP_NAME);
  const toolNames = tools.data
    .map((tool) => tool.name)
    .filter((name): name is string => typeof name === "string");
  for (const required of [
    "compatibility_snapshot",
    "compatibility_audit",
    "compatibility_commit",
  ]) {
    if (!toolNames.includes(required)) {
      throw new Error(`TrueForge MCP discovery did not return ${required}`);
    }
  }

  await upsertAgent(client);
  const session = await client.sessions.create({ agent: { name: AGENT_NAME } });
  const idempotencyKey = `compat-${randomUUID()}`;
  const turn = await client.sessions.createTurn(session.data.id, {
    input: [{ type: "user.message", content: prompt(idempotencyKey) }],
  });
  await collectUntilApprovalWithReconnect(
    config.trueforgeBaseUrl,
    client,
    session.data.id,
    turn.data.id,
  );
  const persistedEvents = await client.sessions.listTurnEvents(
    session.data.id,
    turn.data.id,
    {
      limit: 100,
    },
  );
  const evidence = analyzeEvidence(persistedEvents.data);

  const beforeApproval = await readAuditState(
    config.databaseUrl,
    idempotencyKey,
  );
  if (beforeApproval.exists) {
    throw new Error("Consequential PostgreSQL write happened before approval");
  }

  const approvedCall = evidence.approval.toolCalls.find(
    (call) => call.id === evidence.commitCallId,
  );
  if (!approvedCall) {
    throw new Error("Approval event did not contain the consequential call");
  }
  const approvalStream = await client.sessions.createTurnStream(
    session.data.id,
    {
      input: [
        {
          type: "user.tool_approval",
          approval: { status: "allow" },
          threadId: evidence.approval.threadId,
          toolCallId: approvedCall.id,
        },
      ],
    },
  );
  let approvalTurnId: string | undefined;
  let completed = false;
  for await (const event of approvalStream) {
    if (event.type === "turn.created") {
      approvalTurnId = event.turnId;
    }
    if (event.type === "turn.done") {
      if (event.state.status === "error") {
        throw new Error(
          `TrueForge approval continuation failed: ${JSON.stringify(event.state)}`,
        );
      }
      completed = true;
    }
  }
  if (!completed || !approvalTurnId) {
    throw new Error("Approval continuation did not complete durably");
  }

  const afterApproval = await readAuditState(
    config.databaseUrl,
    idempotencyKey,
  );
  if (!afterApproval.exists) {
    throw new Error("Approved MCP write did not reach PostgreSQL");
  }

  const persisted: PersistedCompatibilityState = {
    approvalTurnId,
    idempotencyKey,
    sessionId: session.data.id,
  };
  await mkdir(dirname(config.statePath), { recursive: true });
  await writeFile(
    config.statePath,
    `${JSON.stringify(persisted, null, 2)}\n`,
    "utf8",
  );

  console.log(
    JSON.stringify({
      approvalPausedBeforeWrite: true,
      approvedWritePersisted: true,
      codeModeExecCalls: evidence.codeModeExecCallIds.length,
      dynamicSubagents: evidence.childThreadCount,
      mcpToolsDiscovered: toolNames.length,
      reconnectResumedWithoutDuplicates: true,
      sandboxCreated: evidence.sandboxCreated,
      sessionId: session.data.id,
      snapshotCalls: evidence.snapshotCallCount,
    }),
  );
}

await main();
