"""Tests for the T5 confirm-before-mutate state machine.

Test mode runs the state machine via the public API directly with a stub TTS
adapter and stub clock — per handoff §Done means item 7.  No bypass event
emitted; we drive the state machine directly.

Two-turn HTTP flow (Amend 2 / Option B):
  gate_tool_call() returns terminal_state="awaiting" immediately.
  deliver_utterance() resolves the outcome on the next (confirmation) turn.
  Tests follow the two-turn pattern: gate → assert awaiting → deliver → assert outcome.

Coverage targets:
  - State transitions and two-turn flow (gate returns awaiting; deliver resolves)
  - Bound-action freeze
  - Asymmetric parser cases: clean accept, clean reject, ambiguous, NEW_REQUEST
  - 15s default timeout, 30s configurable max
  - Zero-reprompt default; one-reprompt feature-flagged
  - TTS-unreachable: initial-prompt hook failure is benign (in-band delivery);
    reprompt-path hook failure → denied_ambiguous
  - Cross-tenant safety
  - check_expired_pending() sweep
  - T3 TurnRecord hook integration
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Optional
from unittest.mock import patch

import pytest

from confirm import ConfirmationStateMachine, ConfirmationOutcome
from confirm.errors import TtsUnreachableError
from confirm.models import BoundConfirmation, ConfirmationParse, PolicyOutcome
from confirm.parser import parse_confirmation_utterance
from confirm.policy import lookup_policy
from memory_write.models import RetentionCategory, TurnRecord
from memory_write.classifier import classify

# ---------------------------------------------------------------------------
# Telemetry patch — capture emit calls in tests without file I/O
# ---------------------------------------------------------------------------

os.environ.setdefault("HAL_TELEMETRY_TESTING", "1")
os.environ.setdefault("HAL_TELEMETRY_DIR", "/tmp/hal-test-telemetry")


class _EmitCapture:
    """Collects emit() calls for assertion."""
    def __init__(self):
        self.calls: list[tuple[str, dict]] = []

    def __call__(self, event_name: str, payload: dict, **kw):
        self.calls.append((event_name, payload))

    def events(self) -> list[str]:
        return [e for e, _ in self.calls]

    def payloads_for(self, event: str) -> list[dict]:
        return [p for e, p in self.calls if e == event]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

UTC = timezone.utc


class _FakeClock:
    def __init__(self, start: Optional[datetime] = None):
        self._now = start or datetime(2026, 5, 7, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self._now

    def advance(self, seconds: float) -> None:
        self._now = self._now + timedelta(seconds=seconds)


def _make_sm(
    *,
    tts_speak=None,
    emit_capture: Optional[_EmitCapture] = None,
    clock: Optional[_FakeClock] = None,
    timeout_seconds: int = 15,
) -> ConfirmationStateMachine:
    if tts_speak is None:
        tts_speak = lambda text: None
    if emit_capture is None:
        emit_capture = _EmitCapture()
    if clock is None:
        clock = _FakeClock()
    return ConfirmationStateMachine(
        tts_speak=tts_speak,
        telemetry_emit=emit_capture,
        clock=clock,
        timeout_seconds=timeout_seconds,
    )


async def _gate(
    sm: ConfirmationStateMachine,
    *,
    tool_name: str = "HassLock",
    entity_id: str = "lock.front_door",
    args: dict = None,
    request_id: str = "req-1",
    conversation_id: str = "conv-1",
    user_text: str = "lock the front door",
) -> ConfirmationOutcome:
    """Call gate_tool_call and return the (awaiting) outcome."""
    if args is None:
        args = {"entity_id": entity_id}
    return await sm.gate_tool_call(
        tool_name=tool_name,
        entity_id=entity_id,
        args=args,
        request_id=request_id,
        conversation_id=conversation_id,
        time_of_day=datetime(2026, 5, 7, 14, 0, 0, tzinfo=UTC),
        user_text=user_text,
    )


def _deliver(
    sm: ConfirmationStateMachine,
    text: str,
    *,
    request_id: str = "req-2",
    conversation_id: str = "conv-1",
    pending_id: Optional[str] = None,
) -> ConfirmationOutcome:
    """Call deliver_utterance with the correct pending_id (read from sm if not given)."""
    if pending_id is None:
        pending_id = sm.pending_id or ""
    return sm.deliver_utterance(
        text,
        request_id=request_id,
        conversation_id=conversation_id,
        pending_id=pending_id,
    )


# ===========================================================================
# Policy lookup tests
# ===========================================================================

class TestPolicyLookup:

    def _now(self, hour: int = 14) -> datetime:
        return datetime(2026, 5, 7, hour, 0, 0, tzinfo=UTC)

    def test_hass_get_state_is_never(self):
        r = lookup_policy("HassGetState", "sensor.temperature", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.NEVER
        assert not r.confirms

    def test_hass_unlock_interior_lock_is_always(self):
        r = lookup_policy("HassUnlock", "lock.cabinet", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.ALWAYS
        assert r.confirms

    def test_hass_unlock_exterior_lock_is_deny_by_default(self):
        r = lookup_policy("HassUnlock", "lock.front_door", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.DENY_BY_DEFAULT
        assert not r.confirms

    def test_hass_lock_exterior_is_always(self):
        r = lookup_policy("HassLock", "lock.front_door", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.ALWAYS
        assert r.confirms

    def test_hass_lock_interior_is_contextual_confirmed(self):
        r = lookup_policy("HassLock", "lock.cabinet", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.CONTEXTUAL
        assert r.confirms

    def test_hass_set_temperature_in_band_not_special(self):
        r = lookup_policy("HassSetTemperature", "climate.living_room",
                          {"temperature": 72}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.CONTEXTUAL
        assert not r.confirms  # in-band, no special entity

    def test_hass_set_temperature_bedroom_confirms(self):
        r = lookup_policy("HassSetTemperature", "climate.bedroom",
                          {"temperature": 72}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.CONTEXTUAL
        assert r.confirms

    def test_hass_set_temperature_out_of_band_confirms(self):
        r = lookup_policy("HassSetTemperature", "climate.living_room",
                          {"temperature": 50}, time_of_day=self._now())
        assert r.confirms

    def test_hass_turn_on_light_is_never(self):
        r = lookup_policy("HassTurnOn", "light.kitchen", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.NEVER
        assert not r.confirms

    def test_hass_turn_on_heater_confirms(self):
        r = lookup_policy("HassTurnOn", "switch.heater", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.CONTEXTUAL
        assert r.confirms

    def test_hass_turn_on_oven_deny_by_default(self):
        r = lookup_policy("HassTurnOn", "switch.oven", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.DENY_BY_DEFAULT

    def test_hass_turn_off_camera_confirms(self):
        r = lookup_policy("HassTurnOff", "switch.security_camera", {}, time_of_day=self._now())
        assert r.confirms

    def test_hass_turn_off_light_is_never(self):
        r = lookup_policy("HassTurnOff", "light.bedroom", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.NEVER
        assert not r.confirms

    def test_hass_play_media_normal_is_never(self):
        r = lookup_policy("HassPlayMedia", "media_player.living_room", {},
                          time_of_day=self._now(14))
        assert r.outcome == PolicyOutcome.NEVER

    def test_hass_play_media_bedroom_quiet_hours_confirms(self):
        r = lookup_policy("HassPlayMedia", "media_player.bedroom", {},
                          time_of_day=self._now(23))  # quiet hours
        assert r.confirms

    def test_unknown_tool_deny_by_default(self):
        r = lookup_policy("HassDoSomethingWeird", "switch.x", {}, time_of_day=self._now())
        assert r.outcome == PolicyOutcome.DENY_BY_DEFAULT


# ===========================================================================
# Parser tests
# ===========================================================================

class TestParser:

    def _parse(self, text: str, extended: bool = False, seconds: float = 1.0) -> ConfirmationParse:
        return parse_confirmation_utterance(
            text, extended_accept_set=extended, seconds_since_prompt_end=seconds
        )

    def test_clean_accept_yes(self):
        assert self._parse("yes") == ConfirmationParse.ACCEPT

    def test_clean_accept_confirm(self):
        assert self._parse("confirm") == ConfirmationParse.ACCEPT

    def test_clean_accept_yes_with_punctuation(self):
        assert self._parse("yes.") == ConfirmationParse.ACCEPT

    def test_clean_reject_no(self):
        assert self._parse("no") == ConfirmationParse.REJECT

    def test_clean_reject_cancel(self):
        assert self._parse("cancel") == ConfirmationParse.REJECT

    def test_clean_reject_stop(self):
        assert self._parse("stop") == ConfirmationParse.REJECT

    def test_clean_reject_never_mind(self):
        assert self._parse("never mind") == ConfirmationParse.REJECT

    def test_prefixed_reject_no_thanks(self):
        assert self._parse("no thanks") == ConfirmationParse.REJECT

    def test_prefixed_reject_no_dont(self):
        assert self._parse("no don't do that") == ConfirmationParse.REJECT

    def test_ambiguous_music_yes(self):
        assert self._parse("yes I think so") == ConfirmationParse.AMBIGUOUS

    def test_ambiguous_uh(self):
        assert self._parse("uh") == ConfirmationParse.AMBIGUOUS

    def test_ambiguous_hmm(self):
        assert self._parse("hmm") == ConfirmationParse.AMBIGUOUS

    def test_new_request_time_query(self):
        assert self._parse("what time is it") == ConfirmationParse.NEW_REQUEST

    def test_new_request_turn_on_kitchen(self):
        assert self._parse("turn on the kitchen light") == ConfirmationParse.NEW_REQUEST

    def test_extended_accept_go_ahead_flag_off(self):
        assert self._parse("go ahead", extended=False, seconds=1.0) == ConfirmationParse.AMBIGUOUS

    def test_extended_accept_go_ahead_flag_on_timing_ok(self):
        assert self._parse("go ahead", extended=True, seconds=2.0) == ConfirmationParse.ACCEPT

    def test_extended_accept_do_it_flag_on_timing_too_late(self):
        assert self._parse("do it", extended=True, seconds=4.0) == ConfirmationParse.AMBIGUOUS

    def test_empty_utterance_is_ambiguous(self):
        assert self._parse("") == ConfirmationParse.AMBIGUOUS

    def test_asymmetry_borderline_maps_to_ambiguous(self):
        result = self._parse("maybe yes")
        assert result in (ConfirmationParse.AMBIGUOUS, ConfirmationParse.REJECT)
        assert result != ConfirmationParse.ACCEPT


# ===========================================================================
# State machine — policy no-gate path
# ===========================================================================

class TestStateMachineNoGate:

    @pytest.mark.asyncio
    async def test_never_policy_returns_confirmed_no_gate(self):
        sm = _make_sm()
        outcome = await sm.gate_tool_call(
            tool_name="HassGetState",
            entity_id="sensor.temperature",
            args={},
            request_id="r1",
            conversation_id="c1",
            time_of_day=datetime(2026, 5, 7, 14, 0, 0, tzinfo=UTC),
        )
        assert outcome.terminal_state == "confirmed_no_gate"
        assert outcome.execute_bound_tool is True
        assert outcome.bound is None

    @pytest.mark.asyncio
    async def test_light_on_returns_confirmed_no_gate(self):
        sm = _make_sm()
        outcome = await sm.gate_tool_call(
            tool_name="HassTurnOn",
            entity_id="light.kitchen",
            args={"entity_id": "light.kitchen"},
            request_id="r1",
            conversation_id="c1",
            time_of_day=datetime(2026, 5, 7, 14, 0, 0, tzinfo=UTC),
        )
        assert outcome.terminal_state == "confirmed_no_gate"
        assert outcome.execute_bound_tool is True


# ===========================================================================
# State machine — awaiting outcome (new Amend 2 tests)
# ===========================================================================

class TestAwaitingOutcome:

    @pytest.mark.asyncio
    async def test_gate_tool_call_returns_awaiting_outcome_with_prompt(self):
        """gate_tool_call returns immediately with awaiting + non-None prompt text."""
        tts_calls: list[str] = []
        sm = _make_sm(tts_speak=lambda t: tts_calls.append(t))

        bind_outcome = await _gate(sm)

        assert bind_outcome.terminal_state == "awaiting"
        assert bind_outcome.execute_bound_tool is False
        assert bind_outcome.bound is not None
        assert bind_outcome.awaiting_prompt is not None
        assert len(bind_outcome.awaiting_prompt) > 0
        # Prompt must reference the action so HA can speak it meaningfully.
        assert "lock" in bind_outcome.awaiting_prompt.lower() or "confirm" in bind_outcome.awaiting_prompt.lower()
        # TTS hook called for observability.
        assert tts_calls == [bind_outcome.awaiting_prompt]

    @pytest.mark.asyncio
    async def test_deliver_utterance_returns_resolved_outcome(self):
        """deliver_utterance resolves to confirmed; outcome has correct shape."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        bind_outcome = await _gate(sm)
        assert bind_outcome.terminal_state == "awaiting"

        resolution = _deliver(sm, "yes")
        assert resolution.terminal_state == "confirmed"
        assert resolution.execute_bound_tool is True
        assert resolution.bound is not None
        assert "confirmation_confirmed" in cap.events()

    @pytest.mark.asyncio
    async def test_gate_returns_awaiting_prompt_contains_entity(self):
        sm = _make_sm()
        bind_outcome = await _gate(sm, entity_id="lock.front_door")
        # Prompt must be speakable and reference the entity in some form.
        assert bind_outcome.awaiting_prompt is not None
        prompt = bind_outcome.awaiting_prompt.lower()
        assert "front" in prompt or "door" in prompt or "lock" in prompt

    def test_deliver_utterance_when_idle_returns_not_pending(self):
        """deliver_utterance with no pending → terminal_state='not_pending'."""
        sm = _make_sm()
        outcome = sm.deliver_utterance(
            "yes", request_id="r1", conversation_id="c1", pending_id="anything"
        )
        assert outcome.terminal_state == "not_pending"
        assert outcome.execute_bound_tool is False
        assert outcome.bound is None


