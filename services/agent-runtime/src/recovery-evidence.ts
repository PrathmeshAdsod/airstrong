import { createHash } from "node:crypto";

import type { TrueForgeApi } from "@truefoundry/trueforge-sdk";

export interface SandboxRecoveryResult {
  artifactHash: string;
  artifactSourceBase64: string;
  candidates: unknown[];
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
    !Array.isArray(value.candidates)
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
    const names = new Set(
      subagentCalls
        .map(({ call }) => parsedArguments(call)?.name)
        .filter((name): name is string => typeof name === "string"),
    );
    if (
      subagentCalls.length !== 3 ||
      childThreads.length !== 3 ||
      !["Aircraft", "Crew", "Passenger"].every((name) => names.has(name))
    ) {
      throw new Error(
        "Recovery investigation did not execute exactly the Aircraft, Crew, and Passenger subagents",
      );
    }
    const childThreadIds = new Set(childThreads.map((event) => event.threadId));
    const requiredTools = new Set([
      "airline_aircraft_investigation",
      "airline_crew_investigation",
      "airline_passenger_investigation",
    ]);
    const childReadTools = new Set<string>();
    for (const { call, threadId } of calls) {
      if (!childThreadIds.has(threadId)) continue;
      if (requiredTools.has(call.toolInfo.name)) {
        childReadTools.add(call.toolInfo.name);
      }
      if (call.toolInfo.name === "exec") {
        const command = parsedArguments(call)?.command;
        if (typeof command === "string") {
          for (const toolName of requiredTools) {
            if (command.includes(toolName)) childReadTools.add(toolName);
          }
        }
      }
      const serializedArguments = JSON.stringify(parsedArguments(call) ?? {});
      for (const toolName of requiredTools) {
        if (serializedArguments.includes(toolName))
          childReadTools.add(toolName);
      }
    }
    if (childReadTools.size !== requiredTools.size) {
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
