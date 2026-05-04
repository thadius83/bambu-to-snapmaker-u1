"""Assemble the final DiffReport from per-stage events.

Each pipeline module emits event lists (IdentitySwap, GcodeSwapEvent, etc).
This module collects them into a single structured DiffReport and provides a
human-readable summary suitable for the frontend's collapsible sections.
"""
from __future__ import annotations

from typing import Any

from models import (
    ClampEvent,
    DiffReport,
    GcodeSwapEvent,
    IdentitySwap,
    KeyDropEvent,
    RuleMatch,
    SlotRemapEvent,
)


class DiffBuilder:
    """Mutable accumulator used by the converter pipeline."""

    def __init__(
        self,
        *,
        source_filename: str,
        output_filename: str,
        reference_profile: str,
    ) -> None:
        self._report = DiffReport(
            source_filename=source_filename,
            output_filename=output_filename,
            reference_profile=reference_profile,
        )

    # -- per-stage hooks ----------------------------------------------------

    def record_identity_swap(
        self, key: str, from_value: Any, to_value: Any
    ) -> None:
        self._report.identity_swaps.append(
            IdentitySwap(key=key, from_value=from_value, to_value=to_value)
        )

    def extend_gcode_swaps(self, events: list[GcodeSwapEvent]) -> None:
        self._report.gcode_swaps.extend(events)

    def extend_keys_dropped(self, events: list[KeyDropEvent]) -> None:
        self._report.keys_dropped.extend(events)

    def extend_values_clamped(self, events: list[ClampEvent]) -> None:
        self._report.values_clamped.extend(events)

    def extend_rules_matched(self, events: list[RuleMatch]) -> None:
        self._report.rules_matched.extend(events)

    def extend_slot_remaps(self, events: list[SlotRemapEvent]) -> None:
        self._report.slot_remaps.extend(events)

    def extend_model_keys_dropped(self, events: list[KeyDropEvent]) -> None:
        self._report.model_keys_dropped.extend(events)

    def record_slice_artifact_stripped(self, name: str) -> None:
        self._report.slice_artifacts_stripped.append(name)

    def record_advanced_override(self, key: str, value: Any) -> None:
        self._report.advanced_overrides_applied[key] = value

    # -- output -------------------------------------------------------------

    def build(self) -> DiffReport:
        return self._report


# ---------------------------------------------------------------------------
# helpers consumed by the frontend / API layer


def summarise(report: DiffReport) -> list[dict[str, Any]]:
    """Flatten a DiffReport into UI-friendly sections.

    Each section has a ``title``, a one-line ``summary`` for the collapsed
    header, and a ``details`` payload the frontend can render expanded.
    """
    sections: list[dict[str, Any]] = []

    if report.identity_swaps:
        printer_changes = [
            s for s in report.identity_swaps
            if s.key in {"printer_model", "printer_settings_id"}
        ]
        summary = f"Identity swapped ({len(report.identity_swaps)} keys)"
        if printer_changes:
            pm = next(
                (s for s in printer_changes if s.key == "printer_model"),
                printer_changes[0],
            )
            summary = f"Identity swapped: {pm.from_value} → {pm.to_value}"
        sections.append(
            {
                "title": "Printer identity",
                "summary": summary,
                "details": [s.model_dump() for s in report.identity_swaps],
            }
        )

    if report.gcode_swaps:
        sections.append(
            {
                "title": "Custom G-code",
                "summary": f"{len(report.gcode_swaps)} blocks replaced",
                "details": [e.model_dump() for e in report.gcode_swaps],
            }
        )

    if report.keys_dropped:
        sections.append(
            {
                "title": "Keys dropped",
                "summary": (
                    f"{len(report.keys_dropped)} Bambu-only keys removed"
                ),
                "details": [e.model_dump() for e in report.keys_dropped],
            }
        )

    if report.values_clamped:
        sections.append(
            {
                "title": "Values clamped",
                "summary": (
                    f"{len(report.values_clamped)} values reduced to U1 max"
                ),
                "details": [e.model_dump() for e in report.values_clamped],
            }
        )

    if report.rules_matched:
        names = ", ".join(r.rule_name for r in report.rules_matched)
        sections.append(
            {
                "title": "Filament rules applied",
                "summary": f"{len(report.rules_matched)} rules matched: {names}",
                "details": [r.model_dump() for r in report.rules_matched],
            }
        )

    if report.slot_remaps:
        sections.append(
            {
                "title": "Filament slots",
                "summary": f"{len(report.slot_remaps)} filaments remapped",
                "details": [s.model_dump() for s in report.slot_remaps],
            }
        )

    if report.model_keys_dropped:
        sections.append(
            {
                "title": "Model settings filtered",
                "summary": (
                    f"{len(report.model_keys_dropped)} per-object keys dropped"
                ),
                "details": [
                    e.model_dump() for e in report.model_keys_dropped
                ],
            }
        )

    if report.slice_artifacts_stripped:
        sections.append(
            {
                "title": "Slice caches stripped",
                "summary": (
                    f"{len(report.slice_artifacts_stripped)} stale "
                    "plate_*.gcode / plate_*.json files removed"
                ),
                "details": list(report.slice_artifacts_stripped),
            }
        )

    if report.advanced_overrides_applied:
        sections.append(
            {
                "title": "Advanced overrides",
                "summary": (
                    f"{len(report.advanced_overrides_applied)} per-key "
                    "overrides applied from the UI"
                ),
                "details": dict(report.advanced_overrides_applied),
            }
        )

    if report.swap_instructions:
        sections.append(
            {
                "title": "Filament swap pauses",
                "summary": (
                    f"{len(report.swap_instructions)} M600 pause"
                    f"{'s' if len(report.swap_instructions) > 1 else ''} inserted"
                ),
                "details": [s.model_dump() for s in report.swap_instructions],
            }
        )

    return sections
