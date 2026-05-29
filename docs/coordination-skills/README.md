# Coordination Skills — Public Portfolio Versions

This folder contains sanitized, recruiter-facing versions of selected HAL coordination skills and operating documents.

These are **not raw operational copies** from the private development environment. They have been rewritten to remove private repository names, local machine paths, credentials, Discord channel names, household-specific context, and implementation details that are not appropriate for a public portfolio.

## Why these documents are included

HAL is not only a personal AI assistant. It is also a structured experiment in using multiple AI systems as a coordinated engineering team. These documents show how the project manages that complexity with explicit process design:

- Canonical project state lives in GitHub issues, pull requests, and tracked decisions.
- Chat and notification tools are transport surfaces, not sources of truth.
- Agent work is bounded by role, authority, stop conditions, and review gates.
- Handoffs are structured so a downstream AI can act without hidden context.
- Safety-sensitive work pauses for human decision rather than improvising.

## Included documents

| Document | Purpose |
|---|---|
| `sprint-planning-and-kickoff.md` | Defines the structured entry point for starting a multi-agent sprint. |
| `code-handoff.md` | Defines the handoff format used when routing work from planning to implementation. |
| `reentry-poll.md` | Explains how the architect lane re-enters a sprint after implementation or review work completes. |

## Public sanitization policy

The documents in this folder intentionally avoid:

- Secrets, tokens, API keys, webhook URLs, and credentials
- Private GitHub repository names or issue links
- Local machine paths and hostnames
- Private Discord channels or bot identifiers
- Household-specific device names or personal context
- Operational steps that would grant production access

Where an operational version would include a concrete command, local path, channel, or issue number, these public versions use placeholders and describe the design intent instead.

## Design theme

The recurring principle is:

> HAL is the product. The orchestrator is the build machine.

The coordination layer is valuable only when it reduces manual handoff burden, improves build reliability, or directly unblocks useful assistant capability.