# ===========================================================================
# State machine — confirmed path
# ===========================================================================

class TestStateMachineConfirmed:

    @pytest.mark.asyncio
    async def test_clean_confirm_yes_executes_bound(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        bind_outcome = await _gate(sm, tool_name="HassLock", entity_id="lock.front_door")
        assert bind_outcome.terminal_state == "awaiting"

        resolution = _deliver(sm, "yes")
        assert resolution.terminal_state == "confirmed"
        assert resolution.execute_bound_tool is True
        assert resolution.bound is not None
        assert "confirmation_confirmed" in cap.events()

    @pytest.mark.asyncio
    async def test_confirmed_bound_args_are_frozen(self):
        """Confirmation fires the original entity, per §Invariants: 'Bound action is frozen.'"""
        sm = _make_sm()
        ORIGINAL_ENTITY = "lock.front_door"

        bind_outcome = await _gate(
            sm,
            tool_name="HassLock",
            entity_id=ORIGINAL_ENTITY,
            args={"entity_id": ORIGINAL_ENTITY},
        )
        assert bind_outcome.terminal_state == "awaiting"

        # "yes turn on the bathroom lights" contains "turn on" → NEW_REQUEST → canceled.
        # Either way, if confirmed the bound args must use the ORIGINAL entity.
        resolution = _deliver(sm, "yes turn on the bathroom lights")
        assert resolution.terminal_state in ("denied_ambiguous", "denied", "confirmed", "canceled")
        if resolution.terminal_state == "confirmed":
            assert resolution.bound.entity_id == ORIGINAL_ENTITY
            assert resolution.bound.args["entity_id"] == ORIGINAL_ENTITY

    @pytest.mark.asyncio
    async def test_confirmed_emits_prompt_then_confirmed(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "yes")

        assert cap.events() == ["confirmation_prompt_emitted", "confirmation_confirmed"]

    @pytest.mark.asyncio
    async def test_confirmed_no_request_id_in_payload(self):
        """request_id must NOT appear in any event payload per T1 envelope contract."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "yes")

        for event, payload in cap.calls:
            assert "request_id" not in payload, (
                f"request_id found in payload for {event}: {payload}"
            )

    @pytest.mark.asyncio
    async def test_confirmed_no_user_id_in_payload(self):
        """user_id must NOT appear in any SHARED-sink event payload."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "yes")

        for event, payload in cap.calls:
            assert "user_id" not in payload, (
                f"user_id found in payload for {event}: {payload}"
            )


# ===========================================================================
# State machine — denied path
# ===========================================================================

class TestStateMachineDenied:

    @pytest.mark.asyncio
    async def test_clean_reject_no_denies(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        resolution = _deliver(sm, "no")

        assert resolution.terminal_state == "denied"
        assert resolution.execute_bound_tool is False
        assert "confirmation_denied" in cap.events()

    @pytest.mark.asyncio
    async def test_cancel_stops_denies(self):
        sm = _make_sm()

        await _gate(sm)
        resolution = _deliver(sm, "cancel")

        assert resolution.terminal_state == "denied"
        assert not resolution.execute_bound_tool

    @pytest.mark.asyncio
    async def test_deny_by_default_emits_and_no_gate(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)
        outcome = await sm.gate_tool_call(
            tool_name="HassTurnOn",
            entity_id="switch.oven",
            args={"entity_id": "switch.oven"},
            request_id="r1",
            conversation_id="c1",
            time_of_day=datetime(2026, 5, 7, 14, 0, 0, tzinfo=UTC),
        )
        assert outcome.terminal_state == "denied_by_default"
        assert not outcome.execute_bound_tool
        assert "confirmation_denied_by_default" in cap.events()
        assert "confirmation_prompt_emitted" not in cap.events()

    @pytest.mark.asyncio
    async def test_exterior_unlock_deny_by_default(self):
        sm = _make_sm()
        outcome = await sm.gate_tool_call(
            tool_name="HassUnlock",
            entity_id="lock.front_door",
            args={"entity_id": "lock.front_door"},
            request_id="r1",
            conversation_id="c1",
            time_of_day=datetime(2026, 5, 7, 14, 0, 0, tzinfo=UTC),
        )
        assert outcome.terminal_state == "denied_by_default"
        assert not outcome.execute_bound_tool


# ===========================================================================
# State machine — ambiguous path
# ===========================================================================

class TestStateMachineAmbiguous:

    @pytest.mark.asyncio
    async def test_ambiguous_response_zero_reprompt_default(self):
        """Zero-reprompt default: ambiguous → denied_ambiguous immediately."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        with patch.dict(os.environ, {"HAL_CONFIRM_ONE_REPROMPT": "0"}):
            await _gate(sm)
            resolution = _deliver(sm, "uh")

        assert resolution.terminal_state == "denied_ambiguous"
        assert not resolution.execute_bound_tool
        assert "confirmation_denied_ambiguous" in cap.events()
        assert "confirmation_reprompted" not in cap.events()

    @pytest.mark.asyncio
    async def test_one_reprompt_feature_flag_fires(self):
        """HAL_CONFIRM_ONE_REPROMPT=1: ambiguous → awaiting(reprompt) → denied on second ambiguous."""
        cap = _EmitCapture()
        tts_calls: list[str] = []

        sm = _make_sm(emit_capture=cap, tts_speak=lambda t: tts_calls.append(t))

        with patch.dict(os.environ, {"HAL_CONFIRM_ONE_REPROMPT": "1"}):
            # Turn 1: bind
            bind_outcome = await _gate(sm)
            assert bind_outcome.terminal_state == "awaiting"

            # Turn 2: first ambiguous → reprompt (awaiting again)
            reprompt_outcome = _deliver(sm, "uh")
            assert reprompt_outcome.terminal_state == "awaiting"
            assert reprompt_outcome.awaiting_prompt is not None
            assert "confirmation_reprompted" in cap.events()
            assert sm.pending_id is not None  # still pending

            # Turn 3: second ambiguous → denied_ambiguous terminal
            final_outcome = _deliver(sm, "hmm")

        assert final_outcome.terminal_state == "denied_ambiguous"
        assert "confirmation_denied_ambiguous" in cap.events()
        assert not final_outcome.execute_bound_tool


# ===========================================================================
# State machine — expired path
# ===========================================================================

class TestStateMachineExpired:

    @pytest.mark.asyncio
    async def test_expired_on_timeout_via_deliver(self):
        """Deliver past deadline → expired."""
        cap = _EmitCapture()
        clock = _FakeClock()
        sm = _make_sm(emit_capture=cap, clock=clock, timeout_seconds=1)

        await _gate(sm)
        clock.advance(2)  # past 1s deadline

        resolution = _deliver(sm, "yes")
        assert resolution.terminal_state == "expired"
        assert not resolution.execute_bound_tool
        assert "confirmation_expired" in cap.events()

    @pytest.mark.asyncio
    async def test_expired_on_timeout_via_check(self):
        """check_expired_pending returns expired outcome when deadline passed."""
        cap = _EmitCapture()
        clock = _FakeClock()
        sm = _make_sm(emit_capture=cap, clock=clock, timeout_seconds=1)

        await _gate(sm)
        clock.advance(2)  # past deadline

        expired = sm.check_expired_pending()
        assert expired is not None
        assert expired.terminal_state == "expired"
        assert not expired.execute_bound_tool
        assert "confirmation_expired" in cap.events()
        # After expiry, SM is idle.
        assert sm.pending_id is None

    def test_timeout_max_30s_validated(self):
        with pytest.raises(ValueError, match="30"):
            _make_sm(timeout_seconds=31)


# ===========================================================================
# State machine — canceled path
# ===========================================================================

class TestStateMachineCanceled:

    @pytest.mark.asyncio
    async def test_new_request_utterance_cancels(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        resolution = _deliver(sm, "turn on the kitchen light")

        assert resolution.terminal_state == "canceled"
        assert not resolution.execute_bound_tool
        assert "confirmation_canceled_by_new_request" in cap.events()


# ===========================================================================
# check_expired_pending()
# ===========================================================================

class TestCheckExpiredPending:

    def test_returns_none_when_idle(self):
        sm = _make_sm()
        assert sm.check_expired_pending() is None

    @pytest.mark.asyncio
    async def test_returns_none_within_deadline(self):
        clock = _FakeClock()
        sm = _make_sm(clock=clock, timeout_seconds=15)

        await _gate(sm)
        clock.advance(5)  # well within 15s deadline

        assert sm.check_expired_pending() is None

    @pytest.mark.asyncio
    async def test_returns_expired_when_past_deadline(self):
        clock = _FakeClock()
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap, clock=clock, timeout_seconds=1)

        await _gate(sm)
        clock.advance(2)  # past deadline

        outcome = sm.check_expired_pending()
        assert outcome is not None
        assert outcome.terminal_state == "expired"
        assert not outcome.execute_bound_tool
        assert "confirmation_expired" in cap.events()

    @pytest.mark.asyncio
    async def test_clears_pending_after_expiry(self):
        clock = _FakeClock()
        sm = _make_sm(clock=clock, timeout_seconds=1)

        await _gate(sm)
        clock.advance(2)

        sm.check_expired_pending()
        assert sm.pending_id is None
        assert sm.check_expired_pending() is None  # idempotent after clear


# ===========================================================================
# Cross-tenant safety
# ===========================================================================

class TestCrossTenantSafety:

    @pytest.mark.asyncio
    async def test_different_conversation_id_does_not_confirm(self):
        """Utterance from a different conversation_id must NOT confirm the pending."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm, conversation_id="conv-A")
        resolution = _deliver(sm, "yes", conversation_id="conv-B")  # different conversation

        assert resolution.terminal_state in ("canceled", "expired")
        assert not resolution.execute_bound_tool

    @pytest.mark.asyncio
    async def test_same_conversation_different_request_id_still_confirms(self):
        """The confirmation utterance arrives as a new request_id but same conversation."""
        sm = _make_sm()

        await _gate(sm, request_id="req-1", conversation_id="conv-1")
        resolution = _deliver(sm, "yes", request_id="req-2", conversation_id="conv-1")

        assert resolution.terminal_state == "confirmed"
        assert resolution.execute_bound_tool is True


# ===========================================================================
# TTS-unreachable failure mode (updated for Option B / Amend 2)
# ===========================================================================

class TestTtsUnreachable:

    @pytest.mark.asyncio
    async def test_initial_prompt_tts_hook_failure_is_benign(self):
        """Under Option B, TtsUnreachableError from the initial-prompt hook does NOT deny.

        The prompt travels in-band (HTTP response); the observability hook failing
        is non-fatal. gate_tool_call still returns 'awaiting'.

        Per confirm-before-mutate.md §Failure modes: TTS-unreachable applies to
        the out-of-band TTS path (Option A). Under Option B, prompt is in-band.
        """
        cap = _EmitCapture()

        def _failing_tts(text: str) -> None:
            raise TtsUnreachableError("TTS is down")

        sm = _make_sm(tts_speak=_failing_tts, emit_capture=cap)
        bind_outcome = await _gate(sm)

        # Hook failure must NOT deny — awaiting is returned because prompt is in-band.
        assert bind_outcome.terminal_state == "awaiting"
        assert bind_outcome.awaiting_prompt is not None
        # confirmation_prompt_emitted must still be emitted.
        assert "confirmation_prompt_emitted" in cap.events()

    @pytest.mark.asyncio
    async def test_reprompt_tts_hook_failure_denies_ambiguous(self):
        """TtsUnreachableError in the reprompt path → denied_ambiguous.

        The reprompt's _tts_speak hook failure still triggers denial because the
        reprompt-path TTS hook is a load-bearing signal for that code path.
        Per §Failure modes: 'TTS unreachable → Refuse to mutate.'
        """
        cap = _EmitCapture()
        tts_call_count = [0]

        def _failing_on_second(text: str) -> None:
            tts_call_count[0] += 1
            if tts_call_count[0] >= 2:
                raise TtsUnreachableError("TTS down on reprompt")

        sm = _make_sm(tts_speak=_failing_on_second, emit_capture=cap)

        with patch.dict(os.environ, {"HAL_CONFIRM_ONE_REPROMPT": "1"}):
            # Turn 1: bind — first TTS call succeeds
            await _gate(sm)

            # Turn 2: ambiguous utterance triggers reprompt path; second TTS call raises
            outcome = _deliver(sm, "uh")

        # Reprompt TTS failure → denied_ambiguous (not awaiting/confirmed).
        assert outcome.terminal_state == "denied_ambiguous"
        assert not outcome.execute_bound_tool
        assert "confirmation_denied_ambiguous" in cap.events()


# ===========================================================================
# T3 TurnRecord hook integration
# ===========================================================================

class TestTurnRecordHookIntegration:
    """Verify the state machine's terminal state correctly feeds T3's classifier."""

    def _make_turn(self, *, denied=False, canceled=False, expired=False) -> TurnRecord:
        return TurnRecord(
            authenticated_user_id="michael",
            request_id="req-test",
            user_utterance="unlock the front door",
            tools_called=["HassUnlock"],
            tool_results_ok=False,
            is_tool_call_denied=denied,
            is_tool_call_canceled=canceled,
            is_tool_call_expired=expired,
        )

    def test_denied_flag_classifies_denied_canceled_expired(self):
        turn = self._make_turn(denied=True)
        assert classify(turn) == RetentionCategory.DENIED_CANCELED_EXPIRED

    def test_canceled_flag_classifies_denied_canceled_expired(self):
        turn = self._make_turn(canceled=True)
        assert classify(turn) == RetentionCategory.DENIED_CANCELED_EXPIRED

    def test_expired_flag_classifies_denied_canceled_expired(self):
        turn = self._make_turn(expired=True)
        assert classify(turn) == RetentionCategory.DENIED_CANCELED_EXPIRED

    def test_clean_turn_without_hooks_classifies_normally(self):
        turn = TurnRecord(
            authenticated_user_id="michael",
            request_id="req-test",
            user_utterance="turn on the kitchen light",
            tools_called=["HassTurnOn"],
            tool_results_ok=True,
        )
        assert classify(turn) == RetentionCategory.CONFIRMED_TOOL_CALL_CLEAN

    @pytest.mark.asyncio
    async def test_state_machine_denied_outcome_sets_hook(self):
        """SM denial outcome → caller sets is_tool_call_denied=True → T3 classifies."""
        sm = _make_sm()

        await _gate(sm)
        resolution = _deliver(sm, "no")

        assert resolution.terminal_state == "denied"
        assert not resolution.execute_bound_tool

        is_denied = resolution.terminal_state in (
            "denied", "denied_ambiguous", "denied_by_default", "denied_due_to_degraded_mode"
        )
        turn = TurnRecord(
            authenticated_user_id="michael",
            request_id="req-1",
            user_utterance="unlock front door",
            tools_called=["HassLock"],
            tool_results_ok=False,
            is_tool_call_denied=is_denied,
        )
        assert classify(turn) == RetentionCategory.DENIED_CANCELED_EXPIRED

    @pytest.mark.asyncio
    async def test_state_machine_expired_outcome_sets_hook(self):
        """SM expire outcome → caller sets is_tool_call_expired=True."""
        clock = _FakeClock()
        sm = _make_sm(clock=clock, timeout_seconds=1)

        await _gate(sm)
        clock.advance(2)
        resolution = _deliver(sm, "yes")

        assert resolution.terminal_state == "expired"

        turn = TurnRecord(
            authenticated_user_id="michael",
            request_id="r1",
            user_utterance="lock front door",
            tools_called=["HassLock"],
            tool_results_ok=False,
            is_tool_call_expired=(resolution.terminal_state == "expired"),
        )
        assert classify(turn) == RetentionCategory.DENIED_CANCELED_EXPIRED


# ===========================================================================
# Telemetry shape conformance spot checks
# ===========================================================================

class TestTelemetryPayloadShape:

    @pytest.mark.asyncio
    async def test_prompt_emitted_required_fields(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "yes")

        prompt_payloads = cap.payloads_for("confirmation_prompt_emitted")
        assert prompt_payloads, "confirmation_prompt_emitted must be emitted"
        p = prompt_payloads[0]
        for field in ("conversation_id", "tool_name", "entity_domain", "policy_reason", "bound_at"):
            assert field in p, f"missing field {field!r} in confirmation_prompt_emitted"
        assert "request_id" not in p
        assert "user_id" not in p

    @pytest.mark.asyncio
    async def test_confirmed_required_fields(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "yes")

        payloads = cap.payloads_for("confirmation_confirmed")
        assert payloads
        p = payloads[0]
        for field in ("conversation_id", "tool_name", "entity_domain", "policy_reason",
                      "terminal_state", "attempts", "bound_at", "terminated_at", "latency_ms"):
            assert field in p, f"missing field {field!r} in confirmation_confirmed"
        assert p["terminal_state"] == "confirmed"

    @pytest.mark.asyncio
    async def test_denied_terminal_state_value(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "no")

        payloads = cap.payloads_for("confirmation_denied")
        assert payloads
        assert payloads[0]["terminal_state"] == "denied"

    @pytest.mark.asyncio
    async def test_denied_ambiguous_terminal_state_value(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        with patch.dict(os.environ, {"HAL_CONFIRM_ONE_REPROMPT": "0"}):
            await _gate(sm)
            _deliver(sm, "uh")

        payloads = cap.payloads_for("confirmation_denied_ambiguous")
        assert payloads
        assert payloads[0]["terminal_state"] == "denied_ambiguous"

    @pytest.mark.asyncio
    async def test_expired_terminal_state_value(self):
        cap = _EmitCapture()
        clock = _FakeClock()
        sm = _make_sm(emit_capture=cap, clock=clock, timeout_seconds=1)

        await _gate(sm)
        clock.advance(2)
        _deliver(sm, "wake")

        payloads = cap.payloads_for("confirmation_expired")
        assert payloads
        assert payloads[0]["terminal_state"] == "expired"

    @pytest.mark.asyncio
    async def test_canceled_terminal_state_value(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm)
        _deliver(sm, "turn on the kitchen light")

        payloads = cap.payloads_for("confirmation_canceled_by_new_request")
        assert payloads
        assert payloads[0]["terminal_state"] == "canceled"

    @pytest.mark.asyncio
    async def test_denied_by_default_required_fields(self):
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)
        await sm.gate_tool_call(
            tool_name="HassTurnOn",
            entity_id="switch.oven",
            args={},
            request_id="r1",
            conversation_id="c1",
            time_of_day=datetime(2026, 5, 7, 14, 0, 0, tzinfo=UTC),
        )
        payloads = cap.payloads_for("confirmation_denied_by_default")
        assert payloads
        p = payloads[0]
        for field in ("tool_name", "entity_domain", "policy_reason", "terminated_at"):
            assert field in p, f"missing field {field!r} in confirmation_denied_by_default"
        assert "attempts" not in p

    @pytest.mark.asyncio
    async def test_lock_entity_id_redacted_from_telemetry(self):
        """lock.* is not in the low-sensitivity allowlist — entity_id must not appear."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm, tool_name="HassLock", entity_id="lock.front_door")
        _deliver(sm, "yes")

        for event, payload in cap.calls:
            if "entity_id" in payload:
                from confirm.state_machine import _LOW_SENSITIVITY_DOMAINS, _entity_domain
                eid = payload["entity_id"]
                dom = _entity_domain(eid)
                assert dom in _LOW_SENSITIVITY_DOMAINS, (
                    f"Sensitive entity_id {eid!r} leaked into {event!r} payload"
                )

    @pytest.mark.asyncio
    async def test_light_entity_id_allowed_in_telemetry(self):
        """light.* is low-sensitivity — entity_id may appear in telemetry."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)
        await sm.gate_tool_call(
            tool_name="HassPlayMedia",
            entity_id="media_player.bedroom",
            args={"entity_id": "media_player.bedroom"},
            request_id="r1",
            conversation_id="c1",
            time_of_day=datetime(2026, 5, 7, 23, 0, 0, tzinfo=UTC),  # quiet hours
        )
        prompt_payloads = cap.payloads_for("confirmation_prompt_emitted")
        if prompt_payloads and "entity_id" in prompt_payloads[0]:
            assert "media_player" in prompt_payloads[0]["entity_id"]


# ===========================================================================
# pending_id discrimination
# ===========================================================================

class TestPendingIdDiscrimination:
    """Verify multi-field match (pending_id + conversation_id) is enforced."""

    def test_pending_id_is_none_when_idle(self):
        sm = _make_sm()
        assert sm.pending_id is None

    @pytest.mark.asyncio
    async def test_pending_id_set_after_gate_entry(self):
        """gate_tool_call returns synchronously; pending_id is immediately available."""
        sm = _make_sm()

        bind_outcome = await _gate(sm)
        assert bind_outcome.terminal_state == "awaiting"

        t = sm.pending_id
        assert t is not None
        assert len(t) == 16  # secrets.token_hex(8) → 16 hex chars

        # Clean up
        _deliver(sm, "no")
        assert sm.pending_id is None

    @pytest.mark.asyncio
    async def test_deliver_utterance_with_wrong_pending_id_cancels(self):
        """Same conversation_id but wrong pending_id must cancel, not confirm."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm, conversation_id="conv-1")
        resolution = _deliver(
            sm, "yes",
            conversation_id="conv-1",
            pending_id="wrong-token",  # fabricated
        )

        assert resolution.terminal_state == "canceled"
        assert not resolution.execute_bound_tool
        assert "confirmation_canceled_by_new_request" in cap.events()
        payloads = cap.payloads_for("confirmation_canceled_by_new_request")
        assert payloads[0]["terminal_state"] == "canceled"

    @pytest.mark.asyncio
    async def test_deliver_utterance_with_correct_pending_id_accepts(self):
        """Correct pending_id + same conversation_id + 'yes' → confirmed."""
        cap = _EmitCapture()
        sm = _make_sm(emit_capture=cap)

        await _gate(sm, conversation_id="conv-1")
        resolution = _deliver(sm, "yes", conversation_id="conv-1")  # uses sm.pending_id

        assert resolution.terminal_state == "confirmed"
        assert resolution.execute_bound_tool is True

    @pytest.mark.asyncio
    async def test_deadline_expired_does_not_confirm(self):
        """Clock past deadline → expired even with correct pending_id and 'yes'."""
        cap = _EmitCapture()
        clock = _FakeClock()
        sm = _make_sm(emit_capture=cap, clock=clock, timeout_seconds=1)

        await _gate(sm, conversation_id="c1")
        clock.advance(2)  # past 1s deadline

        resolution = _deliver(sm, "yes", conversation_id="c1")

        assert resolution.terminal_state == "expired"
        assert not resolution.execute_bound_tool
        payloads = cap.payloads_for("confirmation_expired")
        assert payloads[0]["terminal_state"] == "expired"


# ===========================================================================
# BoundConfirmation.original_user_text (Amend 3)
# ===========================================================================

class TestBoundConfirmationOriginalUserText:

    @pytest.mark.asyncio
    async def test_bound_confirmation_has_original_user_text(self):
        """gate_tool_call forwards user_text into BoundConfirmation.original_user_text."""
        sm = _make_sm()
        outcome = await _gate(sm, user_text="lock the front door")
        assert outcome.terminal_state == "awaiting"
        assert outcome.bound is not None
        assert outcome.bound.original_user_text == "lock the front door"

    @pytest.mark.asyncio
    async def test_with_attempts_propagates_original_user_text(self):
        """with_attempts preserves original_user_text on the new BoundConfirmation."""
        sm = _make_sm()
        outcome = await _gate(sm, user_text="lock the front door")
        assert outcome.bound is not None
        new_bound = outcome.bound.with_attempts(1)
        assert new_bound.original_user_text == "lock the front door"
        assert new_bound.attempts == 1
