"use client";

import { useMemo, useState } from "react";

import type {
  Airport,
  Flight,
  RecoveryAction,
  WorldSnapshot,
} from "@/lib/airline";

type RouteState = "normal" | "affected" | "recovery";

type NetworkRoute = {
  key: string;
  origin: Airport;
  destination: Airport;
  flights: Flight[];
  state: RouteState;
};

type Point = { x: number; y: number };

type NetworkMapProps = {
  snapshot: WorldSnapshot;
  recoveryActions?: RecoveryAction[] | null;
  compact?: boolean;
};

function pointFor(airport: Airport, airports: Airport[]): Point {
  const longitudes = airports.map((item) => item.longitude);
  const latitudes = airports.map((item) => item.latitude);
  const minLongitude = Math.min(...longitudes);
  const maxLongitude = Math.max(...longitudes);
  const minLatitude = Math.min(...latitudes);
  const maxLatitude = Math.max(...latitudes);
  const longitudeRange = Math.max(1, maxLongitude - minLongitude);
  const latitudeRange = Math.max(1, maxLatitude - minLatitude);
  return {
    x: 72 + ((airport.longitude - minLongitude) / longitudeRange) * 756,
    y: 400 - ((airport.latitude - minLatitude) / latitudeRange) * 320,
  };
}

function routePath(origin: Point, destination: Point, key: string): string {
  const midpoint = {
    x: (origin.x + destination.x) / 2,
    y: (origin.y + destination.y) / 2,
  };
  const dx = destination.x - origin.x;
  const dy = destination.y - origin.y;
  const length = Math.max(1, Math.hypot(dx, dy));
  const direction = key.charCodeAt(0) % 2 === 0 ? 1 : -1;
  const bend = Math.min(52, Math.max(20, length * 0.12)) * direction;
  const control = {
    x: midpoint.x + (-dy / length) * bend,
    y: midpoint.y + (dx / length) * bend,
  };
  return `M ${origin.x} ${origin.y} Q ${control.x} ${control.y} ${destination.x} ${destination.y}`;
}

function buildRoutes(
  snapshot: WorldSnapshot,
  recoveryActions: RecoveryAction[],
): NetworkRoute[] {
  const airports = new Map(
    snapshot.airports.map((airport) => [airport.code, airport]),
  );
  const impactedFlights = new Set(
    snapshot.operationalImpacts
      .filter((impact) => impact.entityType === "flight")
      .map((impact) => impact.entityId),
  );
  const recoveryFlights = new Set(
    recoveryActions.map((action) => action.flightId),
  );
  const grouped = new Map<string, Flight[]>();

  for (const flight of snapshot.flights) {
    const key = [flight.origin, flight.destination].sort().join("-");
    grouped.set(key, [...(grouped.get(key) ?? []), flight]);
  }

  return [...grouped.entries()].flatMap(([key, flights]) => {
    const first = flights[0];
    if (!first) return [];
    const origin = airports.get(first.origin);
    const destination = airports.get(first.destination);
    if (!origin || !destination) return [];
    const state: RouteState = flights.some((flight) =>
      recoveryFlights.has(flight.flightId),
    )
      ? "recovery"
      : flights.some(
            (flight) =>
              impactedFlights.has(flight.flightId) ||
              flight.status === "at_risk" ||
              flight.status === "cancelled",
          )
        ? "affected"
        : "normal";
    return [{ key, origin, destination, flights, state }];
  });
}

