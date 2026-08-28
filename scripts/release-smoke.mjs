const requiredUrl = (name) => {
  const raw = process.env[name]?.trim();
  if (!raw) throw new Error(`${name} is required`);
  const parsed = new URL(raw);
  if (!["http:", "https:"].includes(parsed.protocol)) {
    throw new Error(`${name} must use HTTP or HTTPS`);
  }
  return raw.replace(/\/+$/, "");
};

const webBase = requiredUrl("AIRSTRONG_WEB_URL");
const airlineBase = requiredUrl("AIRSTRONG_AIRLINE_BASE_URL");
const runtimeBase = requiredUrl("AIRSTRONG_RUNTIME_BASE_URL");

const request = async (url, expectedType) => {
  const response = await fetch(url, {
    headers: { accept: expectedType },
    redirect: "follow",
  });
  if (!response.ok) {
    throw new Error(
      `${url} returned ${response.status}: ${await response.text()}`,
    );
  }
  return response;
};

const json = async (url) => (await request(url, "application/json")).json();

const landing = await request(webBase, "text/html");
const landingText = await landing.text();
if (!landingText.includes("Airstrong")) {
  throw new Error("The deployed landing page did not identify Airstrong");
}

const airlineHealth = await json(`${airlineBase}/health`);
const runtimeHealth = await json(`${runtimeBase}/health`);
if (airlineHealth.status !== "ok" || runtimeHealth.status !== "ok") {
  throw new Error("A production service did not report healthy");
}

const world = await json(`${airlineBase}/api/worlds/default`);
const worldId = world.worldId;
if (typeof worldId !== "string" || !world.counts || world.counts.flights < 1) {
  throw new Error("The authoritative world response is incomplete");
}

const [snapshot, flights, runs, events] = await Promise.all([
  json(`${airlineBase}/api/worlds/${worldId}/snapshot`),
  json(`${airlineBase}/api/worlds/${worldId}/data/flights`),
  json(`${airlineBase}/api/worlds/${worldId}/recovery/runs`),
  request(
    `${airlineBase}/api/worlds/${worldId}/events?after=0&follow=false`,
    "text/event-stream",
  ),
]);

if (snapshot.worldId !== worldId || snapshot.revision !== world.revision) {
  throw new Error(
    "Snapshot identity or revision does not match the world summary",
  );
}
if (
  !Array.isArray(flights.items) ||
  !flights.items.every((flight) => /^ALN-\d{4}$/.test(flight.flightId))
) {
  throw new Error(
    "Flight data is missing or violates the synthetic ALN identifier contract",
  );
}
if (!Array.isArray(runs.runs)) {
  throw new Error("Durable recovery history is not available");
}
if (!(events.headers.get("content-type") ?? "").includes("text/event-stream")) {
  throw new Error("The durable event replay endpoint is not serving SSE");
}

console.log(
  JSON.stringify(
    {
      airline: airlineHealth.status,
      eventReplay: "ok",
      flightCount: flights.items.length,
      runCount: runs.runs.length,
      runtime: runtimeHealth.status,
      web: "ok",
      worldId,
      worldRevision: world.revision,
    },
    null,
    2,
  ),
);
