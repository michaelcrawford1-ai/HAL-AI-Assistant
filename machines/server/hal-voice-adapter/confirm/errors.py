"""Exception types for the T5 confirm-before-mutate state machine.

Per confirm-before-mutate.md §Failure modes.
"""
from __future__ import annotations


class TtsUnreachableError(Exception):
    """TTS pipeline unreachable when attempting to emit confirmation prompt.

    Per confirm-before-mutate.md §Failure modes: "Refuse to mutate. Do not
    silently execute the bound tool because confirmation could not be requested."
    """


class ConfirmationInfraError(Exception):
    """Generic infrastructure failure in the confirmation path (non-TTS)."""


class AuthMissingError(Exception):
    """Adapter ingress auth precondition violated before state machine entry.

    Should never happen in normal operation — auth is enforced upstream by PR #50.
    Per confirm-before-mutate.md §Preconditions.
    """
