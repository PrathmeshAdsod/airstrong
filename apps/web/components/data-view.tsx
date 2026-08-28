"use client";

import { useEffect, useMemo, useState } from "react";

import {
  apiJson,
  type DataSection,
  formatClock,
  humanize,
} from "@/lib/airline";

import { ServiceState } from "./service-state";
import { useWorld } from "./world-provider";

type DataRecord = Record<string, unknown>;

const sections: Array<{ key: DataSection; label: string }> = [
  { key: "flights", label: "Flights" },
  { key: "aircraft", label: "Aircraft" },
  { key: "crew", label: "Crew" },
  { key: "passengers", label: "Passengers" },
  { key: "airports", label: "Airports" },
  { key: "disruptions", label: "Disruptions" },
];

const columns: Record<DataSection, string[]> = {
  flights: [
    "flightId",
    "origin",
    "destination",
    "scheduledDeparture",
    "aircraftId",
    "status",
  ],
  aircraft: [
    "aircraftId",
    "aircraftType",
    "locationAirport",
    "seats",
    "status",
  ],
  crew: ["crewId", "role", "baseAirport", "qualifications", "flightIds"],
  passengers: ["partyId", "partySize", "itinerary"],
  airports: ["code", "city", "countryCode", "hourlyCapacity", "timezone"],
  disruptions: [
    "disruptionId",
    "kind",
    "airportCode",
    "aircraftId",
    "startsAt",
    "endsAt",
  ],
};

function recordId(record: DataRecord, index: number): string {
  for (const key of [
    "flightId",
    "aircraftId",
    "crewId",
    "partyId",
    "code",
    "disruptionId",
  ]) {
    if (typeof record[key] === "string") return record[key] as string;
  }
  return `row-${index}`;
}

function displayValue(value: unknown, key?: string): string {
  if (value === null || value === undefined || value === "") return "Not set";
  if (typeof value === "boolean") return value ? "Yes" : "No";
  if (typeof value === "number") return String(value);
  if (typeof value === "string") {
    const normalizedKey = key?.toLowerCase();
    if (
      normalizedKey?.endsWith("at") ||
      normalizedKey?.includes("departure") ||
      normalizedKey?.includes("arrival") ||
      normalizedKey?.includes("duty")
    ) {
      const parsed = Date.parse(value);
      if (!Number.isNaN(parsed)) return formatClock(value);
    }
    return humanize(value);
  }
  if (Array.isArray(value)) {
    return value
      .map((item) =>
        typeof item === "object" && item !== null
          ? Object.values(item)
              .filter((part) => typeof part === "string")
              .join(" · ")
          : String(item),
      )
      .join(", ");
  }
  return JSON.stringify(value);
}

export function DataView() {
  const {
    world,
    lastEvent,
    loading: worldLoading,
    error: worldError,
  } = useWorld();
  const [section, setSection] = useState<DataSection>("flights");
  const [items, setItems] = useState<DataRecord[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!world) return;
    const controller = new AbortController();
    void apiJson<{ items: DataRecord[] }>(
      `/api/airline/api/worlds/${world.worldId}/data/${section}`,
      { signal: controller.signal },
    )
      .then((response) => {
        setError(null);
        setItems(response.items);
        setSelectedId((current) => {
          if (
            current &&
            response.items.some(
              (item, index) => recordId(item, index) === current,
            )
          )
            return current;
          return response.items[0] ? recordId(response.items[0], 0) : null;
        });
      })
      .catch((requestError: unknown) => {
        if (
          requestError instanceof DOMException &&
          requestError.name === "AbortError"
        )
          return;
        setError(
          requestError instanceof Error
            ? requestError.message
            : "Data request failed.",
        );
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [lastEvent?.sequence, section, world]);

  const selected = useMemo(
    () =>
      items.find((item, index) => recordId(item, index) === selectedId) ?? null,
    [items, selectedId],
  );

  if (worldLoading) {
    return (
      <ServiceState
        title="Reading operational data"
        detail="Loading the authoritative world revision."
      />
    );
  }
  if (worldError || !world) {
    return (
      <ServiceState
        tone="error"
        title="Operational data is unavailable"
        detail={worldError ?? "No world was returned."}
      />
    );
  }

  return (
    <div className="data-workspace">
      <div className="data-summary" aria-label="Authoritative dataset counts">
        <span>
          <strong>{world.counts.flights}</strong> flights
        </span>
        <span>
          <strong>{world.counts.aircraft}</strong> aircraft
        </span>
        <span>
          <strong>{world.counts.crew}</strong> crew
        </span>
        <span>
          <strong>{world.counts.passengers}</strong> passengers
        </span>
        <span>
          <strong>{world.counts.airports}</strong> airports
        </span>
      </div>
      <div
        className="data-tabs"
        role="tablist"
        aria-label="Operational data sections"
      >
        {sections.map((item) => (
          <button
            aria-selected={section === item.key}
            className={section === item.key ? "is-selected" : ""}
            key={item.key}
            onClick={() => {
              setLoading(true);
              setError(null);
              setSection(item.key);
            }}
            role="tab"
            type="button"
          >
            {item.label}
          </button>
        ))}
      </div>
      {error ? (
        <ServiceState
          tone="error"
          title="This data section could not be read"
          detail={error}
        />
      ) : null}
      {!error ? (
        <div className="data-grid">
          <section className="data-table-wrap" aria-busy={loading}>
            <div className="data-table-heading">
              <div>
                <p>Authoritative rows</p>
                <h2>{humanize(section)}</h2>
              </div>
              <span>
                {loading
                  ? "Reading"
                  : `${items.length} rows · revision ${world.revision}`}
              </span>
            </div>
            {items.length ? (
              <div className="data-table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      {columns[section].map((key) => (
                        <th key={key}>{humanize(key)}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((item, index) => {
                      const id = recordId(item, index);
                      return (
                        <tr
                          className={selectedId === id ? "is-selected" : ""}
                          key={id}
                        >
                          {columns[section].map((key, columnIndex) => (
                            <td key={key}>
                              {columnIndex === 0 ? (
                                <button
                                  onClick={() => setSelectedId(id)}
                                  type="button"
                                >
                                  {displayValue(item[key], key)}
                                </button>
                              ) : (
                                displayValue(item[key], key)
                              )}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            ) : (
              <div className="data-empty">
                No {section} exist in revision {world.revision}.
              </div>
            )}
          </section>
          <aside className="record-detail">
            <p>Selected record</p>
            {selected ? (
              <>
                <h2>{selectedId}</h2>
                <dl>
                  {Object.entries(selected).map(([key, value]) => (
                    <div key={key}>
                      <dt>{humanize(key)}</dt>
                      <dd>{displayValue(value, key)}</dd>
                    </div>
                  ))}
                </dl>
              </>
            ) : (
              <h2>No row selected</h2>
            )}
          </aside>
        </div>
      ) : null}
    </div>
  );
}
