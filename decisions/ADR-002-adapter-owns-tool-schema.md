# ADR-002 — `hal-voice-adapter` owns the tool schema; HA Assist Expose UI is dead surface

- **Status:** Accepted
- **Date:** 2026-04-21
- **Deciders:** Architect (cowork), Michael
- **Tags:** voice, tooling, ha-integration

## Context

Home Assistant exposes a tool schema to the LLM via the "Assist" exposure UI and the `functions=` field on the conversation request. In testing, the adapter pattern worked best when it ignored the inbound HA schema and injected its own canonical 7-tool set.

There are several reasons:

- Schema drift between HA's UI-driven exposure and what the model actually needs is constant.
- The adapter needs to evolve its tool surface independently of HA configuration churn.
- The HA tool must be a **thin pass-through** — never synthesize success on missing fields. The 2026-04-20 Tuya incident proved this rule.

## Decision

The adapter always injects its own 7-tool schema and ignores HA's `functions=` field. The HA Assist Expose UI is treated as a **dead surface for the voice path** — changes there have no effect on what the voice agent can do.

The adapter's tool layer is a thin pass-through to upstream services. No synthesis, no fabrication, no guessing on missing fields.

## Alternatives considered

- **Honor HA `functions=` directly.** Rejected — schema drift, no place to add adapter-specific tools.
- **Hybrid: union of HA schema and adapter schema.** Rejected — operationally confusing; doubles surface area for failure.

## Consequences

- **Positive:** Single source of truth for voice tools. Adapter evolves independently. Pass-through is enforceable in code review.
- **Negative:** The HA Assist Expose UI is a footgun — anyone who configures it expecting effect will be confused.
- **Locks in:** the adapter as the canonical voice tool registry.
- **Defers:** any HA-native tool exposure pattern. Probably permanently for voice.

## Evidence

- 2026-04-20 Tuya incident: HA tool synthesized success when response missing required fields → bad mutation. Memory: `feedback_ha_tool_pass_through.md`
- Memory: `project_adapter_tool_schema_ownership.md`

## Triggers for revisit

- HA introduces a stable, machine-readable, version-controlled schema export
- Voice tools need to multiply faster than the adapter can absorb edits
