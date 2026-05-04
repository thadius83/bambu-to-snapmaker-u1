"""Swap Bambu custom G-code blocks for the U1 reference equivalents.

Bambu's start/end/layer/pause/change_filament G-code contains printer-specific
commands (AMS swaps, chamber control, gantry homing sequences) that would at
best do nothing on a Snapmaker U1 and at worst crash it. We unconditionally
replace every configured block with whatever the reference profile ships, and
record a ``GcodeSwapEvent`` per block so the diff view can show what changed.
"""
from __future__ import annotations

from typing import Any

from models import GcodeSwapEvent

# Keys whose contents are wholesale replaced from the reference profile.
# Both ``layer_change_gcode`` (fires after a layer) and
# ``before_layer_change_gcode`` (fires before) exist in Orca — we swap both
# so timelapse / defect-detection hooks match what the U1 firmware expects.
GCODE_KEYS: tuple[str, ...] = (
    "machine_start_gcode",
    "machine_end_gcode",
    "before_layer_change_gcode",
    "layer_change_gcode",
    "change_filament_gcode",
    "machine_pause_gcode",
    "template_custom_gcode",
    "printing_by_object_gcode",
    "time_lapse_gcode",
)


def _byte_len(value: Any) -> int:
    """Bytes of a G-code value, whether stored as str or list[str]."""
    if value is None:
        return 0
    if isinstance(value, str):
        return len(value.encode("utf-8"))
    if isinstance(value, list):
        # Orca sometimes stores per-extruder lists; collapse to the joined
        # bytes so the diff view shows a stable size.
        return sum(
            len(v.encode("utf-8")) for v in value if isinstance(v, str)
        )
    return len(str(value).encode("utf-8"))


def swap_gcode(
    source: dict[str, Any],
    reference: dict[str, Any],
    *,
    keys: tuple[str, ...] = GCODE_KEYS,
) -> tuple[dict[str, Any], list[GcodeSwapEvent]]:
    """Return (new_settings, events).

    For each ``key`` in ``keys``:
      - if the reference defines the key, the source value is overwritten
        with the reference value (even if the reference value is empty — a
        blank reference means "U1 doesn't run anything here");
      - if the reference does *not* define the key, the key is deleted from
        source (Bambu-only block — shouldn't be emitted by U1);
      - a ``GcodeSwapEvent`` is recorded in every case where the byte count
        changed or the key was removed.
    """
    out = dict(source)
    events: list[GcodeSwapEvent] = []

    for key in keys:
        src_present = key in out
        ref_present = key in reference

        from_bytes = _byte_len(out.get(key))
        if ref_present:
            out[key] = reference[key]
            to_bytes = _byte_len(out[key])
        else:
            # Reference has no opinion → remove the source block.
            if src_present:
                del out[key]
            to_bytes = 0

        if src_present or ref_present:
            # Always log the swap (even when identical) so the diff clearly
            # shows that the pipeline handled this block. The UI can filter
            # zero-delta events if it wants a tighter summary.
            events.append(
                GcodeSwapEvent(
                    key=key, from_bytes=from_bytes, to_bytes=to_bytes
                )
            )

    return out, events
