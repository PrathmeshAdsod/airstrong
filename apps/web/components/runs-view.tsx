"use client";

import { useState } from "react";

import {
  apiJson,
  formatClock,
  formatDuration,
  humanize,
  type RecoveryCandidate,
  type RecoveryRun,
  shortId,
} from "@/lib/airline";

import { ServiceState } from "./service-state";
import { useWorld } from "./world-provider";

type StageState = "complete" | "current" | "pending" | "failed";

function stageState(run: RecoveryRun, stage: string): StageState {
  if (run.status === "failed" && stage !== "Incident") return "failed";
  const completed: Record<string, boolean> = {
    Incident: true,
    Investigation: Boolean(run.investigationTurnId),
    Computation: Boolean(run.batchId),
    Validation: Boolean(run.batchId),
    Approval: ["approved", "consumed", "denied"].includes(
      run.approvalStatus ?? "",
    ),
    Execution: Boolean(run.executionId),
    Verification: run.verificationValid !== null,
  };
  if (completed[stage]) return "complete";
  const currentStage: Record<string, string[]> = {
    Investigation: ["investigating"],
    Computation: ["computing"],
    Validation: ["candidates_ranked", "no_valid_candidate"],
    Approval: ["awaiting_approval", "approved", "denied"],
    Execution: ["executing"],
    Verification: ["verifying"],
  };
  return (currentStage[stage] ?? []).includes(run.status)
    ? "current"
    : "pending";
}

function candidateLabel(index: number): string {
  return `Plan ${String.fromCharCode(65 + index)}`;
}

function orderedCandidates(
  candidates: RecoveryCandidate[],
): RecoveryCandidate[] {
  return [...candidates].sort((left, right) => {
    if (left.rank === null && right.rank !== null) return 1;
    if (left.rank !== null && right.rank === null) return -1;
    if (left.rank !== null && right.rank !== null)
      return left.rank - right.rank;
    return left.candidateId.localeCompare(right.candidateId);
  });
}

function failureDetail(run: RecoveryRun): string | null {
  if (!run.failure) return null;
  if (typeof run.failure === "string") return run.failure;
  return run.failure.detail ?? JSON.stringify(run.failure);
}

