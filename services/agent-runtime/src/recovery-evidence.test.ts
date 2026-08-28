import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import test from "node:test";

import type { TrueForgeApi } from "@truefoundry/trueforge-sdk";

import { analyzeRecoveryEvidence } from "./recovery-evidence.js";

function call(
  id: string,
  name: string,
  arguments_: object,
): TrueForgeApi.ToolCall {
  return {
    function: { arguments: JSON.stringify(arguments_), name },
    id,
    toolInfo: { name, type: "system" },
    type: "function",
  } as unknown as TrueForgeApi.ToolCall;
}

void test("recovery evidence requires real grounded subagents and a self-hashed artifact", () => {
  const source = "print('runtime generated')\n";
  const artifactHash = createHash("sha256").update(source).digest("hex");
  const events = [
    {
      type: "sandbox.created",
      id: "sandbox-event",
      sandboxId: "sandbox-real",
      threadId: null,
      createdAt: "2028-01-01T00:00:00Z",
    },
    ...["aircraft-thread", "crew-thread", "passenger-thread"].map(
      (threadId) =>
        ({
          type: "thread.created",
          threadId,
          agentInfo: {
            input: "Investigate",
            name:
              threadId === "aircraft-thread"
                ? "Aircraft"
                : threadId === "crew-thread"
                  ? "Crew"
                  : "Passenger",
            type: "dynamic",
          },
          parent: {
            threadId: "main",
            toolCallId:
              threadId === "aircraft-thread"
                ? "sub-1"
                : threadId === "crew-thread"
                  ? "sub-2"
                  : "sub-3",
          },
        }) as TrueForgeApi.ThreadCreatedEvent,
    ),
    {
      type: "model.message",
      threadId: "main",
      toolCalls: [
        call("sub-1", "create_sub_agent", { name: "Aircraft" }),
        call("sub-2", "create_sub_agent", { name: "Crew" }),
        call("sub-3", "create_sub_agent", { name: "Passenger" }),
        call("exec-1", "exec", { command: "python3 recovery_problem.py" }),
      ],
    },
    {
      type: "model.message",
      threadId: "aircraft-thread",
      toolCalls: [call("read-1", "airline_aircraft_investigation", {})],
    },
    {
      type: "model.message",
      threadId: "crew-thread",
      toolCalls: [call("read-2", "airline_crew_investigation", {})],
    },
    {
      type: "model.message",
      threadId: "passenger-thread",
      toolCalls: [call("read-3", "airline_passenger_investigation", {})],
    },
    {
      type: "tool.response",
      toolCallId: "exec-1",
      content: JSON.stringify({
        success: true,
        response: {
          exitCode: 0,
          result: `AIRSTRONG_RESULT=${JSON.stringify({
            artifactHash,
            artifactSourceBase64: Buffer.from(source).toString("base64"),
            candidates: [{}, {}, {}],
            snapshotHash: "a".repeat(64),
            worldRevision: 1,
          })}\n`,
        },
      }),
    },
  ] as TrueForgeApi.TurnStreamingEvent[];

  const evidence = analyzeRecoveryEvidence(events, { requireSubagents: true });

  assert.equal(evidence.artifactSource, source);
  assert.equal(evidence.sandboxId, "sandbox-real");
  assert.equal(evidence.subagentThreadIds.length, 3);
  assert.equal(evidence.sandboxResult.candidates.length, 3);

  const aircraftMessage = events.find(
    (event): event is TrueForgeApi.ModelMessageEvent =>
      event.type === "model.message" && event.threadId === "aircraft-thread",
  )!;
  aircraftMessage.toolCalls = [
    call("read-wrong", "airline_crew_investigation", {}),
  ];
  assert.throws(
    () => analyzeRecoveryEvidence(events, { requireSubagents: true }),
    /grounded MCP read/,
  );
});
