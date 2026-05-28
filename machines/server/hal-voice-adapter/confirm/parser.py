"""Utterance parser for the T5 confirm-before-mutate state machine.

Classifies a user utterance during the awaiting-confirm window into one of:
  ACCEPT | REJECT | AMBIGUOUS | NEW_REQUEST

Per confirm-before-mutate.md §Confirmation utterance parsing:
"The parser must be asymmetric in favor of denial — a borderline utterance
maps to ambiguous-then-denied, never to confirmed."
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

from .models import ConfirmationParse

# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

_PUNCT_RE = re.compile(r"[^\w\s]")


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace."""
    lowered = text.lower()
    no_punct = _PUNCT_RE.sub(" ", lowered)
    return " ".join(no_punct.split())


# ---------------------------------------------------------------------------
# Accept sets
# ---------------------------------------------------------------------------

# Phase 1 default accept set: exact-match only.
# Per confirm-before-mutate.md §Confirmation utterance parsing (resolved Q2):
# "Phase 1 uses a strict accept allowlist (yes/confirm); extended phrases are
# feature-flagged."
_DEFAULT_ACCEPT_SET: frozenset[str] = frozenset({"yes", "confirm"})

# Extended-accept phrases (feature-flagged, all three conditions must be met).
# Per spec §Confirmation utterance parsing: "okay do it", "go ahead", "do it"
# are higher false-positive risk.  Enabled only by extended_accept_set=True
# with caller explicitly confirming all three conditions.
_EXTENDED_ACCEPT_SET: frozenset[str] = frozenset({"okay do it", "go ahead", "do it"})

# ---------------------------------------------------------------------------
# Reject set
# ---------------------------------------------------------------------------

# Phase 1 reject set: exact-match OR prefix match.
_REJECT_EXACT: frozenset[str] = frozenset({"no", "cancel", "stop", "never mind", "do not"})

# Prefixes: any utterance starting with these tokens maps to REJECT.
_REJECT_PREFIXES: tuple[str, ...] = ("no ", "cancel ", "stop ", "do not ", "please no")

# ---------------------------------------------------------------------------
# NEW_REQUEST detection
# Per spec: utterance contains a known tool-trigger phrase suggesting different
# intent AND is not in accept/reject sets.
# ---------------------------------------------------------------------------

# HA tool-trigger phrases (heuristic, based on tool_source.py vocabulary)
_NEW_REQUEST_FRAGMENTS: tuple[str, ...] = (
    "turn on", "turn off", "set temperature", "set the temperature",
    "lock the", "unlock the", "play ", "what time", "what is the",
    "what's the", "how is", "how's", "tell me", "remind me",
)


def _looks_like_new_request(normalized: str) -> bool:
    return any(normalized.startswith(frag) or f" {frag}" in normalized
               for frag in _NEW_REQUEST_FRAGMENTS)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def parse_confirmation_utterance(
    text: str,
    *,
    extended_accept_set: bool = False,
    seconds_since_prompt_end: float,
) -> ConfirmationParse:
    """Classify a user utterance during the awaiting-confirm window.

    Asymmetry invariant: borderline utterances map to AMBIGUOUS, never ACCEPT.
    False-deny is recoverable; false-confirm is not.

    Per confirm-before-mutate.md §Confirmation utterance parsing.
    """
    normalized = _normalize(text)

    if not normalized:
        return ConfirmationParse.AMBIGUOUS

    # --- Reject check (highest priority — asymmetry favors denial) ----------
    if normalized in _REJECT_EXACT:
        return ConfirmationParse.REJECT
    for prefix in _REJECT_PREFIXES:
        if normalized.startswith(prefix):
            return ConfirmationParse.REJECT

    # --- Accept check (default set) -----------------------------------------
    if normalized in _DEFAULT_ACCEPT_SET:
        return ConfirmationParse.ACCEPT

    # --- Extended-accept check (all three conditions required) ---------------
    # Per spec: seconds_since_prompt_end <= 3.0 AND utterance contains nothing
    # beyond the affirmative phrase AND caller enabled the flag (default off).
    if normalized in _EXTENDED_ACCEPT_SET:
        if (
            extended_accept_set
            and seconds_since_prompt_end <= 3.0
            and normalized in _EXTENDED_ACCEPT_SET  # phrase is clean match (no extra words)
        ):
            return ConfirmationParse.ACCEPT
        # Flag off or timing missed or extra words → AMBIGUOUS (not REJECT)
        return ConfirmationParse.AMBIGUOUS

    # --- NEW_REQUEST check ---------------------------------------------------
    if _looks_like_new_request(normalized):
        return ConfirmationParse.NEW_REQUEST

    # --- Fallback: AMBIGUOUS -------------------------------------------------
    # Per asymmetry invariant: anything not clearly accept/reject/new_request
    # maps to AMBIGUOUS → caller will treat as DENIED.
    return ConfirmationParse.AMBIGUOUS
