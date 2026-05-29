# Sprint Planning and Kickoff Skill

Public portfolio version. This document is a sanitized design artifact, not an operational runbook.

## Purpose

This skill defines a structured kickoff process for multi-agent development sprints. It exists to prevent ad hoc starts, duplicate tracking issues, unclear ownership, and drift between product work and orchestration work.

The skill is intended for an architect/planning AI that coordinates implementation and review lanes through a GitHub-centered workflow.

## Core doctrine

```text
GitHub issue state is the source of truth.
Notification tools are transport surfaces, not decision surfaces.
The planning lane drafts handoffs and updates GitHub state.
The relay/orchestrator emits notifications.
Implementation and review lanes operate from GitHub issue context.
Scheduled re-entry is the expected mechanism after a downstream lane completes.
```

## When to use

Use this skill when starting or reshaping a multi-agent sprint, such as:

- planning the next implementation loop;
- turning a decision into an execution handoff;
- preparing implementation and review lanes;
- resuming a paused sprint after a result has been posted;
- checking whether a new sprint is actually needed.

Do not use it for simple discussion, one-off edits that do not need orchestration, or active sprints where another lane is already executing.

## Step 1 — Intake

Before starting a sprint, identify:

| Field | Question |
|---|---|
| Sprint name or gate | What is this sprint trying to complete? |
| Tracking issue | Is there already a canonical issue? |
| Decision-maker | Can the architect proceed, or is human approval required? |
| Work type | Product capability, orchestration tooling, or ops hygiene? |
| Continuation or new work | Is this a new sprint or the next turn of an existing sprint? |
| Code changes | Are implementation edits needed? |
| Live-system access | Does the work touch deployment, services, credentials, or controlled devices? |
| Review needs | Is independent code, safety, or architecture review required? |

If an intake field is ambiguous, ask one focused question before dispatching work.

## Step 2 — Mission guardrail

Every sprint must pass the product/tool boundary check:

```text
Is this advancing usable assistant capability?
  → Product work. Proceed.

Is this orchestration tooling?
  → Proceed only if it reduces manual handoff burden, improves relay reliability,
    or directly unblocks assistant capability.

Is this ops hygiene?
  → Proceed only if it is blocking an active gate or creating active friction.
```

This prevents the coordination system from becoming the product.

## Step 3 — Source-of-truth check

The architect must inspect current GitHub state before planning:

- issue body and labels;
- latest comments;
- open pull requests touching the same surface;
- recent merged pull requests;
- unresolved STOP or decision-required comments;
- whether the requested work is already complete;
- whether another dispatch is already in flight.

Chat history and prior handoffs are starting references, not authoritative state.

## Step 4 — Select sprint shape

Choose the lightest structure that fits the work.

| Shape | Use when |
|---|---|
| No sprint | Work is already done or superseded. |
| Decision packet | A human decision is required before work can continue. |
| Single implementation dispatch | One bounded implementation task is needed. |
| Implementation → architect loop | Implementation completes, then architect reviews and decides next step. |
| Implementation → review → architect loop | Code changes need independent review before architect verdict. |
| Ops hygiene dispatch | Cleanup is bounded and does not change architecture. |
| Blocked | Access, configuration, or prerequisite state is missing. |

Avoid multi-loop machinery for work that only needs a single bounded dispatch.

## Step 5 — Use or create a sprint artifact

Default to reusing the existing gate or tracking issue. Create a new issue only when the work is independently trackable or the current issue would become too broad or confusing.

A sprint artifact should include:

```markdown
## Sprint goal
## Win conditions
## Stop conditions
## Decisions requiring human approval
## Budget
## Lane sequence
## Current lane
## Sprint started
```

The sprint artifact is the durable coordination surface. Each lane should read it before acting.

## Step 6 — Handoff discipline

A downstream implementation or review handoff should include:

- goal and scope;
- branch or PR expectations;
- files in scope and files explicitly out of scope;
- test commands;
- STOP triggers;
- done criteria;
- expected result comment;
- lane transition instructions;
- explicit statement that notification tools are not to be manually driven as a substitute for the relay.

Handoffs should be written so the receiving lane can act without needing private chat context.

## Step 7 — Authority and safety gate

Pause for human decision before dispatching if the sprint touches:

- deployment or service restarts;
- credentials, tokens, secrets, or authentication;
- safety-sensitive external actions;
- home automation or physical-world device mutation;
- broad architecture changes;
- new dependencies with licensing or supply-chain implications;
- changes to classifier, confirmation, memory, or approval boundaries;
- changes to orchestration semantics.

The decision packet should explain the decision, why it matters, and the available options.

## Step 8 — Scheduled re-entry check

Before relying on automated re-entry, verify that the re-entry mechanism is active and configured for the correct issue and lane state.

If re-entry is not verified, do not bypass the loop by manually operating the notification surface. Surface the risk and run a controlled smoke test.

## Output modes

The skill should produce exactly one output:

| Output | Description |
|---|---|
| Sprint kickoff package | Tracking issue, win conditions, stop rules, lane sequence, first handoff. |
| Implementation dispatch | Ready handoff for the implementation lane. |
| Review dispatch | Ready handoff for independent review. |
| Decision packet | A human decision is needed before execution. |
| No-op | Work is already complete, superseded, or blocked. |

## Anti-patterns

- Treating chat or notification tools as source of truth
- Starting from stale memory without checking GitHub
- Creating duplicate tracking issues
- Mixing product work and orchestration work without naming the distinction
- Skipping STOP triggers
- Proceeding after live-system mismatch
- Dispatching work from truncated or incomplete context
- Letting orchestration polish displace useful assistant capability

## Public portfolio note

Operational versions of this skill may include concrete repository names, labels, paths, and automation hooks. Those details are intentionally omitted here. This public version documents the design pattern and governance model.