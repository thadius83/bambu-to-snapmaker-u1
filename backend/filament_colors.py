"""Color metadata shared by conversion and upload previews."""
from __future__ import annotations

import re
from typing import Any


def translate_filament_colors(source: dict[str, Any]) -> dict[str, Any]:
    """Translate colors within a single filament before filtering Bambu keys.

    Snapmaker uses pipe-separated colors and inverted display-mode values.
    Existing Snapmaker fields are authoritative when both formats are present.
    The resulting arrays follow the regular filament slot remapping below.
    """
    out = dict(source)
    colors = source.get("filament_multi_colour")
    if (
        "filament_multi_colors" not in out
        and isinstance(colors, list)
        and all(isinstance(value, str) for value in colors)
    ):
        out["filament_multi_colors"] = ["|".join(value.split()) for value in colors]
    modes = source.get("filament_colour_type")
    if "filament_colour_mode" not in out:
        if isinstance(modes, list) and all(isinstance(value, str) for value in modes):
            # Bambu: 0 = gradient, 1 = split. Snapmaker: 1 = gradient, 0 = split.
            out["filament_colour_mode"] = ["1" if value == "0" else "0" for value in modes]
        elif isinstance(out.get("filament_multi_colors"), list):
            out["filament_colour_mode"] = ["0"] * len(out["filament_multi_colors"])
    return out


def describe_filaments(source: dict[str, Any]) -> list[dict[str, Any]]:
    """Expose full per-filament palettes without modifying the uploaded settings."""
    cfg = translate_filament_colors(source)
    ids = cfg.get("filament_settings_id") or []

    def value(key: str, index: int) -> Any:
        values = cfg.get(key)
        return values[index] if isinstance(values, list) and index < len(values) else None

    def is_hex(color: Any) -> bool:
        return isinstance(color, str) and re.fullmatch(
            r"#(?:[0-9a-fA-F]{3}|[0-9a-fA-F]{4}|[0-9a-fA-F]{6}|[0-9a-fA-F]{8})", color
        ) is not None

    filaments = []
    for i in range(len(ids)):
        primary = value("filament_colour", i)
        raw_palette = value("filament_multi_colors", i)
        palette = (
            [c.strip() for c in raw_palette.split("|") if is_hex(c.strip())]
            if isinstance(raw_palette, str) else []
        )
        if not palette and is_hex(primary):
            palette = [primary]
        filaments.append({
            "index": i,
            "settings_id": ids[i],
            "filament_type": value("filament_type", i),
            "vendor": value("filament_vendor", i),
            "colour": primary,
            "colours": palette,
            "colour_mode": "gradient" if str(value("filament_colour_mode", i)) == "1" else "split",
        })
    return filaments
