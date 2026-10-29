"""Edit known model metadata without reserializing slicer extension markup."""
from __future__ import annotations

import re
from xml.parsers import expat

from profile_loader import ProfileLoadError


class MetadataRewriteError(ProfileLoadError):
    """The source metadata cannot be safely rewritten."""


VALUE_REMAP = {
    "ensure_vertical_shell_thickness": {
        "disabled": "none", "enabled": "ensure_all", "partial": "ensure_all",
    },
    "support_style": {"tree_organic": "default"},
    "fuzzy_skin": {"disabled_fuzzy": "none"},
}
_SLOT_KEYS = frozenset({
    "extruder", "wall_filament", "sparse_infill_filament", "solid_infill_filament",
    "support_filament", "support_interface_filament", "wipe_tower_filament",
})
_CONTAINERS = frozenset({"config", "object", "part", "plate"})
_START_TAG = re.compile(rb'''<(?:[^>"']|"[^"]*"|'[^']*')*>''')
_ATTRIBUTE = re.compile(rb'''([^\s=/>]+)\s*=\s*(["'])(.*?)\2''', re.DOTALL)
_ERROR = (
    "Cannot safely update model_settings.config; re-export the project from "
    "its source slicer and try again."
)


def rewrite_model_settings(xml_text: str, remap: dict[int, int]) -> str:
    """Patch metadata value spans; source and target slot numbers are zero-based.

    Snapmaker matches literal slic3rpe:shape/text names, including files without
    namespace declarations. Expat with namespaces disabled accepts that syntax
    while validating XML structure. Only known metadata values are replaced;
    extension tags, quotes, whitespace, entities and text retain their bytes.
    """
    try:
        source = xml_text.encode("utf-8")
    except UnicodeError as err:
        raise MetadataRewriteError(_ERROR) from err

    parser = expat.ParserCreate(encoding="utf-8")
    stack: list[str] = []
    metadata: list[tuple[str, str, int, int]] = []
    object_count = 0

    def start(name: str, attrs: dict[str, str]) -> None:
        nonlocal object_count
        known_context = all(parent in _CONTAINERS for parent in stack)
        if known_context and name == "object":
            object_count += 1
        if known_context and name == "metadata" and "value" in attrs:
            offset = parser.CurrentByteIndex
            tag = _START_TAG.match(source, offset)
            if tag is None:
                raise MetadataRewriteError(_ERROR)
            for attribute in _ATTRIBUTE.finditer(tag.group()):
                if attribute.group(1) == b"value":
                    start, end = attribute.span(3)
                    metadata.append((attrs.get("key", ""), attrs["value"],
                                     offset + start, offset + end))
                    break
            else:
                raise MetadataRewriteError(_ERROR)
        stack.append(name)

    def reject_doctype(*_args: object) -> None:
        # Model settings need no DTD. Reject declarations before any entities
        # can be expanded or external resources requested.
        raise MetadataRewriteError(_ERROR)

    parser.StartElementHandler = start
    parser.EndElementHandler = lambda _name: stack.pop()
    parser.StartDoctypeDeclHandler = reject_doctype
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(source, True)
    except expat.ExpatError as err:
        raise MetadataRewriteError(_ERROR) from err

    raft_values = [value for key, value, _, _ in metadata if key == "raft_layers"]
    effective_raft = set(raft_values)
    if len(raft_values) < object_count:
        effective_raft.add("0")
    normalize_raft = len(effective_raft) > 1

    patches: list[tuple[int, int, bytes]] = []
    for key, value, start, end in metadata:
        replacement = VALUE_REMAP.get(key, {}).get(value, value)
        if key == "raft_layers" and normalize_raft:
            replacement = "0"
        elif key in _SLOT_KEYS:
            try:
                slot = int(value)
            except ValueError:
                continue
            if slot > 0 and slot - 1 in remap:
                replacement = str(max(remap[slot - 1], 0) + 1)
        elif key == "filament_maps":
            # Preserve existing four-toolhead routing normalization.
            slots = value.split()
            replacement = " ".join(str(i % 4 + 1) for i in range(len(slots))) if slots else value
        if replacement != value:
            patches.append((start, end, replacement.encode("utf-8")))

    for start, end, replacement in reversed(patches):
        source = source[:start] + replacement + source[end:]
    return source.decode("utf-8")
