# Selected Engineering Decisions

HAL is built decision-first. Load-bearing choices are written down as Architecture Decision Records, including decisions that were later revisited. A few worth reading:

- **[ADR-010 — Concurrent multi-model execution and resource arbitration](../decisions/ADR-010-concurrent-multi-model-execution.md).** Defines why HAL should not use one model for every task. The voice path needs a fast front model, while planning, drafting, and build work can move to specialist models or delegated workers. This keeps interaction responsive while preserving deeper capability.
- **[ADR-009 — Probe-gated Hermes runtime convergence](../decisions/ADR-009-hermes-runtime-convergence.md).** Revisits the runtime architecture after Hermes added enough native capability to reduce bespoke HAL infrastructure. The decision is probe-gated: HAL may converge onto Hermes only if voice safety, toolset lockdown, ambient filtering, latency, and rollback requirements are satisfied.
- **[ADR-008 — Multi-lane build automation](../decisions/ADR-008-multi-lane-build-automation.md).** The build system itself: an orchestrator that coordinates multiple AI agents through a GitHub-label state machine and an operator surface. It is defined as much by what it refuses to do: it does not auto-merge, does not bypass GitHub as canonical state, and requires review gates for sensitive transitions.
- **[ADR-002 — The adapter owns the tool schema](../decisions/ADR-002-adapter-owns-tool-schema.md).** One component owns the boundary where the assistant is allowed to act on the house. One owner, one mutation surface. Even as runtime architecture evolves, this decision remains a useful safety pattern.
- **[ADR-005 — Canonical voice-path routing ownership](../decisions/ADR-005-canonical-voice-path-routing-ownership.md).** Who owns the request path, so there is never ambiguity about where a voice command is handled.
- **[ADR-001 — Superseding the first voice approach](../decisions/ADR-001-hermes-voice-superseded.md).** Kept on purpose. It records an approach that was later replaced or revisited, so the reasoning and reversal stay legible instead of vanishing.

And the safety subsystem those decisions protect:

- **[confirm-before-mutate](../machines/server/hal-voice-adapter/confirm/)** — a snapshot of the gate that decides when an action needs spoken confirmation, when it is allowed silently, and when it is refused outright. Exterior locks, ovens, space heaters, and disabling smoke or CO sensors are examples of deny-by-default or confirmation-heavy categories. Unknown tools fail closed. The policy is intentionally auditable and testable.

## Why the ADR trail matters

The project is intentionally not a pile of agent scripts. The hard engineering work is deciding where authority lives, how a request crosses from suggestion into action, and when a model is allowed to use tools.

That is why the public portfolio includes both current direction and older superseded decisions. The reversal trail is part of the engineering story.
