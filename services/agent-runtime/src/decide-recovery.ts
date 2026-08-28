import { readRecoveryRuntimeConfig } from "./recovery-config.js";
import { decideRecovery } from "./recovery-runner.js";

const [runId, rawDecision, providedKey] = process.argv.slice(2);
if (!runId || !rawDecision || !["approve", "deny"].includes(rawDecision)) {
  throw new Error(
    "Usage: npm run recovery:decide -- <run-id> <approve|deny> [idempotency-key]",
  );
}
const decision = rawDecision === "approve" ? "approved" : "denied";
const result = await decideRecovery(
  readRecoveryRuntimeConfig(),
  runId,
  decision,
  providedKey ?? `decision-${runId}-${decision}`,
);
console.log(JSON.stringify(result, null, 2));
