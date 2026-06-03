# ADR-009 — Probe-gated Hermes runtime convergence

**Status:** Proposed / probe-gated in the private project  
**Scope:** Public-safe summary  
**Decision type:** Runtime architecture

## Context

HAL originally used a dedicated voice adapter to keep the Home Assistant voice path simple, auditable, and safe. That adapter owned request normalization, the tool schema, and the household mutation boundary.

As the project matured, the private implementation began using Hermes as a more capable agent runtime for non-voice surfaces and builder-style work. Hermes added or exposed several native capabilities that overlap with subsystems HAL had been building separately:

- OpenAI-compatible API access
- voice/runtime integration patterns
- toolsets and surface-specific tool access
- memory and session search
- delegated sub-agents
- scheduled jobs
- rollback/checkpoint concepts
- policy hooks around tool use and request dispatch

That created a strategic question: should HAL continue building every runtime subsystem bespoke, or should it converge onto a maintained agent runtime and supply HAL-specific policy and safety layers?

## Decision

HAL will evaluate a probe-gated convergence onto Hermes as the primary runtime body for voice, memory, tools, and delegated work.

The decision is not an unconditional cutover. The private project treats Hermes convergence as acceptable only if probes demonstrate that the runtime can preserve HAL's safety invariants.

The intended shape is:

```text
voice / chat / dashboard surface
  -> fast front agent
  -> surface-specific input filters
  -> locked toolset
  -> policy hooks
  -> low-risk tool execution or clarification
  -> delegated specialist agents only for bounded draft/stage work
```

## Safety invariants

The convergence path must preserve these invariants:

1. Voice is an intake surface, not unrestricted authority.
2. Ambient or garbled input must not reach mutating tools.
3. The voice surface must be locked to an approved toolset.
4. Terminal, browser, code execution, and unrestricted delegation are not available from voice ingress.
5. Household-impacting actions remain policy-gated.
6. High-risk actions require confirmation or are denied.
7. Builder/delegated agents draft and stage; they do not directly apply production changes.
8. A rollback path must exist during cutover.
9. Human review remains required for durable or risky actions.

## Consequences

### Benefits

- Less bespoke runtime infrastructure to maintain
- Faster path to memory, session search, tools, delegation, and scheduled workflows
- Cleaner separation between HAL policy and generic agent runtime mechanics
- Better support for layered agents: fast front-desk model plus specialist workers
- More realistic path for HAL to help build HAL

### Tradeoffs

- Runtime integration becomes dependent on Hermes behavior and upgrade discipline
- Safety must be enforced through hooks, tool allowlists, and tests rather than only through bespoke adapter code
- Cutovers require stronger runbooks and rollback procedures
- Model selection matters more because the front agent becomes a production-facing interface

## Probe requirements

Before accepting runtime convergence, the private project must verify:

- plain voice turns terminate cleanly;
- no JSON or tool syntax leaks into normal spoken replies;
- Home Assistant tools support required read/action patterns;
- toolset lockdown works by surface;
- ambient/greeting/garbled input is filtered before the model or before mutation paths;
- high-risk actions remain confirmed or denied;
- latency is acceptable for voice;
- streaming/tool-call behavior is safe or disabled;
- rollback to the prior adapter path is documented and tested.

## Public portfolio note

This ADR is intentionally high-level. It omits private machine names, local paths, credentials, exact network configuration, private issue history, and household-specific entity details.