export function NetworkMap({
  snapshot,
  recoveryActions = [],
  compact = false,
}: NetworkMapProps) {
  const activeAirport =
    snapshot.disruptions.find((item) => item.airportCode)?.airportCode ??
    snapshot.airports[0]?.code ??
    null;
  const [selectedAirport, setSelectedAirport] = useState<string | null>(
    activeAirport,
  );
  const routes = useMemo(
    () => buildRoutes(snapshot, recoveryActions ?? []),
    [recoveryActions, snapshot],
  );
  const airportByCode = new Map(
    snapshot.airports.map((airport) => [airport.code, airport]),
  );
  const selected = selectedAirport
    ? airportByCode.get(selectedAirport)
    : undefined;
  const selectedFlights = selectedAirport
    ? snapshot.flights.filter(
        (flight) =>
          flight.origin === selectedAirport ||
          flight.destination === selectedAirport,
      )
    : [];

  return (
    <section className={`network-map ${compact ? "network-map--compact" : ""}`}>
      <div className="network-map__legend" aria-label="Route status legend">
        <span>
          <i className="legend-line legend-line--normal" />
          Scheduled
        </span>
        <span>
          <i className="legend-line legend-line--affected" />
          Affected
        </span>
        <span>
          <i className="legend-line legend-line--recovery" />
          Recovery action
        </span>
      </div>
      <svg
        aria-label={`Operational network with ${snapshot.airports.length} airports and ${snapshot.flights.length} flights`}
        className="network-map__canvas"
        role="img"
        viewBox="0 0 900 480"
      >
        <defs>
          <pattern
            id="coordinate-grid"
            width="60"
            height="60"
            patternUnits="userSpaceOnUse"
          >
            <path
              d="M 60 0 L 0 0 0 60"
              fill="none"
              stroke="currentColor"
              strokeWidth="0.6"
            />
          </pattern>
        </defs>
        <rect
          className="network-map__grid"
          width="900"
          height="480"
          fill="url(#coordinate-grid)"
        />
        <g aria-label="Routes">
          {routes.map((route) => {
            const origin = pointFor(route.origin, snapshot.airports);
            const destination = pointFor(route.destination, snapshot.airports);
            return (
              <path
                className={`network-route network-route--${route.state}`}
                d={routePath(origin, destination, route.key)}
                key={route.key}
              >
                <title>{`${route.origin.code} to ${route.destination.code}: ${route.flights.length} flight${route.flights.length === 1 ? "" : "s"}, ${route.state}`}</title>
              </path>
            );
          })}
        </g>
        <g aria-label="Airports">
          {snapshot.airports.map((airport) => {
            const point = pointFor(airport, snapshot.airports);
            const disrupted = snapshot.disruptions.some(
              (item) => item.airportCode === airport.code,
            );
            const selectedNode = selectedAirport === airport.code;
            return (
              <g
                aria-label={`${airport.code}, ${airport.city}${disrupted ? ", active disruption" : ""}`}
                className={`airport-node ${disrupted ? "airport-node--disrupted" : ""} ${selectedNode ? "airport-node--selected" : ""}`}
                key={airport.code}
                onClick={() => setSelectedAirport(airport.code)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    setSelectedAirport(airport.code);
                  }
                }}
                role="button"
                tabIndex={0}
                transform={`translate(${point.x} ${point.y})`}
              >
                {disrupted ? (
                  <circle className="airport-node__pulse" r="24" />
                ) : null}
                <circle
                  className="airport-node__ring"
                  r={selectedNode ? 12 : 10}
                />
                <circle className="airport-node__dot" r="4" />
                <text className="airport-node__code" x="0" y="-18">
                  {airport.code}
                </text>
                <text className="airport-node__city" x="0" y="25">
                  {airport.city}
                </text>
              </g>
            );
          })}
        </g>
      </svg>
      {selected ? (
        <div className="network-map__selection" aria-live="polite">
          <div>
            <span>Selected airport</span>
            <strong>
              {selected.code} · {selected.city}
            </strong>
          </div>
          <div>
            <span>Scheduled flights</span>
            <strong>{selectedFlights.length}</strong>
          </div>
          <div>
            <span>Hourly capacity</span>
            <strong>{selected.hourlyCapacity}</strong>
          </div>
        </div>
      ) : null}
    </section>
  );
}
