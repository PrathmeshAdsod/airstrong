import { readRecoveryRuntimeConfig } from "./recovery-config.js";
import { runRecovery } from "./recovery-runner.js";

const worldId = process.argv[2]?.trim();
if (!worldId) {
  throw new Error("Usage: npm run recovery:run -- <world-id>");
}

console.log(
  JSON.stringify(await runRecovery(readRecoveryRuntimeConfig(), worldId)),
);
