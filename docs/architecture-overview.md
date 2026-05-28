# Architecture Overview

HAL is designed as a local-first personal AI assistant with a bounded orchestration system around it. The private implementation combines local services, AI model gateways, project-state tracking, and review-controlled automation.

This public overview describes the architecture without exposing private infrastructure details.

## System goals

HAL is intended to support:

- Personal memory and context retrieval
- Project and commitment tracking
- Daily and project-specific briefings
- Human-approved drafting and action preparation
- Voice and home-assistant style interaction
- AI-assisted software development workflows
- Safe expansion toward more autonomous task execution

## Core architecture

```text
User surfaces
  -> assistant interface
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
| Memory review queue | Prevents uncontrolled long-term memory writes |
| Project state layer | Tracks commitments, decisions, roadmaps, and active work |
| Skill layer | Encapsulates repeatable assistant behaviors and output formats |
| Orchestrator | Coordinates work between AI tools and review lanes |
| GitHub state | Canonical project source of truth |
| Notification layer | Sends status, blockers, and completion summaries |
| Local services | Model hosting, home automation, media, and other private integrations |

## State model

HAL separates communication surfaces from canonical state.

- Chat is useful for interaction.
- Notifications are useful for awareness.
- GitHub is used for structured project state.
- Local files and services hold machine-specific runtime context.

This prevents critical decisions from being trapped in transient conversations.

## Human-in-the-loop boundary

HAL is not designed as an unrestricted autonomous agent. The system uses explicit approval boundaries for:

- Memory writes
- External communication
- Production-impacting changes
- Security-sensitive changes
- Financial, legal, or household-impacting decisions
- Any action where the blast radius exceeds low-risk drafting or summarization

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
- Human-centered product constraints
- Practical privacy/security decision-making
