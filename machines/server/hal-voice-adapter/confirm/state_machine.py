"""Confirm-before-mutate state machine (T5 / #106).

Implements the 8-state machine from confirm-before-mutate.md §States and
transitions.  Every resolved tool call enters gate_tool_call(); the caller
learns from ConfirmationOutcome whether to execute the bound tool.

Two-turn HTTP flow (Amend 2 / Option B):
  gate_tool_call() returns immediately with terminal_state="awaiting" and
  awaiting_prompt populated. The adapter returns this prompt as HTTP response
  content; HA TTSes it through its voice pipeline. The next HTTP request
  (confirmation turn) calls deliver_utterance(), which resolves synchronously
  and returns the terminal ConfirmationOutcome.

Key invariants (per confirm-before-mutate.md §Invariants preserved):
  - Adapter owns the confirmation seam.
  - Classifier output cannot authorize confirmation success.
  - LiteLLM cannot authorize confirmation success.
  - Auth precedes confirmation.
  - Asymmetric parser favors denial.
  - Confirmation infrastructure failure refuses to mutate.
  - Restart drops pending confirmations (in-memory only; no persistence).
  - Bound action is frozen (tool/entity/args triple is immutable after bind).
"""
from __future__ import annotations

import logging
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from hal_telemetry import emit

from .errors import TtsUnreachableError
from .models import (
    BoundConfirmation,
    ConfirmationOutcome,
    ConfirmationParse,
    PolicyOutcome,
)
from .parser import parse_confirmation_utterance
from .policy import lookup_policy

logger = logging.getLogger("confirm.state_machine")

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Per confirm-before-mutate.md §Timeout policy: 15s default, 30s max.
# "Reprompt does not reset the original deadline."
_DEFAULT_TIMEOUT_SECONDS = 15
_MAX_TIMEOUT_SECONDS = 30


def _load_timeout() -> int:
    val = int(os.environ.get("HAL_CONFIRM_TIMEOUT_SECONDS", str(_DEFAULT_TIMEOUT_SECONDS)))
    if val > _MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"HAL_CONFIRM_TIMEOUT_SECONDS={val} exceeds maximum {_MAX_TIMEOUT_SECONDS}s. "
            f"Per confirm-before-mutate.md §Timeout policy."
        )
    return val


def _one_reprompt_enabled() -> bool:
    """Feature flag: HAL_CONFIRM_ONE_REPROMPT (default off).

    Per confirm-before-mutate.md §State definitions and §Transition rules:
    "zero reprompts in Phase 1 default; one-reprompt path feature-flagged
    behind HAL_CONFIRM_ONE_REPROMPT (default off)."
    """
    return os.environ.get("HAL_CONFIRM_ONE_REPROMPT", "").lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Low-sensitivity domain allowlist for entity_id in telemetry
# Per telemetry-schema.md §3 sensitivity rules and confirm-before-mutate.md
# §Telemetry contract: entity_id only if low-sensitivity domain.
# ---------------------------------------------------------------------------

_LOW_SENSITIVITY_DOMAINS: frozenset[str] = frozenset({
    "light", "switch", "input_boolean", "sensor", "binary_sensor",
    "media_player", "climate",
})


def _entity_id_for_telemetry(entity_id: str, entity_domain: str) -> Optional[str]:
    """Return entity_id only for low-sensitivity domains; else None."""
    if entity_domain in _LOW_SENSITIVITY_DOMAINS:
        return entity_id
    return None


def _entity_domain(entity_id: str) -> str:
    return entity_id.split(".", 1)[0] if "." in entity_id else entity_id


# ---------------------------------------------------------------------------
# Spoken refusal strings
# ---------------------------------------------------------------------------

_REFUSAL_DENIED = "Okay, I won't do that."
_REFUSAL_DENIED_AMBIGUOUS = "I didn't catch a clear yes or no, so I won't do that."
_REFUSAL_EXPIRED = "I didn't hear a response, so I won't do that."
_REFUSAL_CANCELED = "Got it, I'll handle your new request."
_REFUSAL_DENIED_BY_DEFAULT = "I'm not able to do that by voice."
_REFUSAL_TTS_UNREACHABLE = "I can't ask for confirmation right now. I won't make that change."


