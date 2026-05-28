# ADR-005 — Canonical voice request path and routing ownership

- **Status:** Accepted (2026-04-26)
- **Date:** 2026-04-26
- **Deciders:** Architect (cowork), Reviewer (chatgpt), Michael (final)
- **Tags:** voice, routing, ownership, ha-integration, security

## Context

Phase 0 is cleared (merge `c10195d`). The voice defense stack (filter + stateless + garble + 4-event telemetry) has shipped and has held in production. Phase 1 work — multi-tenant memory, confirm-before-mutate, classifier-driven routing, ambient-noise mitigation — is now blocked on an unambiguous statement of which component owns what in the voice request path.

The repository contains four services that touch voice routing in some way:

- `hal-voice-adapter` (Server, port 4003)
- `hal-proxy` (Server, port 4001)
- `hal-classifier` (Server, port 5000)
- `LiteLLM` (Server, port 4000)

Probe **VOICE-PATH-TRACE-001** (`machines/server/PROBE-2026-04-26-voice-path-trace.md`, branch `probe/voice-path-trace-001`, SHA `a25238c`) established current observed reality:

- **Home Assistant points at `hal-voice-adapter:4003`** via Tailscale `server.tailnet`. Not 4001.
- **Live path:** HA → `hal-voice-adapter:4003` → `LiteLLM:4000` → Mac Ollama (`hal-14b-q3` / `qwen3-14b-hal` at `mac.tailnet:11434`).
- **`hal-proxy:4001` is running but receiving zero traffic.** FastAPI/uvicorn container; the `hal-proxy.conf` nginx file is a dead artifact.
- **`hal-classifier:5000` is running but unreferenced** by any other service. `adapter/endpoints.py:189` explicitly tags it as Phase 1 work. Inert.
- **Tool schema has a single owner** — `hal-voice-adapter` per ADR-002. No drift (`tool_source.py:66-196`, `endpoints.py:108`).
- **No fallback is configured for `hal-14b-q3`.** If Mac Ollama is unreachable, LiteLLM returns an error and the adapter surfaces 502 to HA. Mac Ollama is a hard production dependency today.
- The `docker-compose.yml:126` comment claiming "HA always points to 4001" is **aspirational** — describes an intended Phase 1 routing design that was never wired up.

`docs/ARCHITECTURE.md` describes the pre-pivot path and is stale. `hal-proxy` and `hal-classifier` are parked Phase 1 candidates, not silently competing routers — but their presence in the running container set without explicit parked status creates ambiguity that Phase 1 work cannot tolerate.

## Decision

HAL voice has exactly one canonical ingress: **`hal-voice-adapter` on Server port 4003**. Home Assistant points to this service. The adapter owns the household mutation boundary for voice. Any service that influences voice routing, model choice, memory injection, or tool execution must do so through an explicit interface consumed by the adapter. No other service may independently become the HA-facing voice ingress without superseding this ADR.

`hal-proxy` and `hal-classifier` are **parked Phase 1 candidates**. They are not part of the production voice path as of VOICE-PATH-TRACE-001. Their presence in the repo does not imply architectural authority.

LiteLLM is the **model gateway**, not the safety authority. Home Assistant mutation policy lives in the adapter.

Classifier output, when classifier is promoted from parked, is **advisory**. The adapter remains the final voice safety arbiter.

ADR-005 establishes ownership and invariants for the voice request path. It does **not** define the classifier output schema, degraded-mode behavior, memory-injection mechanics, or confirm-before-mutate state machine. Those are required Phase 1 design deliverables and must be completed before memory/personality or broader household-impacting features proceed.

### Components and ownership

| Concern | Owner |
|---|---|
| HA-facing voice endpoint | `hal-voice-adapter` |
| Voice request normalization | `hal-voice-adapter` |
| Voice system prompt construction | `hal-voice-adapter` |
| Voice tool schema | `hal-voice-adapter` (per ADR-002) |
| Voice tool-call loop | `hal-voice-adapter` |
| Voice tool execution (HA mutation boundary) | `hal-voice-adapter` |
| Voice telemetry (4-event chain + Phase 1 extensions) | `hal-voice-adapter` |
| Voice memory injection seam (Phase 1) | `hal-voice-adapter` |
| Voice confirm-before-mutate seam (Phase 1) | `hal-voice-adapter` |
| Voice safety policy enforcement | `hal-voice-adapter` |
| Model provider routing / endpoint abstraction | `LiteLLM` |
| Cloud/local model gateway | `LiteLLM` |
| Provider keys / retry where safe | `LiteLLM` |
| Intent classification (advisory, when promoted) | `hal-classifier` |
| Voice request ingress for non-HA clients | _not in scope of ADR-005_ |
| HA mutation policy | `hal-voice-adapter` (never `LiteLLM`, never classifier) |
| `hal-proxy` production role | _none_ — parked, transitional |

