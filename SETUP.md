# Local setup

## Requirements

- Node.js 24.x
- npm 11.x
- Python 3.11 or newer for the airline service in later PRs
- Docker Desktop for local integration services in later PRs

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
