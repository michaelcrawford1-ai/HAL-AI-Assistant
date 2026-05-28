# ADR-007 — `hal_music` self-hosted music curation agent (architecture)

- **Status:** Accepted (2026-05-06 via PR #118 merge; both lanes converged)
- **Date:** 2026-05-05
- **Lead:** Cowork architect (Claude.ai)
- **Reviewer:** ChatGPT (independent, security/governance)
- **Decider:** Michael
- **Tags:** music | plex | playlist | propose-only | confirm-before-mutate | memory | phase-3 | personal-context | indexer

## Context

A self-hosted music-curation capability, codenamed `hal_music`, has been desired for HAL: build playlists from Michael's actual Plex library in response to natural-language prompts, under HAL's invariants — unified persona, shared memory, confirm-before-mutate, no hallucinated tracks. The intent is to replace PlexAmp's Sonic Sage for HAL-driven curation because Sonic Sage is opaque, cloud-backed, and can hallucinate.

ChatGPT produced a handoff document and Python scaffold zip before this ADR. That work captured the goal but was produced without repo access, so it is goal articulation, not architecture. The originating scaffold collapsed indexing, planning, ranking, and Plex mutation into one Python module. That does not match HAL's decomposition pattern, where stateful long-running concerns are services and reusable stateless logic is library code imported by surfaces. The scaffold also embedded a confirm-before-mutate violation: `PlexAdapter.create_playlist()` could delete and recreate a same-named playlist without a HAL-owned gate.

Issue #123 later clarified Michael's desired earlier MVP: prompt HAL to create a playlist from the current Plex library and have it appear in Plex/Plexamp. Memory-backed taste learning can wait. Future Plex playback control, such as "Hey HAL, play The Simpsons on Plex on Living Room TV," is related but separate.

Constraints that shape this ADR:

1. **Unified-agent thesis (`docs/VISION.md`).** HAL is one persona, one memory, multiple surfaces. Confirm-before-mutate is at the HAL layer. A vertical music agent with its own confirmation gate would fork the seam.
2. **Confirm-before-mutate state machine (`docs/phase-1/confirm-before-mutate.md`).** Today's seam lives in `hal-voice-adapter` and is design-only; #106 implementation is pending.
3. **Roadmap order.** After PR #119, product rollout is Michael-first, architecture remains multi-user-compatible, and HAL-as-build-agent starts early. Music curation may have a Phase 2/3 MVP carveout, but rich `hal_music` remains a controlled-action Phase 3 capability.
4. **Topology.** Plex Server runs on the NUC. Plex library files live on the NAS and are reached through Plex Server, not direct NAS reads by HAL.
5. **Existing pattern for new NUC services.** Recent precedent is T6 `hal-classifier` at `machines/server/hal3000/classifier/` with a systemd unit.

The cost of getting this wrong is high. A music capability that forks confirmation, owns its own memory store, or becomes a parallel agent would be a fifth-rebuild seed.

This ADR fixes the architectural decisions before any code lands. **No code lands in this ADR's PR.**

## Decision

`hal_music` is a HAL capability, not a parallel agent. It decomposes into an indexer service plus an importable library. The full feature is Phase 3, but #123 defines a narrower Phase 2/3 MVP precursor that this ADR governs.

### Component 1 — `hal-music-indexer` service

A small NUC-resident service maintains a local persistent index of the Plex music library.

- **Location:** `machines/server/hal3000/hal-music-indexer/`.
- **Process:** systemd unit at `machines/server/systemd/hal-music-indexer.service` when implemented.
- **Storage:** local SQLite at `/var/lib/hal-music-indexer/index.db` or analogous implementation path.
- **Inbound surface:** none in MVP. Consumers read the index file directly. If localhost HTTP is proposed later, that is a separate explicit design change or ADR amendment because it changes port posture and service-auth requirements.
- **Outbound:** Plex Server API on the NUC, typically `localhost:32400` if co-located.
- **NAS posture:** never read NAS files directly. Plex Server mediates the library.
- **Failure posture:** hold last-good index and surface staleness metadata. Never synthesize track metadata.

SQLite is the default storage posture because ranker/filter queries will need artist, album, track, genre, rating, date-added, duration, play count, and similar fields. JSON can be reconsidered only if implementation proves the index is small and query needs are trivial.

### Component 2 — `hal_music` library

A Python package importable from HAL surfaces. It is stateless per call. It reads the Plex index, proposes playlists, and shapes commands for a surface-layer mutation seam.

- **Location:** `machines/server/hal3000/hal_music/`.
- **Modules, sketch only:**
  - `planner.py` — natural-language prompt plus bounded candidate set to playlist constraints/proposal.
  - `ranker.py` — indexed library to bounded ranked candidate set.
  - `taste_profile.py` — reads taste-profile records and proposes taste-profile updates.
  - `plex_commands.py` — shapes proposal/action payloads for the surface layer. It does **not** call Plex write endpoints directly.
- **Imported by:** voice adapter, Hermes CLI, Discord/Telegram, or future surfaces as they gain music functionality.

The earlier `plex_writer.py` name is rejected for this ADR because it suggests library-owned mutation. If a future implementation uses that name anyway, it must be explicitly documented as a non-mutating command-shaping module until the surface-layer gate executes the write.

### Planner context contract

The planner must not receive the whole Plex library in the LLM prompt. The required flow is:

```text
user prompt → search/ranker → bounded candidate set → planner → candidate playlist
```

Planner input is limited to:

- current user prompt;
- bounded candidate set from the index/ranker;
- relevant read-only taste-profile slice, when the canonical memory retrieval path exists;
- index staleness and ambiguity metadata.

Planner output is a candidate playlist and rationale. It is not a Plex write.

### Mutation seam — surface layer only

`hal_music` produces proposals. It does **not** create playlists, edit playlists, start playback, queue media, change volume, add albums through Lidarr, or write memory.

A HAL surface may execute a Plex mutation only through the same domain-appropriate confirmation machinery as other HAL mutations. For playlist creation, the write path is:

```text
candidate playlist proposal → user preview → frozen action payload → confirmation → surface executes Plex write
```

The confirmation applies to a **frozen playlist action payload**. If the playlist content, name, target library, or write semantics change after preview, the user must see and confirm the revised payload.

Plex writes require T5 (#106) confirm-before-mutate or a deliberately shared confirmation primitive extracted from T5 and reused by `hal_music`. A one-off Plex-specific confirmation system is rejected because it would fork the authority boundary.

### MVP precursor for #123

Issue #123 is the prompt-to-Plex-playlist MVP precursor governed by this ADR. It is not a separate ADR and should not be split into ADR-007a/ADR-007b.

Allowed earlier, before T5:

- read-only Plex music indexer;
- library search over the local Plex index;
- prompt-to-candidate-playlist planning;
- candidate playlist preview;
- dry-run/propose-only mode.

Not allowed before T5 or the shared confirmation primitive:

- creating, editing, deleting, or replacing Plex playlists;
- starting playback on Plex/Plexamp/TV devices;
- writing taste preferences, reactions, or outcomes to HAL memory;
- Lidarr acquisition or library mutation.

The full Phase 3 `hal_music` feature and the #123 MVP share the same architecture. #123 is a phasing carveout, not a divergent design.

### Taste-profile memory boundary

Taste profile is a memory-backed feature, but `hal_music` is not the memory write authority.

- `hal_music` may **read** taste-profile records through the memory subsystem when the canonical retrieval path exists.
- `hal_music` may **propose** taste-profile updates as structured candidate updates.
- Actual taste-profile writes must route through the canonical memory write surface once T3 exists, or through a thin music-specific wrapper that enforces the same gates:
  - active consent;
  - write-disabled flag;
  - per-user partition isolation;
  - T1 telemetry;
  - no raw prompt or raw tracklist leakage;
  - retention category semantics;
  - safety validation for preference records.

Explicit non-goal: T2 storage primitives are not the feature-level write API for personal-context mutation. This mirrors the Plex rule: the library proposes, a HAL-owned seam mutates.

### Telemetry-not-memory boundary

Playlist creation and accept/reject outcomes are telemetry events in the MVP, not memory writes.

In MVP:

- playlist proposal emitted, playlist write requested, playlist write completed/failed, and accept/reject outcomes may produce minimized telemetry;
- these events do not write to user memory, taste profile, or long-lived preference state;
- telemetry must not include raw prompt text, Plex token, raw NAS paths, or full human-readable library dumps;
- tracklist telemetry, if needed, must use minimized identifiers, counts, or hashes according to the Phase 3 telemetry schema.

Taste-profile learning begins only after the canonical memory write path exists and the feature has an explicit write policy.

### Staleness and ambiguity contract

Indexer queries and playlist proposals must surface staleness and ambiguity explicitly.

Implementation must carry concepts equivalent to:

- `index_built_at` — timestamp of the index refresh backing the query;
- `library_section_id` — Plex library section consulted;
- `candidate_count` — number of ranker candidates returned;
- `stale_warning` — boolean plus reason when the index is older than the implementation threshold or degraded because Plex/NAS was unavailable;
- `unavailable_reason` — when no candidate can be produced.

Ambiguous prompts produce clarification or a preview with clear assumptions. They must not silently assume. If there is no last-good index, the planner returns a clear error rather than hallucinating.

### Adjacent capability: Plex media playback/control

Plex media playback and TV/movie/music control are adjacent but separate from playlist curation.

Examples:

```text
Hey HAL, play The Simpsons on Plex on Living Room TV.
Hey HAL, play my sleep playlist on Plexamp.
Hey HAL, pause Plex in the living room.
```

This requires target-device mapping, likely through Home Assistant `media_player` conventions or Plex client discovery, plus its own confirmation/risk policy. It is out of scope for this ADR's playlist-curation commitment and should be handled by a future ADR or implementation note before activation.

Lidarr acquisition is also out of scope and requires a separate ADR because it mutates a different external surface.

### Activation gating

Full activation lands after the relevant prerequisites have merged and deployed:

- T1 telemetry (#101 / PR #112) for event shape and redaction;
- T2/T3/T4 memory store, write path, and retrieval (#102/#104/#105) for taste profile;
- T5 confirm-before-mutate (#106) for Plex writes/playback;
- user identity and permission model sufficient to distinguish personal vs household music context;
- #100 retention amendment semantics for any user-memory/taste-profile writes.

Read-only indexer/planner work may begin earlier under #123 if it remains strictly non-mutating and does not write memory.

### Per-component summary

| Concern | `hal-music-indexer` | `hal_music` library |
|---|---|---|
| Type | systemd service | Python package |
| Location | `machines/server/hal3000/hal-music-indexer/` | `machines/server/hal3000/hal_music/` |
| State | persistent SQLite index | stateless per call |
| Inbound | none in MVP | none |
| Outbound | Plex Server API | none for read/propose path; surface executes writes |
| Owns mutation? | no | no |
| Uses memory? | no | reads/proposes; writes via canonical memory seam only |
| MVP before T5? | yes, read-only | yes, propose-only |
| Writes before T5? | no | no |

### Other invariants

- **No new persona, no parallel agent.** `hal_music` is a capability of HAL.
- **Local-LLM planner first.** Planner uses the existing LiteLLM + Mac Ollama path for MVP. Cloud LLM requires a named future justification.
- **Outbound-only indexer posture.** No new inbound listener in MVP.
- **No full-library prompt stuffing.** Candidate set is bounded before planner/LLM use.
- **One confirmation seam.** Surface-layer gate owns mutation.
- **One memory seam.** Canonical memory write path owns taste-profile persistence.
- **No hidden learning.** Telemetry observations are not preferences unless explicitly routed through the memory write policy.

## Alternatives considered

- **Single Python module.** Rejected: collapses indexing, planning, ranking, memory, and mutation into one place.
- **Library only, no indexer.** Rejected: every prompt would re-scan Plex and create avoidable latency/load.
- **Indexer only, no library.** Rejected: surfaces would duplicate planner/ranker logic.
- **Single service exposing HTTP API.** Rejected for MVP: adds inbound surface for no current value.
- **Separate ADR for #123 MVP.** Rejected: #123 is a phasing carveout under the same architecture, not a separate design.
- **Library-owned Plex writer.** Rejected: forks the confirmation seam.
- **One-off Plex confirmation before T5.** Rejected: calcifies a divergent authority boundary.
- **Direct taste-profile writes to T2 storage.** Rejected: bypasses consent, write-disabled, telemetry, retention, and safety gates.
- **Dump full Plex library into LLM context.** Rejected: token-expensive, privacy-noisy, and unnecessary.
- **Include playback/TV control.** Rejected for this ADR: requires target-device mapping and a separate media-control policy.
- **Include Lidarr acquisition.** Rejected: different mutation surface and higher impact.
- **Use cloud LLM for the planner.** Rejected for MVP per local-first constraints.
- **Keep Sonic Sage as the solution.** Rejected: opaque cloud agent outside HAL's identity/memory/confirmation envelope.

## Consequences

**Positive:**

- HAL's unified-agent thesis remains intact.
- The first useful playlist MVP can be carved out without waiting for taste-profile learning.
- Indexing is separated from planning; slow Plex scans are not repeated per prompt.
- Plex writes are controlled by HAL's existing mutation policy rather than a music-specific gate.
- Taste learning waits for the canonical memory path.
- Future playback/TV control is acknowledged without being bundled into playlist curation.

**Negative:**

- The MVP may initially feel less personal because it cannot learn taste preferences yet.
- Plex playlist creation cannot ship until T5 or a shared confirmation primitive exists.
- The indexer/planner split is unproven until implementation.
- If Plex token scoping is coarse, blast radius relies on local secret handling and no direct mutation until gated.

**Locks in:**

- Two-component split: indexer service + library.
- Indexer at `machines/server/hal3000/hal-music-indexer/`; library at `machines/server/hal3000/hal_music/`.
- SQLite/file-read MVP; localhost HTTP only by later explicit design change.
- Mutation-at-surface invariant.
- Canonical memory write boundary for taste profiles.
- #123 as MVP precursor under the same ADR.
- Bounded candidate set before planner/LLM.
- Frozen candidate payload before confirmation.
- Plex token high-sensitivity posture.

**Defers:**

- Actual code.
- Plex playlist writer implementation.
- Voice/music tool schema.
- Taste-profile schema implementation.
- Distillation of music preferences.
- Playback/TV/media-player control.
- Lidarr acquisition.
- Cloud-LLM planner.

## Taste profile schema sketch

This is a sketch only. The implementation must adapt to the real T2/T3/T4 memory APIs.

| Field | Type | Notes |
|---|---|---|
| `user_id` | str | Owner/partition key or equivalent ownership semantic |
| `preferred_genres` | list[str] | Distilled from explicit user preference writes, not raw prompts |
| `preferred_moods` | list[str] | Same |
| `anchor_artists` | list[str] | Cleaned through implementation-appropriate entity extraction |
| `avoided` | list[str] | Genres/moods/artists/keywords user explicitly rejects |
| `tempo_band_preferences` | list[object] | Time/context-dependent tempo preferences |
| `time_of_day_overrides` | dict[str, dict] | Optional preference context |
| `reactions_distilled` | list[str] | Structured distillation outputs; no raw transcript |
| `last_distilled_at` | timestamp | Distillation cadence trigger |
| `retention_policy` | str | Per user-controlled retention semantics |

The schema is not authorized to bypass the memory write path. `hal_music` proposes updates; the memory layer decides whether and how they are persisted.

## Failure modes

| Failure | Detection | Behavior |
|---|---|---|
| **NAS offline** | Plex errors or empty/missing results for NAS-backed media | Hold last-good index; surface stale warning and index timestamp; do not synthesize. |
| **Plex Server unreachable** | Connection error during refresh/query | Same as NAS offline. If no last-good index exists, return no-index error. |
| **First run with no index** | SQLite file absent | Attempt initial scan; if unavailable, planner returns explicit `no_index_available`. |
| **Library scan errors** | Per-track exceptions or bad metadata | Skip bad records; record skipped count in refresh summary. |
| **No music library** | No Plex music section | Surface `no_music_library_found`; do not raise from init. |
| **Prompt too broad/ambiguous** | Multiple plausible interpretations | Return clarification candidates or preview assumptions; never silent assumption. |
| **Too few matches** | Candidate count below requested duration/size | Return partial proposal with `candidate_count` and explanation. |
| **LLM unavailable** | LiteLLM/Mac Ollama failure | Return explicit error; do not silently fall back unless disclosed. |
| **PLEX_TOKEN missing** | Secret absent at indexer init | Indexer refuses to start; token value never logged. |
| **Confirmation seam unavailable** | Surface attempts Plex write before T5/shared primitive | Return "music mutation gate not enabled"; no write. |
| **Memory-store partition violation** | Detected at memory boundary | Blocked by memory subsystem; `hal_music` does not implement a parallel guard. |

## Security posture

- **No new inbound listener in MVP.** Indexer is outbound-only; library is in-process.
- **PLEX_TOKEN handling.** Store as a NUC-local secret, preferably `/etc/hal-music/plex_token` or equivalent env/secrets file with owner-readable permissions only (`0400` or tighter). Never commit it, log it, emit it in telemetry, include it in prompts, write it to memory, include it in backup docs, or surface it in shared/digest events. Use the narrowest token capability Plex supports, but treat the token as high-sensitivity even if Plex scoping is coarse. Document actual Plex token capabilities during implementation.
- **NAS exposure not broadened.** `hal_music` never directly accesses NAS paths.
- **Telemetry.** New events are drafted during implementation against the live telemetry schema. Expected concepts include proposal emitted, index refresh completed, index stale query, playlist write requested/completed/failed, and taste-profile update proposed/distilled. Sensitive content not logged: raw prompt, full tracklist by default, Plex token, raw NAS paths, raw playback history beyond minimized aggregate counts.
- **Memory write path.** No taste-profile write through T2 storage primitives. Writes route through canonical memory write surface or equivalent wrapper enforcing the same gates.
- **HassPlayMedia analogy.** Future playback inherits the same disruptive-context risk model as media-player actions: target, volume, time, room, bedroom context, and quiet hours matter.
- **NUC blast radius.** Indexer is co-located with Plex Server; mitigations are outbound-only posture, local secret handling, no inbound listener, and no Plex writes before confirmation gate.

## Evidence

- ChatGPT originating handoff archived at `docs/handoffs/hal_music_chatgpt_handoff_2026-05-05.md`. The originating scaffold zip is goal-articulation only and does not define architecture.
- PR #118 ChatGPT review: two-component split accepted, mutation-at-surface accepted, taste-profile write boundary tightened, Plex token scoping wording corrected.
- Issue #123: prompt-to-Plex playlist MVP and future Plex media control. Architect and ChatGPT lanes converged on single ADR + #123 MVP pointer, no split ADR.
- Direct repo inspection confirmed no prior committed music architecture and current NUC/Plex/NAS topology.
- Cross-references:
  - `docs/VISION.md` unified-agent thesis and cross-phase invariants
  - `docs/ROADMAP.md` revised Michael-first roadmap and Phase 3 controlled-action expansion
  - `docs/CONSTRAINTS.md`
  - `docs/COLLAB.md`
  - `docs/phase-1/confirm-before-mutate.md`
  - `docs/phase-1/telemetry-schema.md`
  - `docs/security/port-posture.md`
  - `docs/security/high-impact-tools.md`
  - `decisions/ADR-005-canonical-voice-path-routing-ownership.md`
  - `decisions/ADR-006-multi-agent-collaboration-protocol.md`

## Triggers for revisit

- T5 confirm-before-mutate lands live.
- T2/T3/T4 memory store/write/retrieval land live.
- #123 implementation starts.
- Playlist creation is proposed before T5.
- Plex token model proves meaningfully different from assumed high-sensitivity local-secret posture.
- Plex playback/TV control becomes implementation work.
- Lidarr acquisition is requested.
- Hardware topology changes: Plex moves off NUC, NAS changes, NUC retired.
- Implementation evidence shows the two-component split is wrong.
- A new inbound indexer API is proposed.
- 2026-08-05 routine ADR+90 review.

## Resolved ChatGPT review questions

1. **Two-component split:** accepted.
2. **Indexer storage:** SQLite/file-read MVP accepted.
3. **Indexer inbound surface:** no inbound surface in MVP; localhost HTTP requires later amendment.
4. **Taste-profile writes:** read/propose in `hal_music`; write through canonical memory write surface or equivalent wrapper with same gates.
5. **Originating handoff disclaimer:** existing archived handoff disclaimer is sufficient.
6. **Phase placement:** full feature Phase 3; #123 read/propose MVP precursor may begin earlier under constraints.
7. **Cloud LLM:** deferred.
8. **NAS uptime:** stale-index posture; refuse only when no last-good index or freshness is required and unavailable.

## Acceptance checklist

- [ ] Status flipped to `Accepted` after Michael approves and PR merges to main.
- [ ] Lead/Reviewer/Decider header present.
- [ ] ChatGPT review captured before merge.
- [ ] #123 MVP precursor is referenced and governed by this ADR.
- [ ] Open questions 3 and 4 are resolved in the ADR text.
- [ ] No code under `machines/server/hal3000/hal_music/` or `machines/server/hal3000/hal-music-indexer/` lands in this PR.
- [ ] No ROADMAP edit, ARCHITECTURE edit, dependency change, service unit, or runtime config lands in this PR.
