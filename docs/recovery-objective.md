# Recovery candidates, twin validation, and ranking

Airstrong separates proposal from authority.

## Candidate generation

The recovery solver accepts an immutable world snapshot, a generated-artifact hash, the affected flight scope discovered from that snapshot, and explicit strategy parameters. Those parameters can vary cancellation tolerance, maximum delay, aircraft substitution, passenger preservation, operational churn, and recovery speed.

The strategy identifier is audit metadata only. It has no connection to a UI letter, outcome, or expected ranking. If two parameter sets produce the same actions, the batch is rejected for insufficient diversity rather than relabelled.

OR-Tools CP-SAT solves each parameter set using integer time slots, deterministic single-worker search, a fixed random seed, aircraft availability, connected rotation timing, and airport-capacity movement limits. The result is a stored set of cancellation, retiming, and aircraft-reassignment actions. CP-SAT's objective helps create meaningfully different candidates. It does not decide which candidate Airstrong recommends.

## Authoritative twin

The backend twin applies every candidate independently to a fresh copy of the same snapshot. It validates:

- snapshot identity and action references;
- aircraft availability, type, location, turnaround, and downstream rotation;
- active airport capacity restrictions;
- crew qualification, duty window, overlap, configured duty limit, and preceding rest;
- passenger seat capacity and configured connection windows.

The twin version, factual metrics, and complete violations are stored with the candidate. A model explanation cannot override them. A rejected candidate becomes structured replanning input containing the violation code, entity, message, and measured facts.

## Deterministic ranking

`ranking-1.0.0` first excludes every candidate with a hard violation. Remaining candidates are compared lexicographically by:

1. cancellations;
2. disrupted passengers;
3. total delay minutes;
4. aircraft reassignments;
5. stabilization minutes;
6. candidate content hash as a deterministic tie-breaker.

This order treats cancellation as the strongest network-level service loss, then minimizes the people disrupted among equally continuous schedules. Delay, operational churn, and recovery time break later ties. It is intentionally not a weighted score: a lower-priority improvement cannot compensate for a higher-priority regression. Changing this policy requires a ranking-version change and new evaluation evidence.

The best valid candidate is the first item after this sort. Plan A, B, or C may later be assigned as presentation labels only after storage and ranking.
