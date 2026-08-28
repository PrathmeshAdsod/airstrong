"use client";

import Link from "next/link";

import { formatClock, humanize } from "@/lib/airline";

import { NetworkMap } from "./network-map";
import { ServiceState } from "./service-state";
import { useWorld } from "./world-provider";

export function LiveView() {
  const { world, snapshot, runs, lastEvent, streamState, loading, error } =
    useWorld();

  if (loading) {
    return (
      <ServiceState
        title="Reading the airline world"
        detail="Airstrong is loading the current PostgreSQL revision and durable event cursor."
      />
    );
  }
  if (error || !world || !snapshot) {
    return (
      <ServiceState
        tone="error"
        title="The operational services are unavailable"
        detail={error ?? "No authoritative world was returned."}
      />
    );
  }

  const availableAircraft = snapshot.aircraft.filter(
    (aircraft) => aircraft.status === "available",
  ).length;
  const affectedFlights = new Set(
    snapshot.operationalImpacts
      .filter((impact) => impact.entityType === "flight")
      .map((impact) => impact.entityId),
  );
  const affectedPassengers = new Set(
    snapshot.operationalImpacts
      .filter((impact) => impact.entityType === "passenger_party")
      .map((impact) => impact.entityId),
  );
  const passengerCount = snapshot.passengerParties
    .filter((party) => affectedPassengers.has(party.partyId))
    .reduce((total, party) => total + party.partySize, 0);
  const latestRun = runs[0] ?? null;
  const activeAirport = snapshot.disruptions.find(
    (disruption) => disruption.airportCode,
  );
  const activeAircraft = snapshot.disruptions.find(
    (disruption) => disruption.aircraftId,
  );

  return (
    <div className="live-layout">
      <div className="metric-strip" aria-label="Current operational totals">
        <article>
          <span>Flights in world</span>
          <strong>{world.counts.flights}</strong>
          <small>{affectedFlights.size} affected</small>
        </article>
        <article>
          <span>Aircraft available</span>
          <strong>{availableAircraft}</strong>
          <small>{world.counts.aircraft} total</small>
        </article>
        <article>
          <span>Passengers affected</span>
          <strong>{passengerCount}</strong>
          <small>{affectedPassengers.size} parties</small>
        </article>
        <article
          className={snapshot.disruptions.length ? "metric-strip__alert" : ""}
        >
          <span>Active disruptions</span>
          <strong>{snapshot.disruptions.length}</strong>
          <small>Revision {world.revision}</small>
        </article>
      </div>

      <div className="live-grid">
        <div className="live-map-panel">
          <div className="panel-heading">
            <div>
              <p>Network state</p>
              <h2>{formatClock(world.simulationClock)}</h2>
            </div>
            <span
              className={`stream-indicator stream-indicator--${streamState}`}
            >
              <i aria-hidden="true" />
              {streamState === "live" ? "Events live" : humanize(streamState)}
            </span>
          </div>
          <NetworkMap
            snapshot={snapshot}
            recoveryActions={latestRun?.executedActions}
          />
        </div>

        <aside className="live-side">
          <section className="incident-panel">
            <div className="incident-panel__heading">
              <p>Current disruption</p>
              <span>{snapshot.disruptions.length ? "Active" : "Clear"}</span>
            </div>
            {snapshot.disruptions.length ? (
              <>
                <h2>
                  {activeAirport?.airportCode
                    ? `${humanize(activeAirport.kind)} at ${activeAirport.airportCode}`
                    : activeAircraft?.aircraftId
                      ? `${humanize(activeAircraft.kind)} · ${activeAircraft.aircraftId}`
                      : humanize(snapshot.disruptions[0]!.kind)}
                </h2>
                <p>
                  The domain engine has propagated this incident to{" "}
                  {affectedFlights.size} flights and {affectedPassengers.size}{" "}
                  passenger parties.
                </p>
                <dl>
                  <div>
                    <dt>Flight impacts</dt>
                    <dd>{affectedFlights.size}</dd>
                  </div>
                  <div>
                    <dt>Crew impacts</dt>
                    <dd>
                      {
                        snapshot.operationalImpacts.filter(
                          (item) => item.entityType === "crew",
                        ).length
                      }
                    </dd>
                  </div>
                  <div>
                    <dt>Passenger impacts</dt>
                    <dd>{passengerCount}</dd>
                  </div>
                </dl>
              </>
            ) : (
              <>
                <h2>No active incident</h2>
                <p>
                  The world is at its baseline state. Start a verified scenario
                  from Simulations.
                </p>
              </>
            )}
          </section>

          <section className="run-callout">
            <p>Recovery run</p>
            {latestRun ? (
              <>
                <div className="run-callout__status">
                  <strong>{humanize(latestRun.status)}</strong>
                  <span>{latestRun.runId.slice(0, 8)}</span>
                </div>
                <p>
                  Stored against world revision {latestRun.startedWorldRevision}
                  . Refreshing keeps this run and its TrueForge session.
                </p>
                <Link href="/runs">
                  Open run record <span aria-hidden="true">→</span>
                </Link>
              </>
            ) : (
              <>
                <h2>No recovery run</h2>
                <p>
                  A run appears here only after the runtime has created it in
                  PostgreSQL.
                </p>
                <Link href="/simulations">
                  Open simulations <span aria-hidden="true">→</span>
                </Link>
              </>
            )}
          </section>

          <section className="event-cursor">
            <span>Durable event cursor</span>
            <strong>
              {lastEvent
                ? `#${lastEvent.sequence} · ${humanize(lastEvent.eventType)}`
                : "Connected, no new event"}
            </strong>
          </section>
        </aside>
      </div>
    </div>
  );
}
