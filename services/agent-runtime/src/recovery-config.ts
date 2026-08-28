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

function endpoint(name: string, fallback: string): string {
  const value = process.env[name]?.trim() || fallback;
  let parsed: URL;
  try {
    parsed = new URL(value);
  } catch {
    throw new Error(`${name} must be a valid URL`);
  }
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`${name} must use HTTP or HTTPS`);
  }
  return value.replace(/\/+$/, "");
}

export function readRecoveryRuntimeConfig(): RecoveryRuntimeConfig {
  return {
    airlineBaseUrl: endpoint(
      "AIRSTRONG_AIRLINE_BASE_URL",
      "http://localhost:4200",
    ),
    airlineMcpUrl: endpoint(
      "AIRSTRONG_AIRLINE_MCP_URL",
      "http://host.docker.internal:4200/mcp",
    ),
    airlineRuntimeToken: required("AIRSTRONG_RUNTIME_TOKEN"),
    daytonaApiKey: required("DAYTONA_API_KEY"),
    geminiApiKey: required("GEMINI_API_KEY"),
    trueforgeBaseUrl: endpoint("TRUEFORGE_BASE_URL", "http://localhost:8790"),
  };
}
