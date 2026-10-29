"""Remap physical filament leaves in Orca/Bambu triangle paint strings.

Encoding references (Snapmaker/OrcaSlicer v2.4.1):
src/libslic3r/TriangleSelector.cpp, TriangleSelector::serialize/deserialize;
src/libslic3r/Model.cpp, FacetsAnnotation::get/set_triangle_as/from_string.
"""
from __future__ import annotations

import re


# Match triangle tags without touching comments, CDATA, or processing instructions.
_TRIANGLES = re.compile(
    r'<!--.*?-->|<!\[CDATA\[.*?\]\]>|<\?.*?\?>|'
    r'''<(?:[\w.-]+:)?triangle(?=[\s/>])(?:[^<>"']|"[^"]*"|'[^']*')*>''',
    re.DOTALL,
)
_ATTRIBUTES = re.compile(r'''([^\s=<>/]+)(\s*=\s*)(["'])(.*?)\3''', re.DOTALL)


def _remap_tree(paint: str, remap: dict[int, int], source_count: int) -> str:
    """Read one tree right to left, preserving split markers and unchanged leaves."""
    pos = len(paint) - 1
    pending = 1
    chunks: list[str] = []
    try:
        while pending:
            if pos < 0:
                return paint
            end = pos + 1
            code = int(paint[pos], 16)
            pos -= 1
            pending -= 1
            splits = code & 3
            if splits:
                pending += splits + 1
                chunks.append(paint[pos + 1:end])
                continue

            state = code >> 2
            if state == 3:
                while True:
                    if pos < 0:
                        return paint
                    extension = int(paint[pos], 16)
                    pos -= 1
                    state += extension
                    if extension != 15:
                        break

            mapped = state
            if 1 <= state <= source_count:
                target = remap.get(state - 1, state - 1)
                mapped = max(1, target + 1)  # Dropped slots match metadata's head-1 fallback.
            if mapped == state:
                chunks.append(paint[pos + 1:end])
            elif mapped < 3:
                chunks.append(format(mapped << 2, "X"))
            else:
                extensions, remainder = divmod(mapped - 3, 15)
                chunks.append(format(remainder, "X") + "F" * extensions + "C")
    except ValueError:
        return paint

    # An incomplete tree or trailing data must never be partially rewritten.
    return "".join(reversed(chunks)) if pos == -1 else paint


def remap_paint_color(
    model_xml: str, remap: dict[int, int], source_filament_count: int
) -> str:
    """Apply the canonical zero-based filament remap only to paint_color values.

    State zero inherits the object/volume extruder, which the converter remaps
    separately. States above the physical source count are native virtual colors
    and remain untouched. Other XML text, including all mesh geometry, is retained.
    """
    if "paint_color" not in model_xml or not any(
        0 <= src < source_filament_count and dst != src for src, dst in remap.items()
    ):
        return model_xml

    cache: dict[str, str] = {}

    def attribute(match: re.Match[str]) -> str:
        if match[1] != "paint_color":
            return match[0]
        paint = match[4]
        if paint not in cache:
            cache[paint] = _remap_tree(paint, remap, source_filament_count)
        return match[1] + match[2] + match[3] + cache[paint] + match[3]

    def triangle(match: re.Match[str]) -> str:
        tag = match[0]
        if tag.startswith(("<!", "<?")) or "paint_color" not in tag:
            return tag
        return _ATTRIBUTES.sub(attribute, tag)

    return _TRIANGLES.sub(triangle, model_xml)