# ---------------------------------------------------------------------------
# State machine
# ---------------------------------------------------------------------------

class ConfirmationStateMachine:
    """Single-conversation-at-a-time confirm-before-mutate state machine.

    Phase 1 is single-tenant; not engineered for concurrent conversations per
    confirm-before-mutate.md §Bound state contents note.

    tts_speak(text: str) -> None — sync callable; used as an observability hook
        (logs confirm_tts_prompt:). The actual prompt delivery is the HTTP
        response body — HA TTSes it through its voice pipeline (Option B).

    clock() -> datetime — injectable for tests; returns UTC datetime.

    Two-turn HTTP flow: gate_tool_call() returns immediately with
    terminal_state="awaiting"; deliver_utterance() resolves on the next turn.
    """

    def __init__(
        self,
        *,
        tts_speak: Callable,
        telemetry_emit: Callable = emit,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
        timeout_seconds: Optional[int] = None,
    ) -> None:
        if timeout_seconds is None:
            timeout_seconds = _load_timeout()
        if timeout_seconds > _MAX_TIMEOUT_SECONDS:
            raise ValueError(
                f"timeout_seconds={timeout_seconds} exceeds maximum {_MAX_TIMEOUT_SECONDS}. "
                f"Per confirm-before-mutate.md §Timeout policy."
            )
        self._tts_speak = tts_speak
        self._emit = telemetry_emit
        self._clock = clock
        self._timeout_seconds = timeout_seconds

        # In-memory pending confirmation.
        # Per §Failure modes: "Adapter restart drops pending confirmations."
        self._pending: Optional[BoundConfirmation] = None

    # -----------------------------------------------------------------------
    # Public: utterance delivery (called by adapter on confirmation turn)
    # -----------------------------------------------------------------------

    def deliver_utterance(
        self,
        text: str,
        *,
        request_id: str,
        conversation_id: str,
        pending_id: str,
    ) -> ConfirmationOutcome:
        """Resolve a delivered confirmation utterance synchronously.

        Called by the adapter on the second HTTP request (confirmation turn).
        Returns a terminal ConfirmationOutcome that the adapter converts to an
        HTTP response: the executed-tool result on confirm, or refusal speech
        on deny/cancel/ambiguous/expired.

        Returns terminal_state="not_pending" if no confirmation is pending —
        the adapter treats this as a normal (non-confirmation) request.

        pending_id must match the token from the pending_id property; a mismatch
        cancels the pending confirmation (multi-field match per
        confirm-before-mutate.md §Bound state contents line 135).
        """
        if self._pending is None:
            return ConfirmationOutcome(
                terminal_state="not_pending",
                execute_bound_tool=False,
                bound=None,
                refusal_speech=None,
            )

        current_bound = self._pending

        # Deadline check — handles utterance arriving past timeout.
        if self._clock() >= current_bound.deadline:
            self._pending = None
            return self._expire(current_bound)

        # Multi-field match per confirm-before-mutate.md line 135.
        if (
            conversation_id != current_bound.conversation_id
            or pending_id != current_bound.pending_id
        ):
            self._pending = None
            return self._cancel(current_bound)

        seconds_since_prompt = (self._clock() - current_bound.bound_at).total_seconds()
        parse = parse_confirmation_utterance(
            text,
            seconds_since_prompt_end=max(0.0, seconds_since_prompt),
        )

        if parse == ConfirmationParse.ACCEPT:
            self._pending = None
            return self._confirm(current_bound)

        if parse == ConfirmationParse.REJECT:
            self._pending = None
            return self._deny(current_bound)

        if parse == ConfirmationParse.NEW_REQUEST:
            self._pending = None
            return self._cancel(current_bound)

        # AMBIGUOUS — check for one-reprompt feature flag.
        if _one_reprompt_enabled() and current_bound.attempts == 0:
            new_bound = current_bound.with_attempts(1)
            self._pending = new_bound
            eid_for_telemetry = _entity_id_for_telemetry(
                new_bound.entity_id, new_bound.entity_domain
            )
            reprompt_payload: dict = {
                "conversation_id": new_bound.conversation_id,
                "tool_name": new_bound.tool_name,
                "entity_domain": new_bound.entity_domain,
                "policy_reason": new_bound.policy_reason,
                "bound_at": new_bound.bound_at.isoformat(),
                "attempts": new_bound.attempts,
            }
            if eid_for_telemetry:
                reprompt_payload["entity_id"] = eid_for_telemetry
            self._emit("confirmation_reprompted", reprompt_payload)
            reprompt_text = "Sorry, I didn't catch that. Confirm: yes or no?"
            try:
                self._tts_speak(reprompt_text)
            except TtsUnreachableError:
                # Reprompt TTS hook unreachable → deny per §Failure modes.
                self._pending = None
                return self._deny_ambiguous(new_bound)
            return ConfirmationOutcome(
                terminal_state="awaiting",
                execute_bound_tool=False,
                bound=new_bound,
                refusal_speech=None,
                awaiting_prompt=reprompt_text,
            )

        # Zero-reprompt default or reprompt already used → denied_ambiguous.
        self._pending = None
        return self._deny_ambiguous(current_bound)

    def check_expired_pending(self) -> Optional[ConfirmationOutcome]:
        """Sweep for a stale pending confirmation past its deadline.

        Called at request entry to emit telemetry for confirmations that timed
        out between HTTP requests (user gave up; no confirmation turn arrived).
        Returns the expired outcome so the adapter can record the event; returns
        None when idle or when the pending is still within its deadline.

        No user-facing surface — the caller continues with the new request fresh.
        """
        if self._pending is None:
            return None
        if self._clock() < self._pending.deadline:
            return None
        expired_bound = self._pending
        self._pending = None
        return self._expire(expired_bound)

    @property
    def pending_id(self) -> Optional[str]:
        """Currently-pending confirmation token, or None if idle.

        The adapter reads this when routing a follow-up utterance into
        deliver_utterance() so the SM can verify multi-field match.
        """
        return self._pending.pending_id if self._pending is not None else None

    # -----------------------------------------------------------------------
    # Public: main entry point (async for FastAPI compatibility; returns sync)
    # -----------------------------------------------------------------------

    async def gate_tool_call(
        self,
        *,
        tool_name: str,
        entity_id: str,
        args: dict,
        request_id: str,
        conversation_id: str,
        time_of_day: datetime,
        user_text: str = "",
        area: Optional[str] = None,
    ) -> ConfirmationOutcome:
        """Gate a resolved tool call through the state machine.

        Returns ConfirmationOutcome immediately — does NOT await a confirmation
        utterance. For gated paths, returns terminal_state="awaiting" with
        awaiting_prompt populated. The adapter returns this prompt as HTTP
        response content; HA TTSes it. The next HTTP request (confirmation turn)
        calls deliver_utterance() to resolve the outcome.

        Per confirm-before-mutate.md §Policy lookup and §States and transitions.
        """
        entity_domain = _entity_domain(entity_id)

        # 1. Policy lookup — the only entry point.
        # Per §Policy lookup: "Classifier output cannot affect this lookup."
        policy = lookup_policy(
            tool_name, entity_id, args,
            time_of_day=time_of_day,
            area=area,
        )

        # 2. deny-by-default: never reaches awaiting-confirm.
        if policy.outcome == PolicyOutcome.DENY_BY_DEFAULT:
            return self._deny_by_default(
                tool_name=tool_name,
                entity_domain=entity_domain,
                policy_reason=policy.policy_reason,
            )

        # 3. No confirmation needed — short-circuit.
        if not policy.confirms:
            return ConfirmationOutcome(
                terminal_state="confirmed_no_gate",
                execute_bound_tool=True,
                bound=None,
                refusal_speech=None,
            )

        # 4. Enter awaiting-confirm (synchronous — returns immediately).
        return self._enter_awaiting_confirm(
            tool_name=tool_name,
            entity_id=entity_id,
            entity_domain=entity_domain,
            args=args,
            request_id=request_id,
            conversation_id=conversation_id,
            policy_reason=policy.policy_reason,
            user_text=user_text,
        )

    # -----------------------------------------------------------------------
    # deny-by-default terminal (per §Transition rules: idle → denied-by-default)
    # -----------------------------------------------------------------------

    def _deny_by_default(
        self,
        *,
        tool_name: str,
        entity_domain: str,
        policy_reason: str,
    ) -> ConfirmationOutcome:
        terminated_at = self._clock()
        self._emit("confirmation_denied_by_default", {
            "tool_name": tool_name,
            "entity_domain": entity_domain,
            "policy_reason": policy_reason,
            "terminated_at": terminated_at.isoformat(),
        })
        return ConfirmationOutcome(
            terminal_state="denied_by_default",
            execute_bound_tool=False,
            bound=None,
            refusal_speech=_REFUSAL_DENIED_BY_DEFAULT,
        )

    # -----------------------------------------------------------------------
    # awaiting-confirm bind (sync — returns immediately with "awaiting")
    # -----------------------------------------------------------------------

    def _enter_awaiting_confirm(
        self,
        *,
        tool_name: str,
        entity_id: str,
        entity_domain: str,
        args: dict,
        request_id: str,
        conversation_id: str,
        policy_reason: str,
        user_text: str = "",
    ) -> ConfirmationOutcome:
        bound_at = self._clock()
        deadline = bound_at + timedelta(seconds=self._timeout_seconds)

        bound = BoundConfirmation(
            request_id=request_id,
            conversation_id=conversation_id,
            pending_id=secrets.token_hex(8),
            tool_name=tool_name,
            entity_id=entity_id,
            entity_domain=entity_domain,
            args=dict(args),  # frozen copy
            policy_reason=policy_reason,
            bound_at=bound_at,
            deadline=deadline,
            original_user_text=user_text,
            attempts=0,
        )

        # Handle existing pending (same conversation_id collision).
        # Per §Failure modes: "Conversation_id collision → treat as canceled."
        if (
            self._pending is not None
            and self._pending.conversation_id == conversation_id
        ):
            old = self._pending
            self._emit("confirmation_canceled_by_new_request", self._terminal_payload(old, terminal_state="canceled"))

        self._pending = bound

        # Build the confirmation prompt.
        prompt_text = self._build_prompt(tool_name, entity_id, args)

        # Side-channel observability hook — the actual prompt delivery is the
        # HTTP response body (Option B / two-turn flow).  TtsUnreachableError
        # from the hook is ignored here because the prompt is in-band; it does
        # NOT block confirmation or deny the tool.
        try:
            self._tts_speak(prompt_text)
        except TtsUnreachableError:
            pass  # hook failure is non-fatal; prompt travels via HTTP response

        # Emit confirmation_prompt_emitted.
        # Per telemetry-schema.md §4: do NOT include request_id in payload
        # (T1 envelope injects it from ContextVar).
        eid_for_telemetry = _entity_id_for_telemetry(entity_id, entity_domain)
        prompt_payload: dict = {
            "conversation_id": conversation_id,
            "tool_name": tool_name,
            "entity_domain": entity_domain,
            "policy_reason": policy_reason,
            "bound_at": bound_at.isoformat(),
        }
        if eid_for_telemetry:
            prompt_payload["entity_id"] = eid_for_telemetry
        self._emit("confirmation_prompt_emitted", prompt_payload)

        # Return immediately — adapter delivers awaiting_prompt as HTTP response.
        # HA TTSes it through its voice pipeline.  The next HTTP request calls
        # deliver_utterance() to resolve the outcome.
        return ConfirmationOutcome(
            terminal_state="awaiting",
            execute_bound_tool=False,
            bound=bound,
            refusal_speech=None,
            awaiting_prompt=prompt_text,
        )

    # -----------------------------------------------------------------------
    # Terminal transitions
    # -----------------------------------------------------------------------

    def _confirm(self, bound: BoundConfirmation) -> ConfirmationOutcome:
        self._pending = None
        self._emit("confirmation_confirmed", self._terminal_payload(bound, terminal_state="confirmed"))
        return ConfirmationOutcome(
            terminal_state="confirmed",
            execute_bound_tool=True,
            bound=bound,
            refusal_speech=None,
        )

    def _deny(self, bound: BoundConfirmation) -> ConfirmationOutcome:
        self._pending = None
        self._emit("confirmation_denied", self._terminal_payload(bound, terminal_state="denied"))
        return ConfirmationOutcome(
            terminal_state="denied",
            execute_bound_tool=False,
            bound=bound,
            refusal_speech=_REFUSAL_DENIED,
        )

    def _deny_ambiguous(self, bound: BoundConfirmation) -> ConfirmationOutcome:
        self._pending = None
        self._emit("confirmation_denied_ambiguous", self._terminal_payload(bound, terminal_state="denied_ambiguous"))
        return ConfirmationOutcome(
            terminal_state="denied_ambiguous",
            execute_bound_tool=False,
            bound=bound,
            refusal_speech=_REFUSAL_DENIED_AMBIGUOUS,
        )

    def _expire(self, bound: BoundConfirmation) -> ConfirmationOutcome:
        self._pending = None
        self._emit("confirmation_expired", self._terminal_payload(bound, terminal_state="expired"))
        return ConfirmationOutcome(
            terminal_state="expired",
            execute_bound_tool=False,
            bound=bound,
            refusal_speech=_REFUSAL_EXPIRED,
        )

    def _cancel(self, bound: BoundConfirmation) -> ConfirmationOutcome:
        self._pending = None
        self._emit("confirmation_canceled_by_new_request", self._terminal_payload(bound, terminal_state="canceled"))
        return ConfirmationOutcome(
            terminal_state="canceled",
            execute_bound_tool=False,
            bound=bound,
            refusal_speech=_REFUSAL_CANCELED,
        )

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    def _terminal_payload(self, bound: BoundConfirmation, *, terminal_state: str) -> dict:
        """Shared payload dict for terminal events.

        Per telemetry-schema.md §4: conversation_id, tool_name, entity_domain,
        policy_reason, terminal_state, attempts, bound_at, terminated_at, latency_ms.
        Per §Telemetry contract:
          - No raw transcript content.
          - No request_id in payload (T1 envelope injects from ContextVar).
          - No user_id (SHARED sink; T1 strips it).
          - entity_id only for low-sensitivity domains.
        """
        terminated_at = self._clock()
        latency_ms = int((terminated_at - bound.bound_at).total_seconds() * 1000)
        eid_for_telemetry = _entity_id_for_telemetry(bound.entity_id, bound.entity_domain)
        payload: dict = {
            "conversation_id": bound.conversation_id,
            "tool_name": bound.tool_name,
            "entity_domain": bound.entity_domain,
            "policy_reason": bound.policy_reason,
            "terminal_state": terminal_state,
            "attempts": bound.attempts,
            "bound_at": bound.bound_at.isoformat(),
            "terminated_at": terminated_at.isoformat(),
            "latency_ms": latency_ms,
        }
        if eid_for_telemetry:
            payload["entity_id"] = eid_for_telemetry
        return payload

    @staticmethod
    def _build_prompt(tool_name: str, entity_id: str, args: dict) -> str:
        """Build the TTS confirmation prompt per #44 template.

        Template: "I heard: <action> <entity>. Confirm: yes or no?"
        Per docs/security/high-impact-tools.md §Initial confirmation prompt requirements.
        """
        display = entity_id.replace(".", " ").replace("_", " ")
        action_map = {
            "HassTurnOn":        f"turn on {display}",
            "HassTurnOff":       f"turn off {display}",
            "HassLock":          f"lock {display}",
            "HassUnlock":        f"unlock {display}",
            "HassPlayMedia":     f"play media on {display}",
            "HassSetTemperature": f"set {display} to {args.get('temperature', '?')} degrees",
        }
        action = action_map.get(tool_name, f"{tool_name} on {display}")
        return f"I heard: {action}. Confirm: yes or no?"
