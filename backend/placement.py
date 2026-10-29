"""Shared bed placement rules for conversion and source-profile warnings."""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from xml.parsers import expat

from model_settings import MetadataRewriteError
from profile_loader import ProfileLoadError


# Use 400 mm so large single-plate beds (for example H2D's 350 mm bed) still
# shift; a larger build-item span is treated as a multi-plate layout.
_MULTIPLATE_SPAN_MM = 400.0

_START_TAG = re.compile(rb'''<(?:[^>"']|"[^"]*"|'[^']*')*>''')
_ATTRIBUTE = re.compile(
    rb'''(?P<name>[^\s=<>/]+)\s*=\s*(?P<quote>["'])(?P<value>.*?)(?P=quote)''',
    re.DOTALL,
)


def _bed_geometry(area: list[str]) -> tuple[float, float, float, float] | None:
    try:
        points = [tuple(map(float, point.split("x"))) for point in area]
        if not points or any(len(point) != 2 or not all(map(math.isfinite, point)) for point in points):
            return None
        min_x, max_x = min(point[0] for point in points), max(point[0] for point in points)
        min_y, max_y = min(point[1] for point in points), max(point[1] for point in points)
        width, height = max_x - min_x, max_y - min_y
        geometry = (min_x + width / 2, min_y + height / 2, width, height)
        if width <= 0 or height <= 0 or not all(map(math.isfinite, geometry)):
            return None
        # A line or isolated points do not define a printable area. Normalize
        # before testing non-collinearity so large finite coordinates stay safe.
        normalized = {(float(x - min_x) / width, float(y - min_y) / height) for x, y in points}
        if len(normalized) < 3:
            return None
        anchor, second, *others = normalized
        dx, dy = second[0] - anchor[0], second[1] - anchor[1]
        if not any((x - anchor[0]) * dy != (y - anchor[1]) * dx for x, y in others):
            return None
        return geometry
    except (AttributeError, TypeError, ValueError):
        return None


def bed_offset(src_area: list[str], ref_area: list[str]) -> tuple[float, float] | None:
    """Return the translation between known bed centres in local coordinates."""
    source, reference = _bed_geometry(src_area), _bed_geometry(ref_area)
    if source is None or reference is None:
        return None
    offset = (reference[0] - source[0], reference[1] - source[1])
    return offset if all(map(math.isfinite, offset)) else None


def decode_model_xml(data: bytes, member: str) -> str:
    """Report invalid model text as an actionable input error."""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError as err:
        raise ProfileLoadError(
            f"Cannot safely read {member} as UTF-8; re-export the project "
            "from its source slicer and try again."
        ) from err


def _parse_xml(parser, data: bytes, member: str, error_type=ProfileLoadError) -> None:
    message = f"Cannot safely read {member}; re-export the project from its source slicer and try again."

    def reject_doctype(*_args: object) -> None:
        raise error_type(message)

    parser.StartDoctypeDeclHandler = reject_doctype
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    try:
        parser.Parse(data, True)
    except expat.ExpatError as err:
        raise error_type(message) from err


@dataclass
class _BuildItem:
    start: int
    end: int
    values: list[str]
    object_id: int | None
    instance_id: int


def _integer(value: str | None, minimum: int = 0) -> int | None:
    try:
        number = int(value)
        return number if number >= minimum else None
    except (TypeError, ValueError):
        return None


def _build_items(model_xml: str) -> list[_BuildItem]:
    """Locate direct build-item attribute values without reserializing XML.

    Expat supplies UTF-8 byte offsets, so non-ASCII text preceding the build
    cannot displace an edit. No mesh tree is retained while parsing resources.
    """
    if not model_xml.strip():
        return []
    data = model_xml.encode("utf-8")
    # Orca accepts undeclared extension prefixes. Resolve only element names
    # ourselves so those extensions cannot masquerade as core build items.
    parser = expat.ParserCreate(encoding="UTF-8")
    scopes: list[dict[str, str]] = [{}]
    path: list[tuple[str | None, str]] = []
    items: list[_BuildItem] = []
    occurrences: dict[int | None, int] = {}

    def start(name: str, attributes: dict[str, str]) -> None:
        declarations = {
            key[6:] if key.startswith("xmlns:") else "": value
            for key, value in attributes.items()
            if key == "xmlns" or key.startswith("xmlns:")
        }
        scope = scopes[-1] | declarations if declarations else scopes[-1]
        scopes.append(scope)
        prefix, separator, local_name = name.partition(":")
        if separator:
            resolved = (scope.get(prefix) or None, local_name)
        else:
            resolved = (scope.get("", ""), name)
        path.append(resolved)
        if len(path) != 3 or path[0][1] != "model":
            return
        namespace = path[0][0]
        if namespace not in ("", "http://schemas.microsoft.com/3dmanufacturing/core/2015/02"):
            return
        if path[1:] != [(namespace, "build"), (namespace, "item")]:
            return
        object_id = _integer(attributes.get("objectid"), 1)
        instance_id = occurrences.get(object_id, 0)
        # Missing/invalid transforms still occupy an instance index in Orca.
        occurrences[object_id] = instance_id + 1
        values = attributes.get("transform", "").split()
        if len(values) != 12:
            return
        try:
            if not all(math.isfinite(float(value)) for value in values):
                return
        except ValueError:
            return
        offset = parser.CurrentByteIndex
        tag = _START_TAG.match(data, offset)
        if tag is None:
            return
        for attribute in _ATTRIBUTE.finditer(tag.group()):
            if attribute.group("name") == b"transform":
                items.append(_BuildItem(offset + attribute.start("value"),
                                        offset + attribute.end("value"), values,
                                        object_id, instance_id))
                break

    def end(_name: str) -> None:
        path.pop()
        scopes.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    _parse_xml(parser, data, "3D/3dmodel.model")
    return items


