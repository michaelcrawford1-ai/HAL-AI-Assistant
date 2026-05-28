# Orchestration Model

HAL uses a multi-agent orchestration model to coordinate planning, coding, review, and project-state updates. The system is designed to reduce manual handoffs between AI tools while preserving human approval for high-impact actions.

## Core concept

The orchestrator treats work as structured state rather than loose chat history.

```text
Goal
  -> issue
  -> labels
  -> lane assignment
  -> bounded agent work
  -> review
  -> state transition
  -> final summary or blocker
```

## Lane model

| Lane | Purpose |
|---|---|
| User / product lane | Defines goals, constraints, and success criteria |
| Architect lane | Converts ambiguous goals into scoped plans and acceptance criteria |
| Code lane | Implements bounded technical changes |
| Review lane | Checks correctness, safety, and fit against requirements |
| Decision lane | Compresses unresolved tradeoffs into decision-ready packages |
| Notification lane | Surfaces blockers, status changes, and completion summaries |

## Canonical state

GitHub issues, pull requests, and labels act as the canonical state layer.

This provides:

- A durable record of work
- Clear status labels
- Reviewable decisions
- Pull request history
- Testable acceptance criteria
- A way for multiple agents to coordinate without relying on fragile chat context

## Example workflow

```text
1. User defines a goal
2. Architect lane creates a scoped issue
3. Issue receives labels describing next lane and state
4. Code lane performs a bounded implementation
5. Review lane checks output against criteria
6. If accepted, state moves forward
7. If blocked, issue is labeled and summarized
8. User receives a concise status update
```

## Review gates

Review gates are used to prevent the system from becoming a blind automation loop.

Typical gates include:

- Scope is clear
- Success criteria are testable
- Stop conditions are defined
- Output can be verified
- Security boundaries are not expanded silently
- Public-facing material is sanitized
- Human approval is required before irreversible or external-impacting action

## Why this pattern matters

Most AI workflows fail when important context is scattered across chats, local files, and informal handoffs. HAL's orchestration model moves the critical state into structured, reviewable artifacts.

The result is a system that can use AI assistance without losing accountability.

## Current public status

This public repository documents the orchestration model at a portfolio level. Private implementation details, local runtime configuration, credentials, and internal coordination history are intentionally excluded.
