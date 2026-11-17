"""Conservative cleanup of unreferenced embedded printer presets."""
from __future__ import annotations

import re
import zipfile
from typing import Any, BinaryIO

from ijson import JSONError

try:
    from ijson.backends.yajl2_c import basic_parse
except ImportError:
    # Other backends differ in how strictly they validate ignored settings.
    # Conversion remains available without this optional cleanup.
    basic_parse = None

_IDENTITY_FIELDS = frozenset({"printer_settings_id", "printer_model", "name", "inherits"})
_VECTOR_REFERENCES = ("inherits_group", "compatible_printers", "print_compatible_printers")
_SURROGATE_ESCAPE = re.compile(rb"\\u[dD][89a-fA-F][0-9a-fA-F]{2}")


class _CheckedStream:
    """Avoid YAJL silently replacing invalid surrogate escapes with '?'."""

    def __init__(self, stream: BinaryIO):
        self.stream = stream
        self.tail = b""

    def read(self, size: int) -> bytes:
        chunk = self.stream.read(size)
        if _SURROGATE_ESCAPE.search(self.tail + chunk):
            # Conservatively keep the family, including valid surrogate pairs.
            raise ValueError("Surrogate escape requires preserving preset metadata")
        self.tail = (self.tail + chunk)[-5:]
        return chunk


def _plain_string(value: Any) -> bool:
    # Orca unescapes strings again after JSON decoding. Do not guess at those
    # identities, or at invalid Unicode/control characters in preset names.
    return isinstance(value, str) and not any(
        ch == "\\" or ord(ch) < 32 or 0xD800 <= ord(ch) <= 0xDFFF for ch in value
    )


def _read_identity(stream: BinaryIO) -> dict[str, str]:
    """Validate a JSON object without materializing its unrelated settings."""
    events = basic_parse(_CheckedStream(stream))
    if next(events, None) != ("start_map", None):
        raise ValueError("Preset is not a JSON object")
    fields: dict[str, str] = {}
    depth = 1
    key = None
    for event, value in events:
        if depth == 1:
            if event == "map_key":
                key = value
                if key in _VECTOR_REFERENCES or key == "inherits_cummulative" or key in fields:
                    raise ValueError("Ambiguous preset identity or inheritance")
            elif event != "end_map" and key in _IDENTITY_FIELDS:
                if event != "string" or not _plain_string(value):
                    raise ValueError("Ambiguous preset identity or inheritance")
                fields[key] = value
        if event in ("start_map", "start_array"):
            depth += 1
        elif event in ("end_map", "end_array"):
            depth -= 1
    return fields


def foreign_machine_presets_to_strip(
    archive: zipfile.ZipFile, project_settings: dict[str, Any],
) -> set[str]:
    """Remove only clearly foreign, unreferenced canonical machine embeds.

    Ambiguous metadata leaves the entire machine family intact. Keep every
    named parent, including parents of presets removed by this pass.
    """
    if basic_parse is None:
        return set()
    try:
        return _find_foreign_presets(archive, project_settings)
    except (JSONError, ValueError, UnicodeError, RecursionError, MemoryError, OverflowError):
        # Cleanup is optional. Retain the original entries if parsing fails.
        return set()


def _find_foreign_presets(
    archive: zipfile.ZipFile, project_settings: dict[str, Any],
) -> set[str]:
    target_model = project_settings.get("printer_model")
    target_id = project_settings.get("printer_settings_id")
    if not all(_plain_string(value) and value.strip() for value in (target_model, target_id)):
        return set()
    if "inherits_cummulative" in project_settings:
        return set()

    target_model = target_model.strip().casefold()
    protected: set[str] = set()
    for key in ("printer_settings_id", "printer_model", "inherits"):
        value = project_settings.get(key, "")
        if not _plain_string(value):
            return set()
        protected.add(value)
    for key in _VECTOR_REFERENCES:
        values = project_settings.get(key, [])
        # A scalar can encode Orca's semicolon-separated vector format.
        # Preserve the family rather than interpret it as a single name.
        if not isinstance(values, list) or not all(_plain_string(value) for value in values):
            return set()
        protected.update(values)

    presets: list[tuple[str, str, set[str]]] = []
    seen_names: set[str] = set()
    seen_aliases: set[str] = set()
    for item in archive.infolist():
        name = item.filename
        normalized = name.replace("\\", "/").lower()
        # Noncanonical or legacy process/filament embeds survive archive cleanup
        # and may still reference a machine. Keep its family without guessing.
        if normalized.startswith(("metadata/print_setting_", "metadata/process_settings_",
                                  "metadata/filament_settings_")):
            if not re.fullmatch(r"Metadata/(?:process|filament)_settings_[0-9]+\.config", name):
                return set()
        # Orca accepts this prefix case-insensitively and normalizes backslashes.
        if not normalized.startswith("metadata/machine_settings_"):
            continue
        if not re.fullmatch(r"Metadata/machine_settings_[0-9]+\.config", name) or name in seen_names:
            return set()
        seen_names.add(name)
        with archive.open(item) as stream:
            config = _read_identity(stream)
        preset_id = config.get("printer_settings_id", "")
        if not preset_id.strip():
            return set()
        aliases = {value for value in (preset_id, config.get("name", "")) if value}
        if not aliases.isdisjoint(seen_aliases):
            return set()
        seen_aliases.update(aliases)
        model = config.get("printer_model", "").strip().casefold()
        protected.add(config.get("inherits", ""))
        if not model or model == target_model:
            protected.update(aliases)
        presets.append((name, model, aliases))

    return {
        name for name, model, aliases in presets
        if model and model != target_model and aliases.isdisjoint(protected)
    }
