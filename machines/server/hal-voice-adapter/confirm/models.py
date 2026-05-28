"""Data models for the T5 confirm-before-mutate state machine.

Per confirm-before-mutate.md §States and transitions and §Bound state contents.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Optional


class PolicyOutcome(Enum):
    """Four outcomes from docs/security/high-impact-tools.md policy lookup."""
    NEVER = "never"
    CONTEXTUAL = "contextual"
    ALWAYS = "always"
    DENY_BY_DEFAULT = "deny-by-default"


@dataclass(frozen=True)
class PolicyResult:
    """Structured result from policy lookup.

    confirms=True means the state machine must be entered.
    Per confirm-before-mutate.md §Policy lookup.
    """
    outcome: PolicyOutcome
    policy_reason: str   # e.g. "always", "contextual+bedroom", "deny-by-default", "never"
    confirms: bool       # True if state machine should gate this tool call


@dataclass(frozen=True)
class BoundConfirmation:
    """Immutable triple frozen at awaiting-confirm entry.

    Per confirm-before-mutate.md §Bound state contents: "the bound tool is
    fixed at awaiting-confirm entry" — immutable through every terminal state.
    """
    request_id: str
    conversation_id: str
    pending_id: str        # generated at bind; required for multi-field match
    tool_name: str
    entity_id: str
    entity_domain: str
    args: dict
    policy_reason: str
    bound_at: datetime
    deadline: datetime
    original_user_text: str  # user's action utterance for T3 memory capture on resolution
    attempts: int = 0

    def with_attempts(self, n: int) -> "BoundConfirmation":
        return BoundConfirmation(
            request_id=self.request_id,
            conversation_id=self.conversation_id,
            pending_id=self.pending_id,
            tool_name=self.tool_name,
            entity_id=self.entity_id,
            entity_domain=self.entity_domain,
            args=self.args,
            policy_reason=self.policy_reason,
            bound_at=self.bound_at,
            deadline=self.deadline,
            original_user_text=self.original_user_text,
            attempts=n,
        )


class ConfirmationParse(Enum):
    """Result of parsing a user utterance during awaiting-confirm.

    Per confirm-before-mutate.md §Confirmation utterance parsing.
    Asymmetry invariant: borderline utterances map to AMBIGUOUS, not ACCEPT.
    """
    ACCEPT = "accept"
    REJECT = "reject"
    AMBIGUOUS = "ambiguous"
    NEW_REQUEST = "new_request"


@dataclass(frozen=True)
class ConfirmationOutcome:
    """Result returned by ConfirmationStateMachine.gate_tool_call() and deliver_utterance().

    The adapter handler consumes this to decide whether to execute the tool.
    Per confirm-before-mutate.md §States and transitions.
    """
    terminal_state: str
    # "awaiting" | "confirmed" | "denied" | "expired" | "canceled" | "denied_ambiguous"
    # | "denied_by_default" | "confirmed_no_gate" | "denied_due_to_degraded_mode"
    # | "not_pending" (synthetic — deliver_utterance called with no pending confirmation)

    execute_bound_tool: bool   # only True for "confirmed" and "confirmed_no_gate"
    bound: Optional[BoundConfirmation]  # populated for all gated paths; None for no_gate
    refusal_speech: Optional[str]       # TTS text for non-confirmed terminals
    awaiting_prompt: Optional[str] = None  # populated when terminal_state == "awaiting"

    def _now() -> datetime:  # noqa: N805
        return datetime.now(timezone.utc)
