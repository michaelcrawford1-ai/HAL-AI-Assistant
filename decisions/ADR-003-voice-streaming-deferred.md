# ADR-003 — Voice streaming deferred behind two named gates

- **Status:** Accepted
- **Date:** 2026-04-21
- **Deciders:** Architect (cowork), Michael
- **Tags:** voice, streaming, litellm, ha

## Context

Streaming voice responses is desirable: lower perceived latency, more natural conversational feel, partial-output rendering. Two upstream issues block it today:

1. **HA Assist streaming** is not yet end-to-end reliable. The HA-side streaming surface is in motion.
2. **LiteLLM 1.82.6** streams `tool_calls` as `delta.content` text. The tool-call shape is silently broken in streaming mode — tool calls are emitted as conversational text and never invoked.

Either issue alone makes streaming voice produce subtly wrong behavior. Together they make it actively dangerous (a streamed tool call that doesn't fire is worse than a delayed one that does).

## Decision

Voice streaming is **deferred**. Phase 0 voice adapter operates non-streaming.

Streaming will not be enabled until **BOTH** gates clear:

- **Gate A:** HA Assist streaming end-to-end works.
- **Gate B:** LiteLLM Ollama streaming `tool_calls` is fixed (or the project has migrated off LiteLLM).

Both gates must clear independently. Either alone is insufficient.

## Alternatives considered

- **Custom streaming pipeline bypassing LiteLLM.** Rejected — too much surface area for Phase 0; LiteLLM upgrade or migration is cheaper when timed right.
- **Stream conversational text only, never streaming tool calls.** Rejected — the model emits both interleaved; cannot reliably split.

## Consequences

- **Positive:** No silently-broken tool calls in streaming mode. Phase 0 voice has predictable behavior.
- **Negative:** Latency feels worse than it could. Acceptable for Phase 0.
- **Locks in:** non-streaming as the default voice operating mode for now.
- **Defers:** any streaming-dependent UX work.

## Evidence

- Memory: `feedback_qwen3_tool_call_format.md` — LiteLLM 1.82.6 streams tool_calls as delta.content text
- Memory: `project_hal_voice_streaming_deferred.md`

## Triggers for revisit

- LiteLLM upstream releases a fix
- Migration off LiteLLM completes (e.g., direct Ollama integration)
- HA Assist ships verified end-to-end streaming
