# ADR-008 — Multi-lane build automation: orchestrator + Discord ops surface

**Status:** Proposed (drafted 2026-05-11)
**Author:** Cowork architect (Claude.ai)
**Reviewer:** ChatGPT (pending)
**Decider:** Michael
**Companion to:** `docs/COLLAB.md`, `docs/COLLAB_STACK.md`, `docs/SESSION-PROTOCOL.md`, ADR-006

---

## Context

The team's coordination layers — `docs/COLLAB.md` (operating model), `docs/COLLAB_STACK.md` (which tool when), ADR-006 (lane discipline, single-owner-per-artifact, no concurrent design), and `docs/SESSION-PROTOCOL.md` v1.2 (the four-phase session cadence) — describe *what each AI may do* and *how a unit of work passes between them*. They do not describe the *infrastructure* that connects the lanes.

Today, the connective tissue is Michael. He triggers each Cowork session, courriers state when the existing rails don't suffice, decides when to dispatch a Codex audit, opens new sessions after rollover, and walks each PR through review → merge. SESSION-PROTOCOL.md v1.2 is explicit that "live AI-to-AI realtime exchange" and "automation infrastructure beyond local-host typing" are out of its scope.

Earlier attempts at automating the connective tissue (PRs #79, #88, #91, ticket #78) targeted the *desktop UI* — daemon-typed clipboard delivery into the Cowork composer. They mitigated specific failure modes but the underlying surface — the AX-opaque Cowork content webview, the daemon's L4 `prompt_submitted_unverified` ceiling, the silent-absorb-on-selection class of bugs, the Copy-button mis-click on rendered code blocks — proved structurally fragile.

The opportunity is to move connective tissue off the GUI entirely. Every automated lane in the v1 stack has CLI or SDK access without relying on desktop GUI automation: Claude Code CLI for the architect lane (subscription-backed, subject to §2.3 verification), Codex CLI/SDK for subscription-backed OpenAI-side automation, and Claude Code SDK for the code lane (same subscription path). Interactive ChatGPT remains a manual Michael-invoked review surface with GitHub connector access. GitHub already serves as canonical state (session issues, PR comments, the validated `## Architect lane review` / `## ChatGPT review requested` pattern). Discord can serve as the operator's surface — status board, decision queue, and escalation channel reachable from anywhere.

Phase 1 is now far enough along that the per-PR coordination overhead is the dominant cost of forward motion. Codex audits at Phase-exit have caught architectural patterns both architect and ChatGPT lanes approved (H-01, H-02, M-05; `feedback_external_audit_value_for_architect_blind_spots`). Three-lane review is durable but expensive to invoke manually. Session rollovers are currently triggered ad-hoc; context-window degradation in long sessions is a recurring failure mode noted across multiple incidents.

This ADR is the architectural decision to build that connective tissue.

## Scope and precedence

- ADR-006 (lane discipline) is preserved as-is. ADR-008 does not change *what each AI may do*; it provides the infrastructure that lets them do it without the desktop GUI bottleneck.
- `docs/COLLAB.md`, `docs/COLLAB_STACK.md`, and `docs/SESSION-PROTOCOL.md` are preserved as-is. ADR-008 implements the connective tissue v1.2 explicitly punts.
- ADR-008 binds the *infrastructure shape*. Implementation details (specific languages, libraries, deployment mechanics) are non-binding and may evolve in follow-up PRs without an ADR amendment, provided they preserve the invariants in §Decision.

## Decision

### 1. Orchestrator: a single launchd service on the Mac

A small daemon (`hal-orchestrator`) runs as a launchd `KeepAlive` user agent on the Mac that hosts Cowork, Claude Code, and Codex CLI. It maintains local state in SQLite (decision queue, lane statuses, milestone tracking, session ages, dispatch history). Its responsibilities are dispatch, state, and notification — *not* workflow logic. All workflow logic lives in skills in the `hal-coordination` plugin.

The Mac is the host because (a) it co-locates the orchestrator with the lane runners that live there (Claude Code SDK, Codex CLI, the architect's Cowork sessions), (b) it has the Discord client and notification surface Michael already uses, (c) Docker is not required, reducing the operational surface, and (d) GitHub Actions adds cold-start latency and constrains the runtime in ways that hurt rollover automation. The NUC is reserved for HAL runtime services per ADR-005 and is not the right host for build coordination.


### 1.1 Audit log privacy

Every lane-runner invocation is logged to SQLite per Invariant 5 — auditable by Michael at any time. Because that log will contain prompts, response excerpts, code context, repo state, decision text, and potentially credentials captured incidentally in environment dumps, the audit log is bound by a minimum data-handling contract:

- **Redaction at write.** API keys, tokens, secrets, credentials, private keys, cookies, and `Authorization` / `Bearer` / `Cookie` HTTP header values are redacted before the row is inserted. Redaction is identity-preserving — substituted with a `[REDACTED:<class>]` token — so audits can detect that a secret was present without leaking its value.
- **Bounded excerpts by default.** Prompt and response fields are capped at a configurable byte limit (default 8 KB each). Full raw transcripts are written only when the `HAL_ORCH_LOG_RAW=1` debug flag is set explicitly; the flag is disabled by default and is not stored in the standard launchd plist.
- **Retention.** Rows older than a configurable window (default 30 days) are pruned by a daily compaction job. Phase-exit audit briefs that reference older rows refer to them by content hash rather than retaining the row.
- **Local-only.** The SQLite file lives under the orchestrator user account's home directory with `0600` permissions. Backups and exports require explicit Michael-initiated commands. Raw prompts and responses are never posted to Discord or GitHub by the orchestrator.
- **Manual purge.** A `hal-orchestrator purge --since <time>` command wipes rows in a window. Used after debug-flag runs or before sharing a snapshot externally.

The principle: the orchestrator log is a local operator's audit trail, not a corpus.

### 2. Communication backbone: GitHub for state, Discord for the human

GitHub remains canonical state for all AI-to-AI artifacts: session issues, PR comments (with the existing `## Architect lane review` and `## ChatGPT review requested` headers), the `decision-required` label, labels for session phase. The orchestrator never bypasses GitHub for AI-to-AI handoffs; the desktop daemon (PR #79 era) is retired for AI-to-AI traffic. (HAL voice-driven dispatch, if revived, is a separate surface and out of scope for this ADR.)

Discord is the operator's surface. The orchestrator posts to a per-purpose channel layout:

- `#status` — rolling state board: open PRs, lane statuses, session ages, milestone progress
- `#decisions` — pending-approval pings (one message per pending decision, with reasoning)
- `#architect`, `#chatgpt`, `#codex`, `#code` — per-lane activity logs (verdicts posted, audits run, dispatches initiated)
- `#escalations` — anything that needs Michael's attention outside the decision queue (lane disagreements, hard-cap hits, auth failures)

Michael responds via Discord reactions, slash commands, or threaded replies. Manual lane dispatch and rollover triggers are available as slash commands.


### 2.1 Discord authorization contract

Discord is an operator-control surface, not canonical project state. Discord-initiated authority over the orchestrator (approvals, slash commands, rejects) is valid only if all of the following hold:

1. The interaction originates from an allowlisted Discord user ID mapped to Michael.
2. The interaction is tied to a specific decision-package message created by the orchestrator (reaction/button → that package's message ID; threaded reply → that thread).
3. The decision-package message contains the PR number, head SHA, preflight result ID, architect-lane verdict comment ID, Codex verdict comment ID, and any manual ChatGPT verdict comment ID if ChatGPT was invoked for this PR.
4. Before any merge or dispatch, the orchestrator re-validates current GitHub state: PR head SHA still matches the package; required labels and approvals still hold; no new blocking comments or `decision-required` label have appeared since package creation; the branch is mergeable; preflight is still current (re-run if older than a configurable freshness window).
5. Reactions and buttons are single-use and idempotent. Replayed or duplicate approvals are no-ops, never re-triggers.
6. Slash commands are accepted only in configured channels and only from allowlisted Discord user IDs.
7. Every Discord-approved action is mirrored to GitHub as a comment on the relevant PR or issue **before** the action executes. The GitHub comment is the canonical decision record; Discord is the interaction surface.
8. Any ambiguity — unknown interaction shape, stale package, mismatched SHA, missing GitHub mirror, allowlist miss — fails closed and routes to `#escalations`. The orchestrator does not infer intent.

This contract is binding architecturally. Implementation specifics (Discord bot scopes, signature verification, replay-protection mechanism, allowlist storage) may evolve in follow-up PRs without an ADR amendment, provided these invariants hold.


### 2.2 OpenAI-side automation boundary

ADR-008 v1 is **subscription-first**: automated lane runners may only use OpenAI-side capabilities reachable through subscription-backed tooling already available on the host (Codex CLI, Codex SDK). Headless OpenAI API access (separately metered per-token billing) is **not** an automation path in v1.

This binds the lane model:

- **Interactive ChatGPT (project session)** — a manual review surface. Michael invokes it from the ChatGPT project session for high-judgment review and prior-art / scope-research work. It can read GitHub artifacts and post comments when Michael drives. It is **not** a persistent worker, does **not** read or write Discord, and is **not** an orchestrator subprocess.
- **Automated OpenAI-side work** — uses Codex CLI/SDK with Michael's subscription-backed access where available. Codex receives scope-setting briefs from the orchestrator and writes findings back through GitHub-mediated workflows. Codex remains read-only / suggest-mode by default unless a later ADR grants broader authority.

A future headless OpenAI API runner — for example, a per-token ChatGPT lane runner — requires explicit Michael approval and an ADR amendment that names the separate operating and cost model. The hook for that change is preserved in §11.3 but is not part of v1.


### 2.3 Anthropic-side automation boundary

ADR-008 v1 is subscription-first on the Anthropic side as well as the OpenAI side. Automated Anthropic lane runners (architect + Code) must use a Claude Code CLI / headless path authenticated through Michael's existing Claude subscription that does **not** require separately metered per-token API billing.

The preferred candidate is Claude Code CLI headless mode (`claude -p`) with subscription-backed authentication, subject to local smoke-test verification before Phase B/C implementation. Exact auth mechanics — token name, lifetime, setup command, observed billing surface — belong in the Phase B implementation runbook after verification, not in this ADR.

If the only viable headless path requires an API key or separately metered API billing, that path is out of scope for ADR-008 v1 and requires explicit Michael approval plus an ADR amendment that names the separate operating and cost model.

This places the per-milestone Anthropic AI usage budget (§4.5) on the right surface: the subscription quota Michael's interactive Cowork and Claude Code sessions consume, which is what he experiences when running other projects in parallel. The budget would lose meaning if Anthropic-side automation silently leaked onto a metered API surface.

**Pre-flight verification gate (Phase A/B).** Before enabling automated Anthropic lane dispatch, run a local auth/billing smoke test proving that the selected headless invocation path works unattended and consumes the intended subscription quota rather than API credits. Record the exact command, environment variables, observed usage surface, and any failure mode in the runbook.


### 2.4 Browser / desktop UI automation boundary

ADR-008 v1 does **not** rely on ChatGPT Desktop, Chrome, Discord-in-browser, or any visual desktop-control surface as an automated lane runner or authority path. The prior GUI-fragility class (`feedback_daemon_copy_button_mistarget`, `feedback_silent_absorb_is_selection_state`, `project_claude_desktop_ax_opaque`, the PR #79 / #88 / #91 lineage) is retired for AI-to-AI traffic and must not be reintroduced through a different GUI surface.

Browser and desktop-UI use are allowed only as **manual** convenience surfaces for Michael (e.g., Michael opening Discord-in-browser to read `#decisions`, or invoking the ChatGPT Desktop app for a manual review session). Any approval, dispatch, review, or merge-relevant action must be mediated by the orchestrator and mirrored to GitHub canonical state per the §2.1 Discord authorization contract.

Automated OpenAI-side repo work uses Codex CLI/SDK (§2.2). Automated Anthropic-side work uses Claude Code CLI/SDK headless mode (§2.3). Visual control of ChatGPT, Discord, or any browser as an orchestrator subprocess is out of scope for v1.

### 3. Lane runners: each AI in its native habitat

Lane runners are subprocess invocations from the orchestrator. None of them paste through a GUI; all read and write GitHub state directly.

| Lane | Runtime | Trigger surface |
|---|---|---|
| Architect (Cowork) | Claude Code CLI / headless path authenticated through Michael's Claude subscription (preferred candidate: `claude -p` with subscription-backed auth, subject to §2.3 verification gate); `hal-coordination` plugin loaded | Orchestrator subprocess; also wake-on-decision via Cowork session for judgment work |
| ChatGPT interactive | ChatGPT project session with GitHub connector | **Manual Michael-invoked** review surface; not an orchestrator subprocess; no Discord I/O |
| Codex (automated OpenAI-side) | Codex CLI / SDK using Michael's subscription-backed access | Orchestrator subprocess; multiple invocation modes — mid-cycle parallel review, decision-package validation, scope-research support, milestone audit pass 1/2, phase-exit audit |
| Code | Claude Code CLI / SDK headless on the same subscription-backed path as the architect lane (§2.3) | Orchestrator subprocess; hook-driven on `approved-for-amend` PR label |

The architect lane runs *headless* by default for routine PR reviews — verdict posted to GitHub, no Cowork session opened. "Judgment" work surfaced from `#decisions` opens a Cowork session so Michael can talk to the architect directly. The existing `hal-coordination:lane-router` skill is extended to make this distinction; the orchestrator dispatches based on its verdict.

The **Codex lane** has multiple invocation modes (mid-cycle parallel review, decision-package validation, scope-research support, milestone audit, phase-exit audit). All modes are stateless — each invocation reads code and PRs fresh — preserving the cold-eye property at audit time even though Codex also serves as the second mid-cycle reviewer. Mode is set by the orchestrator's scope-setting brief at dispatch (see §5).

**Anthropic-side auth.** The architect and Code lanes both use a Claude Code CLI / headless path authenticated through Michael's Claude subscription. The preferred candidate is `claude -p` with subscription-backed auth, subject to the local smoke-test verification gate in §2.3 before Phase B/C enablement. Exact auth mechanics (token name, lifetime, setup command, observed billing surface) live in the Phase B implementation runbook after verification, not in this ADR. The Claude Agent SDK direct path is rejected for v1 because at the time of authoring it requires `ANTHROPIC_API_KEY` and runs on per-token API billing, which violates the subscription-first constraint. If a future ADR introduces an Agent-SDK-based path or any other API-keyed Anthropic runner, the cost/operating model must be named explicitly per Invariant 10.

### 4. Workflow cadence and autonomy

The orchestrator implements a per-milestone state machine with three Michael-gated boundaries: scope agreement (gate-in), Discord pings on block/decision/breakage (mid-flight), and decision packages before merge (gate-out). The orchestrator never auto-merges and never advances past a Michael-gated boundary without explicit human authorization.

#### 4.1 Milestone scope agreement (gate-in)

A *milestone* is a scope-bounded unit of work with goals, deliverables, dependency graph, and a clock time limit, agreed in writing by all three governance lanes (architect + ChatGPT + Michael) before any execution work begins. Codex does not participate in scope agreement; its role is post-completion audit per §5.

Each milestone is tracked as a GitHub session issue with milestone-prefixed labels. The state machine for each milestone is:

```
0. milestone:scope-pending      Architect proposes scope; ChatGPT reviews
1. milestone:scope-agreed       Both lanes posted explicit "agree" comment
2. milestone:awaiting-go        Awaits Michael's "go" comment on the issue
3. milestone:in-progress        Per-deliverable inner loops execute (§4.2)
4. milestone:awaiting-audit-1   All deliverables merged; Codex pass 1 dispatched
5. milestone:audit-amend        Codex pass 1 found issues; amendment loops via §4.2
6. milestone:awaiting-audit-2   Amendments merged; Codex pass 2 dispatched
7. milestone:done               Codex pass 2 clean; session rollover triggered
```

The scope-agreement artifact declares:

- Goals (what "done" looks like)
- Deliverables (the PRs / docs / probes that comprise the milestone)
- Dependency graph (which deliverables block which — informs §4.4 parallel work)
- Clock time limit (the wall-clock budget for inner loops + audits — anti-thrashing defense)
- **Anthropic AI usage budget** (per-milestone cap on Anthropic-side token usage across all Anthropic invocations — architect headless reviews, Code dispatches, Cowork interactive sessions attributed to the milestone — to prevent any one milestone from burning through Michael's daily/weekly subscription capacity that other projects also depend on)
- Named lanes per deliverable (architect-writes, code-writes, Codex review)
- Exit criteria (the conditions under which `milestone:done` is reached)

Before the scope artifact is finalized, a *scope-research sub-step* runs: prior-art search, comparable-systems analysis, library/framework options, known failure modes from public projects in adjacent spaces. **In v1 this runs as a manual ChatGPT step**: Michael invokes the ChatGPT project session against an orchestrator-generated `scope-research-brief` (the proposed milestone scope + the surfaces it touches) and posts the findings back to the milestone session issue as a comment titled `## Scope research`. Both designers (architect-lane and Michael's manual ChatGPT pass) read the research before scope-agreement verdicts. The orchestrator-generated brief makes this step low-friction without requiring an automated OpenAI API runner; the manual surface keeps the cost-and-quality lever in Michael's hand. Codex may *assist* the research with repo-grounded queries when the prior-art question is repo-local.

#### 4.2 Per-deliverable inner loop

Each deliverable in scope follows one of two write-source flows that converge on the same review loop:

**Architect-writes flow** (mechanical-doc PR pattern: single new file or surgical edit, no new env vars or test surfaces, per `feedback_chatgpt_blockers_amend_thru_code`):

1. Architect commits + opens PR
2. **Codex mid-cycle review** (automated, default). Per §5 invocation mode 1.
3. **Manual ChatGPT review required only for high-stakes PRs**: ADR / VISION / ROADMAP changes, security-touching code, memory-of-record changes, anything carrying the `architecture` or `decision-required` label, or Michael-requested for any other PR. Otherwise optional.
4. Architect amend if blockers
5. Codex re-review (and manual ChatGPT re-review if it was required in step 3)
6. Loop 4–5 until the required review surface verdicts "approve" with no blockers; then decision package per §4.3

**Why Codex as the default secondary on architect-writes flow:** §2.3's subscription-first boundary keeps the automated path on Codex (subscription-backed). Forcing manual ChatGPT on every architect-written PR would re-introduce the per-PR coordination overhead ADR-008 is designed to remove — the orchestrator can only reduce Michael's load if the default review path doesn't depend on his manual invocation. Manual ChatGPT remains the diversity escape hatch for high-stakes work where the union-of-concerns argument from `feedback_review_lane_complementarity` matters most.

**Code-writes flow** (multi-file, new tests, new env vars, ≥30 LOC, or per architect judgment):

1. Architect dispatches via `hal-coordination:code-handoff`
2. Code commits + opens PR
3. **Architect 1st-pass review and Codex review dispatched in parallel.** Codex's invocation mode for this dispatch is mid-cycle review (see §5). Neither lane reads the other's verdict before posting. The orchestrator publishes both verdicts to the PR once both have completed.
4. Amend (architect-self if within architect threshold, otherwise Code via code-handoff)
5. Re-review of the amend, again dispatched in parallel (architect + Codex)
6. Loop 4–5 until both lanes verdict "approve" with no blockers; then decision package per §4.3

**Manual ChatGPT review remains available out-of-band.** Michael may invoke the ChatGPT project session against a PR at any point in the inner loop for high-judgment review or for a third opinion when architect and Codex disagree. Manual reviews post to the PR like any other comment; the orchestrator surfaces them in `#chatgpt` but does not dispatch them.

In both flows: decision package → Michael approval → merge → clean context handoff → next non-blocked deliverable dispatched.

Multiple deliverables within a milestone may be in flight simultaneously when their dependency graph permits. The orchestrator tracks per-deliverable state and dispatches parallel non-blocked deliverables.

**Why parallel reviews:** sequential reviews anchor the second reviewer to the first lane's framing. The H-01 / H-02 / M-05 pattern (`feedback_external_audit_value_for_architect_blind_spots`) showed that once one lane writes "approve," the other lane tilts toward agreement — the union of independent reviews catches more than the intersection of sequenced reviews (`feedback_review_lane_complementarity`). Parallel dispatch preserves lane complementarity. In v1 the two automated lanes are **architect + Codex**; the orchestrator's atomic-publish semantics enforce independence: neither lane sees the other's verdict on the PR until both have posted.
**Publish semantics.** Parallel reviews are dispatched to private staging, not directly to the PR. Each lane runner writes its draft verdict to an orchestrator-owned record (SQLite row or orchestrator-private artifact) keyed to the PR + head SHA + review cycle. Neither lane runner posts to the PR during the private-review phase. Once both verdicts are present in staging, the orchestrator publishes both review comments to GitHub in sequence and records their GitHub comment IDs. After publication, GitHub is canonical; staging records are temporary dispatch state, not project state, and are pruned after the cycle closes.

**One-lane-timeout failure rule.** If one parallel review completes and the other times out or errors past §10's auth-failure backoff, the completed review remains in staging — unpublished — until Michael decides whether to retry the failed lane, publish single-lane (acknowledging the lost independence), or cancel the review cycle. The orchestrator pings `#escalations` with the staged-but-unpublished state and does not silently publish one lane early. This rule keeps parallel-review independence and the GitHub-canonical-once-published invariant compatible with real-world lane failures.


#### 4.3 Decision-package contents

Built when a PR reaches "both lanes approved + preflight clean." Posted to `#decisions`:

- PR reference and title
- Architect-lane verdict (verbatim quote of the GitHub comment)
- Secondary review verdict: Codex automated verdict by default (verbatim quote), plus any manual ChatGPT verdict if Michael invoked ChatGPT for this PR (verbatim quote)
- Preflight result (output of `hal-coordination:pr-preflight`)
- Codex audit result (if applicable — milestone-audit deliverables)
- Recommended action and the reasoning behind it
- Alternatives considered, with the reasoning for rejecting them
- Any lane disagreements, with both sides
- Risk factors, especially around irreversibility, household impact, security, or memory-of-record (the criteria from `docs/COLLAB.md` §Disagreement protocol)

Before the package is posted to `#decisions`, the orchestrator dispatches the `decision-package-validator` skill (**Codex-lane, headless** — see §5 invocation modes). The validator checks: completeness against this §4.3 checklist, framing bias in the recommended-action narrative, missing risk factors, downweighted alternatives, gaps between the stated verdicts and the actual review comments. The validator returns `approved` or `concerns: [list]`. `Concerns` routes the package back to the architect-lane for revision before posting; `approved` releases the package to `#decisions`. The validator is a fast completeness/bias check, not a full PR re-review — it does not re-examine the underlying code, only the package framing. (Codex doing both mid-cycle review and decision-package validation is safe because each invocation is stateless and reads from GitHub fresh; the framing-bias check on the package is a different surface from the code-correctness check on the PR. **Tradeoff acknowledged:** using Codex for both mid-cycle review and decision-package validation is a v1 cost/subscription tradeoff; it is weaker than true cross-lane diversity. Manual ChatGPT review (§4.2 architect-writes flow, high-stakes branch) remains the diversity escape hatch for ADR / security / memory / disputed work where union-of-concerns matters most.)

This step exists because architect-authored decision packages carry architect framing bias; an external completeness check catches this without burning ChatGPT on a full re-review.

Michael approves via Discord (reaction or button), which authorizes the orchestrator to merge. Reject or request-changes routes back to the inner loop.

#### 4.4 Blocking and parallel work

If the inner loop breaks (lane disagreement past §10 hard cap, infrastructure failure, ambiguous scope), or a decision falls outside the orchestrator's authority, or a deliverable blocks waiting on Michael:

- Orchestrator pings `#escalations` (decision needed) or `#decisions` (block needing input) immediately and waits for Michael's response **on that path**.
- Work continues on **non-blocked, non-dependent deliverables within the same milestone**, dispatched per the §4.1 dependency graph.
- If nothing else in the milestone can advance cleanly, all lane work stops; orchestrator transitions the milestone to `milestone:blocked` and pings `#escalations` with a full state summary.

This rule is the core efficiency invariant: blocks on one path do not stall the whole milestone unless every parallel path is also blocked or dependent.

#### 4.5 Clock time and AI usage limits

Every milestone carries two budget caps set at scope-agreement (§4.1): a *clock time limit* (wall-clock budget for inner loops + audits) and an *Anthropic AI usage budget* (per-milestone token cap across all Anthropic-side invocations). Both are anti-thrashing defenses; both share the same soft/hard threshold structure.

**Clock time** is the cumulative wall-clock budget for inner loops + audits, not the calendar window the milestone may span. **Anthropic usage** is the cumulative Anthropic-side token usage across architect headless reviews, Code dispatches, and Cowork interactive sessions attributed to the milestone (Discord posts, memory writes, and other Haiku-class background work are excluded). Codex usage is on Michael's separate OpenAI subscription and is not gated by this cap.

Thresholds (per budget, independently):

- **Soft cap** (default: 80% of agreed budget): orchestrator posts to `#escalations` with a state summary — current deliverable status, remaining work, observed thrash signals, current usage vs cap — and asks whether to continue, pause, or rescope. Work continues until Michael responds.
- **Hard cap** (100% of agreed budget): orchestrator stops dispatch of new deliverable work in the milestone, allows any deliverable already mid-review to finish through the inner loop, and posts to `#escalations` for rescope. Pending deliverables transition to `milestone:blocked`. If both budgets hit hard cap at different times, the first to hit triggers the stop.

Both limits are renegotiable mid-milestone but only via explicit architect + Michael agreement recorded on the milestone session issue (manual ChatGPT review may be invited if the renegotiation is non-trivial).

**Why a separate Anthropic budget:** Michael's Claude subscription is shared across HAL3000 and other projects. A single thrashing milestone can burn the daily or weekly cap and starve unrelated work. Per-milestone budgeting at scope-agreement is the user-facing lever that keeps the AI-cost surface inside Michael's mental model rather than discovered after-the-fact.

#### 4.6 Autonomy ceiling

The orchestrator never auto-merges. Per-deliverable merges require Michael's Discord approval via decision package per §4.3. Autonomy may graduate by category in future ADRs — explicit ADR amendment required.

### 5. Codex cadence: multi-mode lane runner

Codex is the automated OpenAI-side lane (§2.2). It serves multiple invocation modes; each mode has its own scope-setting brief template and is dispatched independently. All invocations are stateless — Codex reads code and PRs fresh on every call.

**Invocation modes:**

1. **Mid-cycle parallel review** (per §4.2). Dispatched when a PR opens or is amended. Codex reads the PR's diff + the surrounding code + the issue body, and posts a verdict comment in parallel with the architect-lane review. Scope brief: PR number, head SHA, related issue, surfaces touched.
2. **Decision-package validation** (per §4.3). Dispatched when architect + Codex mid-cycle reviews both approve. Codex reads the draft decision package and returns `approved` or `concerns: [list]`. Scope brief: the package draft + the two verdict comments + the PR diff. Framing-bias check only, not a re-review of the code.
3. **Scope-research support** (per §4.1). Optional. Dispatched when scope research has a repo-grounded prior-art question ("does our existing memory_store already do X?"). Scope brief: the question + the relevant repo subtree.
4. **Milestone audit pass 1**.
5. **Milestone audit pass 2**.
6. **Phase-exit audit**.

The **audit modes (4–6)** preserve the established cold-eye property because Codex is stateless across invocations — phase-exit Codex does not remember mid-cycle Codex. Independence is preserved by isolation, not by lane identity. Audit modes are the trigger points for the original `feedback_external_audit_value_for_architect_blind_spots` pattern:

- **Audit mode 4 — Milestone audit pass 1** (per §4.1 state `milestone:awaiting-audit-1`). Triggered when all deliverables in a scope-agreed milestone have merged. Codex audits the milestone's merged surface for the architectural patterns that escape architect + ChatGPT review (the H-01 / H-02 / M-05 class — placeholder fields, contract drift, silent coercion, doc-stated-but-not-implemented behavior). Findings open follow-up issues; amendments execute via the §4.2 inner loop and merge under the same decision-package gate.
- **Audit mode 5 — Milestone audit pass 2** (per §4.1 state `milestone:awaiting-audit-2`). Triggered after pass-1 amendments have merged. Confirms the amendments closed all findings and introduced no new ones. Clean pass-2 transitions the milestone to `milestone:done`.
- **Audit mode 6 — Phase-exit audit.** Triggered when a `phase-exit` issue closes. Codex runs a deeper pass across all milestone audits since the prior phase-exit, with cross-milestone pattern detection. Preserves the `feedback_external_audit_value_for_architect_blind_spots` pattern.

The two-pass milestone pattern closes the loop Michael called out: pass 1 catches issues; pass 2 confirms the fix didn't introduce new ones. The phase-exit audit remains the broader integrity check across multiple milestones.

Codex findings that require architectural input open follow-up issues with `decision-required`.

**Codex scope-setting brief — not state handoff.** At every Codex dispatch (across all six invocation modes), the orchestrator writes a mode-appropriate brief to the relevant session issue:

- *Milestone audits (passes 1 and 2):* `CODEX-AUDIT-BRIEF-<milestone>.md` containing the scope-agreement (goals, deliverables, exit criteria), the list of merged PRs with one-line descriptions and architect + Codex verdicts (plus manual ChatGPT verdicts where present), and the architectural surfaces touched (file paths, not code).
- *Phase-exit audits:* a brief covering all milestone audits since the prior phase-exit, with one-line summaries and outstanding findings.

The brief is scope-setting context only — not a state handoff. Codex remains stateless across audits; each audit is a cold-eye read of the actual code and PRs. The brief lets Codex pressure-test the architect + prior-Codex verdicts (and any manual ChatGPT verdicts) directly rather than spending tokens reverse-engineering what was claimed. This preserves the structural independence that makes Codex's external-audit value real (`feedback_external_audit_value_for_architect_blind_spots`).

**Codex model:** deepest available across all audits. Per-audit cost is one-shot and audit quality dominates token cost.

### 6. Session rollover: automated at stop points

The orchestrator triggers session rollovers automatically. A *stop point* is one of:

- A `milestone` ticket closes
- The active Cowork session crosses a context threshold (heuristic: message count + estimated token count)
- Michael invokes the `/rollover` slash command
- A **3-hour** wall-clock cap on continuous Cowork-session activity (default; will be tuned up or down based on observed context-degradation in practice)

On rollover, the orchestrator invokes (in order):

1. **Per-lane handoff artifacts authored in parallel:**
   - `hal-coordination:session-handoff-out` (architect-lane) — writes `NEXT-COWORK-SESSION.md` with live state, pre-flight reminders, open issues snapshot, honest wins/lessons/stale-followups
   - `hal-coordination:chatgpt-handoff-out` — **orchestrator-generated** manual-ChatGPT handoff artifact based on GitHub canonical state, prior manual ChatGPT comments (if any), and the architect's lane summary. Writes `NEXT-CHATGPT-SESSION.md` for Michael to paste/load into a future ChatGPT project session. **Not** authored by a headless ChatGPT runner — there is no headless ChatGPT runner in v1 (§2.2). If a manual ChatGPT session adds a closeout note, the orchestrator includes that as source material rather than implying ChatGPT authorship.
   - Codex receives no session-rollover handoff. Codex remains stateless across audits per §5; cross-audit context flows through the per-milestone audit brief, not through rollover.
2. `anthropic-skills:wrapup` — pushes the session summary to NotebookLM (see §7 for cadence)
3. Closes the current session issue with appropriate session-phase label
4. Opens a new session issue scaffolded by `hal-coordination:session-issue-scaffold`
5. Spawns a fresh Cowork session and Claude Code session pre-loaded with their respective handoff docs. ChatGPT session bootstraps from `NEXT-CHATGPT-SESSION.md` on next dispatch. Codex bootstraps fresh per milestone-audit brief.

Each AI bootstraps from its own lane-specific handoff artifact. The architect does not read ChatGPT's handoff. `NEXT-CHATGPT-SESSION.md` is now a *manual-invocation* artifact: Michael loads it into a fresh ChatGPT project session when he wants ChatGPT context-continuity across his own review sessions. Codex remains stateless across audits — it receives a per-milestone scope-setting brief at audit dispatch but does not carry across rollovers. This removes Cowork auto-memory as a single-pointed cross-session dependency and gives each lane (architect, manual ChatGPT) an independent continuity surface while keeping Codex cold-eye.

The rollover skill and the new `chatgpt-handoff-out` skill both live in `hal-coordination` per §8.

### 7. NotebookLM cadence: batched daily + lightweight rollover snapshots

The `anthropic-skills:wrapup` skill is heavy (full transcript push) and running it on every rollover would dilute signal. Instead:

- **Per-rollover:** lightweight memory save (delta from last rollover, key decisions, open threads) — local to memory dirs, no NotebookLM push.
- **End-of-day:** batched wrapup — full day's session-arc pushed to NotebookLM. Triggered by a daily launchd timer (default 23:00 local), or manually via `/wrapup` slash command.

This is a default; Michael may override the cadence by setting `NOTEBOOKLM_PUSH_CADENCE` in the orchestrator config to `per-rollover` if signal density turns out to be fine.

### 8. Every recurring action becomes a skill

Workflow logic does not live in the orchestrator. Every repeated action is a skill in the `hal-coordination` plugin, callable both by the orchestrator (as a subprocess invocation) and interactively by Michael in a Cowork session. New skills required:

| Skill | Purpose |
|---|---|
| `decision-package` | Build the merge-decision artifact described in §4.3 |
| `decision-package-validator` | **Codex-lane** completeness/bias check on a draft decision package (§4.3) |
| `scope-research-brief` | Generate the orchestrator-side brief Michael feeds to a manual ChatGPT scope-research session (§4.1). Optionally invoked alongside Codex repo-grounded queries. |
| `milestone-codex-audit` | Trigger and process a milestone-close Codex audit, including audit-brief authorship (§5) |
| `phase-exit-codex-audit` | Trigger and process a phase-exit Codex audit (§5) |
| `chatgpt-handoff-out` | Manual-invocation handoff artifact Michael loads into ChatGPT for review continuity (§6) |
| `session-rollover` | The full rollover workflow in §6 |
| `notebooklm-batch-push` | The end-of-day wrapup in §7 |
| `lane-dispatch` | Spawn a lane runner subprocess; thin wrapper, applies model routing per §11 |
| `discord-status-refresh` | Rebuild the `#status` board from live state |

Existing skills are extended where needed:

- `lane-router` — add headless-vs-visible distinction (§3)
- `pr-architect-review` — confirm headless-callable (already partially supported)
- `session-handoff-out` — already exists, used as-is

### 9. Webhook delivery: polling, not inbound tunneling

The orchestrator polls GitHub every 30 seconds for state changes (PR opens, comment posts, issue closes, label changes). Polling is simpler than tunneling (no cloudflared, no smee.io third-party dependency, no inbound port exposure on the Mac), and 30-second latency is fine for a review workflow.

If polling proves insufficient — e.g., the orchestrator misses time-sensitive triggers, or polling causes GitHub rate-limit pressure — switching to a cloudflared tunnel + webhook receiver is a swap-out, not an architecture change.

Polling is reconciliation-based, not pure delta-consumption. On startup and periodically thereafter (default every 5 minutes), the orchestrator rebuilds its working view from GitHub labels, comments, and PR states rather than relying solely on observed deltas. SQLite stores local workflow state and a cache of recently-seen items; GitHub is the source of truth when reconciliation finds a conflict. A missed polling cycle during downtime does not strand items — the next reconciliation catches them.

### 10. Hard caps and escalation

The orchestrator never loops without bound. Per-deliverable and per-milestone hard caps complement the workflow-cadence escalation rules in §4.4 (blocking and parallel work) and §4.5 (clock time limits). Defaults:

- Max **3 amend cycles** per PR before paging Michael (`#escalations`). Triggers parallel-work continuation per §4.4.
- Max **2 lane-disagreement rounds** before paging Michael; lane-convergence-pending is not auto-resolved.
- Any `decision-required` label triggers `#decisions` ping immediately and the orchestrator does not auto-act on the affected artifact until Michael closes the decision.
- Milestone soft cap (§4.5) pings `#escalations` but does not stop work.
- Milestone clock-time hard cap (§4.5) stops new dispatch in the affected milestone; in-flight deliverables drain through the inner loop.
- Milestone Anthropic-usage hard cap (§4.5) stops new Anthropic-side dispatch in the affected milestone; in-flight Anthropic-side reviews drain; Codex-side work may continue if not blocked by the Anthropic-stopped path.
- Auth failures (gh token expired, OpenAI/Anthropic API errors, Discord webhook 4xx) page `#escalations` and the orchestrator backs off the affected lane until cleared.

### 11. Model routing

Lane runners are dispatched as subprocesses; the orchestrator selects model per invocation. This section binds Anthropic-side routing (architect headless lane + Claude Code headless lane) and Codex routing. ChatGPT model selection is determined by Michael's account configuration and is **not** prescribed by this ADR — the ChatGPT lane runner inherits whatever model is configured at the OpenAI account level at dispatch time.

#### 11.1 Anthropic-side routing matrix

Default routing for headless invocations (all Anthropic-side headless invocations route through Michael's subscription-backed Claude Code CLI path per §2.3; quota is the monthly Claude subscription, not API credits):

| Surface | Model |
|---|---|
| ADR / VISION / ROADMAP authorship + review | Opus |
| Decision-package authorship (architect-lane) | Opus |
| Scope-agreement architect participation | Opus |
| Lane-disagreement resolution | Opus |
| Architect-lane PR review when PR touches `decisions/`, `docs/`, `status/`, telemetry schema, security docs; carries `architecture` or `decision-required` label; or is ≥200 LOC across ≥3 files | Opus |
| Architect-lane PR review when PR is well-specified implementation-only (mechanical-doc / impl-from-spec) | Sonnet |
| Code-lane implementation from well-specified handoff | Sonnet |
| Code-lane implementation when handoff is open-ended | Opus |
| `pr-preflight` mechanical checks | Sonnet |
| Skill execution (most) | Sonnet |
| Discord status posts, memory writes, heartbeats | Haiku |

Default if uncertain: **Opus**. Quality-first applies.

Cowork interactive sessions (the architect chat surface) remain Opus by default; the chat surface does not currently expose model selection per turn.

Expected distribution under this matrix: roughly 70% Sonnet / 25% Opus / 5% Haiku by invocation count, with the high-judgment 25% getting Opus. Vs current "Opus for everything," this is a substantial cost reduction without quality loss on the surfaces that matter.

#### 11.2 Codex routing

Codex audits (milestone passes 1 + 2, phase-exit) use the deepest model available. Per-audit cost is one-shot and audit quality dominates.

#### 11.3 OpenAI-side routing

Under the §2.2 subscription-first boundary, ADR-008 v1 binds:

- **ChatGPT interactive** runs in Michael's ChatGPT project session at whatever model that session is configured for; the orchestrator does not select a model here because the orchestrator does not dispatch ChatGPT.
- **Codex** uses its CLI/SDK default model under Michael's subscription; deepest available is preferred where the subscription exposes a selector. Codex cost is one-shot per invocation and bounded by Michael's subscription cap rather than per-token billing.

If a future ADR introduces a headless OpenAI API runner, that ADR will define routing for the metered surface. ADR-008 does not prescribe it.

#### 11.4 Mechanism

Each skill in `hal-coordination` carries a default model in its SKILL.md frontmatter (`default_model: opus | sonnet | haiku`). The orchestrator can override based on per-invocation heuristics — PR file paths, label set, LOC, surface classification. Override logic lives in the orchestrator's routing module (`hal-orchestrator/routing.py`), not in skills.

The override matrix is itself configuration — `model-routing.yml` in the orchestrator config dir, with the §11.1 table as the v1 default. Routine threshold tuning of the matrix does not require an ADR amendment; the matrix is a tuning parameter. The *principle* in §11 is what's load-bearing: judgment-heavy surfaces get Opus, spec-following gets Sonnet, mechanical gets Haiku.

**Downgrade governance.** Changing the *principle* — for example, allowing Haiku on architect-lane PR review, Sonnet on ADR authorship, or any reclassification that drops a judgment-heavy surface below the class specified in §11.1 — requires either an ADR amendment or an explicit Michael approval recorded on a `decision-required`-labeled GitHub issue. The matrix is tunable; the principle is load-bearing.

## Phased build

Each phase is independently shippable and useful. Manual lanes continue in parallel until the automated lane has earned trust.

| Phase | Scope | Earned-trust gate |
|---|---|---|
| A | Orchestrator skeleton on Mac: launchd + SQLite + GitHub polling + Discord webhook out + `decision-package` skill. Lane dispatch is still manual. | One week of clean status-board posting + decision-package generation |
| B | Architect-lane headless runner via Claude Agent SDK. `pr-architect-review` plumbed in. | Five consecutive headless architect-lane reviews are spot-checked by Michael (or by the visible architect lane) against the same PR surface and require no material correction before publication |
| C | Codex-lane runner via Codex CLI/SDK for mid-cycle parallel review + decision-package validation. | Five consecutive parallel reviews (architect + Codex) complete within the configured staging window, with no material missed blockers found when manually re-checked |
| D | Codex milestone audit pass 1/2 + phase-exit audit triggers (separate invocation modes from Phase C mid-cycle review). | One milestone-close audit (pass 1 → amend → pass 2) + one phase-exit audit complete without manual intervention |
| E | Session-rollover automation: handoff-out + wrapup + new-session spawn. | Three consecutive automated rollovers preserve full context into the next session |

Phase A is the load-bearing phase — once the status board and decision queue are working, the manual lanes are still in service, but Michael's coordination overhead drops immediately. Phase E is the highest-risk phase because session-spawn semantics differ across Cowork, Claude Code, and Codex; if the abstraction leaks, it leaks here.

**Phase A does not perform merges.** Decision packages are generated and Michael's responses recorded, but `gh pr merge` remains a manual action (Michael typing the command or invoking it via Cowork or Claude Code) throughout Phase A. Automated merge execution is introduced explicitly in a later phase under its own earned-trust gate; until that phase ships, "Michael approves via Discord" surfaces in `#decisions` and triggers a manual-merge prompt rather than autonomous orchestrator action. This keeps the §4.6 autonomy ceiling enforced through the trust-building phase.

## Invariants the orchestrator must preserve

These are the architectural commitments. Implementation may evolve, but these must hold:

1. The orchestrator **never auto-merges** without Michael's explicit approval via Discord.
2. The orchestrator **never bypasses GitHub** as canonical state. All AI-to-AI artifacts live in GitHub.
3. The orchestrator **never edits ADRs, VISION.md, ROADMAP.md, or COLLAB.md** without explicit human authorship — these surfaces are owner-authored per ADR-006.
4. The orchestrator **never sends money, makes purchases, or executes irreversible household actions** (locks, alarms, anything in `docs/security/high-impact-tools.md`). Household-impacting changes route through the existing voice safety boundary in the adapter, not the build orchestrator.
5. Every lane runner invocation is **logged** to SQLite with its prompt, response excerpt, and dispatched-by reason — auditable by Michael at any time.
6. Hard caps in §10 may **not be raised** without an ADR amendment.
7. Discord commands and approvals are accepted only from allowlisted operator identities, are tied to specific decision-package messages, and are revalidated against current GitHub state before any merge or dispatch action; every approval is mirrored to GitHub before executing (§2.1).
8. Orchestrator audit logs are redacted, bounded-excerpt by default, retention-bounded, local-only, and never treated as canonical project state. Raw transcripts require an explicit debug flag (§1.1).
9. Automated OpenAI-side work uses subscription-backed Codex CLI/SDK only. A headless OpenAI API runner (per-token-metered) is **not** in v1 and requires explicit ADR amendment to introduce (§2.2).
10. Automated Anthropic-side work (architect + Code lanes) runs through a subscription-backed Claude Code CLI / headless path; API-keyed paths that incur per-token billing are out of scope for v1 and require explicit ADR amendment to introduce (§2.3). Exact auth mechanics are implementation-runbook concerns; the architectural invariant is subscription-first.

## Alternatives considered

- **GitHub Actions instead of a Mac daemon.** Zero infra, but cold-start latency (30s–2min) makes the decision-queue ping-back slow, and the runtime constraints (ephemeral filesystem, no persistent SQLite, no Codex CLI) would require workarounds. Picked Mac daemon because the lane runners already live there.
- **NUC instead of Mac.** NUC has Docker Compose already in service, but it's reserved for HAL runtime per ADR-005, and the lane runners (Claude Code, Codex CLI, Cowork) all live on the Mac. Moving them to the NUC would be a bigger change than the orchestrator itself.
- **Keep the desktop daemon (PR #79 lineage).** AI-to-AI via daemon clipboard is structurally fragile (PR #91, ticket #78). The daemon remains useful for HAL voice-driven dispatch if that path is revived; not for AI-to-AI.
- **Phase-exit-only Codex (my original proposal).** Michael's milestone+phase-exit two-pass catches issues earlier, when the surface is small and the fix is cheap. Accepted his refinement.
- **Auto-merge at high-confidence categories.** Rejected for v1 — autonomy starts at zero. Graduation requires ADR amendment.
- **Inbound webhook tunneling (cloudflared/ngrok/smee).** Polling at 30s is sufficient for review workflows and avoids inbound network surface on the Mac. Tunnel is a swap-out if polling proves insufficient.
- **Headless ChatGPT API runner (per-token-metered).** Rejected for v1 per §2.2 — Michael's monthly Claude and ChatGPT subscriptions cover automation needs, and adding metered OpenAI API spend before the subscription envelope is exhausted is not value-positive. Codex covers the automated OpenAI-side surface under existing subscription. Hook preserved in §11.3 for a future ADR if subscription proves insufficient.
- **Claude Agent SDK headless architect runner.** Rejected for v1 per §2.3 — at the time of authoring the Python/TypeScript Agent SDK requires `ANTHROPIC_API_KEY` and runs on per-token API billing, which would re-introduce metered spend on top of Michael's existing Claude subscription. A subscription-backed Claude Code CLI / headless path covers the same surface, and the `hal-coordination` plugin already runs there natively. Hook preserved for a future ADR if Agent SDK gains subscription-auth support or a Claude Code CLI affordance gap forces it.

## Consequences

**Positive:**

- Michael's coordination overhead drops from "trigger and courier every step" to "review decision packages and resolve escalations." The architect lane stops being a forwarding service.
- Three-lane review (architect + ChatGPT + Codex) becomes the default rather than an episodic special case.
- Context-window degradation in long Cowork sessions is mitigated automatically via stop-point rollover.
- NotebookLM signal density improves: daily batched wrapups capture session arc, not noise.
- Every recurring action is codified as a skill, callable by both the orchestrator and Michael directly — the orchestrator is replaceable without losing workflow knowledge.
- Discord becomes a single surface for cross-lane communication, reachable from phone.

**Negative / costs:**

- One new always-on service to operate (~500-1000 LOC plus orchestration glue). New failure modes around auth, polling, Discord webhooks.
- Decision packages need to be *well-built* to be useful; a low-quality decision package is worse than no automation because it shifts review burden onto Michael without giving him the context to act efficiently.
- The orchestrator's SQLite state and the GitHub state must not drift; reconciliation needs to be deterministic. Documented in §10 hard caps but worth watching during Phase A.
- Headless architect-lane runs lose the conversational interface; "judgment" calls that surface mid-review still need to escalate to a real Cowork session. The lane-router distinction in §3 needs to be sharp.

**Locks in:**

- The Mac as the build-coordination host. Migrating to another host requires re-deploying the launchd service and the lane-runner sub-process invocations.
- Discord as the operator surface. Migrating to Slack / Telegram / email would require rewriting the notification layer.
- GitHub as canonical state for AI-to-AI. Migrating to another forge would be a strictly larger change than ADR-008.

**Defers:**

- HAL itself as a build-lane contributor (mentioned in VISION.md capability-transfer trajectory) — out of scope for v1.
- Auto-merge at any autonomy level — explicit follow-up ADR.
- A web UI for the orchestrator — Discord is sufficient for v1; web UI is a possible add-on.
- Anthropic-side Claude Code hooks for automatic ChatGPT review request after architect-lane verdict posts — partially supported in Code SDK today; will be designed in Phase B.

## Evidence

- `feedback_external_audit_value_for_architect_blind_spots.md` — Codex caught H-01, H-02, M-05 after both lanes approved. Justification for §5 milestone+phase-exit cadence.
- `project_claude_desktop_delivery_unsolved_after_pr76.md`, `project_claude_desktop_ax_opaque.md`, `feedback_daemon_copy_button_mistarget.md`, `feedback_silent_absorb_is_selection_state.md` — Justification for §2 retiring the desktop daemon for AI-to-AI.
- `feedback_review_lane_complementarity.md` — Justification for §3 parallel architect + ChatGPT dispatch.
- `feedback_decision_required_close_out_discipline.md` — Justification for §10 `decision-required` never auto-resolving.
- `project_session_protocol_v1.md` v1.2 explicitly puts "automation infrastructure beyond local-host typing" out of scope — this ADR fills that explicit gap.
- `project_hal_coordination_plugin.md` — Existing `hal-coordination` plugin codifies a substantial portion of the workflow; §8 extends rather than replaces it.

## Triggers for revisit

- Discord becomes unreliable as a notification surface (rate limits, account issues, region availability).
- Mac as host is no longer viable (machine retired, replaced, or sustained sleep behavior breaks always-on).
- A second human joins the build loop and the operator-surface assumptions in §2 no longer hold.
- Polling rate-limit pressure or missed triggers make webhook tunneling necessary — §9 swap-out trigger.
- Decision packages prove insufficient in practice; Michael wants either richer context (more in the package) or partial autonomy (auto-merge eligibility). Either requires an ADR amendment.
- A new lane joins the team that doesn't fit the §3 runner pattern.

---

## Decisions made by the architect that Michael should explicitly approve at PR merge

These are the calls I made on the open questions from the prior conversations. Each is a defensible default; flag any you want changed before merge.

1. **§4.1 Milestone scope-agreement participants** — defaulted to architect + ChatGPT + Michael (three-way), with Codex explicitly excluded from scope-setting (only audits post-completion). Reasoning: matches the role split in `docs/COLLAB.md` — Codex is the independent auditor; designers should not also be the auditors that validate their own designs.

2. **§4.1 Research sub-step in scope-agreement — manual ChatGPT + Codex repo-grounded assist** — research runs as a manual ChatGPT project-session invocation against an orchestrator-generated brief, with optional Codex repo-grounded queries when the prior-art question is repo-local. Findings post to the milestone session issue. Reasoning: research is ChatGPT's strongest specialty, but v1's subscription-first boundary (§2.2) keeps the automated lane on Codex; manual ChatGPT preserves the depth without per-token cost.

3. **§4.2 Parallel reviews on initial + amend cycles, with private staging + atomic publish (architect + Codex)** — both architect 1st-pass review and Codex mid-cycle review dispatched in parallel; neither lane sees the other's verdict before posting. Lane runners write draft verdicts to orchestrator-owned private staging keyed to PR + head SHA + cycle; both verdicts publish to GitHub atomically once present in staging. One-lane-timeout pages `#escalations` and holds the completed review in staging until Michael decides. Reasoning: sequential reviews anchor the second reviewer to the first lane's framing; H-01 / H-02 / M-05 caught by Codex after both lanes approved sequentially. Private staging is what actually preserves independence — "lanes write GitHub directly" without staging anchors the second-finisher same as sequential.

4. **§4.3 Decision-package validator (Codex-lane)** — Codex runs a completeness/bias check on the decision-package before it posts to `#decisions`. Reasoning: architect-authored decision-packages carry architect framing bias; quick external check catches this without burning the full mid-cycle review cost. Codex's stateless invocation isolation lets it serve both mid-cycle review and decision-package validation without independence loss.

5. **§4.5 Clock-time-limit thresholds** — defaulted to soft cap at 80% of agreed clock (ping, work continues), hard cap at 100% (stop new dispatch). Reasoning: 80% gives Michael a forewarning before the budget is gone; 100% prevents thrashing past the agreed budget without explicit renegotiation.

6. **§5 "Milestone" boundaries** — defaulted to scope-agreed milestone units rather than per-ticket. Reasoning: Michael's spec frames Codex as triggering "at completion of work needed for milestone" — that's milestone-level, not ticket-level. Pass 1 catches issues, pass 2 confirms the fix.

7. **§5 Codex audit brief, not state handoff** — Codex remains stateless across audits but receives a per-milestone scope-setting brief (scope-agreement + merged PRs + verdicts + surfaces touched). Reasoning: Codex's external-audit value depends on cold-eye perspective; stateful handoff erodes independence. The brief is scope-setting context, not memory carryover — Codex still reads actual code fresh and uses the brief to pressure-test the team's stated verdicts.

8. **§6 Per-lane handoff artifacts at rollover** — architect writes `NEXT-COWORK-SESSION.md`; `NEXT-CHATGPT-SESSION.md` is a manual-invocation artifact Michael loads into a fresh ChatGPT project session for continuity across review sessions; Codex receives no rollover handoff (stateless per §5). Reasoning: cross-session continuity should not single-point on Cowork auto-memory; ChatGPT continuity is opt-in and operator-driven.

9. **§6 Rollover triggers** — defaulted to four triggers: milestone-done close, context threshold, `/rollover` command, and a **3-hour wall-clock cap** on continuous Cowork-session activity. Reasoning: milestone close is the natural stop point; context threshold protects against degradation; wall-clock prevents Michael forgetting; manual slash command for explicit control. **3 hours is the starting cap; will be tuned up or down based on observed context-degradation in practice.**

10. **§7 NotebookLM cadence** — defaulted to batched daily + lightweight rollover snapshots. Reasoning: wrapup-skill is heavy; per-rollover dilutes NotebookLM signal. Daily push captures the day's arc. Configurable via `NOTEBOOKLM_PUSH_CADENCE`.

11. **§9 Webhook delivery** — defaulted to 30-second polling, no tunneling. Reasoning: simplest path, no inbound network surface, easy swap-out if it fails.

12. **§3 Architect headless-vs-visible split** — defaulted to "routine PR reviews headless, judgment work opens a Cowork session, routed by `lane-router`." Reasoning: minimizes Cowork-session churn on routine work while preserving the conversational interface for actual architecture decisions.

13. **§4.6 Autonomy ceiling, with Phase A explicit no-merge execution** — defaulted to zero autonomy per Michael's "start minimum." Decision packages before every merge. **In Phase A, the orchestrator does not execute merges at all** — approval surfaces in `#decisions` and triggers a manual-merge prompt; `gh pr merge` is invoked by Michael directly. Automated merge execution is introduced in a later phase under its own earned-trust gate. No category-based auto-merge for v1; that requires an ADR amendment.

14. **§11 Model routing — dynamic, task-based; subscription-backed Anthropic path** — Anthropic-side: Opus for ADR/VISION/ROADMAP authorship, decision-package authorship, scope-agreement, lane-disagreement, architectural PR review, open-ended Code work. Sonnet for spec-compliance, well-specified implementation, skill execution. Haiku for Discord posts, memory writes, heartbeats. All Anthropic-side headless invocations route through Michael's subscription-backed Claude Code CLI path per §2.3 — quota is the monthly Claude subscription, not API credits. Codex deepest available under subscription. ChatGPT interactive: whatever Michael's project-session is configured for at the time (manual surface — orchestrator does not route). Reasoning: the matrix is dynamic per-task per §11.4 mechanism; the ~70% Sonnet / 25% Opus / 5% Haiku distribution is an estimation that will shift as the team learns which surfaces actually need Opus quality. The routing principle is load-bearing; the distribution numbers are not.

15. **Phasing order** — A → B → C → D → E. Reasoning: orchestrator skeleton + decision-package skill earns trust before adding automated lane runners; rollover automation is last because it's highest-risk.
16. **§2.1 Discord authorization contract** — defaulted to an 8-point contract: allowlisted Discord identity, decision-package-bound interaction, current-GitHub-state revalidation, idempotent reactions, channel-scoped slash commands, GitHub-mirrored before execution, fail-closed on ambiguity. Reasoning: Discord becomes a merge-authority surface in Phase D+; without an explicit auth contract, implementation can drift into trusting any-user-in-channel or any-reaction-on-old-package. The contract pins the invariants and leaves implementation specifics free to evolve.

17. **§1.1 Audit log privacy** — defaulted to identity-preserving redaction at write, 8 KB bounded prompt/response excerpts, 30-day retention, `0600` local-only file permissions, raw transcripts behind a `HAL_ORCH_LOG_RAW=1` debug flag disabled by default, and a `purge` command. Reasoning: the audit log will contain credentials, decision text, and code context; data-minimization from day one is cheaper than retrofitting after a leak, and the orchestrator log should never be confused with canonical project state.

18. **§11.4 Model-routing downgrade governance** — defaulted to: routine threshold tuning of `model-routing.yml` by config PR; any reclassification that downgrades a judgment-heavy surface below its §11.1 class requires either ADR amendment or `decision-required`-labeled Michael approval. Reasoning: the §11.1 principle (judgment-heavy → Opus) is load-bearing; thresholds are tuning, but reclassifying a surface is a principle change and shouldn't slip through as config-PR ergonomics.

19. **§9 Polling is reconciliation-based** — defaulted to: 30-second delta polling plus a periodic (default 5-minute) full reconciliation that rebuilds working view from GitHub labels/comments/PR states. GitHub is source-of-truth on reconciliation conflict. Reasoning: pure delta-polling strands items on missed cycles during downtime; reconciliation is robust against that without taking on the operational burden of a webhook tunnel.
20. **§4.1 + §4.5 Per-milestone Anthropic AI usage cap** — every milestone scope-agreement names an Anthropic-side token-usage budget; orchestrator tracks cumulative usage across architect headless reviews, Code dispatches, and Cowork interactive sessions attributed to the milestone. Soft/hard cap structure parallel to clock-time (80% / 100%). Reasoning: Michael's Claude subscription is shared across HAL3000 and other projects; a single thrashing milestone can starve unrelated work. Per-milestone budgeting at scope-agreement is the user-facing lever that keeps the AI-cost surface inside his mental model rather than discovered after-the-fact.

21. **§2.2 + Invariant 9 OpenAI subscription-first boundary** — automated OpenAI-side work uses Codex CLI/SDK on Michael's subscription. No headless OpenAI API runner in v1; that would require ADR amendment to introduce. ChatGPT interactive remains a manual review surface with no orchestrator dispatch and no Discord I/O. Reasoning: Michael's monthly Claude and ChatGPT subscriptions cover automation needs; adding metered OpenAI API spend before subscription envelopes are exhausted is not value-positive.

22. **§5 Codex multi-mode lane runner** — Codex serves six invocation modes (mid-cycle parallel review, decision-package validation, scope-research support, milestone audit pass 1, milestone audit pass 2, phase-exit audit) with mode-appropriate scope-setting briefs. All invocations are stateless. Reasoning: Codex's external-audit value depends on cold-eye perspective at audit time; statelessness across invocations preserves that even when Codex also serves as the second mid-cycle reviewer. Independence comes from isolation, not from lane identity.

23. **§2.3 + Invariant 10 Anthropic subscription-first boundary** — automated Anthropic-side lane runners (architect + Code) must run through a subscription-backed Claude Code CLI / headless path; API-keyed paths that incur per-token billing are out of scope for v1. Preferred candidate is `claude -p` with subscription-backed auth, subject to a Phase A/B pre-flight smoke-test verification gate before automated lane enablement. Exact auth mechanics are implementation-runbook concerns and intentionally not bound by this ADR. Reasoning: parallel constraint to §2.2 / decision #21; both monthly subscriptions cover automation needs, and the per-milestone Anthropic AI usage budget (§4.5) is meaningful only if it tracks the actual subscription quota Michael experiences. A future Agent SDK lane requires ADR amendment that names the operating and cost model.

24. **§4.2 architect-writes flow secondary-review default** — Codex is the automated secondary reviewer on architect-written PRs; manual ChatGPT review is required only for ADR / VISION / ROADMAP changes, security-touching code, memory-of-record changes, `architecture`-labeled or `decision-required`-labeled PRs, or when Michael explicitly requests it. Reasoning: forcing manual ChatGPT on every architect-written PR re-introduces the per-PR coordination overhead ADR-008 is designed to remove; the orchestrator can reduce Michael's load only if the default review path doesn't gate on his manual invocation. Manual ChatGPT remains the diversity escape hatch for high-stakes work.

25. **§2.4 Browser / desktop UI automation boundary** — ADR-008 v1 does not use ChatGPT Desktop, Chrome, Discord-in-browser, or any visual desktop-control surface as an automated lane runner or authority path. Manual operator use is fine; automation must be API/CLI/SDK-mediated with GitHub canonical state. Reasoning: retires the PR #79 / #88 / #91 / #78 GUI-fragility class for AI-to-AI traffic and prevents it from re-entering through a different GUI surface.

