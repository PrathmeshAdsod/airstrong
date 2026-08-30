# Airstrong setup

This guide reproduces the local development stack and the approved production topology. Commands use PowerShell on Windows with Docker Desktop running Linux containers.

## Prerequisites

- Git
- Node.js 24.x and npm 11.x
- Python 3.12
- uv 0.11.27
- Docker Desktop with Linux containers and Docker Compose
- a Google Gemini API key authorized for the model in `infra/trueforge/model-catalog.yaml`
- a Daytona API key
- Railway CLI and Vercel CLI for production deployment only

Check the main tools:

```powershell
node --version
npm --version
python --version
uv --version
docker version
docker compose version
```

## Clone and install

```powershell
git clone https://github.com/PrathmeshAdsod/airstrong.git
Set-Location airstrong
npm ci
```

Create the ignored provider file:

```powershell
Copy-Item .env.example .env.compatibility.local
```

Set only these values in `.env.compatibility.local`:

```dotenv
GEMINI_API_KEY=replace-with-your-key
DAYTONA_API_KEY=replace-with-your-key
```

Never put secrets in `NEXT_PUBLIC_*` variables. Never commit an `.env` file.

## Start the authoritative airline world

Build and start PostgreSQL and the airline service:

```powershell
docker compose -f docker-compose.airline.yml up --build -d
docker compose -f docker-compose.airline.yml ps
```

The airline startup applies its versioned migrations and creates the default Aliens Airline world once. Verify it:

```powershell
Invoke-RestMethod http://127.0.0.1:4200/health
Invoke-RestMethod http://127.0.0.1:4200/api/worlds/default
```

The local database is available at `127.0.0.1:5434`. Its credentials are development-only values from `docker-compose.airline.yml`.

## Start TrueForge and prove the sponsor stack

Run the Linux compatibility proof:

```powershell
.\scripts\run-sponsor-compatibility.ps1
```

This starts TrueForge 0.1.4, PostgreSQL, Redis, and an isolated compatibility MCP. It then exercises the configured Gemini model, real MCP discovery/calls, exactly three dynamic subagents, runtime-generated Python, TrueForge Code Mode, Daytona, a real tool approval pause, durable event replay, service restart, and session persistence.

The proof fails closed. It never substitutes a fixture or static result. It writes only non-secret identifiers to the ignored `.airstrong/compatibility-state.json` file.

Verify TrueForge:

```powershell
Invoke-RestMethod http://127.0.0.1:8790/healthz
```

Native Windows startup is not the supported path. TrueForge 0.1.4 has a Windows ESM path issue; use the pinned Linux container instead of patching the dependency.

## Start the recovery runtime

Load `GEMINI_API_KEY` and `DAYTONA_API_KEY` from the ignored file into the current PowerShell process. Then set the non-secret local endpoints and shared development token:

```powershell
$env:AIRSTRONG_RUNTIME_TOKEN = "local-runtime-token-only"
$env:AIRSTRONG_AIRLINE_BASE_URL = "http://127.0.0.1:4200"
$env:AIRSTRONG_AIRLINE_MCP_URL = "http://host.docker.internal:4200/mcp"
$env:TRUEFORGE_BASE_URL = "http://127.0.0.1:8790"
npm run dev:runtime
```

The runtime health endpoint is `http://127.0.0.1:4300/health`.

## Start the web application

In another terminal:

```powershell
npm run dev
```

Open `http://localhost:3000`. Use:

- `/live` for the current network and SSE state;
- `/runs` for durable recovery lineage;
- `/data` for authoritative operational records;
- `/simulations` to start or reset the hero scenario.

## Trigger, approve, reset, and resume

The browser stores stable idempotency keys. Refreshing does not create another scenario, run, approval, or execution.

The same recovery flow is available from the runtime commands:

```powershell
npm run recovery:run -- <world-id>
npm run recovery:decide -- <run-id> approve <decision-idempotency-key>
```

Use `deny` instead of `approve` to reject the exact stored plan. The decision continues the persisted TrueForge tool call. Replaying the same key returns the existing result.

To reset the synthetic world through REST:

```powershell
$world = Invoke-RestMethod http://127.0.0.1:4200/api/worlds/default
$resetKey = [guid]::NewGuid().ToString()
Invoke-RestMethod "http://127.0.0.1:4200/api/worlds/$($world.worldId)/reset" `
  -Method Post `
  -Headers @{ "Idempotency-Key" = $resetKey }
```

Reset is a real database mutation. Historical run records remain available for audit.

## Test the repository

Run the Node checks from the repository root:

```powershell
npm run format:check
npm run check
npm run build
```

With `docker-compose.airline.yml` running, test the airline service:

```powershell
Set-Location services/airline
$env:UV_LINK_MODE = "copy"
$env:AIRSTRONG_TEST_DATABASE_URL = "postgresql://airstrong:local-airstrong-only@127.0.0.1:5434/airstrong"
uv sync --frozen
uv run pytest
uv run ruff check .
uv run ruff format --check src tests
uv run mypy src
Set-Location ../..
```

The integration suite creates isolated worlds, mutates PostgreSQL, exercises REST/MCP/SSE, verifies event cursor catch-up, evaluates generated candidates, enforces approval, executes stored actions, checks idempotency, and removes its test worlds.

Before changing the production model, run more than one representative real trial:

```powershell
npm run model:evaluate -- 3
```

Each trial creates an isolated synthetic world and runs the real three-subagent, generated-code, Daytona, twin, and approval path. It confirms no operational write happens at the pause and denies the stored plan. Results are printed for private development review and are not committed.

## Production topology

The approved topology is fixed:

1. Next.js on Vercel Hobby.
2. `airline`, `trueforge`, and `agent-runtime` as three separate Railway services.
3. Railway PostgreSQL for authoritative airline state and TrueForge sessions.
4. Railway Redis for TrueForge coordination.
5. Daytona for short-lived generated-code sandboxes.
6. Gemini for the root and exactly three investigation subagents.

Do not combine services, expose TrueForge, replace PostgreSQL/Redis, or force a static export for cost alone.

## Deploy the five Railway resources

Authenticate and create one project:

```powershell
railway login
railway init --name airstrong --workspace <workspace-id> --json
railway add --database postgres --json
railway add --database redis --json
railway add --service airline --json
railway add --service trueforge --json
railway add --service agent-runtime --json
```

Keep one replica for each service. Leave App Sleeping off until TrueForge session continuity, SSE, and database connections pass a measured cold-start test.

### Railway variables

Use Railway reference variables for private dependencies.

**airline**

```text
AIRSTRONG_DATABASE_URL=${{Postgres.DATABASE_URL}}
AIRSTRONG_RUNTIME_TOKEN=<long-random-secret-shared-with-runtime>
AIRSTRONG_WEB_ORIGINS=https://<vercel-production-domain>
HOST=0.0.0.0
PORT=4200
```

**trueforge**

```text
STANDALONE=false
POSTGRES_HOST=${{Postgres.PGHOST}}
POSTGRES_PORT=${{Postgres.PGPORT}}
POSTGRES_USER=${{Postgres.PGUSER}}
POSTGRES_PASSWORD=${{Postgres.PGPASSWORD}}
POSTGRES_DB=${{Postgres.PGDATABASE}}
REDIS_URL=${{Redis.REDIS_URL}}
MODEL_CATALOG_PATH=/app/catalog/model-catalog.yaml
SANDBOX_CATALOG_PATH=/app/catalog/sandbox-catalog.yaml
HOST=0.0.0.0
PORT=8790
PUBLIC_BASE_URL=http://trueforge.railway.internal:8790
```

**agent-runtime**

```text
AIRSTRONG_AIRLINE_BASE_URL=http://airline.railway.internal:4200
AIRSTRONG_AIRLINE_MCP_URL=http://airline.railway.internal:4200/mcp
AIRSTRONG_RUNTIME_TOKEN=<same-secret-as-airline>
TRUEFORGE_BASE_URL=http://trueforge.railway.internal:8790
GEMINI_API_KEY=<secret>
DAYTONA_API_KEY=<secret>
AIRSTRONG_WEB_ORIGINS=https://<vercel-production-domain>
PORT=4300
RAILWAY_DOCKERFILE_PATH=services/agent-runtime/Dockerfile
```

Use `railway variable set <KEY> --stdin --skip-deploys` for secrets so values do not appear in shell history. Do not print `railway variable list --json`; it includes raw values.

### Deploy application sources

The production-verified CLI deployment is:

```powershell
railway up services/airline --path-as-root --service airline --environment production --detach
railway up infra/trueforge --path-as-root --service trueforge --environment production --detach
railway up --service agent-runtime --environment production --detach
```

The equivalent GitHub configuration uses `/services/airline` as the airline root, `/infra/trueforge` as the TrueForge root, and the repository root plus `/services/agent-runtime/Dockerfile` for the runtime.

Generate public domains only for airline and runtime:

```powershell
railway domain --service airline --port 4200 --json
railway domain --service agent-runtime --port 4300 --json
```

TrueForge, PostgreSQL, and Redis must have no public domain.

## Deploy Vercel

Link the repository to a Vercel project. `vercel.json` selects `apps/web` and routes public traffic to that single web service without using static export.

Set these production variables:

