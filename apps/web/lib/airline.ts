export type DataSection =
  "flights" | "aircraft" | "crew" | "passengers" | "airports" | "disruptions";

export type WorldSummary = {
  worldId: string;
  displayName: string;
  baselineVersion: string;
  simulationClock: string;
  revision: number;
  state: string;
  createdAt: string;
  expiresAt: string;
  counts: {
    flights: number;
    aircraft: number;
    crew: number;
    passengerParties: number;
    passengers: number;
    airports: number;
    disruptions: number;
  };
};

export type Airport = {
  code: string;
  name: string;
  city: string;
  countryCode: string;
  timezone: string;
  latitude: number;
  longitude: number;
  hourlyCapacity: number;
  domesticConnectionMinutes: number;
  internationalConnectionMinutes: number;
};

export type Aircraft = {
  aircraftId: string;
  aircraftType: string;
  seats: number;
  locationAirport: string;
  status: string;
  availableFrom: string;
  minimumTurnaroundMinutes: number;
};

export type Flight = {
  flightId: string;
  origin: string;
  destination: string;
  scheduledDeparture: string;
  scheduledArrival: string;
  aircraftId: string;
  aircraftType: string;
  capacity: number;
  status: string;
};

export type CrewMember = {
  crewId: string;
  role: string;
  baseAirport: string;
  qualifications: string[];
  dutyStart: string;
  dutyEnd: string;
  previousDutyEnd: string;
};

export type CrewAssignment = {
  crewId: string;
  flightId: string;
  role: string;
};

export type PassengerParty = {
  partyId: string;
  partySize: number;
};

export type ItineraryLeg = {
  partyId: string;
  flightId: string;
  legOrder: number;
};

export type Disruption = {
  disruptionId: string;
  kind: string;
  airportCode: string | null;
  startsAt: string;
  endsAt: string;
  capacityMultiplier: number | null;
  aircraftId: string | null;
};

export type OperationalImpact = {
  entityType: string;
  entityId: string;
  reason: string;
  depth: number;
  rootDisruptionId: string;
  sourceEntityType: string;
  sourceEntityId: string;
};

export type WorldSnapshot = {
  worldId: string;
  revision: number;
  airports: Airport[];
  aircraft: Aircraft[];
  flights: Flight[];
  crew: CrewMember[];
  crewAssignments: CrewAssignment[];
  passengerParties: PassengerParty[];
  itineraryLegs: ItineraryLeg[];
  disruptions: Disruption[];
  operationalImpacts: OperationalImpact[];
};

export type RecoveryAction = {
  actionType: string;
  flightId: string;
  aircraftId?: string;
  departure?: string;
  arrival?: string;
  crewId?: string;
  itineraryId?: string;
};

export type CandidateMetrics = {
  cancellations: number;
  disruptedPassengers: number;
  totalDelayMinutes: number;
  operationalReassignments: number;
  stabilizationMinutes: number;
};

export type TwinViolation = {
  code: string;
  message: string;
  entityType: string;
  entityId: string;
  facts: Record<string, unknown>;
};

export type RecoveryCandidate = {
  candidateId: string;
  strategyParameters: Record<string, unknown>;
  actions: RecoveryAction[];
  solverVersion: string;
  solverStatus: string;
  objectiveValue: number;
  simulatorVersion: string;
  valid: boolean;
  metrics: CandidateMetrics;
  violations: TwinViolation[];
  rank: number | null;
  recommended: boolean;
};

export type RecoveryBatch = {
  batchId: string;
  worldId: string;
  worldRevision: number;
  snapshotHash: string;
  artifactHash: string;
  rankingVersion: string;
  createdAt: string;
  candidates: RecoveryCandidate[];
};

export type RecoveryRun = {
  runId: string;
  worldId: string;
  startedWorldRevision: number;
  snapshotHash: string;
  idempotencyKey: string;
  status: string;
  trueforgeSessionId: string | null;
  investigationTurnId: string | null;
  executionTurnId: string | null;
  batchId: string | null;
  recommendedCandidateId: string | null;
  failure: { stage?: string; detail?: string } | string | null;
  createdAt: string;
  updatedAt: string;
  approvalContinuationTurnId: string | null;
  approvalId: string | null;
  approvalStatus: string | null;
  approvalActions: RecoveryAction[] | null;
  approvalSummary: Record<string, number> | null;
  planHash: string | null;
  expectedWorldRevision: number | null;
  trueforgeThreadId: string | null;
  trueforgeToolCallId: string | null;
  trueforgeApprovalEventId: string | null;
  executionId: string | null;
  appliedWorldRevision: number | null;
  executedActions: RecoveryAction[] | null;
  verificationId: string | null;
  verificationValid: boolean | null;
  verificationFacts: Array<Record<string, unknown>> | null;
  verificationWorldRevision: number | null;
};

export type AirlineEvent = {
  sequence: number;
  eventType: string;
  worldRevision: number;
  payload: Record<string, unknown>;
  createdAt: string;
};

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function apiJson<T>(
  input: string,
  init?: RequestInit,
): Promise<T> {
  const response = await fetch(input, { cache: "no-store", ...init });
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = (await response.json()) as {
        detail?: string;
        error?: string;
      };
      detail = body.detail ?? body.error ?? detail;
    } catch {
      // The HTTP status remains the factual fallback when a service has no JSON body.
    }
    throw new ApiError(response.status, detail);
  }
  return (await response.json()) as T;
}

export function humanize(value: string): string {
  return value
    .replaceAll("_", " ")
    .replace(/\b\w/g, (character) => character.toUpperCase());
}

export function shortId(value: string | null | undefined): string {
  return value ? value.slice(0, 8) : "Not recorded";
}

export function formatClock(value: string): string {
  return new Intl.DateTimeFormat("en-IN", {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
    timeZone: "Asia/Kolkata",
    timeZoneName: "short",
  }).format(new Date(value));
}

export function formatDuration(minutes: number): string {
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.floor(minutes / 60);
  const remainder = minutes % 60;
  return remainder === 0 ? `${hours} hr` : `${hours} hr ${remainder} min`;
}