### Adapter explicitly does not own

The following are out of scope for `hal-voice-adapter`. Listed because each has plausible drift risk; obvious non-temptations are excluded to keep the list load-bearing:

- Long-term planning
- Multi-surface memory database (storage layer)
- Non-voice surface orchestration
- Arbitrary tool execution outside the voice-approved tool set
- Cloud-provider policy or provider selection, except requesting an approved model/tier through `LiteLLM` or a later approved router
- Discord, Telegram, or terminal agent behavior

### Parked-services policy

Running-but-unused services are permitted only when explicitly marked as parked and assigned a review trigger.

`hal-proxy` and `hal-classifier` will be reviewed at the **start of Phase 1 model-routing work OR ADR-005 + 90 days, whichever comes first**. If either service remains unwired at the trigger, archive it (preserve git history) and remove it from the running container set unless Michael explicitly reauthorizes continued parking.

`docs/ARCHITECTURE.md` and `status/server.STATUS.md` must reflect parked status before Phase 1 work begins.

### Mac Ollama as current production dependency

HAL voice production currently depends on Mac Ollama availability for `hal-14b-q3`. No fallback is configured for that route as of VOICE-PATH-TRACE-001. If Mac Ollama is unavailable, LiteLLM returns an error and the adapter surfaces failure to HA. ADR-005 accepts this as **current reality, not desired terminal architecture**. A degraded-mode design is required before Phase 1 expands voice capability.

### Out of scope for ADR-005 (Phase 1 design deliverables)

The following must be designed and accepted as Phase 1 work, but their mechanics are not specified here:

- Classifier output schema (likely fields: intent class, suggested model tier, suggested safety class, confidence, reason code — exact shape deferred)
- Degraded-mode routing mechanics for Mac Ollama unavailability
- Confirm-before-mutate state machine (which tools require confirmation, prompt shape, timeout, fallback to deny)
- Memory injection mechanics (per-user pre-prompt assembly)
- Full Phase 1 telemetry schema (extensions to the 4-event chain: `classifier_decision`, `confirmation_required`, `confirmation_outcome`, `fallback_invoked`)

## Alternatives considered

### Option A — Collapse

Adapter stays canonical HA entry. `hal-proxy` and `hal-classifier` are deleted (or archived). Multi-model routing lives entirely in `LiteLLM`'s native router config.

**Rejected** — discards parked work that has plausible Phase 1 value (advisory classification, future router consolidation) before Phase 1 routing and cloud/local escalation are designed. ADR-005 instead parks these services with an explicit review trigger; they earn deletion or promotion via the trigger, not by default.

### Option B — Migrate HA ingress to `hal-proxy`

HA is reconfigured to point at `hal-proxy:4001` (the originally intended Phase 1 design). `hal-proxy` becomes routing hub. `hal-voice-adapter` becomes a sub-component behind it.

**Rejected** — splits the household safety boundary from the mutation boundary. The adapter is already where voice input, tool schema, model tool calls, HA mutation, telemetry, and future confirmation state naturally meet. Moving HA ingress to `hal-proxy` is the kind of soft boundary that produced previous rebuild cycles. Also risks turning `hal-proxy` into a god object.

### Option C — Adapter as ingress, proxy/classifier as internal services (selected)

HA stays at `hal-voice-adapter:4003`. Adapter optionally consults classifier (advisory hint) and may delegate model selection to `LiteLLM`'s router or to a future promoted role for `hal-proxy`. Adapter retains HA boundary, tool schema, telemetry, confirm-before-mutate, memory injection.

**Selected** — preserves the strongest proven component at the safety boundary, generalizes ADR-002's "one owner per concern" pattern from tool schema to ingress, and keeps confirm-before-mutate inside the same component as tool execution. Does not waste parked work but does not bless it as required.

## Trade-off analysis

The central trade-off is between **boundary clarity** (one component owns the HA boundary, mutation boundary, tool schema, and confirmation gate) and **adapter scope creep** (the same component now also injects memory, consults the classifier, and emits telemetry).

Option C accepts the scope-creep risk and mitigates it via the explicit "does not own" list above and by deferring mechanics to Phase 1 design docs. The alternative — splitting the boundary across two services (Option B) — eliminates scope creep at the cost of fragmenting the safety surface, which is a worse failure mode.

