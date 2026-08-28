# Airstrong

Airstrong checks an airline disruption, computes recovery candidates, tests every candidate against an operational twin, and asks before changing operations.

Aliens Airline, its operating day, and injected disruptions are synthetic. The PostgreSQL state, TrueForge agent work, three investigation subagents, MCP calls, generated Python, Daytona execution, OR-Tools candidates, twin validation, deterministic ranking, approval pause, operational writes, SSE resume, reset, and verification are real.

## The working hero flow

The production path is intentionally narrow and complete:

1. Trigger `Cyclone at BOM + aircraft unavailable` against the current world.
2. Recalculate aircraft rotations, crew duties, passenger itineraries, and airport capacity from PostgreSQL.
3. Start one durable TrueForge root session and exactly three dynamic subagents: Aircraft, Crew, and Passenger.
4. Generate incident-specific Python during the run and execute it in a short-lived Daytona sandbox through TrueForge Code Mode.
5. Store the generated artifact, hashes, strategy parameters, and solver-produced candidate actions.
6. Reconstruct and evaluate every action in the authoritative digital twin.
7. Rank valid candidates with the versioned deterministic objective. Plan letters are assigned only for display.
8. Pause the consequential MCP tool in TrueForge until a person approves the stored action set.
9. Apply the approved plan once, advance the world revision, re-read every affected record, and persist verification.

The runtime supports all candidates valid, some candidates invalid, or no valid recovery. It has no expected winner, expected rejection, static recovery fixture, or production fallback.

## Product

- **Live** shows the real operational world, propagated impact, custom SVG network, durable event cursor, and current recovery state.
- **Runs** shows stored TrueForge, artifact, candidate, twin, ranking, approval, execution, and verification lineage.
- **Data** reads Flights, Aircraft, Crew, Passengers, Airports, and Disruptions from the authoritative service.
- **Simulations** exposes only scenarios that actually work. The hero scenario is the current release target.

## Repository

- `apps/web`: Next.js landing page and product interface
- `services/agent-runtime`: TrueForge orchestration, evidence checks, reconnect, and approval continuation
- `services/airline`: authoritative PostgreSQL world, MCP/REST/SSE service, solver primitives, twin, and deterministic ranking
- `services/compatibility-mcp`: isolated sponsor-stack proof; never a recovery fallback
- `infra/trueforge`: pinned Linux TrueForge image and verified Gemini/Daytona catalogs

Read [SETUP.md](SETUP.md) for local and deployment instructions. The system boundaries are documented in [docs/architecture.md](docs/architecture.md); simplified public operating assumptions and ranking rules are in [docs/domain-assumptions.md](docs/domain-assumptions.md) and [docs/recovery-objective.md](docs/recovery-objective.md).

## Verification

```powershell
npm ci
npm run check
npm run build

Set-Location services/airline
$env:AIRSTRONG_TEST_DATABASE_URL = "postgresql://airstrong:local-airstrong-only@127.0.0.1:5434/airstrong"
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check src tests
uv run mypy src
```

The live sponsor gate and multi-trial model evaluation require real Gemini and Daytona credentials. They fail closed rather than substituting fixtures:

```powershell
.\scripts\run-sponsor-compatibility.ps1
npm run model:evaluate -- 3
```

Pull requests are reviewed by CodeAnt before merge. The review trail is preserved in the public [Airstrong pull requests](https://github.com/PrathmeshAdsod/airstrong/pulls?q=is%3Apr+is%3Aclosed).

## Safety and cost

Airstrong uses one configured Gemini model, bounded generation/repair, one judging-scale recovery at a time, durable idempotency keys, and Daytona auto-stop/archive/delete controls. The deployment keeps the web app, runtime, TrueForge, airline service, PostgreSQL, and Redis in their approved roles. It does not collapse services or replace persistence merely to fit a nominal free tier.

No `.env` file, provider credential, local database, generated run artifact, or browser dump belongs in the repository.