```text
AIRSTRONG_AIRLINE_BASE_URL=https://<airline-public-domain>
AIRSTRONG_RUNTIME_BASE_URL=https://<runtime-public-domain>
NEXT_PUBLIC_AIRSTRONG_EVENTS_BASE_URL=https://<airline-public-domain>
NEXT_PUBLIC_GITHUB_URL=https://github.com/PrathmeshAdsod/airstrong
```

Redeploy after changing `NEXT_PUBLIC_*` values because they are embedded in the client build.

## Production smoke check

```powershell
$env:AIRSTRONG_WEB_URL = "https://<vercel-production-domain>"
$env:AIRSTRONG_AIRLINE_BASE_URL = "https://<airline-public-domain>"
$env:AIRSTRONG_RUNTIME_BASE_URL = "https://<runtime-public-domain>"
npm run release:smoke
```

The read-only smoke verifies the web app, both public health endpoints, authoritative world/snapshot identity, `ALN-####` flight records, durable runs, and SSE replay content type.

Then run the hero twice. For each run verify:

- exactly three TrueForge subagents and one stored session;
- a runtime-generated artifact and Daytona sandbox lineage;
- three stored solver candidates, with factual twin results;
- no world write before approval;
- the approval tool is paused with exact stored actions;
- one approved execution and a higher world revision;
- authoritative verification is valid;
- replaying start and approval keys does not execute twice;
- browser refresh restores the same run and stage.

## Railway cost controls

Railway Hobby includes the first $5 of workspace resource usage. It is still usage-based, so inspect both workspace and service totals:

```powershell
railway usage --workspace <workspace-id> --json
railway usage projects --project <project-id> --json
```

Set the native $5 compute email alert and disable Railway Agent spend:

```powershell
railway usage limit set --target workspace --soft 5 --workspace <workspace-id> --json
railway usage limit set --target agent --hard 0 --workspace <workspace-id> --json
railway usage limit status --workspace <workspace-id> --json
```

Do not configure Railway Agent, increase limits, or upgrade plans automatically. Keep Daytona auto-stop at 5 minutes, auto-archive at 30 minutes, auto-delete at 120 minutes, and judging concurrency low.

## Tested Railway pause and resume

Removing an active deployment stops its compute without deleting the service, variables, domain, project, or volume. Do not use `railway service delete`, `railway project delete`, `railway volume delete`, or Wipe Volume.

Stop in this order so no writer outlives its dependencies:

```powershell
railway down --service agent-runtime --environment production --yes
railway down --service airline --environment production --yes
railway down --service trueforge --environment production --yes
railway down --service Redis --environment production --yes
railway down --service Postgres --environment production --yes
```

If a repeated command reports `No deployments found`, that service is already stopped. Confirm all deployment IDs are empty and both volumes remain `Ready`:

```powershell
railway service list --json
railway volume list --json
```

Restart in dependency order, waiting for `SUCCESS` after each command:

```powershell
railway redeploy --service Postgres --environment production --from-source --yes --json
railway redeploy --service Redis --environment production --from-source --yes --json
railway redeploy --service trueforge --environment production --from-source --yes --json
railway redeploy --service airline --environment production --from-source --yes --json
railway redeploy --service agent-runtime --environment production --from-source --yes --json
```

After restart, run `npm run release:smoke` and confirm the previous world revision, run records, TrueForge session IDs, and verification records are still present. This procedure was exercised against the production project on 30 August 2026 with both PostgreSQL and Redis volumes preserved.

## Troubleshooting

**TrueForge fails on native Windows**

Use `infra/trueforge/Dockerfile`. Do not patch TrueForge to work around the Windows ESM path issue.

**Runtime health is OK but recovery fails immediately**

Check the private `AIRSTRONG_AIRLINE_BASE_URL`, MCP URL, TrueForge URL, shared runtime token, and provider credentials. Inspect service logs without printing variables.

**A run becomes stale**

The world revision changed after the snapshot or approval. This is intentional. Reset or recompute from the current world; never force the old plan.

**Generated code fails after the bounded repair**

The run must end in a factual failed state. There is no production fixture fallback.

**No valid candidate exists**

The run must report that result. Do not bypass hard constraints or fabricate a plan.

**The browser stream reconnects**

The client resumes from its last durable event sequence. Verify the airline domain is reachable and that the exact Vercel origin is present in `AIRSTRONG_WEB_ORIGINS`.

**Vercel builds but public pages return 404**

Keep the top-level `/(.*)` rewrite in `vercel.json`; Vercel Services remain internal until the selected web service is exposed by that route.

**Railway usage values differ briefly between workspace and project views**

Usage aggregation can update at different times. Record both outputs with their billing-period timestamps and recheck before making a cost claim.