def _build_transforms(model_xml: str) -> list[tuple[int, int, list[str]]]:
    return [(item.start, item.end, item.values) for item in _build_items(model_xml)]


def _spans_plates(transforms: list[tuple[int, int, list[str]]]) -> bool:
    if not transforms:
        return False
    for axis in (9, 10):
        positions = [float(values[axis]) for _, _, values in transforms]
        if max(positions) - min(positions) > _MULTIPLATE_SPAN_MM:
            return True
    return False


@dataclass
class _Plate:
    plate_id: int | None = None
    members: list[tuple[int, int]] = field(default_factory=list)
    populated: bool = False
    valid: bool = True


def _plates(model_settings_xml: str | None) -> list[_Plate]:
    if not model_settings_xml:
        return []
    # Slicer metadata may contain undeclared slic3rpe:shape/text tags.
    parser = expat.ParserCreate(encoding="UTF-8")
    path: list[str] = []
    plates: list[_Plate] = []
    plate_keys: set[str] = set()
    instance: dict[str, str] = {}

    def at(*names: str) -> bool:
        if not path or path[0].rsplit(":", 1)[-1] != "config":
            return False
        prefix = path[0][:-len("config")]
        return path[1:] == [prefix + name for name in names]

    def start(name: str, attributes: dict[str, str]) -> None:
        nonlocal plate_keys, instance
        path.append(name)
        if at("plate"):
            plates.append(_Plate())
            plate_keys = set()
        elif at("plate", "metadata") and attributes.get("key") == "plater_id":
            if "plater_id" in plate_keys:
                plates[-1].valid = False
            plate_keys.add("plater_id")
            plates[-1].plate_id = _integer(attributes.get("value"), 1)
        elif at("plate", "model_instance"):
            instance = {}
        elif at("plate", "model_instance", "metadata"):
            key = attributes.get("key")
            if key in ("object_id", "instance_id"):
                if key in instance:
                    plates[-1].valid = False
                instance[key] = attributes.get("value", "").strip()
                if key == "object_id" and instance[key]:
                    plates[-1].populated = True

    def end(_name: str) -> None:
        if at("plate", "model_instance") and instance:
            object_id = _integer(instance.get("object_id"), 1)
            instance_id = _integer(instance.get("instance_id"))
            if object_id is None or instance_id is None:
                plates[-1].valid = False
            else:
                plates[-1].members.append((object_id, instance_id))
        path.pop()

    parser.StartElementHandler = start
    parser.EndElementHandler = end
    _parse_xml(parser, model_settings_xml.encode("utf-8"),
               "Metadata/model_settings.config", MetadataRewriteError)
    return plates


def is_multiplate(model_xml: str, model_settings_xml: str | None = None) -> bool:
    """Use populated plate assignments, with build span as a fallback."""
    transforms = _build_transforms(model_xml)
    return sum(plate.populated for plate in _plates(model_settings_xml)) > 1 or _spans_plates(transforms)


def bed_shift(
    model_xml: str,
    src_printable_area: list[str],
    ref_printable_area: list[str],
    model_settings_xml: str | None = None,
) -> tuple[str, bool]:
    """Preserve bed-local layout while translating metadata-assigned plate cells."""
    items = _build_items(model_xml)
    plates = _plates(model_settings_xml)
    source, reference = _bed_geometry(src_printable_area), _bed_geometry(ref_printable_area)
    offset = bed_offset(src_printable_area, ref_printable_area)
    if offset is None or source == reference or not items:
        return model_xml, False

    assignments: dict[tuple[int, int], int | None] = {}
    if plates:
        # Include empty plates in the grid. IDs are one-based, not XML order.
        if (any(not plate.valid for plate in plates)
                or {plate.plate_id for plate in plates} != set(range(1, len(plates) + 1))):
            return model_xml, False
        columns = math.isqrt(len(plates) - 1) + 1
        for plate in plates:
            for member in plate.members:
                # Duplicate assignments are ambiguous, including repeats on one plate.
                assignments[member] = None if member in assignments else plate.plate_id - 1
        # Keep layout and tower translation atomic when membership is uncertain.
        if any(assignments.get((item.object_id, item.instance_id)) is None for item in items):
            return model_xml, False
    else:
        transforms = [(item.start, item.end, item.values) for item in items]
        if _spans_plates(transforms):
            return model_xml, False

    data = model_xml.encode("utf-8")
    chunks: list[bytes] = []
    previous = 0
    for item in items:
        dx, dy = offset
        if plates:
            plate_index = assignments.get((item.object_id, item.instance_id))
            if plate_index is None:
                continue
            row, column = divmod(plate_index, columns)
            # Orca's plate grid has 20% gaps, with rows extending toward -Y.
            dx += column * 1.2 * (reference[2] - source[2])
            dy -= row * 1.2 * (reference[3] - source[3])
        if dx == 0 and dy == 0:
            continue
        x, y = float(item.values[9]) + dx, float(item.values[10]) + dy
        if not math.isfinite(x) or not math.isfinite(y):
            continue
        values = item.values.copy()
        values[9], values[10] = f"{x:.15g}", f"{y:.15g}"
        chunks.extend((data[previous:item.start], " ".join(values).encode("utf-8")))
        previous = item.end
    if not chunks:
        return model_xml, False
    chunks.append(data[previous:])
    return b"".join(chunks).decode("utf-8"), True
