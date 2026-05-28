# ADR-006 — Lane Discipline and Artifact Ownership

**Status:** Accepted (2026-04-26 via PR #34 merge; Michael approved merge after ChatGPT re-review)
**Author:** Cowork architect (Claude.ai)
**Reviewer:** ChatGPT
**Decider:** Michael

---

## Context

`docs/COLLAB.md` (PR #33, merged 2026-04-26) is the team's operating-model doc. It defines roles, authority ladder, decision surfaces, claim discipline, disagreement protocol, security-review checklist, safety-freeze rule, verification posture, and coordination hazards.

ADR-005 (canonical voice path) elevated ChatGPT to the independent-reviewer / governance / second-architect role.

What COLLAB.md does *not* explicitly bind:

1. Per-artifact ownership and review attribution — there is no convention requiring each PR / ADR / design doc to name its lead and reviewer in its header.
2. The boundary between *concurrent architecture work on the same artifact* (a coordination hazard) and *independent security/governance work* (a feature of ADR-005). COLLAB.md §Coordination hazards documents that shared-login parallel work has happened, but does not define when concurrent design is forbidden vs. permitted.
3. Inbound-context discipline — when Michael relays a question to either AI, there is no explicit rule that he name whether the other AI has weighed in.

ADR-006 is the binding architectural decision that fills those three gaps. It is deliberately narrow. It does not restate or compete with COLLAB.md on anything COLLAB.md already covers.

## Scope and precedence

- `docs/COLLAB.md` is the day-to-day operating model. Its §Roles, §Authority ladder, §Decision surfaces, §Claim discipline, §Disagreement protocol, §Security-review checklist, §Safety freeze rule, §Verification posture, and §Coordination hazards are authoritative for everything they cover. ADR-006 incorporates them by reference and does not supersede.
- ADR-006 is binding only for the three rules below. Where ADR-006 is silent, COLLAB.md governs.
- Repo HEAD is canonical for accepted truth. Active PR branches are canonical for proposed changes under review (per ADR-006 §1).

## Decision

### 1. Single-owner-per-artifact

Every PR, ADR, design doc, probe report, and session log carries an explicit header naming:

- **Lead** — the AI (or Michael) responsible for content.
- **Reviewer** — the AI (or Michael) responsible for independent review.

The header may also name additional reviewers when warranted (security review, downstream-impact review, etc.) per COLLAB.md §Security-review checklist.

This rule binds *direct edits to the artifact's primary content*. It does **not** restrict:

- PR comments, review comments, suggested changes, or change requests (these are review activity per GitHub semantics, not unilateral edits).
- Issue comments on issues that reference the artifact.
- Independent commentary in a separate artifact (e.g., a security audit issue referencing the ADR).

### 2. No concurrent architectural design on the same artifact

Cowork architect and ChatGPT shall not concurrently produce competing architecture artifacts answering the same question without an explicit handoff.

Operationally: if the architect is drafting an ADR or design doc on topic X, ChatGPT does not draft a competing artifact on topic X (and vice versa). Handoff happens via PR / issue / comment per COLLAB.md §Authority ladder rule 5.

Carve-outs (none of these constitute concurrent architectural design):

- ChatGPT may at any time initiate security reviews, governance reviews, invariant audits, risk registers, threat models, confirmation-gate reviews, or independent alternative analyses when within the reviewer lane (per ADR-005 and COLLAB.md §Roles) or when Michael explicitly asks. These are reviewer outputs, not competing architecture artifacts.
- Either party may post review comments, change-requests, or suggested edits on any artifact regardless of who its lead is.
- Emergency risk-reducing work follows COLLAB.md §Security-review checklist's emergency-bypass clause: it may merge before formal review only to actively reduce risk, and it must create a follow-up review issue immediately.

### 3. Inbound-context discipline

When Michael brings a question on hot work to either AI, he should state whether the other AI has already weighed in (link or paste). When unstated, the AI receiving the question asks before answering on hot work.

This is the only durable defense against the architect and reviewer iterating against paraphrased versions of each other's positions.

## Consequences

**Positive:**

- Every artifact has an unambiguous owner and reviewer, named in the artifact itself — visible in the diff, surviving in history.
- The shared-login parallel-work hazard (COLLAB.md §Coordination hazards) gains an explicit rule: no concurrent architectural design on the same artifact, with carve-outs that preserve ChatGPT's independent-review lane.
- Telephone-game refinement through Michael as messenger has a named protocol step that breaks it.

**Negative / costs:**

- Adds a small header convention to every artifact. Lightweight; codifies existing implicit practice.
- Requires the parties to recognize when a draft is *concurrent architectural design* vs. *independent review/audit*. The carve-outs make the line clear in normal cases; ambiguous cases default to "ask before drafting" or filing a `decision-required` issue per COLLAB.md §Disagreement protocol.

## Alternatives considered

1. **No formal rule; rely on COLLAB.md §Coordination hazards.** Rejected: §Coordination hazards documents the failure mode but does not bind a rule. The 2026-04-26 collisions (issues #21–#32 dedup, ADR-006-vs-COLLAB.md overlap) showed that documentation alone is insufficient.
2. **Fold these rules into COLLAB.md as additions.** Considered. Rejected because COLLAB.md is the operating-model doc, amendable via PR for tactical updates; ADRs are the binding-decision surface that is meant to be permanent unless explicitly superseded. Single-owner discipline is a binding decision, not a tactical convention.
3. **Stricter rule forbidding ChatGPT from any concurrent drafting.** Rejected: would undermine ADR-005's grant of independent-review lane. Security/governance/audit artifacts must remain ChatGPT-initiable.

## Conflict edge cases

These are surfaced for the record so future-us doesn't have to relitigate them. None require new rules beyond §Decision above; each is resolved by named existing rules.

- **Stale branch vs. current main.** PR branches are canonical only for the changes under review; merge bases are checked against current `main` per COLLAB.md §Verification posture before claiming acceptance.
- **Same GitHub login causing attribution ambiguity.** Use the author header in the artifact (this ADR's "Author:" field), not the commit author, for attribution. COLLAB.md §Coordination hazards documents the underlying hazard.
- **Duplicate issues / duplicate PRs.** Resolved by COLLAB.md §Coordination hazards "branch in flight / issue in triage" mitigation. ADR-006 §1's lead/reviewer header makes duplicates more visible.
- **PR merged before required review.** Treated as a claim-discipline violation per COLLAB.md §Claim discipline. Recovery: revert or follow-up review issue.
- **Accepted ADR status not updated after merge.** Architect updates the ADR's `Status:` field in a follow-up PR. Open as a `adr-followup` issue if not done in same PR.
- **Evidence file cited by ADR exists only on another branch.** ADR cites should resolve on `main` at the time of acceptance. If they don't, block acceptance until the cited file lands.

## Future HAL

COLLAB.md §Roles defines a "Future contributor" lane for HAL itself, gated by capability-transfer per `docs/VISION.md`. ADR-006 binds Cowork and ChatGPT today. When HAL is brought in as a bounded contributor under that capability-transfer trajectory, a follow-up ADR will extend §1 (single-owner-per-artifact) and §2 (no concurrent design) to cover HAL's lane. Until then, HAL is not a party to ADR-006.

## Related

- `docs/COLLAB.md` — operating model (companion doc)
- `docs/COLLAB_STACK.md` — day-to-day cadence
- `docs/VISION.md` — long-term shape
- `decisions/ADR-005-canonical-voice-path-routing-ownership.md` — established ChatGPT's reviewer lane

## Revision history

- **rev 1** — original draft (2026-04-26). Withdrawn after ChatGPT review on PR #34 identified overlap with PR #33 (`docs/COLLAB.md`), incorrect source-of-truth paths, over-restricted ChatGPT lane, missing emergency carve-out, and missing review-vs-edit distinction.
- **rev 2** — accepted 2026-04-26. Narrowed scope to defer to COLLAB.md by reference; added carve-outs for ChatGPT-initiated security/governance work and review-comment activity; added emergency-bypass cross-reference; added conflict edge cases; clarified Future HAL deferred to follow-up ADR.
