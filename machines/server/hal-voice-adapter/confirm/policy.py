"""Policy lookup for the T5 confirm-before-mutate state machine.

Maps (tool_name, entity_id, args, time_of_day, area) to a PolicyResult
encoding the outcome from docs/security/high-impact-tools.md (#44).

The policy is encoded directly as Python — the doc remains authoritative and
this module mirrors it.  All logic is in one function for easy diff against the
doc.  Do NOT parse the markdown at runtime.

Per confirm-before-mutate.md §Policy lookup and docs/security/high-impact-tools.md.
"""
from __future__ import annotations

import re
from datetime import datetime, time as dtime
from typing import Optional

from .models import PolicyOutcome, PolicyResult

# ---------------------------------------------------------------------------
# Entity domain helpers
# ---------------------------------------------------------------------------

def _domain(entity_id: str) -> str:
    """Extract HA domain from entity_id (e.g. 'light.kitchen' → 'light')."""
    return entity_id.split(".", 1)[0] if "." in entity_id else entity_id


def _entity_lower(entity_id: str) -> str:
    return entity_id.lower()


# High-risk switch/device name fragments.  A HassTurnOn/Off targeting an entity
# whose friendly-name or entity_id contains one of these strings is contextual+matched.
_HIGH_RISK_FRAGMENTS: tuple[str, ...] = (
    "heater", "heat", "pump", "oven", "stove", "appliance", "garage",
    "security", "camera", "cam", "alarm", "server", "router", "network",
    "medical", "refrigerator", "fridge", "freezer", "sprinkler",
    "high_watt", "high-watt", "hvac", "boiler", "furnace",
)

_QUIET_HOURS_START = dtime(22, 0)   # 10 PM
_QUIET_HOURS_END   = dtime(7, 0)    # 7 AM

_BEDROOM_FRAGMENTS: tuple[str, ...] = ("bedroom", "master", "guest_room", "guest room")
_SLEEP_FRAGMENTS: tuple[str, ...] = _BEDROOM_FRAGMENTS

_EXTERIOR_LOCK_FRAGMENTS: tuple[str, ...] = (
    "front", "back", "rear", "garage", "exterior", "deadbolt", "entry",
    "main", "door", "gate", "access",
)

_GARAGE_FRAGMENTS: tuple[str, ...] = ("garage", "gate", "access_point")
_SAFETY_SENSOR_FRAGMENTS: tuple[str, ...] = (
    "smoke", "co", "carbon_monoxide", "leak", "water_sensor",
)

_MEDIA_DISRUPTION_FRAGMENTS: tuple[str, ...] = (
    "bedroom", "master", "living_room",
)


def _has_fragment(entity_id: str, *fragment_sets: tuple[str, ...]) -> bool:
    el = entity_id.lower()
    for fragments in fragment_sets:
        if any(f in el for f in fragments):
            return True
    return False


def _is_quiet_hours(tod: datetime) -> bool:
    t = tod.time()
    if _QUIET_HOURS_START <= _QUIET_HOURS_END:
        return _QUIET_HOURS_START <= t <= _QUIET_HOURS_END
    # Overnight crossing
    return t >= _QUIET_HOURS_START or t <= _QUIET_HOURS_END


