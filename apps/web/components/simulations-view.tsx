"use client";

import Link from "next/link";
import { useRef, useState } from "react";

import {
  apiJson,
  formatDuration,
  humanize,
  type RecoveryRun,
} from "@/lib/airline";

import { NetworkMap } from "./network-map";
import { ServiceState } from "./service-state";
import { useWorld } from "./world-provider";

type ScenarioResult = {
  scenarioInvocationId: string;
  worldId: string;
  worldRevision: number;
  replayed: boolean;
};

function storedKey(storageKey: string): string {
  const current = window.sessionStorage.getItem(storageKey);
  if (current) return current;
  const created = crypto.randomUUID();
  window.sessionStorage.setItem(storageKey, created);
  return created;
}

export function SimulationsView() {
  const { world, snapshot, runs, lastEvent, loading, error, refresh } =
    useWorld();
  const [starting, setStarting] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const resetDialog = useRef<HTMLDialogElement>(null);

  if (loading) {
    return (
      <ServiceState
        title="Reading scenario state"
        detail="Checking the current world revision before enabling any mutation."
      />
    );
  }
  if (error || !world || !snapshot) {
    return (
      <ServiceState
        tone="error"
        title="Simulations are unavailable"
        detail={error ?? "No authoritative world was returned."}
      />
    );
  }

  const authoritativeWorld = world;
  const scenarioActive = snapshot.disruptions.length > 0;
  const latestScenarioRun = scenarioActive ? (runs[0] ?? null) : null;
  const airportDisruption = snapshot.disruptions.find(
    (disruption) => disruption.airportCode === "BOM",
  );
  const aircraftDisruptions = snapshot.disruptions.filter(
    (disruption) => disruption.aircraftId,
  );
  const durationMinutes = airportDisruption
    ? Math.round(
        (Date.parse(airportDisruption.endsAt) -
          Date.parse(airportDisruption.startsAt)) /
          60_000,
      )
    : null;
  const capacityReduction =
    airportDisruption?.capacityMultiplier === null ||
    airportDisruption?.capacityMultiplier === undefined
      ? null
      : Math.round((1 - airportDisruption.capacityMultiplier) * 100);

  async function start() {
    if (starting) return;
    setStarting(true);
    setActionError(null);
    try {
      let revision = authoritativeWorld.revision;
      let lineage = `revision-${revision}`;
      if (!scenarioActive) {
        const scenarioStorage = `airstrong:scenario-key:${authoritativeWorld.worldId}`;
        const scenarioKey = storedKey(scenarioStorage);
        const result = await apiJson<ScenarioResult>(
          `/api/airline/api/worlds/${authoritativeWorld.worldId}/scenarios/hero`,
          {
            method: "POST",
            headers: { "Idempotency-Key": scenarioKey },
          },
        );
        revision = result.worldRevision;
        lineage = result.scenarioInvocationId;
      }

      const recoveryStorage = `airstrong:recovery-key:${authoritativeWorld.worldId}:${revision}`;
      const recoveryKey = storedKey(recoveryStorage);
      await apiJson<{ run: RecoveryRun }>(
        `/api/runtime/api/worlds/${authoritativeWorld.worldId}/recovery`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": recoveryKey,
          },
          body: JSON.stringify({ idempotencyKey: recoveryKey, lineage }),
        },
      );
      await refresh();
    } catch (requestError) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : "The scenario could not start.",
      );
    } finally {
      setStarting(false);
    }
  }

  async function reset() {
    if (resetting) return;
    setResetting(true);
    setActionError(null);
    const resetStorage = `airstrong:reset-key:${authoritativeWorld.worldId}`;
    const resetKey = storedKey(resetStorage);
    try {
      await apiJson<{ worldId: string; worldRevision: number }>(
        `/api/airline/api/worlds/${authoritativeWorld.worldId}/reset`,
        { method: "POST", headers: { "Idempotency-Key": resetKey } },
      );
      window.sessionStorage.removeItem(
        `airstrong:scenario-key:${authoritativeWorld.worldId}`,
      );
      window.sessionStorage.removeItem(resetStorage);
      resetDialog.current?.close();
      await refresh();
    } catch (requestError) {
      setActionError(
        requestError instanceof Error
          ? requestError.message
          : "The world could not reset.",
      );
    } finally {
      setResetting(false);
    }
  }

  return (
    <div className="simulation-workspace">
      <section className="scenario-card">
        <div className="scenario-card__copy">
          <p className="eyebrow">Verified hero scenario</p>
          <h2>Cyclone at BOM + aircraft unavailable</h2>
          <p>
            Mutates the current synthetic world, recalculates dependencies, then
            starts the real TrueForge recovery workflow.
          </p>
          <div className="scenario-facts">
            <div>
              <span>Airport</span>
              <strong>{scenarioActive ? "BOM" : "Written on trigger"}</strong>
            </div>
            <div>
              <span>Capacity reduction</span>
              <strong>
                {capacityReduction === null
                  ? "Written on trigger"
                  : `${capacityReduction}%`}
              </strong>
            </div>
            <div>
              <span>Duration</span>
              <strong>
                {durationMinutes === null
                  ? "Written on trigger"
                  : formatDuration(durationMinutes)}
              </strong>
            </div>
            <div>
              <span>Aircraft unavailable</span>
              <strong>
                {scenarioActive
                  ? aircraftDisruptions.length
                  : "Written on trigger"}
              </strong>
            </div>
          </div>
          <div className="scenario-actions">
            {latestScenarioRun ? (
              <Link className="button button--primary" href="/runs">
                Open {humanize(latestScenarioRun.status)} run
              </Link>
            ) : (
              <button
                className="button button--primary"
                disabled={starting}
                onClick={() => void start()}
                type="button"
              >
                {starting
                  ? "Starting real workflow"
                  : scenarioActive
                    ? "Start recovery"
                    : "Start scenario"}
              </button>
            )}
            <span>World revision {authoritativeWorld.revision}</span>
          </div>
          {actionError ? (
            <p className="form-error" role="alert">
              {actionError}
            </p>
          ) : null}
        </div>
        <NetworkMap
          compact
          snapshot={snapshot}
          recoveryActions={latestScenarioRun?.executedActions}
        />
      </section>

      <section className="scenario-reality">
        <div>
          <p>Current state</p>
          <h3>
            {scenarioActive
              ? `${snapshot.disruptions.length} active disruption records`
              : "Baseline operational world"}
          </h3>
        </div>
        <dl>
          <div>
            <dt>Flights at risk</dt>
            <dd>
              {
                snapshot.flights.filter((flight) => flight.status === "at_risk")
                  .length
              }
            </dd>
          </div>
          <div>
            <dt>Stored run</dt>
            <dd>
              {latestScenarioRun ? latestScenarioRun.runId.slice(0, 8) : "None"}
            </dd>
          </div>
          <div>
            <dt>Latest event</dt>
            <dd>{lastEvent ? `#${lastEvent.sequence}` : "No new event"}</dd>
          </div>
        </dl>
      </section>

      <section className="reset-panel">
        <div>
          <p>Reset synthetic world</p>
          <h3>Return Aliens Airline to the versioned baseline</h3>
          <span>
            Reset is a real idempotent database mutation. Historical runs remain
            available for audit.
          </span>
        </div>
        <button
          className="button button--danger-outline"
          onClick={() => resetDialog.current?.showModal()}
          type="button"
        >
          Reset airline
        </button>
      </section>

      <dialog className="confirm-dialog" ref={resetDialog}>
        <form method="dialog">
          <p>Reset world</p>
          <h2>Return to the baseline?</h2>
          <p>
            The operational state will be replaced with the versioned synthetic
            baseline. The action cannot be undone, but durable run history
            remains.
          </p>
          <div>
            <button
              className="button button--quiet"
              disabled={resetting}
              value="cancel"
            >
              Cancel
            </button>
            <button
              className="button button--consequential"
              disabled={resetting}
              onClick={(event) => {
                event.preventDefault();
                void reset();
              }}
              value="confirm"
            >
              {resetting ? "Resetting" : "Reset airline"}
            </button>
          </div>
        </form>
      </dialog>
    </div>
  );
}
