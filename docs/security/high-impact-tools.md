# High-impact Home Assistant tool confirmation list

**Status:** Policy input for design — no implementation in this PR  
**Issue:** #10 / ADR-005 §10.7  
**Date:** 2026-04-27  
**Sources:** ADR-005, VOICE-PATH-TRACE-001, `adapter/tool_source.py`

## Purpose

ADR-005 requires confirm-before-mutate before Phase 1 expands voice capability. This document ranks the current `hal-voice-adapter` Home Assistant tool schema by household impact and defines the initial confirmation policy that should feed the confirm-before-mutate state-machine design (#13).

This document does **not** implement confirmation gating. It is a policy input for later design and implementation.

## Current tool schema

Current static voice tools from `machines/server/hal-voice-adapter/adapter/tool_source.py`:

| Tool | Type | Mutation? |
|---|---|---|
| `HassGetState` | HA state read | No |
| `HassTurnOn` | HA service mutation | Yes |
| `HassTurnOff` | HA service mutation | Yes |
| `HassSetTemperature` | HA climate mutation | Yes |
| `HassLock` | HA lock mutation | Yes |
| `HassUnlock` | HA lock mutation | Yes |
| `HassPlayMedia` | HA media mutation | Yes |

## Policy vocabulary

| Policy | Meaning |
|---|---|
| `never` | Confirmation not required for this tool category. The adapter may still refuse ambiguous requests. |
| `contextual` | Confirmation required only when entity, value, time, area, or domain makes the action higher impact. |
| `always` | Confirmation required before execution. |
| `deny-by-default` | Do not execute by voice until a later design explicitly permits it. |

Reversibility scale:

| Reversibility | Meaning |
|---|---|
| Instant | Easy to reverse immediately through another voice command or UI action. |
| Minutes | Reversal may take time or cause temporary household disruption. |
| Physical action | Reversal may require someone to physically intervene. |
| Security-sensitive | Reversal may be impossible after exposure, entry, or access occurs. |

Impact scale:

| Score | Meaning |
|---:|---|
| 1 | Low nuisance risk |
| 2 | Minor household disruption |
| 3 | Meaningful comfort, privacy, or cost impact |
| 4 | Safety, security, or significant household disruption |
| 5 | Physical-security or irreversible/high-consequence impact |

## Tool ranking

| Rank | Tool | Impact | Reversibility | Confirmation policy | Rationale |
|---:|---|---:|---|---|---|
| 1 | `HassUnlock` | 5 | Security-sensitive | `always`; consider `deny-by-default` for exterior locks until #13 lands | Unlocking a door/deadbolt can allow unsupervised entry or exit, intruder entry, or unauthorized access. A mistaken unlock cannot be fully undone after exposure. ADR-005 names this as high-impact. |
| 2 | `HassLock` | 4 | Physical action / minutes | `always` for exterior locks; `contextual` for noncritical locks | Locking can secure the home, but accidental lock actions can lock people out or interfere with access. Lower risk than unlock, but still physical-security state. |
| 3 | `HassSetTemperature` | 3 | Minutes | `contextual` | Climate changes affect comfort, cost, sleep, and potentially pipes/heat safety. Confirmation should depend on value, delta, target entity, and mode if mode control is added later. |
| 4 | `HassTurnOff` | 2–4 | Instant to physical action | `contextual` | Turning off lights is usually low risk. Turning off cameras, network gear, heaters, medical devices, pumps, refrigerators, or safety-adjacent switches can be high impact. |
| 5 | `HassTurnOn` | 2–4 | Instant to physical action | `contextual` | Turning on lights is usually low risk. Turning on heaters, pumps, appliances, garage-related devices, or high-load switches can be high impact. |
| 6 | `HassPlayMedia` | 1–3 | Instant | `never` by default; `contextual` for disruptive contexts | Usually nuisance-only. Can become disruptive at night, on shared speakers, at high volume, or in bedrooms or sleep areas if volume/entity context exists. |
| 7 | `HassGetState` | 1 | N/A | `never` | Read-only. Confirmation is not required, but the adapter should still refuse ambiguous or proactive state reads. |

## Default confirmation requirements

### Always confirm

The adapter should require explicit confirmation before executing:

- `HassUnlock` for any lock entity.
- `HassLock` for exterior locks, deadbolts, garage-connected locks, or any access-control lock.

### Contextually confirm

The adapter should require confirmation when context indicates elevated risk:

- `HassSetTemperature`
  - target temperature outside configured safe/comfort band;
  - large temperature delta;
  - bedroom or sleep-related climate entity;
  - any future mode change such as heat/cool/off/emergency heat.
- `HassTurnOn`
  - entity domain or friendly name suggests heater, pump, appliance, garage, oven/stove, high-wattage load, security device, camera, or automation;
  - action occurs during quiet hours or sleeping hours and affects bedrooms or sleep areas;
  - target is ambiguous but potentially high impact.
- `HassTurnOff`
  - entity domain or friendly name suggests camera, alarm, network, router, server, medical device, refrigerator/freezer, heater, HVAC, pump, or safety device;
  - action affects a whole area rather than a single light;
  - target is ambiguous but potentially high impact.
- `HassPlayMedia`
  - target is bedroom or shared speaker during quiet hours;
  - requested media could be disruptive and volume context is unavailable;
  - future tool arguments add volume, announcement, broadcast, or group playback.

### Never require confirmation by default

The adapter should not require confirmation for:

- `HassGetState`, because it is read-only.
- low-risk `HassTurnOn` / `HassTurnOff` for clearly resolved light entities.
- normal `HassPlayMedia` on explicitly requested media player targets outside quiet/disruptive context.

### Deny-by-default until explicit later design

The adapter should deny these by voice until a later design explicitly allows them:

- unlocking exterior doors without a mature confirmation state machine;
- opening garage doors, gates, or access points if future tools/entities enable them;
- disabling alarms, cameras, locks, leak sensors, smoke/CO sensors, or other security/safety systems;
- turning on ovens, stoves, space heaters, high-wattage loads, or other hazardous devices;
- service calls outside the approved static tool schema;
- any tool call with unresolved or low-confidence entity binding where the target might be high impact.

## Initial confirmation prompt requirements

The confirmation prompt should be concise, explicit, and bound to a single pending tool call.

Template:

```text
I heard: <action> <resolved entity/display name>. Confirm: yes or no?
```

Examples:

```text
I heard: unlock front door. Confirm: yes or no?
I heard: lock back door. Confirm: yes or no?
I heard: set bedroom thermostat to 76 degrees. Confirm: yes or no?
I heard: turn off security camera. Confirm: yes or no?
```

Minimum requirements for #13:

- Confirmation must bind to the exact tool name, resolved entity, arguments, and request ID.
- Confirmation must expire quickly.
- Silence, timeout, ambiguity, or unrelated follow-up should deny/cancel by default.
- A new unrelated request should clear the pending confirmation.
- Confirmation outcome must be logged without storing unnecessary sensitive transcript content.
- Classifier output must not authorize confirmation success.
- LiteLLM must not authorize confirmation success.
- The adapter owns the confirmation seam and final household mutation boundary.

## Accepted and rejected confirmation utterances

Final utterance parsing belongs in #13, but this list is the recommended starting point.

Accepted examples:

- yes
- confirm
- do it
- go ahead

Rejected/canceling examples:

- no
- cancel
- stop
- never mind
- do not

Ambiguous responses should either deny or re-prompt once, depending on the #13 state-machine design. They should not execute the pending tool.

## Telemetry inputs for #15

The later telemetry schema should include at least:

- `confirmation_required`
  - tool name
  - entity domain
  - risk category
  - confirmation policy: `always`, `contextual`, or `deny-by-default`
  - correlation/request ID
- `confirmation_outcome`
  - outcome: confirmed, denied, timeout, canceled, ambiguous
  - tool name
  - entity domain
  - correlation/request ID

Avoid logging full auth headers, secrets, long raw transcripts, or unnecessary household-sensitive content by default.

## Follow-up issue candidates

If accepted, this document should feed:

- #13 — confirm-before-mutate state machine;
- #15 — telemetry schema extension;
- a later implementation issue for adapter confirmation gating;
- a later implementation issue for entity/domain risk tagging, if the adapter cannot currently distinguish low-risk light actions from high-risk switch/device actions.

## Non-goals

This document does not:

- implement confirmation gating;
- change tool schema;
- change HA permissions;
- add new tools;
- decide final confirmation UX beyond initial prompt requirements;
- solve entity grounding;
- authorize Phase 1 capability expansion by itself.

## Acceptance checklist for issue #10

- [x] Ranks each mutating tool by household impact.
- [x] Includes `HassUnlock` as the highest-impact tool.
- [x] Includes reversibility assessment.
- [x] Defines confirmation policy: `always`, `contextual`, `never`, or `deny-by-default`.
- [x] Includes rationale for each tool.
- [x] Leaves implementation to #13 and later implementation work.
