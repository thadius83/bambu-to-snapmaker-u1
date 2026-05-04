"""Key filtering and value clamping.

Two related operations that run after identity + gcode swap:

1.  ``filter_to_schema`` — drop any key in the source settings that is not in
    the U1 reference schema. Bambu ships a superset of keys; Snapmaker Orca
    ignores unknowns but in some versions will warn or silently misread, so we
    quietly strip them.

2.  ``clamp_numeric_ceilings`` — for a configured set of speed / acceleration
    keys, enforce the U1 reference profile's value as an upper bound. Values
    are stored in Orca profiles as *strings* (e.g. ``"200"``), sometimes as
    lists of strings; we preserve the original type when clamping.
"""
from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from models import ClampEvent, KeyDropEvent

# Keys that represent a speed (mm/s) or acceleration (mm/s^2) ceiling. The
# actual numeric ceiling comes from the U1 reference profile at runtime, not
# hard-coded here — this is just the list of keys *eligible* for clamping.
DEFAULT_CLAMP_KEYS: frozenset[str] = frozenset(
    {
        # speeds
        "outer_wall_speed",
        "inner_wall_speed",
        "sparse_infill_speed",
        "internal_solid_infill_speed",
        "top_surface_speed",
        "gap_infill_speed",
        "travel_speed",
        "initial_layer_speed",
        "initial_layer_infill_speed",
        "initial_layer_travel_speed",
        "overhang_1_4_speed",
        "overhang_2_4_speed",
        "overhang_3_4_speed",
        "overhang_4_4_speed",
        "bridge_speed",
        "support_speed",
        "support_interface_speed",
        # accelerations
        "default_acceleration",
        "outer_wall_acceleration",
        "inner_wall_acceleration",
        "sparse_infill_acceleration",
        "top_surface_acceleration",
        "initial_layer_acceleration",
        "travel_acceleration",
        "bridge_acceleration",
        # prime tower — Bambu uses -1 as sentinel; reference supplies valid default
        "prime_tower_brim_width",
    }
)

# Keys that are *always* identity-controlled and must never be dropped when
# filtering the source profile — they will have been overwritten from the
# reference already in the identity-swap stage, but we keep them regardless.
IDENTITY_KEYS: frozenset[str] = frozenset(
    {
        "printer_settings_id",
        "printer_model",
        "printer_variant",
        "printable_area",
        "printable_height",
        "nozzle_diameter",
        "extruder_count",
        "compatible_printers",
        "compatible_printers_condition",
        "print_settings_id",
    }
)


# ---------------------------------------------------------------------------
# helpers


def _to_float(value: Any) -> float | None:
    """Parse Orca's string-or-number settings into a float, or None on fail."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return None
    return None


def _preserve_type(original: Any, new_value: float) -> Any:
    """Return ``new_value`` coerced to the same representation as ``original``.

    Orca stores most numeric settings as strings. We keep whatever string
    formatting the original used where possible; ints stay ints.
    """
    if isinstance(original, str):
        # Preserve integer-looking strings as integers when the clamped value
        # is integral; otherwise emit a plain %g-style float.
        if new_value.is_integer():
            return str(int(new_value))
        return f"{new_value:g}"
    if isinstance(original, int) and not isinstance(original, bool):
        return int(new_value)
    return new_value


# ---------------------------------------------------------------------------
# public API


def filter_to_schema(
    source: dict[str, Any],
    schema_keys: Iterable[str],
    *,
    keep_keys: Iterable[str] = (),
) -> tuple[dict[str, Any], list[KeyDropEvent]]:
    """Return (filtered_dict, dropped_events).

    ``source`` is mutated-free; we return a new dict containing only keys in
    ``schema_keys`` (plus any in ``keep_keys``). Identity keys are always kept
    even if absent from the schema, since the identity-swap stage writes them.
    """
    allowed = set(schema_keys) | set(keep_keys) | IDENTITY_KEYS
    filtered: dict[str, Any] = {}
    dropped: list[KeyDropEvent] = []
    for key, value in source.items():
        if key in allowed:
            filtered[key] = value
        else:
            dropped.append(KeyDropEvent(key=key, reason="not-in-target-schema"))
    return filtered, dropped


def clamp_numeric_ceilings(
    settings: dict[str, Any],
    reference: dict[str, Any],
    *,
    clamp_keys: Iterable[str] = DEFAULT_CLAMP_KEYS,
) -> tuple[dict[str, Any], list[ClampEvent]]:
    """Clamp ``settings`` values against ceilings from ``reference``.

    For each key in ``clamp_keys`` that exists in both dicts and parses as a
    number (scalar or list of scalars), enforce reference-value as an upper
    bound. Values above the ceiling are lowered; values at or below are left
    alone. Lists are clamped element-wise (one ClampEvent per affected index).

    Returns ``(new_settings, events)`` without mutating the input.
    """
    out = dict(settings)
    events: list[ClampEvent] = []

    for key in clamp_keys:
        if key not in out or key not in reference:
            continue

        ref_val = reference[key]
        cur_val = out[key]

        # list-of-scalars: clamp element-wise.
        if isinstance(cur_val, list) and isinstance(ref_val, list) and ref_val:
            new_list = list(cur_val)
            changed = False
            # Pad reference if shorter — use its last element as the ceiling
            # for trailing slots (matches Orca's "broadcast last" convention).
            for i, element in enumerate(new_list):
                ref_elem = ref_val[i] if i < len(ref_val) else ref_val[-1]
                ceiling = _to_float(ref_elem)
                current = _to_float(element)
                if ceiling is None or current is None:
                    continue
                if current > ceiling:
                    new_element = _preserve_type(element, ceiling)
                    events.append(
                        ClampEvent(
                            key=f"{key}[{i}]",
                            from_value=element,
                            to_value=new_element,
                            ceiling=ref_elem,
                        )
                    )
                    new_list[i] = new_element
                    changed = True
            if changed:
                out[key] = new_list
            continue

        ceiling = _to_float(ref_val)
        current = _to_float(cur_val)
        if ceiling is None or current is None:
            continue
        # 0 and -1 are Bambu sentinels meaning "inherit from default". Replace
        # with the reference value so the U1 gets an explicit, valid setting.
        if current in (0, -1) and ceiling > 0:
            new_val = _preserve_type(cur_val, ceiling)
            events.append(
                ClampEvent(
                    key=key,
                    from_value=cur_val,
                    to_value=new_val,
                    ceiling=ref_val,
                )
            )
            out[key] = new_val
        elif current > ceiling:
            new_val = _preserve_type(cur_val, ceiling)
            events.append(
                ClampEvent(
                    key=key,
                    from_value=cur_val,
                    to_value=new_val,
                    ceiling=ref_val,
                )
            )
            out[key] = new_val

    return out, events
