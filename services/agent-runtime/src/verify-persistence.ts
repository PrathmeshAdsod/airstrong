import { readFile } from "node:fs/promises";

import { TrueForge } from "@truefoundry/trueforge-sdk";

import { readCompatibilityConfig } from "./config.js";
import { readAuditState } from "./database.js";

interface PersistedCompatibilityState {
  approvalTurnId: string;
  idempotencyKey: string;
  sessionId: string;
}

async function main(): Promise<void> {
  const config = readCompatibilityConfig();
  const saved = JSON.parse(
    await readFile(config.statePath, "utf8"),
  ) as PersistedCompatibilityState;
  const client = new TrueForge({ baseUrl: config.trueforgeBaseUrl });

  const [session, turn, events, audit] = await Promise.all([
    client.sessions.get(saved.sessionId),
    client.sessions.getTurn(saved.sessionId, saved.approvalTurnId),
    client.sessions.listTurnEvents(saved.sessionId, saved.approvalTurnId),
    readAuditState(config.databaseUrl, saved.idempotencyKey),
  ]);

  if (
    session.data.id !== saved.sessionId ||
    turn.data.id !== saved.approvalTurnId
  ) {
    throw new Error(
      "TrueForge did not recover the stored session and turn after restart",
    );
  }
  if (events.data.length === 0) {
    throw new Error(
      "TrueForge did not recover persisted turn events after restart",
    );
  }
  if (!audit.exists) {
    throw new Error(
      "The approved idempotent MCP write was not durable after restart",
    );
  }

  console.log(
    JSON.stringify({
      approvedWriteDurable: true,
      persistedEvents: events.data.length,
      sessionRecovered: true,
      turnRecovered: true,
    }),
  );
}

await main();
