# Airstrong

Airstrong checks an airline disruption, tests recovery plans against an operational twin, and asks before changing the synthetic airline world.

The product is under active construction. The fictional airline and its data are synthetic; tool calls, generated computation, validation, approval, execution, and verification are real.

## Workspace

- `apps/web`: Next.js landing page and product interface
- `services/agent-runtime`: TrueForge integration runtime and live compatibility gate
- `services/airline`: authoritative PostgreSQL world, versioned baseline, and deterministic dependency engine
- `services/compatibility-mcp`: isolated real MCP/PostgreSQL sponsor-stack probe
- `packages/contracts`: shared API and event contracts, added in a later PR

Run the current web foundation:

```bash
npm install
npm run dev
```

See [SETUP.md](SETUP.md) for local requirements and [docs/architecture.md](docs/architecture.md) for the approved system boundaries.

The sponsor compatibility proof is deliberately separate from the airline domain. It verifies the real provider path without introducing recovery candidates, expected outcomes, or production fallbacks.

The airline domain currently seeds a small, coherent Aliens Airline operating day. The hero mutation writes a BOM capacity restriction and one aircraft unavailability to PostgreSQL, then recalculates affected rotations, crew, and passenger itineraries from that state. See [docs/domain-assumptions.md](docs/domain-assumptions.md) for the public grounding and explicit simplifications.

The same authoritative service exposes data-backed REST routes, durable SSE replay, and read-only investigation tools over Streamable HTTP MCP. Its container remains separate from the Airstrong runtime and TrueForge.
