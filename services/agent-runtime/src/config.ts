import { resolve } from "node:path";

export interface CompatibilityConfig {
  databaseUrl: string;
  daytonaApiKey: string;
  geminiApiKey: string;
  statePath: string;
  trueforgeBaseUrl: string;
}

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for the live compatibility proof`);
  }
  return value;
}

export function readCompatibilityConfig(): CompatibilityConfig {
  return {
    databaseUrl:
      process.env.AIRSTRONG_DATABASE_URL ??
      "postgresql://airstrong:local-airstrong-only@localhost:5433/airstrong",
    daytonaApiKey: required("DAYTONA_API_KEY"),
    geminiApiKey: required("GEMINI_API_KEY"),
    statePath: resolve(
      process.env.AIRSTRONG_COMPATIBILITY_STATE_PATH ??
        ".airstrong/compatibility-state.json",
    ),
    trueforgeBaseUrl: process.env.TRUEFORGE_BASE_URL ?? "http://localhost:8790",
  };
}
