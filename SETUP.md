# Local setup

## Requirements

- Node.js 24.x
- npm 11.x
- Python 3.12 for Python services
- uv 0.11.27
- Docker Desktop with the Linux engine

## Web foundation

```bash
npm install
npm run dev
```

Open `http://localhost:3000`.

The PR1 product pages intentionally show factual empty states until the airline and runtime APIs exist. They do not invent operational metrics or progress.

## Checks

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

Secrets will be documented when their integrations land. Do not commit `.env` files, model keys, Daytona keys, database URLs, or generated run artifacts.

## Live sponsor-stack compatibility gate

This gate runs TrueForge 0.1.4 in Linux with PostgreSQL and Redis. It configures the authenticated `gemini-3.5-flash-lite` model, discovers and calls the real MCP server, creates exactly three dynamic subagents, generates Python during the turn, runs it in a Daytona sandbox through Code Mode, proves that the consequential write pauses before PostgreSQL changes, approves it, reconnects with a durable sequence cursor, restarts TrueForge, and verifies the stored session, events, and idempotent write.

Copy `.env.example` to the ignored `.env.compatibility.local` file and set the two server-only credentials there:

```powershell
GEMINI_API_KEY=...
DAYTONA_API_KEY=...
```

The runner reads only those two names from that local file. Shell environment variables with the same names remain supported.

Then run:

```powershell
.\scripts\run-sponsor-compatibility.ps1
```

The proof writes only identifiers to `.airstrong/compatibility-state.json`, which is ignored by Git. It never commits model output, sandbox artifacts, credentials, or a generated Python file.
