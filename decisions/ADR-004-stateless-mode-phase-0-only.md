# ADR-004 — Voice stateless mode is a Phase 0 defense, not a terminal architecture

- **Status:** Accepted
- **Date:** 2026-04-23
- **Deciders:** Architect (cowork), Michael
- **Tags:** voice, memory, phase-0, phase-1

## Context

Phase 0 ships voice in stateless mode: each turn is independent, no cross-turn memory, no identity carryover. This was a deliberate defensive choice given:

- Ambient audio + wake-word false-positives + Whisper garble → real tool fires
- `qwen3-14b` ignores prompt prohibitions and `tool_choice`
- `hal-2b` over-generalizes in-context prohibitions across the session
- Entity grounding still invents `entity_id`s

Stateless mode is a containment strategy. It limits the blast radius when the voice path misbehaves.

It is **not the terminal shape** for HAL voice. The HAL vision is one persona per user, present across surfaces, with unified memory and identity. A stateless local voice surface that calcifies into a "Siri clone" is an explicit failure mode to avoid.

## Decision

Voice operates in stateless mode for Phase 0. When the Phase 1 classifier router lands, stateless mode is replaced by:

- **Confirm-before-mutate** on writes (any tool call that changes household state requires a confirm step in the conversation)
- **Self-healing-intent** on reads (model can ask back-questions to ground entities, rather than inventing them)

These two patterns together carry the safety properties of stateless mode without sacrificing memory and identity.

## Alternatives considered

- **Keep stateless permanently.** Rejected — collapses HAL into a local Siri clone; abandons the unified-persona vision.
- **Skip stateless and ship stateful Phase 0.** Rejected — the failure modes documented above are real and would have produced household-visible mutations.

## Consequences

- **Positive:** Phase 0 ships safely. Phase 1 has a clear architectural target.
- **Negative:** Phase 1 is now load-bearing for the long-term vision; if it slips, voice stays as a Siri clone longer than acceptable.
- **Locks in:** memory + classifier router as Phase 1 priorities.
- **Defers:** unified cross-surface memory until Phase 1 ships.

## Evidence

- Phase 0 voice defense stack (filter + stateless + garble + 4-event telemetry) cleared at merge `c10195d`
- Memory: `feedback_voice_not_siri_clone.md`
- Memory: `project_phase1_reshape.md`

## Triggers for revisit

- Phase 1 memory + classifier router demonstrably ready, with confirm-before-mutate and self-healing-intent verified in probe
- Stateless mode's containment proves insufficient for a household incident
