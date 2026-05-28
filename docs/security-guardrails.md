# Security and Privacy Guardrails

HAL is intentionally designed with conservative boundaries. The assistant is meant to become more useful over time, but not by silently expanding authority or storing sensitive information without review.

## Guardrail principles

- Privacy is a product requirement, not an afterthought.
- Long-term memory should be reviewed before becoming persistent.
- External actions require explicit approval unless they are low-risk and pre-authorized.
- Local-first design is preferred where practical.
- The system should fail closed when uncertain.
- Automation should be auditable.
- Higher autonomy requires stronger logging, review, and rollback paths.

## Approval boundaries

| Action type | Default stance |
|---|---|
| Summarizing provided content | Allowed |
| Drafting messages or plans | Allowed as draft-only |
| Writing long-term memory | Requires review queue |
| Sending external communications | Requires explicit approval |
| Changing household automation state | Requires defined safety rules |
| Modifying production services | Requires explicit approval |
| Handling credentials or secrets | Never publish; minimize exposure |
| Financial, legal, medical, or employment decisions | Advise and draft only; human decides |

## Memory model

HAL's memory model should avoid uncontrolled accumulation of sensitive context.

Preferred flow:

```text
Candidate memory detected
  -> classify sensitivity
  -> present for review
  -> user approves, edits, or rejects
  -> only approved memory persists
```

## External communication model

For email, messages, posts, or other external-facing actions:

```text
Assistant drafts
  -> user reviews
  -> user approves or edits
  -> send action occurs only after approval
```

## Public repository sanitation

The public portfolio copy excludes:

- API keys
- Tokens
- Webhooks
- Local file paths
- Machine names and sensitive network details
- Private household context
- Private issue and pull request discussions
- Security-sensitive automation rules
- Operational notes that would make the system easier to attack

## Autonomy levels

| Level | Description | Public stance |
|---|---|---|
| Read-only | Summarize, classify, retrieve, analyze | Safe default |
| Draft-only | Prepare text, plans, and proposed actions | Safe with review |
| Approval-required write | Mutate state after human approval | Allowed in bounded workflows |
| Pre-authorized write | Mutate low-risk state under fixed rules | Requires strong controls |
| Autonomous high-impact action | External or irreversible action without review | Out of scope |

## Practical risk controls

- Explicit stop conditions for automated work
- Usage and time limits for agent loops
- Separate planning, execution, and review roles
- Human-readable status summaries
- No auto-merge for sensitive changes
- No silent expansion of permissions
- No public exposure of private configuration

## Portfolio relevance

These guardrails show the project is not just an AI automation experiment. It is a controlled system design exercise around privacy, reviewability, and bounded autonomy.
