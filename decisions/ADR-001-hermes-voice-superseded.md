# ADR-001 — Hermes is the wrong shape for voice; voice path superseded

- **Status:** Accepted (2026-04-21 PM)
- **Date:** 2026-04-21
- **Deciders:** Architect (cowork), Michael
- **Tags:** voice, hermes, architecture

## Context

The original architecture used Hermes (a general-purpose CLI agent framework) as the voice agent. In probing, two failure modes converged:

1. Hermes cannot terminate a conversational turn on plain-text content. It is structured around tool-calling loops; a plain-text "answer" gets re-routed back through a tool-evaluation step.
2. When the toolset was trimmed to constrain behavior, the model redirected down a JSON-leak enumeration path — outputting JSON tool-call shapes as conversational content.

These are not bugs to fix. They are properties of Hermes' shape. Voice does not want them.

## Decision

The voice path is superseded off Hermes. Voice flows through:

```
HA Ext OpenAI Conv → hal-voice-adapter (Server :4003) → LiteLLM → Ollama
```

Hermes is **retained for Discord, Telegram, and terminal surfaces** — where its shape is correct.

## Alternatives considered

- **Stay on Hermes, patch around it.** Rejected after multiple probe rounds — the failure modes are intrinsic, not addressable by config.
- **acon96/home-llm.** Considered as a HA-native option. The adapter approach was selected because it preserves the cowork architect's ability to evolve the schema without HA-side dependencies.
- **HA Assist Expose UI as schema source.** Rejected — see ADR-002.

## Consequences

- **Positive:** Voice path now has its own thin adapter; toolset is owned by the adapter; turn termination is correct.
- **Negative:** Hermes and adapter are two codebases now (one per surface family). This is acceptable cost.
- **Locks in:** the adapter as the long-term voice body shape.
- **Defers:** unifying tooling between voice and Hermes — Phase 1 memory work will surface this question.

## Evidence

- Multiple voice probe rounds 2026-04-19 → 2026-04-21
- Memory: `feedback_hermes_wrong_shape_for_voice.md`
- Voice MVP cleared Phase 0 at merge `c10195d` (2026-04-23) on the new path

## Triggers for revisit

- Hermes upstream adds plain-content turn termination as a first-class behavior
- Adapter approach fails to scale across multiple voice surfaces (HA, mobile, etc.)
