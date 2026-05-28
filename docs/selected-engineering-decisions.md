# Selected Engineering Decisions

HAL3000 is built decision-first. Every load-bearing choice is written down as an Architecture Decision Record, including the ones that were later reversed. A few worth reading:

- **[ADR-008 — Multi-lane build automation](../decisions/ADR-008-multi-lane-build-automation.md).** The build system itself: an orchestrator that coordinates four AI agents (planning, execution, audit, launch) through a GitHub-label state machine and a Discord operator surface. It is defined as much by what it refuses to do: it never auto-merges, never bypasses GitHub as canonical state, logs every agent invocation with secrets redacted before the row is written, enforces hard caps on amend cycles and spend, and ships in phases where each automated lane has to earn trust against the manual lane before it takes over. The alternatives considered, and why each was rejected, are in the record.
- **[ADR-002 — The adapter owns the tool schema](../decisions/ADR-002-adapter-owns-tool-schema.md).** One component owns the boundary where the assistant is allowed to act on the house. One owner, one mutation surface.
- **[ADR-005 — Canonical voice-path routing ownership](../decisions/ADR-005-canonical-voice-path-routing-ownership.md).** Who owns the request path, so there is never ambiguity about where a voice command is handled.
- **[ADR-001 — Superseding the first voice approach](../decisions/ADR-001-hermes-voice-superseded.md).** Kept on purpose. It records an approach that was later replaced, so the reasoning and the reversal stay legible instead of vanishing.

And the safety subsystem those decisions protect:

- **[confirm-before-mutate](../machines/server/hal-voice-adapter/confirm/)** — the gate that decides when an action needs spoken confirmation, when it is allowed silently, and when it is refused outright. Exterior locks, ovens, space heaters, and disabling smoke or CO sensors are deny-by-default. Bedroom and sleep-area actions during quiet hours require confirmation. Unknown tools fail closed. The whole policy lives in one auditable function ([policy.py](../machines/server/hal-voice-adapter/confirm/policy.py)) that mirrors a written security spec, with tests alongside it.

> Maintainer note: these one-line summaries were drafted from a recent working snapshot. Confirm they still match the current ADR bodies before publishing.