export function RunsView() {
  const { world, runs, recoveryBatch, loading, error, refresh } = useWorld();
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null);
  const [deciding, setDeciding] = useState(false);
  const [decisionError, setDecisionError] = useState<string | null>(null);

  const selectedRun =
    runs.find((run) => run.runId === selectedRunId) ?? runs[0] ?? null;
  const candidates =
    selectedRun?.batchId && recoveryBatch?.batchId === selectedRun.batchId
      ? orderedCandidates(recoveryBatch.candidates)
      : [];

  if (loading) {
    return (
      <ServiceState
        title="Reading durable recovery runs"
        detail="Run state is being restored from PostgreSQL, not reconstructed in the browser."
      />
    );
  }
  if (error || !world) {
    return (
      <ServiceState
        tone="error"
        title="Run history is unavailable"
        detail={error ?? "The authoritative world could not be read."}
      />
    );
  }
  if (!selectedRun) {
    return (
      <ServiceState
        title="No recovery run exists"
        detail="Start the working hero scenario. A run appears here only after the runtime stores it."
      />
    );
  }

  const stages = [
    ["Incident", "World revision captured"],
    ["Investigation", "Three TrueForge subagents"],
    ["Computation", "Generated Python in Daytona"],
    ["Validation", "Authoritative twin and ranking"],
    ["Approval", "Consequential write paused"],
    ["Execution", "Approved MCP actions"],
    ["Verification", "Authoritative state re-read"],
  ] as const;
  const awaitingHuman =
    selectedRun.status === "awaiting_approval" &&
    selectedRun.approvalStatus === "pending" &&
    Boolean(selectedRun.trueforgeToolCallId);

  async function decide(decision: "approved" | "denied") {
    if (!awaitingHuman || deciding) return;
    setDeciding(true);
    setDecisionError(null);
    const storageKey = `airstrong:decision-key:${selectedRun.runId}:${decision}`;
    const idempotencyKey =
      window.sessionStorage.getItem(storageKey) ?? crypto.randomUUID();
    window.sessionStorage.setItem(storageKey, idempotencyKey);
    try {
      await apiJson<{ run: RecoveryRun }>(
        `/api/runtime/api/recovery/runs/${selectedRun.runId}/decision`,
        {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "Idempotency-Key": idempotencyKey,
          },
          body: JSON.stringify({ decision, idempotencyKey }),
        },
      );
      await refresh();
    } catch (requestError) {
      setDecisionError(
        requestError instanceof Error
          ? requestError.message
          : "Decision failed.",
      );
    } finally {
      setDeciding(false);
    }
  }

  return (
    <div className="runs-layout">
      <aside className="run-index" aria-label="Recovery runs">
        <div className="run-index__summary">
          <span>{runs.length} stored</span>
          <strong>World revision {world.revision}</strong>
        </div>
        {runs.map((run, index) => (
          <button
            className={run.runId === selectedRun.runId ? "is-selected" : ""}
            key={run.runId}
            onClick={() => setSelectedRunId(run.runId)}
            type="button"
          >
            <span>Run {String(runs.length - index).padStart(2, "0")}</span>
            <strong>{humanize(run.status)}</strong>
            <small>{formatClock(run.createdAt)}</small>
          </button>
        ))}
      </aside>

      <section className="run-record">
        <header className="run-record__header">
          <div>
            <p>
              Run {shortId(selectedRun.runId)} · revision{" "}
              {selectedRun.startedWorldRevision}
            </p>
            <h2>Cyclone at BOM + aircraft unavailable</h2>
          </div>
          <span className={`status-pill status-pill--${selectedRun.status}`}>
            {humanize(selectedRun.status)}
          </span>
        </header>

        {failureDetail(selectedRun) ? (
          <div className="run-failure" role="alert">
            <strong>Recovery stopped factually</strong>
            <p>{failureDetail(selectedRun)}</p>
          </div>
        ) : null}

        <ol className="run-stages">
          {stages.map(([name, detail], index) => {
            const state = stageState(selectedRun, name);
            return (
              <li className={`run-stage run-stage--${state}`} key={name}>
                <span>{String(index + 1).padStart(2, "0")}</span>
                <div>
                  <strong>{name}</strong>
                  <small>{detail}</small>
                </div>
                <em>{humanize(state)}</em>
              </li>
            );
          })}
        </ol>

        {candidates.length ? (
          <section className="candidate-section">
            <div className="section-row-heading">
              <div>
                <p>Twin evaluation</p>
                <h3>{candidates.length} stored candidates</h3>
              </div>
              <span>{recoveryBatch?.rankingVersion}</span>
            </div>
            <div className="candidate-grid">
              {candidates.map((candidate, index) => (
                <article
                  className={`candidate-card ${candidate.recommended ? "candidate-card--recommended" : ""} ${!candidate.valid ? "candidate-card--invalid" : ""}`}
                  key={candidate.candidateId}
                >
                  <div className="candidate-card__heading">
                    <div>
                      <span>{candidateLabel(index)}</span>
                      <small>ID {shortId(candidate.candidateId)}</small>
                    </div>
                    <strong>
                      {candidate.recommended
                        ? "Recommended"
                        : candidate.valid
                          ? `Rank ${candidate.rank}`
                          : "Rejected by twin"}
                    </strong>
                  </div>
                  <dl>
                    <div>
                      <dt>Cancellations</dt>
                      <dd>{candidate.metrics.cancellations}</dd>
                    </div>
                    <div>
                      <dt>Passengers</dt>
                      <dd>{candidate.metrics.disruptedPassengers}</dd>
                    </div>
                    <div>
                      <dt>Total delay</dt>
                      <dd>
                        {formatDuration(candidate.metrics.totalDelayMinutes)}
                      </dd>
                    </div>
                    <div>
                      <dt>Reassignments</dt>
                      <dd>{candidate.metrics.operationalReassignments}</dd>
                    </div>
                  </dl>
                  <details>
                    <summary>
                      {candidate.actions.length} computed actions
                    </summary>
                    <ul>
                      {candidate.actions.map((action, actionIndex) => (
                        <li
                          key={`${action.actionType}-${action.flightId}-${actionIndex}`}
                        >
                          <strong>{humanize(action.actionType)}</strong>
                          <span>
                            {action.flightId}
                            {action.aircraftId ? ` · ${action.aircraftId}` : ""}
                          </span>
                        </li>
                      ))}
                    </ul>
                  </details>
                  {candidate.violations.length ? (
                    <div className="candidate-card__violation">
                      <strong>{candidate.violations[0]!.code}</strong>
                      <p>{candidate.violations[0]!.message}</p>
                    </div>
                  ) : null}
                </article>
              ))}
            </div>
          </section>
        ) : null}

        {selectedRun.approvalId ? (
          <section
            className={`approval-panel ${awaitingHuman ? "approval-panel--ready" : ""}`}
          >
            <div className="approval-panel__copy">
              <p>Human approval</p>
              <h3>
                {awaitingHuman
                  ? "Ready to apply the ranked recovery"
                  : selectedRun.verificationValid
                    ? "Recovery applied and verified"
                    : `Approval ${humanize(selectedRun.approvalStatus ?? "pending")}`}
              </h3>
              <p>
                {awaitingHuman
                  ? "These counts come from the stored recommended candidate. No operational write has run yet."
                  : `Plan hash ${shortId(selectedRun.planHash)} · ${selectedRun.approvalActions?.length ?? 0} stored actions.`}
              </p>
            </div>
            <dl className="approval-summary">
              {Object.entries(selectedRun.approvalSummary ?? {}).map(
                ([key, value]) => (
                  <div key={key}>
                    <dt>{humanize(key)}</dt>
                    <dd>{value}</dd>
                  </div>
                ),
              )}
            </dl>
            {awaitingHuman ? (
              <div className="approval-actions">
                <button
                  className="button button--quiet"
                  disabled={deciding}
                  onClick={() => void decide("denied")}
                  type="button"
                >
                  Deny
                </button>
                <button
                  className="button button--consequential"
                  disabled={deciding}
                  onClick={() => void decide("approved")}
                  type="button"
                >
                  {deciding ? "Submitting decision" : "Apply recovery"}
                </button>
              </div>
            ) : null}
            {decisionError ? (
              <p className="form-error" role="alert">
                {decisionError}
              </p>
            ) : null}
          </section>
        ) : null}

        <footer className="run-lineage">
          <span>Snapshot {shortId(selectedRun.snapshotHash)}</span>
          <span>
            TrueForge session {shortId(selectedRun.trueforgeSessionId)}
          </span>
          <span>Batch {shortId(selectedRun.batchId)}</span>
          <span>Verification {shortId(selectedRun.verificationId)}</span>
        </footer>
      </section>
    </div>
  );
}