The probe also resolved a secondary trade-off: parked services were thought to be silently competing in production. They are not — they are inert. ADR-005 therefore parks them rather than deleting them (Option A) or promoting them (Option B).

## Consequences

- **Positive:** Single HA-facing voice ingress, single mutation boundary, single owner for confirm-before-mutate. Classifier and proxy work is preserved with an explicit review trigger. Phase 1 design has clear seams: memory injection in adapter pre-prompt assembly, confirm gate between tool decision and HA executor, telemetry extensions in adapter event chain.
- **Negative:** `hal-voice-adapter` becomes load-bearing. Requires test coverage and a documented kill-switch path. The "does not own" list must be enforced in code review or it becomes a kitchen sink.
- **Locks in:** adapter as voice ingress; LiteLLM as model gateway with no household mutation authority; classifier as advisory-only when promoted; Mac Ollama as a named hard dependency requiring degraded-mode design before Phase 1 expansion.
- **Defers:** classifier output schema, degraded-mode mechanics, confirm-before-mutate state machine, memory injection mechanics, and full Phase 1 telemetry schema — to named Phase 1 design docs that this ADR requires.

## Security implications

- Concentrating the HA-facing voice surface at one component (`hal-voice-adapter:4003`) means inbound auth requirements live at one boundary. Positive for audit; concentrates blast radius.
- Inbound auth posture for ports 4000, 4001, 4003, 5000 is **out of scope for ADR-005** but is the named follow-on review (separate work item, owner: chatgpt + cowork).
- High-impact tools (e.g. `HassUnlock`) require confirm-before-mutate. The mechanism is Phase 1 work, but the requirement is recorded here. The canonical "must-confirm-before-execute" tool list is also a named follow-on (owner: chatgpt).

## Evidence

- Probe report: `machines/server/PROBE-2026-04-26-voice-path-trace.md` (branch `probe/voice-path-trace-001`, SHA `a25238c`)
- Headline finding: HA at `4003`; `hal-proxy` and `hal-classifier` running but receiving zero traffic; tool schema has single owner; no fallback configured for `hal-14b-q3`
- Live capture: `journalctl -u hal-voice-adapter` 2026-04-23, 4-event telemetry chain confirmed on real `HassTurnOn` request
- ADR-001 (Hermes voice superseded), ADR-002 (adapter owns tool schema), ADR-003 (voice streaming deferred), ADR-004 (stateless mode Phase 0 only)
- Memory: `project_hal_voice.md`, `project_adapter_tool_schema_ownership.md`, `feedback_voice_not_siri_clone.md`, `project_phase1_reshape.md`

## Cleanup tickets derived from this ADR

To be opened after acceptance:

1. `stale-docs`: Update `docs/ARCHITECTURE.md` to reflect VOICE-PATH-TRACE-001 and ADR-005
2. `cleanup`: Fix or remove `docker-compose.yml:126` comment claiming HA always points to 4001
3. `cleanup`: Archive or delete dead `hal-proxy.conf` nginx artifact
4. `architecture`: Mark `hal-proxy` as parked/transitional in `STATUS/ARCHITECTURE`
5. `architecture`: Mark `hal-classifier` as parked/advisory in `STATUS/ARCHITECTURE`; record review trigger
6. `security`: Audit inbound auth and bind posture for ports 4000, 4001, 4003, 5000
7. `security`: Produce high-impact-tools confirmation list, starting with `HassUnlock`

Phase 1 design deliverables required before Phase 1 capability expansion:

8. Classifier output schema design doc
9. Degraded-mode design doc (Mac Ollama unavailability)
10. Confirm-before-mutate state machine design doc
11. Memory injection mechanics design doc
12. Phase 1 telemetry schema extension doc

## Triggers for revisit

- Voice latency p95 regresses by >30%
- A new voice surface (mobile, web) requires a different ingress shape
- Classifier accuracy below threshold (threshold TBD in classifier output schema design)
- Any household incident traced to voice routing
- Mac Ollama outage causing user-visible voice failure (would trigger degraded-mode work if not yet shipped)
- Parked-services review trigger fires (Phase 1 model-routing start OR 2026-07-25, whichever first)

## Acceptance log

- 2026-04-26 — Drafted by Cowork (architect), reviewed by ChatGPT (independent reviewer), accepted and merged by Michael as PR #1 (`c9d1b34`).
- 2026-04-26 — Post-merge review by ChatGPT against 7-point checklist: concur on substance, no requested changes to ADR-005 content. One non-blocking process note (status hygiene) addressed by this amendment. See PR #1 issue comments for the full review.
