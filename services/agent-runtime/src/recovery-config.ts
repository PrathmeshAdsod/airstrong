export interface RecoveryRuntimeConfig {
  airlineBaseUrl: string;
  airlineMcpUrl: string;
  airlineRuntimeToken: string;
  daytonaApiKey: string;
  geminiApiKey: string;
  trueforgeBaseUrl: string;
}

function required(name: string): string {
  const value = process.env[name]?.trim();
  if (!value) {
    throw new Error(`${name} is required for the Airstrong recovery runtime`);
  }
  return value;
}

export function readRecoveryRuntimeConfig(): RecoveryRuntimeConfig {
  return {
    airlineBaseUrl:
      process.env.AIRSTRONG_AIRLINE_BASE_URL ?? "http://localhost:4200",
    airlineMcpUrl:
      process.env.AIRSTRONG_AIRLINE_MCP_URL ??
      "http://host.docker.internal:4200/mcp",
    airlineRuntimeToken: required("AIRSTRONG_RUNTIME_TOKEN"),
    daytonaApiKey: required("DAYTONA_API_KEY"),
    geminiApiKey: required("GEMINI_API_KEY"),
    trueforgeBaseUrl: process.env.TRUEFORGE_BASE_URL ?? "http://localhost:8790",
  };
}
