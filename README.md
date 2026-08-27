# Airstrong

Airstrong checks an airline disruption, tests recovery plans against an operational twin, and asks before changing the synthetic airline world.

The product is under active construction. The fictional airline and its data are synthetic; tool calls, generated computation, validation, approval, execution, and verification are real.

## Workspace

- `apps/web`: Next.js landing page and product interface
- `services/agent-runtime`: Airstrong workflow runtime, added in a later PR
- `services/airline`: authoritative synthetic airline service, added in a later PR
- `packages/contracts`: shared API and event contracts, added in a later PR

Run the current web foundation:

```bash
npm install
npm run dev
```

See [SETUP.md](SETUP.md) for local requirements and [docs/architecture.md](docs/architecture.md) for the approved system boundaries.
