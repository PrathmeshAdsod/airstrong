import type { TrueForgeApi } from "@truefoundry/trueforge-sdk";

export interface CompatibilityEvidence {
  approval: TrueForgeApi.ToolApprovalRequiredEvent;
  childThreadCount: number;
  codeModeExecCallIds: string[];
  commitCallId: string;
  eventIds: string[];
  sandboxCreated: boolean;
  snapshotCallCount: number;
}

function toolName(call: TrueForgeApi.ToolCall): string {
  return call.toolInfo.name;
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

function isGeneratedPythonExecution(call: TrueForgeApi.ToolCall): boolean {
  const command = parsedArguments(call)?.command;
  return (
    typeof command === "string" &&
    command.includes("mcp_client") &&
    />\s*\S+\.py\b/.test(command) &&
    /\bpython3?\s+\S+\.py\b/.test(command)
  );
}

function successfulToolResponse(
  events: TrueForgeApi.TurnStreamingEvent[],
  toolCallId: string,
): boolean {
  const response = events.find(
    (event): event is TrueForgeApi.ToolResponseEvent =>
      event.type === "tool.response" && event.toolCallId === toolCallId,
  );
  if (!response || typeof response.content !== "string") {
    return false;
  }
  try {
    const value = JSON.parse(response.content) as {
      response?: { exitCode?: unknown };
      success?: unknown;
    };
    return value.success === true && value.response?.exitCode === 0;
  } catch {
    return false;
  }
}

export function analyzeEvidence(
  events: TrueForgeApi.TurnStreamingEvent[],
): CompatibilityEvidence {
  const approval = events.find(
    (event): event is TrueForgeApi.ToolApprovalRequiredEvent =>
      event.type === "tool.approval_required",
  );
  if (!approval) {
    throw new Error("TrueForge never emitted tool.approval_required");
  }

  const modelMessages = events.filter(
    (event): event is TrueForgeApi.ModelMessageEvent =>
      event.type === "model.message",
  );
  const toolCalls = modelMessages.flatMap((event) =>
    (event.toolCalls ?? []).map((call) => ({ call, threadId: event.threadId })),
  );
  const subagentCalls = toolCalls.filter(
    ({ call }) => toolName(call) === "create_sub_agent",
  );
  const execCalls = toolCalls.filter(({ call }) => toolName(call) === "exec");
  const codeModeExecCalls = execCalls.filter(({ call }) =>
    isGeneratedPythonExecution(call),
  );
  const commitCalls = toolCalls.filter(
    ({ call }) => toolName(call) === "compatibility_commit",
  );
  const snapshotCalls = toolCalls.filter(
    ({ call }) => toolName(call) === "compatibility_snapshot",
  );
  const childThreads = events.filter(
    (event) => event.type === "thread.created",
  );

  if (subagentCalls.length !== 3 || childThreads.length !== 3) {
    throw new Error(
      `Expected exactly three real dynamic subagents; saw ${subagentCalls.length} calls and ${childThreads.length} threads`,
    );
  }
  const subagentNames = new Set(
    subagentCalls
      .map(({ call }) => parsedArguments(call)?.name)
      .filter((name) => typeof name === "string"),
  );
  if (
    subagentNames.size !== 3 ||
    !["Aircraft", "Crew", "Passenger"].every((name) => subagentNames.has(name))
  ) {
    throw new Error(
      "The three real subagents were not Aircraft, Crew, and Passenger",
    );
  }
  if (codeModeExecCalls.length === 0) {
    throw new Error(
      "No runtime-generated and executed Python Code Mode call was observed",
    );
  }
  if (codeModeExecCalls.length > 2) {
    throw new Error(
      "Runtime-generated Python exceeded the single bounded repair attempt",
    );
  }
  if (
    !codeModeExecCalls.some(({ call }) =>
      successfulToolResponse(events, call.id),
    )
  ) {
    throw new Error(
      "Runtime-generated Python never completed successfully in the sandbox",
    );
  }
  const childThreadIds = new Set(childThreads.map((event) => event.threadId));
  const rootSnapshots = snapshotCalls.filter(
    ({ threadId }) => threadId === "main",
  );
  const childSnapshots = snapshotCalls.filter(({ threadId }) =>
    childThreadIds.has(threadId),
  );
  if (rootSnapshots.length !== 1 || childSnapshots.length !== 3) {
    throw new Error(
      `Expected one root and three child compatibility_snapshot calls; saw ${rootSnapshots.length} and ${childSnapshots.length}`,
    );
  }
  if (commitCalls.length !== 1) {
    throw new Error(
      `Expected one consequential MCP call; saw ${commitCalls.length}`,
    );
  }
  if (!events.some((event) => event.type === "sandbox.created")) {
    throw new Error("TrueForge did not create a Daytona sandbox");
  }

  const approvedIds = new Set(approval.toolCalls.map((call) => call.id));
  if (!approvedIds.has(commitCalls[0]!.call.id)) {
    throw new Error(
      "The consequential MCP call did not enter the approval gate",
    );
  }

  return {
    approval,
    childThreadCount: childThreads.length,
    codeModeExecCallIds: codeModeExecCalls.map(({ call }) => call.id),
    commitCallId: commitCalls[0]!.call.id,
    eventIds: events.map((event) => event.id),
    sandboxCreated: true,
    snapshotCallCount: snapshotCalls.length,
  };
}

export function assertReconnectHasNoOverlap(
  beforeDisconnect: number[],
  afterReconnect: number[],
): void {
  const priorSequenceNumbers = new Set(beforeDisconnect);
  const duplicate = afterReconnect.find((sequenceNumber) =>
    priorSequenceNumbers.has(sequenceNumber),
  );
  if (duplicate) {
    throw new Error(
      `Reconnect replayed sequence ${duplicate} at or before the resume cursor`,
    );
  }
}
