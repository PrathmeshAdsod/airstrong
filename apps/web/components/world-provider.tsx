"use client";

import {
  createContext,
  type ReactNode,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";

import {
  type AirlineEvent,
  apiJson,
  type RecoveryBatch,
  type RecoveryRun,
  type WorldSnapshot,
  type WorldSummary,
} from "@/lib/airline";

type StreamState = "connecting" | "live" | "reconnecting" | "unavailable";

type WorldContextValue = {
  world: WorldSummary | null;
  snapshot: WorldSnapshot | null;
  recoveryBatch: RecoveryBatch | null;
  runs: RecoveryRun[];
  lastEvent: AirlineEvent | null;
  streamState: StreamState;
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
};

const eventTypes = [
  "world.created",
  "world.recalculated",
  "world.reset",
  "scenario.triggered",
  "recovery.run_started",
  "recovery.computing",
  "recovery.candidates_evaluated",
  "recovery.approval_requested",
  "recovery.approval_paused",
  "recovery.approval_approved",
  "recovery.approval_denied",
  "recovery.applied",
  "recovery.verified",
  "recovery.verification_failed",
  "recovery.failed",
] as const;

const WorldContext = createContext<WorldContextValue | null>(null);

async function loadRuns(worldId: string): Promise<RecoveryRun[]> {
  const response = await apiJson<{ runs: RecoveryRun[] }>(
    `/api/airline/api/worlds/${worldId}/recovery/runs`,
  );
  return response.runs;
}

type WorldProviderProps = { children: ReactNode };

export function WorldProvider({ children }: WorldProviderProps) {
  const [world, setWorld] = useState<WorldSummary | null>(null);
  const [snapshot, setSnapshot] = useState<WorldSnapshot | null>(null);
  const [recoveryBatch, setRecoveryBatch] = useState<RecoveryBatch | null>(
    null,
  );
  const [runs, setRuns] = useState<RecoveryRun[]>([]);
  const [lastEvent, setLastEvent] = useState<AirlineEvent | null>(null);
  const [streamState, setStreamState] = useState<StreamState>("connecting");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const worldIdRef = useRef<string | null>(null);
  const refreshPromise = useRef<Promise<void> | null>(null);

  const refresh = useCallback(async () => {
    if (refreshPromise.current) return refreshPromise.current;
    const task = (async () => {
      try {
        const currentWorld = worldIdRef.current
          ? await apiJson<WorldSummary>(
              `/api/airline/api/worlds/${worldIdRef.current}`,
            )
          : await apiJson<WorldSummary>("/api/airline/api/worlds/default");
        worldIdRef.current = currentWorld.worldId;
        const [currentSnapshot, currentRecovery, currentRuns] =
          await Promise.all([
            apiJson<WorldSnapshot>(
              `/api/airline/api/worlds/${currentWorld.worldId}/snapshot`,
            ),
            apiJson<{ batch: RecoveryBatch | null }>(
              `/api/airline/api/worlds/${currentWorld.worldId}/recovery`,
            ),
            loadRuns(currentWorld.worldId),
          ]);
        setWorld(currentWorld);
        setSnapshot(currentSnapshot);
        setRecoveryBatch(currentRecovery.batch);
        setRuns(currentRuns);
        setError(null);
      } catch (requestError) {
        setError(
          requestError instanceof Error
            ? requestError.message
            : "The Airstrong services could not be reached.",
        );
      } finally {
        setLoading(false);
      }
    })();
    refreshPromise.current = task;
    try {
      await task;
    } finally {
      refreshPromise.current = null;
    }
  }, []);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    if (!world?.worldId) return;
    const cursorKey = `airstrong:event-cursor:${world.worldId}`;
    const cursor = window.localStorage.getItem(cursorKey) ?? "0";
    const configuredBase = process.env.NEXT_PUBLIC_AIRSTRONG_EVENTS_BASE_URL;
    const base = configuredBase
      ? configuredBase.replace(/\/$/, "")
      : "/api/airline";
    const source = new EventSource(
      `${base}/api/worlds/${world.worldId}/events?after=${encodeURIComponent(cursor)}`,
    );

    const receive = (rawEvent: Event) => {
      const message = rawEvent as MessageEvent<string>;
      try {
        const event = JSON.parse(message.data) as AirlineEvent;
        window.localStorage.setItem(cursorKey, String(event.sequence));
        setLastEvent(event);
        void refresh();
      } catch {
        setError("A durable event arrived with an invalid payload.");
      }
    };

    source.onopen = () => setStreamState("live");
    source.onerror = () => setStreamState("reconnecting");
    for (const eventType of eventTypes) {
      source.addEventListener(eventType, receive);
    }

    return () => {
      for (const eventType of eventTypes) {
        source.removeEventListener(eventType, receive);
      }
      source.close();
    };
  }, [refresh, world?.worldId]);

  const value = useMemo<WorldContextValue>(
    () => ({
      world,
      snapshot,
      recoveryBatch,
      runs,
      lastEvent,
      streamState,
      loading,
      error,
      refresh,
    }),
    [
      world,
      snapshot,
      recoveryBatch,
      runs,
      lastEvent,
      streamState,
      loading,
      error,
      refresh,
    ],
  );

  return (
    <WorldContext.Provider value={value}>{children}</WorldContext.Provider>
  );
}

export function useWorld(): WorldContextValue {
  const value = useContext(WorldContext);
  if (!value) throw new Error("useWorld must be used inside WorldProvider");
  return value;
}
