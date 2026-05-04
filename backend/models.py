"""Pydantic models shared across backend modules.

These describe:
  - the conversion request options from the frontend
  - per-stage event types used to build the diff report
  - the final DiffReport shape returned alongside the converted file
  - YAML rule definitions loaded from /rules/
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator


# -------- request options ----------------------------------------------------


class ConversionSettings(BaseModel):
    """Options posted by the frontend alongside the uploaded 3mf."""

    reference_profile: str = Field(
        ...,
        description="Filename (stem or full name) of a U1 reference profile "
        "from /profiles or /user_profiles.",
    )
    apply_rules: bool = True
    clamp_speeds: bool = True
    strip_custom_gcode: bool = True  # enforced true at the pipeline boundary
    preserve_color_painting: bool = True
    advanced_overrides: dict[str, Any] = Field(default_factory=dict)
    # 0-indexed source slot → 0-indexed U1 toolhead. Empty = identity map.
    slot_map: dict[int, int] = Field(default_factory=dict)
    # Insert M600 pauses when a physical toolhead must swap filament mid-print.
    insert_swap_pauses: bool = False


# -------- diff events --------------------------------------------------------


class IdentitySwap(BaseModel):
    key: str
    from_value: Any = None
    to_value: Any = None


class GcodeSwapEvent(BaseModel):
    key: str
    from_bytes: int
    to_bytes: int


class KeyDropEvent(BaseModel):
    key: str
    reason: str = "not-in-target-schema"


class ClampEvent(BaseModel):
    key: str
    from_value: Any
    to_value: Any
    ceiling: Any


class RuleMatch(BaseModel):
    rule_name: str
    priority: int
    matched_on: dict[str, Any]
    overrides_applied: dict[str, Any]


class SlotRemapEvent(BaseModel):
    from_index: int
    to_index: int
    filament_id: str | None = None


class SwapInstruction(BaseModel):
    """One physical-toolhead filament swap the user must perform mid-print."""
    z: float             # Z height of the M600 pause
    toolhead: int        # 1-based physical toolhead number
    from_slot: int       # 1-based source slot being replaced
    to_slot: int         # 1-based source slot taking over
    from_colour: str     # hex colour being replaced
    to_colour: str       # hex colour being loaded
    label: str           # human-readable e.g. "T1: #000000 → #FFFF00"


class DiffReport(BaseModel):
    """Structured summary of everything the pipeline changed."""

    model_config = {"protected_namespaces": ()}

    source_filename: str
    output_filename: str
    reference_profile: str

    identity_swaps: list[IdentitySwap] = Field(default_factory=list)
    gcode_swaps: list[GcodeSwapEvent] = Field(default_factory=list)
    keys_dropped: list[KeyDropEvent] = Field(default_factory=list)
    values_clamped: list[ClampEvent] = Field(default_factory=list)
    rules_matched: list[RuleMatch] = Field(default_factory=list)
    slot_remaps: list[SlotRemapEvent] = Field(default_factory=list)

    model_keys_dropped: list[KeyDropEvent] = Field(default_factory=list)
    slice_artifacts_stripped: list[str] = Field(default_factory=list)
    advanced_overrides_applied: dict[str, Any] = Field(default_factory=dict)
    swap_instructions: list[SwapInstruction] = Field(default_factory=list)
    swap_pauses_skipped_painted: bool = False

    def counts(self) -> dict[str, int]:
        return {
            "identity_swaps": len(self.identity_swaps),
            "gcode_swaps": len(self.gcode_swaps),
            "keys_dropped": len(self.keys_dropped),
            "values_clamped": len(self.values_clamped),
            "rules_matched": len(self.rules_matched),
            "slot_remaps": len(self.slot_remaps),
            "model_keys_dropped": len(self.model_keys_dropped),
            "slice_artifacts_stripped": len(self.slice_artifacts_stripped),
            "advanced_overrides_applied": len(self.advanced_overrides_applied),
            "swap_instructions": len(self.swap_instructions),
        }


# -------- rule YAML schema ---------------------------------------------------


class RuleMatchConditions(BaseModel):
    filament_settings_id_contains: str | None = None
    filament_vendor: str | None = None
    filament_type: str | None = None
    base_profile_contains: str | None = None


class RuleDefinition(BaseModel):
    name: str
    description: str = ""
    match: RuleMatchConditions = Field(default_factory=RuleMatchConditions)
    overrides: dict[str, Any] = Field(default_factory=dict)
    priority: int = 0
    enabled: bool = True

    # Not part of the YAML — populated by the loader for round-tripping.
    source_path: str | None = None

    @field_validator("name")
    @classmethod
    def _name_nonempty(cls, v: str) -> str:
        if not v or not v.strip():
            raise ValueError("rule name cannot be empty")
        return v.strip()


class ProfileDescriptor(BaseModel):
    """One entry in the reference-profile list exposed to the frontend."""

    id: str  # stable id the client posts back (filename stem)
    display_name: str
    path: str
    source: str  # "bundled" or "user"
    layer_height: str | None = None
    printer_variant: str | None = None
