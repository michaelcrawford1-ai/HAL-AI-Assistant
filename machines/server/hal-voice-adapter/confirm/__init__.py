"""T5 confirm-before-mutate state machine package.

Public API:
    ConfirmationStateMachine  — core state machine; gate_tool_call() is the entry point
    PolicyOutcome             — enum: NEVER | CONTEXTUAL | ALWAYS | DENY_BY_DEFAULT
    ConfirmationOutcome       — result returned to the adapter handler
    BoundConfirmation         — immutable frozen action triple
"""
from .errors import AuthMissingError, ConfirmationInfraError, TtsUnreachableError
from .models import BoundConfirmation, ConfirmationOutcome, PolicyOutcome
from .state_machine import ConfirmationStateMachine

__all__ = [
    "ConfirmationStateMachine",
    "PolicyOutcome",
    "ConfirmationOutcome",
    "BoundConfirmation",
    "TtsUnreachableError",
    "ConfirmationInfraError",
    "AuthMissingError",
]
