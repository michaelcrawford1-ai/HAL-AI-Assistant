# Code Handoff Skill

Public portfolio version. This document is a sanitized design artifact, not an operational runbook.

## Purpose

This skill defines how planning work is handed off to an implementation agent in a multi-agent development workflow.

The goal is to prevent vague instructions, hidden context, runaway debugging, and implementation drift. A good handoff should let the receiving agent understand the task, execute within bounds, stop when appropriate, and report results in a way the next lane can evaluate.

## Core pattern

The operational version uses a two-artifact model:

1. **Handoff document** — full implementation instructions for the receiving lane.
2. **Dispatch record** — short coordination note that points to the handoff and updates the canonical project state.

In this public version, the exact private file paths and automation hooks are omitted. The design principle remains:

```text
The handoff document is the execution payload.
The project issue or tracking artifact is the durable source of truth.
Notification tools only announce that a handoff exists.
```

## Why this skill exists

AI-assisted coding becomes unreliable when downstream agents receive loose prompts such as “fix the bug” or “continue the previous work.” The handoff skill forces the planning lane to provide:

- verified current state;
- exact scope;
- authority boundaries;
- tests and acceptance criteria;
- explicit stop conditions;
- result-reporting requirements;
- enough context to act without relying on private chat memory.

## Pre-flight checks

Before drafting a handoff, the planning lane should verify:

- the tracking issue or task exists and is current;
- branch or pull request state is accurate;
- prior claims have been checked against the repository;
- no duplicate work is already in flight;
- relevant design documents or acceptance criteria are known;
- the intended output belongs in implementation, review, decision, or no-op status.

Stale handoff text is not authoritative. Current repository state wins.

## Handoff document structure

A strong implementation handoff includes these sections.

```markdown
# Implementation Handoff — <topic>

Status: ready-for-implementation
Source: architect lane
Date: <date>
Model / capability tier: <if relevant>
Branch or PR: <target branch or pull request>
Topic: <short explanation>
Read first: <issue, design doc, review comment, or acceptance criteria>

## Goal

<Outcome and why it matters.>

## Authority boundaries

- What may be changed.
- What must not be changed.
- Whether deployment, service restarts, credentials, or external actions are out of scope.

## Work items

1. <Concrete task>
2. <Concrete task>
3. <Concrete task>

## Tests required

- <test command or verification step>
- <test command or verification step>

## STOP triggers

- Stop if a required precondition is false.
- Stop if the implementation conflicts with the design.
- Stop after repeated build or test failure.
- Stop if the task would require broader authority than granted.

## Done means

1. <verifiable completion criterion>
2. <verifiable completion criterion>
3. <result comment or summary posted>
```

## Dispatch record

The dispatch record is intentionally short. It should not contain the entire implementation plan.

Example:

```markdown
## Lane Handoff

Sprint: <tracking issue or work item>
Lane: implementation
Date: <date>
Handoff: <pointer to handoff document or artifact>
Goal: <one or two sentences>
Model / capability tier: <optional>
```

The dispatch record exists so the relay can notify the next lane without overflowing a chat or notification surface.

## Model or capability selection

The planning lane should match model capability to task complexity:

| Tier | Use when |
|---|---|
| Low-cost / fast model | Mechanical, small, verbatim changes. |
| Standard coding model | Normal implementation, test additions, and multi-file comprehension. |
| Highest-reasoning model | Security-sensitive, architecture-heavy, or ambiguous work. |

The model choice should be visible in the handoff when it affects cost, risk, or expected judgment.

## Stop conditions

Every implementation handoff should have explicit stop conditions. These are not decorative. They prevent an implementation agent from burning time or silently expanding scope.

Common stops:

- precondition mismatch;
- missing branch or issue;
- second build or test failure;
- unclear acceptance criteria;
- proposed change touches unauthorized files;
- security or credential surface appears unexpectedly;
- deployment would be required but is not authorized.

## Result reporting

The receiving lane should report:

- what changed;
- what tests were run;
- what failed or was skipped;
- whether any stop condition triggered;
- what remains for review;
- exact artifacts produced, such as a pull request, commit, or issue comment.

The next lane should not need to reconstruct the implementation from chat history.

## Anti-patterns

- Sending full implementation instructions only through a chat message.
- Relying on prior conversation instead of current project state.
- Hiding stop conditions in prose.
- Omitting tests or done criteria.
- Allowing implementation to change deployment, credentials, or runtime configuration without explicit approval.
- Treating notification tools as the durable record.
- Letting a receiving agent infer scope from incomplete context.

## Public portfolio note

The private operational version includes concrete paths, repository labels, and automation conventions. Those details are intentionally removed here. This public version documents the system design pattern: structured handoff, bounded execution, explicit authority, and auditable results.