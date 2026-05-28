# Confirm-before-mutate state machine (Phase 1 design)

**Status:** Design only — no implementation in this PR
**Issue:** #13 / ADR-005 §10.10
**Date:** 2026-04-27
**Sources:** ADR-005, `docs/security/high-impact-tools.md` (#44), `docs/security/port-posture.md` (#43), PR #50 coordination note (auth-precedes-confirmation), `docs/phase-1/sprint-plan.md` (PR #49 if merged), `docs/phase-1/classifier-output-schema.md` (PR #51 if merged), project memory

## Purpose

ADR-005 §10.10 names confirm-before-mutate as a Phase 1 design deliverable. The 2026-04-23 ambient-noise probe showed that openwakeword false-fires plus Whisper garble can produce real Home Assistant tool calls. Phase 0 ships partial defense (filter + stateless + garble patterns) but those are not Phase 1 answers.

This document specifies the state machine that gates mutating tool calls inside `hal-voice-adapter`. It consumes the per-tool policy from `docs/security/high-impact-tools.md` (#44) and produces:

- A bounded set of states with explicit transitions.
- Preconditions for entering the state machine at all.
- Confirmation prompt UX shape, timeout, cancel, and ambiguity handling.
- Audit log shape for every transition (input to #15).
- Failure modes when supporting infrastructure is unavailable.
- Defenses against the phantom-trigger class without re-introducing the stateless-mode posture.

This document does **not** implement the gate, change adapter code, or pick a parsing strategy for confirmation utterances. Implementation gates on (a) this doc landing, (b) issue #54 deploy-sync (NUC↔monorepo path verified), and (c) a separate implementation issue for #13. Note: #45 adapter API-key auth has been implemented in PR #50 and is deployed and verified live per `status/server.STATUS.md`.

## Scope

In scope:

- The confirm-before-mutate state machine itself.
- Interaction with #44's confirmation policy (`always` / `contextual` / `never` / `deny-by-default`).
- Interaction with #50's adapter ingress auth as a precondition.
- Phantom-trigger defense without re-entering Phase 0 stateless posture.
- Telemetry contract for #15.

Out of scope:

- Multi-modal confirmation (visual / companion-app).
- Per-user confirmation preferences (Phase 5+).
- Self-healing-intent design (separate Phase 1 thread, not yet ADR-tracked).
- Implementation: storage of pending-confirmation state, parsing strategy, prompt wording beyond the template in #44.
- Confirmation across multiple HA conversation turns spanning >5 minutes (treat that as a new request).

## Preconditions

Before any tool call can enter the state machine, all of these must already be true:

1. **Adapter ingress auth validated.** Per PR #50 / issue #45 (deployed and verified live), the request reached the adapter only because `Authorization: Bearer <ADAPTER_API_KEY>` matched. The state machine assumes auth has already passed; it never validates auth itself.
2. **Tool call resolved.** The LLM has emitted a tool call, the adapter has resolved the tool name, target entity, and arguments via the existing `tool_source.py` + `prompt_builder.py` path.
3. **Tool name is in the schema.** Per `project_adapter_tool_schema_ownership.md`, the adapter injects its own 7-tool schema. Anything outside that schema short-circuits to denial well before this state machine.

If any precondition is false, the state machine is never entered. The adapter rejects the request via the existing pre-handler path.

## Policy lookup

When a tool call is resolved, the adapter consults `docs/security/high-impact-tools.md` (#44) at `(tool_name, entity_domain, args, time_of_day, area)` and gets back one of four policy outcomes:

| Policy outcome | Adapter action |
|---|---|
| `never` | Skip the state machine entirely; execute tool directly. |
| `contextual` (no elevated risk) | Skip the state machine; execute tool directly. |
| `contextual` (elevated risk matched) | Enter state machine at `awaiting-confirm`. |
| `always` | Enter state machine at `awaiting-confirm`. |
| `deny-by-default` | Enter state machine at `denied`; emit safe spoken refusal; never executes. |

Policy lookup is the only entry point. Classifier output cannot affect this lookup. Per #51 invariants and #44 invariants, classifier output is advisory and cannot authorize confirmation success.

## States and transitions

```text
                     ┌──────────────────────────────────────┐
                     │                                      │
                     │     ┌────► confirmed ─► (execute)    │
   (idle) ─► awaiting-confirm                               │
       │             │     │                                │
       │             │     ├────► denied ─► (safe refusal)  │
       │             │     │                                │
       │             │     ├────► expired ─► (safe refusal) │
       │             │     │                                │
       │             │     ├────► canceled ─► (handle new)  │
       │             │     │                                │
       │             │     └────► denied-ambiguous ─►       │
       │             │              (reprompt OR deny)      │
       │             │                                      │
       │             └──────────────────────────────────────┘
       │
       └─► denied-by-default ─► (safe refusal — never reaches awaiting-confirm)
```

### State definitions

| State | Meaning | Terminal? |
|---|---|---|
| `idle` | No pending confirmation. Default state per request. | No |
| `awaiting-confirm` | Tool resolved + policy says confirm. Adapter has emitted confirmation prompt and is waiting for user response. | No |
| `confirmed` | User affirmed the bound action. Adapter executes the tool. | Yes |
| `denied` | User explicitly denied or canceled. Adapter does not execute. Adapter emits safe spoken acknowledgment. | Yes |
| `expired` | Timeout reached without confirmation response. Adapter does not execute. Emits "I didn't hear a response, so I won't do that." | Yes |
| `canceled` | New unrelated request arrived. Pending tool is dropped. New request is handled as a fresh idle-state turn. | Yes |
| `denied-ambiguous` | User response did not parse cleanly as yes or no. In Phase 1 default (zero reprompts), transitions immediately to `denied`. A one-reprompt path remains in the state machine as a feature-flagged option but is not the Phase 1 default. | Yes |
| `denied-by-default` | Policy was `deny-by-default`. Tool never reached `awaiting-confirm`. Emits safe spoken refusal. | Yes |

### Transition rules

| From | To | Trigger | Side effect |
|---|---|---|---|
| `idle` | `awaiting-confirm` | tool resolved + policy = `always` or `contextual+matched` | Bind `(tool, entity, args, request_id, conversation_id, deadline)`; emit confirmation prompt; emit `confirmation_prompt_emitted` telemetry. |
| `idle` | `denied-by-default` | tool resolved + policy = `deny-by-default` | Emit safe spoken refusal; emit `confirmation_denied_by_default` telemetry. |
| `awaiting-confirm` | `confirmed` | next user utterance parses as accept | Execute bound tool; emit `confirmation_confirmed`. |
| `awaiting-confirm` | `denied` | next user utterance parses as reject/cancel | Emit safe acknowledgment; emit `confirmation_denied`. |
| `awaiting-confirm` | `expired` | deadline reached with no user utterance | Drop bound tool; emit "I didn't hear a response"; emit `confirmation_expired`. |
| `awaiting-confirm` | `canceled` | new unrelated user request arrives in same conversation | Drop bound tool; handle new request fresh; emit `confirmation_canceled_by_new_request`. |
| `awaiting-confirm` | `denied-ambiguous` | next user utterance fails to parse cleanly | Phase 1 default (zero reprompts): transition directly to `denied-ambiguous` terminal; emit `confirmation_denied_ambiguous`. Feature-flagged one-reprompt path: remain in `awaiting-confirm` with `attempts += 1`; emit `confirmation_reprompted`. |
| `denied-ambiguous` | `denied` | (feature-flagged path only) reprompt also fails to parse | Emit safe denial; emit `confirmation_denied_ambiguous`. |

Rationale for zero-reprompt default: each reprompt opens an additional ambient-confirm window. The asymmetry rule — false-deny is safer than false-confirm — argues against a free reprompt. The one-reprompt path remains in the state machine for later activation via feature flag once real-world testing confirms it does not increase false-confirm rates.

Confirmed, denied, expired, canceled, denied-ambiguous, and denied-by-default are all terminal — the request ends and the bound tool is either executed once (confirmed) or dropped.

## Bound state contents

When the adapter enters `awaiting-confirm`, it stores per-pending-confirmation:

| Field | Purpose |
|---|---|
| `request_id` | Correlation across telemetry. |
| `conversation_id` | Match incoming utterances to pending confirmation. |
| `tool_name` | Exact tool from the schema (`HassUnlock`, etc.). |
| `entity_id` | Resolved entity from `prompt_builder.py`. |
| `args` | Tool arguments. |
| `policy_reason` | Which #44 policy bucket fired (`always`, `contextual+bedroom`, etc.). |
| `bound_at` | Timestamp. |
| `deadline` | `bound_at + timeout` (see §Timeout). |
| `attempts` | Reprompt counter, starts at 0. |

Critical invariant: **the bound tool is fixed at `awaiting-confirm` entry.** A subsequent confirmation utterance can never broaden the action, change the entity, or alter the arguments. Confirmation is a binary decision over a frozen action.

Confirmation-response matching is multi-field, not single-key: an incoming utterance is matched against the pending confirmation using `(request_id, pending-confirmation token, deadline, conversation_id, source metadata)` together. The `request_id` and `deadline` fields in the table above are load-bearing participants in this match — `conversation_id` alone is insufficient and must not be the sole discriminator in the implementation.

## Timeout policy

| Scenario | Default | Maximum configurable | Rationale |
|---|---|---|---|
| Total wait for response | **15 seconds** | 30 seconds | See rationale below. |
| Behavior on timeout | `expired` → safe spoken refusal | — | Never proceed silently. |
| Reprompt timeout | inherited from total wait | — | Reprompt does not reset the original deadline. |
| Conversation idle eviction | 5 minutes from `bound_at` | — | Drops abandoned pending confirmations even if conversation_id is later reused. |

The 15-second default reflects the ambient-confirmation false-positive argument: the surface area for a false accept scales directly with the listening window. A false denial is recoverable — the user reissues the command — but a false confirmation is not. Halving the default window from 30s to 15s halves the false-confirm surface at low usability cost. Operators who need a longer window for slower speech environments may configure up to 30 seconds. Reprompts do not reset the original deadline in either case — the clock starts when the adapter enters `awaiting-confirm` and does not restart.

## Confirmation utterance parsing

#44 listed accept and reject examples. The state machine treats them as policy input:

| Class | Example utterances | Maps to |
|---|---|---|
| Accept (Phase 1 default) | "yes", "confirm" | `confirmed` |
| Reject | "no", "cancel", "stop", "never mind", "do not" | `denied` |
| Ambiguous | "uh", "hmm", "maybe", off-topic content | `denied-ambiguous` → `denied` (see §State definitions) |
| New request | clearly different intent ("what time is it", "turn on the kitchen lights") | `canceled` |

**Extended-accept set (feature-flagged, default off).** The phrases `"okay do it"`, `"go ahead"`, and `"do it"` are higher false-positive risk under ambient-noise + Whisper-garble and are **not** in the Phase 1 default accept set. They may be enabled via an explicit feature flag subject to all three conditions being met simultaneously:

1. Response arrives within 3 seconds of confirmation-prompt end (immediate post-prompt timing).
2. The utterance contains no content beyond the affirmative phrase itself (no extraneous words or fragments).
3. The feature flag is explicitly enabled (default: off).

If the flag is off, these phrases map to `denied-ambiguous` rather than `confirmed`.

The implementation issue selects the parser. **Background-music interference** is a known concern: music with sung "yes" or "do it" lyrics could parse as accept. Mitigation candidates for the implementation lane: require single-word response; require response within shorter window; lower the parser's confidence threshold for affirmative responses than for negatives. (Asymmetry: false-deny is safer than false-confirm.)

The doc does not pick a final parser. It sets the constraint that **the parser must be asymmetric in favor of denial** — a borderline utterance maps to ambiguous-then-denied, never to confirmed.

## Phantom-trigger interaction

The phantom-trigger pattern observed 2026-04-23:

```text
ambient noise → openwakeword false-fire → Whisper garble → LLM emits tool call
```

How the state machine collapses this class:

1. Tool call resolved against #44 policy.
2. Most phantom calls hit `mutate` tools that policy gates as `always` or `contextual+matched`.
3. Adapter enters `awaiting-confirm` and emits a confirmation prompt over TTS.
4. User did not trigger HAL — they say nothing relevant in the next 15s (default; up to 30s if configured higher).
5. State machine times out → `expired` → tool does not fire.

Two failure modes specific to phantom triggers:

- **Phantom + audible reply.** Background TV/music produces "yes" within the window. Mitigation: asymmetric parser (above), short response window, single-word constraint.
- **Phantom + silent room.** Most realistic case. Timeout cleanly handles it.

The state machine does not eliminate the phantom-trigger class — it reduces blast radius from "real action fires" to "TTS prompt plays + nothing happens." That is the intended Phase 1 outcome. Eliminating phantom triggers entirely is the ambient-noise mitigation thread (separate Phase 1 priority per `docs/ROADMAP.md`).

## Telemetry contract (input to #15)

One terminal event per state-machine traversal. Each event includes:

| Field | Required |
|---|---|
| `request_id` | yes |
| `conversation_id` | yes |
| `tool_name` | yes |
| `entity_domain` | yes (full `entity_id` only if low-sensitivity domain) |
| `policy_reason` | yes |
| `terminal_state` | yes |
| `attempts` | yes (0 or 1) |
| `bound_at`, `terminated_at` | yes |
| `latency_ms` | yes |

The terminal events themselves:

```text
confirmation_confirmed
confirmation_denied
confirmation_denied_ambiguous
confirmation_expired
confirmation_canceled_by_new_request
confirmation_denied_by_default
```

Plus two non-terminal events used during the awaiting-confirm window:

```text
confirmation_prompt_emitted
confirmation_reprompted
```

What **must not** appear in telemetry (consistent with #44 redaction stance):

- Raw transcript content from the user, before or after confirmation.
- Raw tool-call arguments for sensitive entities (lock entity IDs may be redacted to `lock.<area>` granularity if implementation finds full IDs leak too much).
- Auth headers or tokens.
- Confirmation prompt full text (the prompt template is known from this doc; logging the rendered text is unnecessary).

## Failure modes

| Failure | Detection | Adapter behavior |
|---|---|---|
| Auth precondition missing | Should never happen because auth is enforced upstream. If it does (bug), refuse to enter the state machine and log a high-severity event. | Reject before entering state machine. |
| LLM unreachable mid-turn | Connection error during initial tool-call inference | No state machine entered. Standard request-error path. |
| TTS pipeline unreachable | `awaiting-confirm` cannot emit prompt | **Refuse to mutate.** Do not silently execute the bound tool because confirmation could not be requested. Drop pending; emit safe error to HA log. |
| Telemetry sink unreachable | Telemetry write fails | State machine continues; events queue locally; emit a single late event when sink returns. **Do not block confirmation flow on telemetry availability.** |
| Conversation_id collision | Pending confirmation exists when a new request arrives with the same conversation_id but unrelated content | Treat as `canceled` per the awaiting-confirm → canceled rule. |
| Pending confirmation across adapter restart | Adapter restart loses in-memory state | Pending confirmations are dropped. New requests start fresh. **Do not persist pending confirmations across restarts** — restart is treated as conservative reset. |

The two load-bearing safety properties:

- **TTS unreachable does not silently confirm.** If the user cannot be asked, the action is refused.
- **Adapter restart drops pending confirmations.** No state survives restart that could allow a stale confirmation to reach `confirmed` after the user's intent has lapsed.

## Bypass paths

Phase 1 has **no bypass paths** for `always` and `deny-by-default`. The two gates always fire.

`contextual` is not a bypass — it's a policy-shaped decision encoded in #44 (e.g., "don't confirm a light when context is clear"). The state machine respects whatever #44 evaluates; if the policy returns "no need to confirm," the adapter executes directly.

Specifically out of scope for Phase 1:

- Trusted-context shortcuts (e.g., "Michael is at home, skip confirmation").
- Repeat-action implicit confirmation ("you already confirmed this 5 seconds ago").
- Per-user confirmation preferences.

These are Phase 2+ once multi-tenant identity (Phase 5) is real.

## Invariants preserved

These are load-bearing and must survive into implementation:

- **Adapter owns the confirmation seam.** No external service authorizes confirmation. (#44, ADR-005.)
- **Classifier output cannot authorize confirmation success.** Even if classifier emits `confirmed` with confidence 1.0, the state machine ignores it. (#44, #51.)
- **LiteLLM cannot authorize confirmation success.** The model emits the tool call; the user authorizes its execution. (#44.)
- **Auth precedes confirmation.** Confirmation can only be entered for a request that already cleared adapter ingress auth. (#50.)
- **Asymmetric parser favors denial.** Borderline utterances do not authorize mutation.
- **Confirmation infrastructure failure refuses to mutate.** Never proceeds silently.
- **Restart drops pending confirmations.** No stale state spans process boundaries.
- **Bound action is frozen.** Confirmation is binary over a frozen tool/entity/args triple.

## Open questions for ChatGPT review

This is a security-shaped deliverable; per the sprint plan in PR #49, ChatGPT review is **required**. The following questions remain open (questions 1–3 have been resolved per ChatGPT review and Cowork convergence comment 4346251863):

1. ~~**Is 30 seconds the right total-wait window?**~~ **Resolved:** 15s default, 30s configurable max. See §Timeout policy.
2. ~~**Is the asymmetric-parser principle sufficient, or do we want an explicit allowlist?**~~ **Resolved:** Phase 1 uses a strict accept allowlist (`yes`/`confirm`); extended phrases are feature-flagged. See §Confirmation utterance parsing.
3. ~~**Should `denied-ambiguous` reprompt zero times instead of once?**~~ **Resolved:** Zero reprompts is the Phase 1 default; one-reprompt path is feature-flagged. See §State definitions and §Transition rules.
4. **Should `confirmation_prompt_emitted` and `confirmation_reprompted` be the only non-terminal events, or should we also emit a `confirmation_state_entered` per state for richer trace data?** Lean against the per-state firehose (cardinality, redaction surface), but want a second pair of eyes.
5. **Restart-drops-pending — is that the right policy, or should we make pending-confirmations survive a brief restart window (e.g., 60s)?** Lean: drop is safer.
6. **Is the `denied-by-default` state worth keeping separate from `denied`, or should they collapse into one state with a `reason` field?** Lean: keep separate because `denied-by-default` never asks the user — a different observable behavior pattern.

Fallback: if no review in 1–2 sessions, Cowork lane proceeds with the design as written and moves to #14.

## Acceptance checklist for issue #13

- [x] Defines explicit states and transitions.
- [x] Lists trigger conditions per #44 policy outcome.
- [x] Specifies confirmation prompt UX shape.
- [x] Specifies timeout policy and behavior at expiry.
- [x] Specifies cancel and ambiguous-response handling.
- [x] Defines audit log shape (feeds #15).
- [x] States that Phase 1 has no bypass paths for `always` / `deny-by-default`.
- [x] Specifies failure modes when supporting infrastructure is unavailable.
- [x] Defends against the phantom-trigger class without re-introducing stateless mode.
- [x] Defers implementation to a separate issue.

## Cross-references

- ADR-005 §10.10 (`docs/ARCHITECTURE.md`)
- `docs/security/high-impact-tools.md` (#44) — per-tool confirmation policy
- `docs/security/port-posture.md` (#43) — voice-adjacent ports
- `docs/phase-1/sprint-plan.md` (PR #49)
- `docs/phase-1/classifier-output-schema.md` (PR #51) — classifier output is advisory and cannot authorize confirmation
- PR #50 — adapter ingress auth precedes confirmation entry
- Issues #11, #12, #13, #14, #15, #45

Closes #13