def _safe_band_temp(args: dict) -> bool:
    """True if the temperature is within a 'normal comfort' band (60–80 °F / 15–27 °C)."""
    temp = args.get("temperature")
    if temp is None:
        return True
    try:
        temp = float(temp)
    except (TypeError, ValueError):
        return True
    # Accept both Fahrenheit and Celsius ranges loosely — flag outliers
    return 60.0 <= temp <= 80.0 or 15.0 <= temp <= 27.0


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def lookup_policy(
    tool_name: str,
    entity_id: str,
    args: dict,
    *,
    time_of_day: datetime,
    area: Optional[str] = None,
) -> PolicyResult:
    """Return PolicyResult for a resolved tool call.

    Encodes policy from docs/security/high-impact-tools.md (#44) as a simple
    conditional ladder.  Keep it in one function — easy to diff against the doc.

    Per confirm-before-mutate.md §Policy lookup: "Policy lookup is the only
    entry point. Classifier output cannot affect this lookup."
    """
    domain = _domain(entity_id)
    el = _entity_lower(entity_id)
    area_lower = (area or "").lower()

    # ------------------------------------------------------------------
    # HassGetState — never requires confirmation (read-only)
    # Per #44: "never" — "Read-only. Confirmation is not required."
    # ------------------------------------------------------------------
    if tool_name == "HassGetState":
        return PolicyResult(
            outcome=PolicyOutcome.NEVER,
            policy_reason="never",
            confirms=False,
        )

    # ------------------------------------------------------------------
    # HassUnlock — always requires confirmation
    # Per #44: "`always`; consider `deny-by-default` for exterior locks
    # until #13 lands"
    # Now that #13 is landing, exterior locks become deny-by-default.
    # ------------------------------------------------------------------
    if tool_name == "HassUnlock":
        if domain == "lock" and _has_fragment(entity_id, _EXTERIOR_LOCK_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.DENY_BY_DEFAULT,
                policy_reason="deny-by-default",
                confirms=False,
            )
        return PolicyResult(
            outcome=PolicyOutcome.ALWAYS,
            policy_reason="always",
            confirms=True,
        )

    # ------------------------------------------------------------------
    # HassLock — always for exterior locks; contextual otherwise
    # Per #44: "`always` for exterior locks, deadbolts, garage-connected
    # locks, or any access-control lock"
    # ------------------------------------------------------------------
    if tool_name == "HassLock":
        if domain == "lock" and _has_fragment(entity_id, _EXTERIOR_LOCK_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.ALWAYS,
                policy_reason="always",
                confirms=True,
            )
        if domain == "lock":
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+interior_lock",
                confirms=True,
            )
        return PolicyResult(
            outcome=PolicyOutcome.CONTEXTUAL,
            policy_reason="contextual",
            confirms=False,
        )

    # ------------------------------------------------------------------
    # HassSetTemperature — contextual
    # Per #44: target temp outside safe/comfort band; large delta;
    # bedroom/sleep areas; future mode changes.
    # ------------------------------------------------------------------
    if tool_name == "HassSetTemperature":
        if not _safe_band_temp(args):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+temp_out_of_band",
                confirms=True,
            )
        if _has_fragment(entity_id, _SLEEP_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+bedroom",
                confirms=True,
            )
        # Mode changes: "heat" / "cool" / "off" / "emergency heat" in args
        mode = args.get("hvac_mode") or args.get("mode") or ""
        if mode:
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+mode_change",
                confirms=True,
            )
        return PolicyResult(
            outcome=PolicyOutcome.CONTEXTUAL,
            policy_reason="contextual",
            confirms=False,
        )

    # ------------------------------------------------------------------
    # HassTurnOn — contextual
    # Per #44: high-risk entity; quiet hours + bedroom/sleep areas; ambiguous.
    # Low-risk lights skip confirmation.
    # deny-by-default: ovens, stoves, space heaters, high-wattage, hazardous.
    # ------------------------------------------------------------------
    if tool_name == "HassTurnOn":
        # Deny-by-default: ovens, stoves, space heaters, hazardous appliances
        if _has_fragment(entity_id, ("oven", "stove", "space_heater")):
            return PolicyResult(
                outcome=PolicyOutcome.DENY_BY_DEFAULT,
                policy_reason="deny-by-default",
                confirms=False,
            )
        # Deny-by-default: disabling alarms / safety sensors
        if _has_fragment(entity_id, _SAFETY_SENSOR_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.DENY_BY_DEFAULT,
                policy_reason="deny-by-default",
                confirms=False,
            )
        # Contextual+high-risk device
        if _has_fragment(entity_id, _HIGH_RISK_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+high_risk_device",
                confirms=True,
            )
        # Contextual: quiet hours + bedroom/sleep areas
        if _is_quiet_hours(time_of_day) and _has_fragment(entity_id, _SLEEP_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+quiet_hours_sleep",
                confirms=True,
            )
        # Light entity — low risk; never confirm
        if domain == "light":
            return PolicyResult(
                outcome=PolicyOutcome.NEVER,
                policy_reason="never",
                confirms=False,
            )
        # Switch with no high-risk fragment — contextual, no elevated match
        return PolicyResult(
            outcome=PolicyOutcome.CONTEXTUAL,
            policy_reason="contextual",
            confirms=False,
        )

    # ------------------------------------------------------------------
    # HassTurnOff — contextual (mirrors HassTurnOn with different hazard list)
    # Per #44: cameras, alarms, network, servers, medical, refrigerators,
    # heaters, HVAC, pumps, safety devices.
    # ------------------------------------------------------------------
    if tool_name == "HassTurnOff":
        # Deny-by-default: safety sensors
        if _has_fragment(entity_id, _SAFETY_SENSOR_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.DENY_BY_DEFAULT,
                policy_reason="deny-by-default",
                confirms=False,
            )
        # Contextual+high-risk
        if _has_fragment(entity_id, _HIGH_RISK_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+high_risk_device",
                confirms=True,
            )
        # Quiet hours + bedroom/sleep areas
        if _is_quiet_hours(time_of_day) and _has_fragment(entity_id, _SLEEP_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+quiet_hours_sleep",
                confirms=True,
            )
        # Light — low risk
        if domain == "light":
            return PolicyResult(
                outcome=PolicyOutcome.NEVER,
                policy_reason="never",
                confirms=False,
            )
        return PolicyResult(
            outcome=PolicyOutcome.CONTEXTUAL,
            policy_reason="contextual",
            confirms=False,
        )

    # ------------------------------------------------------------------
    # HassPlayMedia — never by default; contextual for disruptive contexts
    # Per #44: "never" by default; "contextual" for bedroom/sleep areas during
    # quiet hours, or disruptive contexts.
    # ------------------------------------------------------------------
    if tool_name == "HassPlayMedia":
        if _is_quiet_hours(time_of_day) and _has_fragment(entity_id, _MEDIA_DISRUPTION_FRAGMENTS):
            return PolicyResult(
                outcome=PolicyOutcome.CONTEXTUAL,
                policy_reason="contextual+quiet_hours_media",
                confirms=True,
            )
        return PolicyResult(
            outcome=PolicyOutcome.NEVER,
            policy_reason="never",
            confirms=False,
        )

    # ------------------------------------------------------------------
    # Unknown tool — deny-by-default per #44:
    # "service calls outside the approved static tool schema"
    # ------------------------------------------------------------------
    return PolicyResult(
        outcome=PolicyOutcome.DENY_BY_DEFAULT,
        policy_reason="deny-by-default",
        confirms=False,
    )
