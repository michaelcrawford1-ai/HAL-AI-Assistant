# ADR-010 — Concurrent multi-model execution and resource arbitration

**Status:** Proposed in the private project  
**Scope:** Public-safe summary  
**Decision type:** Runtime/resource architecture

## Context

HAL's target runtime is no longer a single model answering every request. The system is moving toward layered agents:

- a fast front agent for voice and simple routing;
- stronger specialist models for planning, drafting, analysis, and code-oriented work;
- background or delegated workers for bounded tasks;
- local services that may share the same machine resources.

This creates a resource-management problem. If multiple models or agents run at once without coordination, the assistant may become slow, unreliable, or unsafe. Voice interaction is especially sensitive to latency.

## Decision

HAL will treat model execution as a scheduled resource, not as an unlimited background activity.

The target architecture separates model roles:

| Role | Purpose | Resource posture |
|---|---|---|
| Front model | Fast voice intake, short answers, simple tools, clarification | Always preferred for latency |
| Specialist model | Deep reasoning, drafting, automation design, project analysis | Off-path or delegated |
| Utility model | Summaries, classification, extraction, fixtures | Batchable / lower priority |
| External/cloud model | Optional high-capability fallback where allowed | Explicitly selected and policy-gated |

## Policy

The front voice path gets priority. Long-running or heavy model work should not make voice unusable.

Resource arbitration should consider:

- latency sensitivity;
- model size;
- hardware load;
- active voice session state;
- whether a task is interactive or background;
- whether output is draft-only or action-bearing;
- whether a cheaper/faster model is sufficient.

## Consequences

### Benefits

- Keeps voice interaction responsive
- Enables deeper specialist work without making every request slow
- Supports model bakeoffs and measured routing decisions
- Makes local hardware constraints explicit
- Provides a clean path for HAL to build and evaluate its own capabilities

### Tradeoffs

- Requires routing and scheduling discipline
- Adds complexity around queues, priorities, and cancellation
- Requires measurement rather than model choice by preference alone
- Forces the project to define acceptable latency and quality thresholds

## Evaluation requirements

Model and routing decisions should be based on test matrices rather than subjective impressions alone.

For the front voice model, evaluation should include:

- first-token latency;
- total response latency;
- correct tool/no-tool decision;
- correct Home Assistant entity and argument selection;
- no thinking trace leakage;
- no JSON/tool leakage;
- correct clarification behavior;
- correct safety behavior;
- ability to escalate complex work instead of taking unsafe action.

## Public portfolio note

This ADR summarizes the resource-arbitration problem and decision. It intentionally omits private hardware details, local model names that are not useful in a public portfolio context, local paths, and operational configuration.
