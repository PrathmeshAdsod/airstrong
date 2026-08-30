# Airstrong

Airstrong checks an airline disruption, computes recovery candidates, tests each candidate against an operational twin, and asks before changing operations.

[Open Airstrong](https://airstrong.vercel.app) · [Setup](SETUP.md) · [Architecture](docs/architecture.md) · [Pull request trail](https://github.com/PrathmeshAdsod/airstrong/pulls?q=is%3Apr+is%3Amerged)

Aliens Airline, its operating day, and injected incidents are synthetic. The PostgreSQL state, APIs, TrueForge sessions, subagents, MCP calls, generated Python, Daytona sandbox, solver, digital twin, ranking, approval pause, writes, event replay, reset, and verification are real.

## Why it exists

An airline disruption rarely ends at one delayed flight. Aircraft rotations, crew duty, airport capacity, and passenger connections can propagate the impact through the network. A useful recovery system must understand the incident while leaving operational validity to deterministic rules.

Airstrong keeps those responsibilities separate:

- the TrueForge agent investigates the current incident, delegates factual reads, and formulates the computation;
- generated Python calls trusted OR-Tools-backed solver primitives inside Daytona;
- the airline service rebuilds every candidate and evaluates it in the authoritative digital twin;
- a versioned deterministic objective ranks valid candidates;
- a person must approve the exact stored actions before the consequential MCP tool can run.

## The real recovery flow

1. Trigger `Cyclone at BOM + aircraft unavailable` against the current PostgreSQL world.
2. Recalculate aircraft rotations, crew duties, passenger itineraries, and airport capacity.
3. Start one durable TrueForge root session and exactly three dynamic subagents: Aircraft, Crew, and Passenger.
4. Generate incident-specific Python during the run and execute it through TrueForge Code Mode in a short-lived Daytona sandbox.
5. Persist the generated artifact, hashes, strategy parameters, and solver-produced candidate actions.
6. Independently validate every candidate in the authoritative digital twin.
7. Rank valid candidates with the documented deterministic objective. Plan letters are display labels only.
8. Pause the consequential MCP tool until the stored action set is approved.
9. Apply the approved actions once, advance the world revision, reread affected state, and persist verification.

The runtime truthfully supports all candidates valid, some invalid, or no valid recovery. There is no expected winner, forced rejection, seeded candidate result, LLM-selected plan, static recovery fixture, or production fallback.

## Architecture

```text
Next.js on Vercel
  | REST + SSE
  v
Airline service on Railway <---- PostgreSQL
  ^          ^                       ^
  | MCP      | approved writes       | durable sessions
  |          |                       |
Agent runtime on Railway -------> TrueForge on Railway <---- Redis
                                      |
                                      +---- Gemini Flash-Lite
                                      +---- Daytona sandbox
```

TrueForge is load-bearing. It owns persistent sessions, Google Gemini provider access, the real airline MCP connection, dynamic subagents, Code Mode, Daytona execution, tool approval events, and approval continuation. Removing TrueForge stops the recovery workflow.

The airline backend remains authoritative for domain rules, candidate validation, deterministic ranking, operational writes, and post-write verification. The model cannot overrule it.

## Product

- **Live** shows the current operational world, propagated impact, a state-derived SVG network, durable event status, and current recovery state.
- **Runs** shows stored TrueForge, artifact, candidate, twin, ranking, approval, execution, and verification lineage.
- **Data** reads Flights, Aircraft, Crew, Passengers, Airports, and Disruptions from the authoritative service.
- **Simulations** exposes the working hero incident and an idempotent baseline reset.

## Safety and auditability

- generated code reads an immutable snapshot and cannot mutate live operations;
- every candidate stores its actions, parameters, snapshot hash, artifact hash, solver bundle hash, and engine versions;
- hard-rule violations always defeat a model claim;
- approval is tied to the plan hash, snapshot revision, and exact stored actions;
- world revision, approval ID, plan hash, action keys, and durable event sequence prevent duplicate work;
- verification rereads the authoritative database and checks that execution occurred once.

Public simplified operating assumptions are documented in [docs/domain-assumptions.md](docs/domain-assumptions.md). The ranking contract is documented in [docs/recovery-objective.md](docs/recovery-objective.md).

## Stack

- Next.js 16 and React 19
- Python 3.12, FastMCP, PostgreSQL, OR-Tools, and NetworkX
- TrueForge 0.1.4 with Google Gemini and Daytona
- Railway for the three application services, PostgreSQL, and Redis
- Vercel Hobby for the web application

## Run it locally

The shortest verified entry point is:

```powershell
npm ci
docker compose -f docker-compose.airline.yml up --build -d
Copy-Item .env.example .env.compatibility.local
# Add GEMINI_API_KEY and DAYTONA_API_KEY to the ignored file.
.\scripts\run-sponsor-compatibility.ps1
```

Continue with the runtime and web startup in [SETUP.md](SETUP.md). That guide also covers initialization, tests, production deployment, troubleshooting, cost controls, and the tested Railway pause/resume procedure.

## Verification and review

The repository is split into substantive pull requests for foundation, authoritative state, twin/ranking, APIs/events, TrueForge recovery, safety/execution, product UI, release hardening, and deployment fixes. CodeAnt, now part of Qodo's review workflow, reviewed the pull requests before merge; the public comments record the commit and review completion. GitHub Actions run application, airline-domain, and compatibility-MCP gates, and Vercel reports deployment status.

## Qodo Code Review Evidence

Qodo/CodeAnt was used throughout the substantive pull requests, with fixes and follow-up reviews for valid findings. [PR #5](https://github.com/PrathmeshAdsod/airstrong/pull/5) is the representative example. Qodo found that generated artifact hashes could be reused across execution lineages with incorrect provenance. We fixed this with execution-specific artifact lineage, stronger snapshot and revision locking and validation, added tests, and requested a follow-up review. The complete [merged pull request history](https://github.com/PrathmeshAdsod/airstrong/pulls?q=is%3Apr+is%3Amerged) preserves the broader review trail.

Release validation on 30 August 2026 completed two consecutive production hero runs. Both reached a real TrueForge approval pause, applied one approved execution, survived browser refresh, and passed authoritative verification. The Railway stop/redeploy drill then restored the same world, both run records, and both TrueForge session IDs from persistent storage.

No provider credential, `.env` file, local database, generated run artifact, browser dump, or temporary log belongs in this repository.
