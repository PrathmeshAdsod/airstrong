# Airstrong architecture

## Approved logical and deployment boundaries

The canonical deployment remains:

1. Next.js web application on Vercel.
2. Airstrong agent runtime and browser-facing API on Railway.
3. Private TrueForge service on Railway.
4. Python airline service on Railway, exposed to agents through MCP tools.
5. Railway Postgres for authoritative airline state and durable TrueForge state.
6. Railway Redis where required by TrueForge.
7. Daytona for short-lived generated-code sandboxes.
8. Google Gemini for the root agent and exactly three investigation subagents.

The airline company and operational dataset are synthetic. Database mutations, agent work, tool calls, generated code, sandbox execution, twin validation, approval, execution, event streaming, reconnect, reset, and verification must be real.

## Recovery boundary

```text
Airstrong runtime
  -> TrueForge root session
  -> Aircraft, Crew, and Passenger subagents
  -> read-only MCP investigation tools
  -> runtime-generated scenario Python
  -> Daytona execution against an immutable snapshot
  -> candidate actions
  -> authoritative digital twin validation
  -> deterministic ranking and factual replanning
  -> TrueForge approval pause
  -> idempotent MCP operational writes
  -> authoritative state re-read and verification
```

Generated code may call checked-in trusted solver primitives, but it never writes to the live airline state. Plan letters are presentation labels assigned only after candidates have been stored and ranked. They have no strategy or outcome semantics.

The PR5 sandbox contract keeps that boundary auditable. The generated Python reads the world and a hashed solver-library bundle through the airline MCP, materializes that bundle inside its session-scoped Daytona sandbox, and hashes its own exact source. It proposes incident-specific parameters and executes the pinned OR-Tools primitives. The airline service then reconstructs every returned action, verifies candidate, snapshot, solver, and artifact hashes, persists the source and TrueForge/Daytona lineage, and independently runs the twin and ranker. Untrusted model text cannot mark a candidate valid or recommended.

Parameter exploration is deterministic but outcome-neutral. It starts with the model's incident-specific proposals, derives bounded cancellation, delay, and substitution variants from the actual disruption duration and recovery scope, skips infeasible formulations, and keeps only distinct action sets. It does not require a rejected candidate, a valid candidate, or a predetermined winner. A run may truthfully produce all valid candidates, some invalid candidates, or no valid recovery.

Candidate generation, authoritative validation, and the versioned lexicographic objective are specified in [recovery-objective.md](recovery-objective.md). Solver weights create proposal diversity; they never replace the twin or select the recommendation.

## Safe usage controls

These controls preserve the approved architecture:

- one small Daytona sandbox per active recovery run;
- no Daytona warm pools;
- sandbox auto-stop, bounded wall-clock lifetime, and cleanup after stored results exist;
- one configured Gemini model with bounded calls, bounded repair attempts, compact tool results, and rate-limit backoff;
- no frontend polling for progress; durable server events drive the interface;
- conservative world, session, event, and generated-artifact retention;
- one judging-scale recovery run at a time unless testing proves a higher safe limit;
- idempotency keys and snapshot, world-revision, and plan hashes so retries never repeat work;
- no background work or keepalive traffic without a measured reliability need.

## Infrastructure change gate

Free-tier fit is a constraint to measure, not authority to collapse boundaries or replace services. Before any material change from the approved deployment, record:

1. the original architecture;
2. the proposed change;
3. the verified limitation requiring it;
4. compatibility evidence;
5. reliability implications;
6. added complexity;
7. estimated usage or cost.

Then obtain user approval.

The following are unapproved hypotheses until that gate is complete:

- combining the agent runtime, TrueForge, and airline service in one process or container;
- replacing Railway Postgres or Redis with Neon or Upstash;
- forcing a Next.js static export;
- assuming Railway Serverless can sleep while the actual runtime and connection pools are active.

If a critical component cannot run reliably within a free allowance, Airstrong will report the minimum expected cost before a paid service is enabled. It will not replace real execution with fixtures or scripted outcomes.

## Foundation compatibility boundary

PR1 includes an isolated sponsor-stack compatibility service. It performs a real PostgreSQL read and an idempotent write, but contains no airline recovery logic and cannot be used as a production fallback. Its only purpose is to fail closed unless TrueForge, Gemini, MCP, dynamic subagents, Daytona Code Mode, approval events, durable SSE resume, and persisted sessions work together on Linux.

The checked-in `model-catalog.yaml` adds the officially verified `gemini-3.5-flash-lite` identifier because TrueForge 0.1.4's shipped catalog predates that stable entry. It uses TrueForge's supported catalog override and does not modify TrueForge source.
