# Public Roadmap

This roadmap summarizes the public, recruiter-safe direction of HAL without exposing private implementation details.

## Current strategic emphasis — Hermes convergence

The private project recently shifted from building every assistant subsystem bespoke toward a probe-gated Hermes convergence path.

The public-safe version of that decision:

- Keep HAL local-first and review-controlled.
- Prefer maintained runtime capabilities when they satisfy the safety model.
- Supply HAL-specific policy, validation, and approval boundaries instead of rebuilding generic agent infrastructure.
- Use a fast front agent for voice and simple commands.
- Use delegated specialist agents for deeper planning, drafting, and build tasks.
- Preserve rollback paths during runtime cutovers.

This does not mean unrestricted autonomy. It means the project is moving toward a cleaner runtime model where the assistant can eventually use native tools, memory, delegation, and scheduled workflows behind explicit guardrails.

## Phase 0 — Foundation

Goal: establish the basic architecture, local services, project structure, and design principles.

Representative work:

- Define local-first assistant goals
- Establish privacy and approval constraints
- Document architecture direction
- Set up project-state tracking
- Separate HAL product work from orchestrator tooling

Status: substantially complete in the private working repository.

## Phase 1 — Safety and voice baseline

Goal: make the assistant safe enough for low-risk household and project workflows.

Representative work:

- Voice path ownership and routing rules
- Confirm-before-mutate policy
- Ambient and garbled-input handling
- Home Assistant tool boundaries
- Lighting/group/entity discovery
- Rollback flags and burn-in checks
- Basic dashboard and status surfaces

Success criteria:

- Voice input can trigger low-risk assistant workflows
- Household actions are classified by risk
- Mutating actions are approval-gated unless explicitly safe
- Unsafe or ambiguous requests fail closed or ask for clarification
- There is a known rollback path for runtime cutovers

## Phase 2 — Useful assistant core

Goal: make HAL useful for daily assistant work without hiding decisions.

Representative work:

- Daily briefings
- Project summaries
- Commitment tracking
- Follow-up reminders
- Decision summaries
- Draft-only action preparation
- Memory review queue

Success criteria:

- HAL can summarize active work accurately
- HAL can identify open loops and commitments
- HAL can draft next actions without taking them automatically
- User approval remains clear and explicit

## Phase 3 — Hermes runtime convergence

Goal: evaluate and adopt a unified agent runtime where it improves reliability and reduces bespoke code.

Representative work:

- Probe Hermes as a voice/API-server runtime
- Lock voice surfaces to approved tools only
- Filter greetings, ambient noise, and garbled inputs before model execution
- Select a fast local front-desk voice model
- Preserve a stronger delegated model for complex work
- Define model/resource arbitration rules
- Maintain adapter fallback during staged cutover

Success criteria:

- The front agent is fast, concise, and reliable
- Tool calls are structured and auditable
- Unsafe tools are unavailable from voice ingress
- Ambient or garbled inputs do not reach mutation paths
- Streaming, model routing, and delegation are tested before production use

## Phase 4 — Project orchestration loop

Goal: reduce manual handoffs between AI planning, coding, and review tools.

Representative work:

- Structured sprint issues
- Lane labels and routing rules
- Architect/code/review handoffs
- Pull request preflight checks
- Bounded execution loops
- Blocker and completion notifications
- Deduplication and retry logic for handoffs

Success criteria:

- A scoped task can move through at least one multi-lane cycle
- The system stops cleanly when blocked
- Human approval is required for sensitive transitions
- Status remains visible from GitHub

## Phase 5 — Memory and personalization maturity

Goal: improve HAL's ability to help through durable, reviewed context.

Representative work:

- Personal context taxonomy
- Memory write review queue
- Confidence and freshness metadata
- Sensitive-memory handling
- Retrieval quality evaluation
- Session search and summarization

Success criteria:

- HAL remembers useful context without becoming invasive
- Memory is editable, reviewable, and removable
- Sensitive context is handled with stricter rules

## Phase 6 — Expanded automation

Goal: introduce carefully bounded automation for routine workflows.

Representative work:

- Pre-authorized low-risk actions
- Scheduled summaries
- Inbox and notification triage
- Project dashboard concepts
- Local service monitoring
- Home Assistant automation drafting
- Validation/apply/rollback pipeline for staged changes

Success criteria:

- Automation saves time without hiding decisions
- Logs and summaries make actions auditable
- Higher-risk workflows still require approval
- Drafting and applying remain separate steps

## Phase 7 — Portfolio-grade demonstration

Goal: produce a clean public demonstration of the architecture and engineering approach.

Representative work:

- Public-safe documentation
- Sanitized example workflows
- Architecture diagrams
- Demo scripts
- Security model explanation
- Recruiter-friendly project summary

Success criteria:

- Hiring managers can understand the project quickly
- The repo demonstrates systems thinking and technical execution
- No private or sensitive operational material is exposed

## Roadmap note

The private project continues to evolve. This public roadmap is intentionally high-level and omits implementation details that would expose private infrastructure, security posture, household-specific context, or local machine configuration.
