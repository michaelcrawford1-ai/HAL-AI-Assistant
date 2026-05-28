# Public Roadmap

This roadmap summarizes the public, recruiter-safe direction of HAL without exposing private implementation details.

## Phase 0 — Foundation

Goal: establish the basic architecture, local services, project structure, and design principles.

Representative work:

- Define local-first assistant goals
- Establish privacy and approval constraints
- Document architecture direction
- Set up project-state tracking
- Separate HAL product work from orchestrator tooling

Status: partially complete in the private working repository.

## Phase 1 — Useful assistant core

Goal: make HAL useful for low-risk daily assistant work.

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

## Phase 2 — Project orchestration loop

Goal: reduce manual handoffs between AI planning, coding, and review tools.

Representative work:

- Structured sprint issues
- Lane labels and routing rules
- Architect/code/review handoffs
- Pull request preflight checks
- Bounded execution loops
- Blocker and completion notifications

Success criteria:

- A scoped task can move through at least one multi-lane cycle
- The system stops cleanly when blocked
- Human approval is required for sensitive transitions
- Status remains visible from GitHub

## Phase 3 — Home and voice surfaces

Goal: add natural interaction surfaces while maintaining approval and safety boundaries.

Representative work:

- Voice interface planning
- Home Assistant integration patterns
- Household command classification
- Safe mutation boundaries
- Ambient context handling

Success criteria:

- Voice input can trigger low-risk assistant workflows
- Household actions are classified by risk
- Mutating actions are approval-gated unless explicitly safe

## Phase 4 — Memory and personalization maturity

Goal: improve HAL's ability to help through durable, reviewed context.

Representative work:

- Personal context taxonomy
- Memory write review queue
- Confidence and freshness metadata
- Sensitive-memory handling
- Retrieval quality evaluation

Success criteria:

- HAL remembers useful context without becoming invasive
- Memory is editable, reviewable, and removable
- Sensitive context is handled with stricter rules

## Phase 5 — Expanded automation

Goal: introduce carefully bounded automation for routine workflows.

Representative work:

- Pre-authorized low-risk actions
- Scheduled summaries
- Inbox and notification triage
- Project dashboard concepts
- Local service monitoring

Success criteria:

- Automation saves time without hiding decisions
- Logs and summaries make actions auditable
- Higher-risk workflows still require approval

## Phase 6 — Portfolio-grade demonstration

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

The private project continues to evolve. This public roadmap is intentionally high-level and omits implementation details that would expose private infrastructure, security posture, or household-specific context.
