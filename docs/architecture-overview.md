# Architecture Overview

HAL is designed as a local-first personal AI assistant with a bounded orchestration system around it. The private implementation combines local services, AI model gateways, project-state tracking, review-controlled automation, and a probe-gated transition toward a unified Hermes agent runtime.

This public overview describes the architecture without exposing private infrastructure details.

## System goals

HAL is intended to support:

- Personal memory and context retrieval
- Project and commitment tracking
- Daily and project-specific briefings
- Human-approved drafting and action preparation
- Voice and Home Assistant-style interaction
- AI-assisted software development workflows
- Safe expansion toward more autonomous task execution
- Runtime portability between local models and agent surfaces

## Core architecture

```text
User surfaces
  -> voice / chat / dashboard interaction
  -> front agent / assistant interface
  -> policy hooks and toolset lockdown
  -> memory / context review queue
  -> planning and drafting skills
  -> approval boundary
  -> local services and external integrations

Development surfaces
  -> GitHub issue / PR state
  -> lane routing labels
  -> architect / code / review agents
  -> bounded execution loop
  -> status notifications
```

## Major components

| Component | Role |
|---|---|
| Assistant persona | Consistent interaction model across surfaces |
| Voice front agent | Fast intake layer for spoken requests, short answers, and safe tool routing |
| Hermes runtime | Candidate unified runtime for tools, memory, delegation, API-server access, and scheduled work |
| Policy hooks | Enforce input filtering, tool allowlists, mutation rules, and safety boundaries |
| Memory review queue | Prevents uncontrolled long-term memory writes |
| Project state layer | Tracks commitments, decisions, roadmaps, and active work |
| Skill layer | Encapsulates repeatable assistant behaviors and output formats |
| Orchestrator | Coordinates work between AI tools and review lanes |
| GitHub state | Canonical project source of truth |
| Notification layer | Sends status, blockers, and completion summaries |
| Local services | Model hosting, home automation, media, and other private integrations |

## Runtime direction

The project started with a dedicated voice adapter that owned the Home Assistant tool schema and mutation boundary. That remains an important fallback and a clean example of safety-first design.

Recent private work has moved toward a probe-gated Hermes convergence path. The goal is to stop building generic agent infrastructure from scratch where a maintained runtime already provides the capability. HAL still owns the policy, safety, validation, and product-specific behavior.

```text
Voice / chat surface
  -> fast front agent
  -> input filters
  -> surface-specific tool allowlist
  -> Home Assistant / memory / briefing / delegation tools
  -> review or confirmation boundary
```

The important invariant is not which process receives the request. The invariant is that every surface has a clear authority boundary.

## Agent layering

The target runtime separates front-desk work from specialist work:

| Layer | Purpose | Constraints |
|---|---|---|
| Front agent | Fast response, intent routing, simple Home Assistant reads/actions, clarification | Small local model, no thinking leakage, locked toolset |
| Specialist agents | Draft automations, summarize complex context, analyze project state | Off-path, delegated, draft/stage only |
| Validator/apply layer | Check staged work and apply approved changes | Human-approved, auditable, rollback-aware |

This avoids using a large reasoning model for every spoken request while still allowing deeper work when needed.

## State model

HAL separates communication surfaces from canonical state.

- Chat is useful for interaction.
- Notifications are useful for awareness.
- GitHub is used for structured project state.
- Local files and services hold machine-specific runtime context.
- Runtime memory is reviewed before becoming durable.

This prevents critical decisions from being trapped in transient conversations.

## Human-in-the-loop boundary

HAL is not designed as an unrestricted autonomous agent. The system uses explicit approval boundaries for:

- Memory writes
- External communication
- Production-impacting changes
- Security-sensitive changes
- Financial, legal, or household-impacting decisions
- Any action where the blast radius exceeds low-risk drafting or summarization

Voice input deserves special care because ambiguous speech, background audio, and imperfect transcription can create unsafe commands. HAL therefore treats voice as an intake surface, not blanket authority.

## Orchestrator role

The orchestrator is not the product. It exists to reduce manual handoff burden while building HAL.

A target workflow looks like this:

```text
Goal defined
  -> GitHub sprint issue created
  -> planning lane reviews scope
  -> code lane implements bounded change
  -> review lane validates output
  -> final state posted back to GitHub
  -> user receives completion or blocker notification
```

## Design tradeoffs

| Decision | Benefit | Tradeoff |
|---|---|---|
| Local-first architecture | Better privacy and control | More operational complexity |
| Hermes runtime convergence | Less bespoke infrastructure, faster capability transfer | Requires careful probes and cutover discipline |
| Fast front agent + specialist agents | Better voice latency and better deep work quality | Requires routing and resource arbitration |
| GitHub as canonical state | Auditable, structured workflow | Less conversational fluidity |
| Human approval gates | Safer automation | Slower fully autonomous execution |
| Multi-agent lanes | Better separation of planning, code, and review | Requires routing discipline |
| Public/private repo split | Recruiter-safe portfolio surface | Public copy is not the full runtime system |

## Portfolio relevance

This architecture demonstrates:

- Systems thinking
- Workflow design
- Automation risk management
- Technical documentation
- AI tool orchestration
- Runtime evaluation and model selection
- Human-centered product constraints
- Practical privacy/security decision-making
