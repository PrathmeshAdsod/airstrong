import assert from "node:assert/strict";
import { describe, it } from "node:test";

import {
  dashboardNavigation,
  dataSections,
  landingNavigation,
} from "./navigation.ts";

describe("locked information architecture", () => {
  it("keeps the dashboard horizontal navigation focused", () => {
    const dashboardLabels: readonly string[] = dashboardNavigation.map(
      (item) => item.label,
    );

    assert.deepEqual(dashboardLabels, ["Live", "Runs", "Data", "Simulations"]);
    assert.equal(dashboardLabels.includes("GitHub"), false);
  });

  it("keeps landing navigation minimal", () => {
    assert.deepEqual(
      landingNavigation.map((item) => item.label),
      ["How it works", "Scenarios"],
    );
  });

  it("exposes every authoritative data section", () => {
    assert.deepEqual(dataSections, [
      "Flights",
      "Aircraft",
      "Crew",
      "Passengers",
      "Airports",
      "Disruptions",
    ]);
  });
});
