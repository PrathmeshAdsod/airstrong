# Airstrong setup

## Requirements

- Node.js 24.x and npm 11.x
- Python 3.12 and uv 0.11.27
- Docker Desktop using Linux containers
- a Google Gemini API key authorized for the configured Flash-Lite model
- a Daytona API key

Copy `.env.example` to the ignored `.env.compatibility.local` file and set only:

```powershell
GEMINI_API_KEY=...
DAYTONA_API_KEY=...
```

Do not place credentials in `NEXT_PUBLIC_*` variables or commit any `.env` file.

## Local services

Install the Node workspaces:

```powershell
npm ci
```

Start the authoritative airline service and its PostgreSQL database:

```powershell
docker compose -f docker-compose.airline.yml up --build -d
```

Start the Linux TrueForge compatibility stack with PostgreSQL, Redis, and the isolated MCP probe:

```powershell
.\scripts\run-sponsor-compatibility.ps1
```

That proof uses real TrueForge, the configured Gemini model, MCP discovery/calls, exactly three dynamic subagents, runtime-generated Python, Daytona Code Mode, a genuine tool approval pause, durable event resume, service restart, and stored-session verification. It writes only non-secret identifiers to the ignored `.airstrong/compatibility-state.json` file.

Start the recovery runtime after loading the two provider credentials into the process environment:

```powershell
$env:AIRSTRONG_RUNTIME_TOKEN = "local-runtime-token-only"
$env:AIRSTRONG_AIRLINE_BASE_URL = "http://127.0.0.1:4200"
$env:AIRSTRONG_AIRLINE_MCP_URL = "http://host.docker.internal:4200/mcp"
$env:TRUEFORGE_BASE_URL = "http://127.0.0.1:8790"
npm run dev:runtime
```

In another terminal, start the web app:

```powershell
npm run dev
```

Open `http://localhost:3000`. The service health endpoints are:

- airline: `http://127.0.0.1:4200/health`
- runtime: `http://127.0.0.1:4300/health`
- TrueForge: `http://127.0.0.1:8790/healthz`

## Real recovery flow

Use the Simulations page to trigger the hero scenario and follow the run. The browser uses stable idempotency keys, so refresh does not trigger another scenario, run, approval, or execution.

The same flow is available from the runtime commands:

```powershell
npm run recovery:run -- <world-id>
npm run recovery:decide -- <run-id> approve <decision-idempotency-key>
```

Use `deny` instead of `approve` to reject the stored plan. The approval command continues the exact persisted TrueForge tool call. Replays return the existing terminal result.

## Checks

```powershell
npm run check
npm run build

Set-Location services/airline
$env:UV_LINK_MODE = "copy"
$env:AIRSTRONG_TEST_DATABASE_URL = "postgresql://airstrong:local-airstrong-only@127.0.0.1:5434/airstrong"
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check src tests
uv run mypy src
```

The airline integration tests create isolated worlds, mutate the actual database, exercise REST/MCP/SSE, validate cursor resume and missed-notification catch-up, execute and verify stored actions, replay idempotency keys, and remove their test worlds.

Run the same representative agent recovery more than once before changing the configured production model:

```powershell
npm run model:evaluate -- 3
```

Each trial creates an isolated synthetic world, executes the real three-subagent/generated-code/Daytona/twin path, confirms that no operational write occurs at the approval pause, and denies the plan. Trial starts are spaced to respect the verified development RPM limit. Results are printed for private development review and are not written to the repository.

## Approved deployment

The release topology remains separate:

1. Next.js on Vercel Hobby.
2. Airline service, agent runtime, and TrueForge as separate Railway services.
3. Railway PostgreSQL for airline and TrueForge durability.
4. Railway Redis for TrueForge coordination.
5. Daytona for short-lived generated-code sandboxes.
6. Gemini for the root and exactly three investigation subagents.

### Railway

Create one Railway project with PostgreSQL and Redis, then connect the public GitHub repository to three services:

| Service         | Source/build                                                     | Public network | Health path |
| --------------- | ---------------------------------------------------------------- | -------------- | ----------- |
| `airline`       | root directory `/services/airline`                               | yes            | `/health`   |
| `trueforge`     | root directory `/infra/trueforge`                                | no             | `/healthz`  |
| `agent-runtime` | repository root, Dockerfile `/services/agent-runtime/Dockerfile` | yes            | `/health`   |

Use Railway private networking between services. Keep one replica for judging and do not enable Serverless/App Sleeping until the actual TrueForge, SSE, and database connection behavior has passed a cold-start test. Railway documents that outbound traffic and persistent database connections can prevent sleeping and that the first wake request may return 502.

Required variables by service:

**airline**

- `AIRSTRONG_DATABASE_URL`: Railway PostgreSQL connection URL
- `AIRSTRONG_RUNTIME_TOKEN`: long random secret shared only with the runtime
- `AIRSTRONG_WEB_ORIGINS`: final Vercel production origin
- `HOST=0.0.0.0`

**trueforge**

- `STANDALONE=false`
- Railway PostgreSQL `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, and `POSTGRES_DB`
- Railway Redis `REDIS_URL`
- `MODEL_CATALOG_PATH=/app/catalog/model-catalog.yaml`
- `SANDBOX_CATALOG_PATH=/app/catalog/sandbox-catalog.yaml`
- `HOST=0.0.0.0`
- `PUBLIC_BASE_URL`: the TrueForge private service URL

**agent-runtime**

- `AIRSTRONG_AIRLINE_BASE_URL`: airline private service URL
- `AIRSTRONG_AIRLINE_MCP_URL`: airline private service URL plus `/mcp`
- `AIRSTRONG_RUNTIME_TOKEN`: the same secret as the airline service
- `TRUEFORGE_BASE_URL`: TrueForge private service URL
- `GEMINI_API_KEY`
- `DAYTONA_API_KEY`
- `AIRSTRONG_WEB_ORIGINS`: final Vercel production origin

PostgreSQL and Redis remain separate infrastructure services. Do not replace them, expose TrueForge publicly, or combine the three application processes to save a small amount of credit without a reviewed architecture change.

### Vercel

Import the repository as one Vercel project. The checked-in `vercel.json` selects only `apps/web` as the Vercel service and routes public traffic to it with an explicit catch-all rewrite. It does not force a static export.

Set these server-side production variables:

- `AIRSTRONG_AIRLINE_BASE_URL`: public Railway airline URL
- `AIRSTRONG_RUNTIME_BASE_URL`: public Railway runtime URL
- `NEXT_PUBLIC_AIRSTRONG_EVENTS_BASE_URL`: public Railway airline URL so browser SSE does not consume a long-lived Vercel function

Set `NEXT_PUBLIC_GITHUB_URL=https://github.com/PrathmeshAdsod/airstrong`. After Vercel assigns the production URL, add that exact origin to `AIRSTRONG_WEB_ORIGINS` on the airline and runtime services.

### Release smoke check

```powershell
$env:AIRSTRONG_WEB_URL = "https://<vercel-production-domain>"
$env:AIRSTRONG_AIRLINE_BASE_URL = "https://<airline-public-domain>"
$env:AIRSTRONG_RUNTIME_BASE_URL = "https://<runtime-public-domain>"
npm run release:smoke
```

The smoke check is read-only. It verifies the web app, both public health endpoints, authoritative world/snapshot identity, ALN flight records, durable run history, and SSE replay content type.

Railway's current trial is a one-time $5 credit for up to 30 days, followed by a Free plan with $1 monthly credit. Measure actual service usage. If the approved runtime cannot remain reliable inside that allowance, report the minimum expected charge before enabling a paid plan; do not degrade or fake the product.
