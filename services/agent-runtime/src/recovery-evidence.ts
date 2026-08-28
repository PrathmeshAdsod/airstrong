import { createHash } from "node:crypto";

import type { TrueForgeApi } from "@truefoundry/trueforge-sdk";

export interface SandboxRecoveryResult {
  artifactHash: string;
  artifactSourceBase64: string;
  bundleHash: string;
  candidates: unknown[];
  snapshotHash: string;
  worldRevision: number;
}

export interface RecoveryEvidence {
  artifactSource: string;
  codeModeExecCallIds: string[];
  sandboxId: string;
  sandboxResult: SandboxRecoveryResult;
  subagentThreadIds: string[];
}

function parsedArguments(
  call: TrueForgeApi.ToolCall,
): Record<string, unknown> | undefined {
  try {
    const value = JSON.parse(call.function.arguments) as unknown;
    return typeof value === "object" && value !== null
      ? (value as Record<string, unknown>)
      : undefined;
  } catch {
    return undefined;
  }
}

function successfulResult(
  event: TrueForgeApi.ToolResponseEvent,
): string | undefined {
  try {
    const body = JSON.parse(event.content) as {
      response?: { exitCode?: unknown; result?: unknown };
      success?: unknown;
    };
    return body.success === true &&
      body.response?.exitCode === 0 &&
      typeof body.response.result === "string"
      ? body.response.result
      : undefined;
  } catch {
    return undefined;
  }
}

function parseSandboxResult(result: string): SandboxRecoveryResult | undefined {
  const marker = "AIRSTRONG_RESULT=";
  const line = result
    .split(/\r?\n/)
    .find((candidate) => candidate.startsWith(marker));
  if (!line) return undefined;
  const value = JSON.parse(line.slice(marker.length)) as SandboxRecoveryResult;
  if (
    typeof value.artifactHash !== "string" ||
    typeof value.artifactSourceBase64 !== "string" ||
    typeof value.bundleHash !== "string" ||
    !Array.isArray(value.candidates) ||
    typeof value.snapshotHash !== "string" ||
    !Number.isInteger(value.worldRevision)
  ) {
    throw new Error("Daytona returned an invalid Airstrong result envelope");
  }
  return value;
}

export function analyzeRecoveryEvidence(
  events: TrueForgeApi.TurnStreamingEvent[],
  options: { requireSubagents: boolean },
): RecoveryEvidence {
  const modelMessages = events.filter(
    (event): event is TrueForgeApi.ModelMessageEvent =>
      event.type === "model.message",
  );
  const calls = modelMessages.flatMap((event) =>
    (event.toolCalls ?? []).map((call) => ({ call, threadId: event.threadId })),
  );
  const subagentCalls = calls.filter(
    ({ call }) => call.toolInfo.name === "create_sub_agent",
  );
  const childThreads = events.filter(
    (event): event is TrueForgeApi.ThreadCreatedEvent =>
      event.type === "thread.created",
  );
  if (options.requireSubagents) {
    const requiredByName = new Map([
      ["Aircraft", "airline_aircraft_investigation"],
      ["Crew", "airline_crew_investigation"],
      ["Passenger", "airline_passenger_investigation"],
    ]);
    const callById = new Map(subagentCalls.map(({ call }) => [call.id, call]));
    const childByName = new Map(
      childThreads.map((event) => [event.agentInfo.name, event]),
    );
    const childThreadIds = new Set(childThreads.map((event) => event.threadId));
    if (
      subagentCalls.length !== 3 ||
      childThreads.length !== 3 ||
      childByName.size !== 3 ||
      childThreadIds.size !== 3 ||
      subagentCalls.some(({ threadId }) => threadId !== "main") ||
      childThreads.some(
        (event) =>
          event.agentInfo.type !== "dynamic" ||
          event.parent.threadId !== "main",
      ) ||
      [...requiredByName].some(([name]) => {
        const child = childByName.get(name);
        if (!child) return true;
        const parentCall = callById.get(child.parent.toolCallId);
        return !parentCall || parsedArguments(parentCall)?.name !== name;
      })
    ) {
      throw new Error(
        "Recovery investigation did not execute exactly the Aircraft, Crew, and Passenger subagents",
      );
    }
    const callsByThread = new Map<string, TrueForgeApi.ToolCall[]>();
    for (const { call, threadId } of calls) {
      callsByThread.set(threadId, [
        ...(callsByThread.get(threadId) ?? []),
        call,
      ]);
    }
    const missingGrounding = [...requiredByName].some(
      ([name, requiredTool]) => {
        const child = childByName.get(name)!;
        return !(callsByThread.get(child.threadId) ?? []).some(
          (call) => call.toolInfo.name === requiredTool,
        );
      },
    );
    if (missingGrounding) {
      throw new Error(
        "One or more recovery subagents did not perform its grounded MCP read",
      );
    }
  } else if (subagentCalls.length || childThreads.length) {
    throw new Error("A replanning turn created extra subagents");
  }

  const execCalls = calls.filter(
    ({ call, threadId }) =>
      threadId === "main" && call.toolInfo.name === "exec",
  );
  const responseByCall = new Map(
    events
      .filter(
        (event): event is TrueForgeApi.ToolResponseEvent =>
          event.type === "tool.response",
      )
      .map((event) => [event.toolCallId, event]),
  );
  const completed = execCalls.flatMap(({ call }) => {
    const response = responseByCall.get(call.id);
    if (!response) return [];
    const result = successfulResult(response);
    if (!result) return [];
    const sandboxResult = parseSandboxResult(result);
    return sandboxResult ? [{ call, sandboxResult }] : [];
  });
  if (execCalls.length > 2 || completed.length !== 1) {
    throw new Error(
      "Runtime-generated recovery Python did not complete within the single bounded repair",
    );
  }
  const completedResult = completed[0]!;
  const artifactSource = Buffer.from(
    completedResult.sandboxResult.artifactSourceBase64,
    "base64",
  ).toString("utf8");
  const sourceHash = createHash("sha256").update(artifactSource).digest("hex");
  if (sourceHash !== completedResult.sandboxResult.artifactHash) {
    throw new Error(
      "Runtime-generated artifact source does not match its SHA-256 hash",
    );
  }
  if (completedResult.sandboxResult.candidates.length !== 3) {
    throw new Error(
      "Runtime-generated artifact did not produce three stored candidates",
    );
  }
  const sandboxEvent = events.find(
    (event): event is TrueForgeApi.SandboxCreatedEvent =>
      event.type === "sandbox.created",
  );
  if (!sandboxEvent) {
    throw new Error("TrueForge did not create a Daytona sandbox");
  }
  return {
    artifactSource,
    codeModeExecCallIds: execCalls.map(({ call }) => call.id),
    sandboxId: sandboxEvent.sandboxId,
    sandboxResult: completedResult.sandboxResult,
    subagentThreadIds: childThreads.map((event) => event.threadId),
  };
}
