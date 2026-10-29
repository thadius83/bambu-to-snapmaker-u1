"""Translate Prusa triangle-range volumes to native Orca mesh parts."""
from __future__ import annotations

from copy import deepcopy
from xml.etree import ElementTree as ET
from xml.parsers import expat

from profile_loader import ProfileLoadError

_VOLUME_TYPES = {
    "ModelPart": "normal_part", "NegativeVolume": "negative_part",
    "ParameterModifier": "modifier_part", "SupportEnforcer": "support_enforcer",
    "SupportBlocker": "support_blocker",
}
_ERROR = "Cannot safely import Prusa volume assignments; re-export the project from PrusaSlicer and try again."


def _parse(xml_text: str) -> ET.Element:
    # Retain literal extension names, as Orca does; never resolve XML entities.
    builder = ET.TreeBuilder()
    parser = expat.ParserCreate()
    parser.StartElementHandler = builder.start
    parser.EndElementHandler = builder.end
    parser.CharacterDataHandler = builder.data

    def reject_dtd(*_args: object) -> None:
        raise ProfileLoadError(_ERROR)

    parser.StartDoctypeDeclHandler = reject_dtd
    parser.SetParamEntityParsing(expat.XML_PARAM_ENTITY_PARSING_NEVER)
    parser.Parse(xml_text, True)
    return builder.close()


def import_prusa_parts(model_xml: str, prusa_xml: str, settings_xml: str) -> tuple[str, str]:
    """Keep volume geometry/painting and add each part's filament to every instance.

    Snapmaker's active loader matches parts by mesh object ID, not triangle
    ranges. Source volume matrices describe geometry already baked into the
    vertices; retain component/build transforms and do not apply them again.
    """
    try:
        return _import_parts(model_xml, prusa_xml, settings_xml)
    except (expat.ExpatError, ValueError, TypeError, KeyError, IndexError) as err:
        raise ProfileLoadError(_ERROR) from err


def _import_parts(model_xml: str, prusa_xml: str, settings_xml: str) -> tuple[str, str]:
    prusa = _parse(prusa_xml)
    if not prusa.findall('object/volume'):
        return model_xml, settings_xml
    model = _parse(model_xml)
    resources = model.find('resources')
    if resources is None:
        raise ProfileLoadError(_ERROR)
    objects = {obj.attrib['id']: obj for obj in resources.findall('object')}
    if len(objects) != len(resources.findall('object')):
        raise ProfileLoadError(_ERROR)
    next_id = max(int(resource.attrib["id"]) for resource in resources if "id" in resource.attrib) + 1
    definitions: dict[str, ET.Element] = {}
    source_metadata: dict[str, dict[str, str]] = {}
    seen = set()
    for config_obj in prusa.findall('object'):
        oid = config_obj.attrib['id']
        if oid in seen:
            raise ProfileLoadError(_ERROR)
        seen.add(oid)
        volumes = config_obj.findall('volume')
        if not volumes:
            continue
        obj = objects[oid]
        mesh = obj.find('mesh')
        if mesh is None or obj.find('components') is not None:
            raise ProfileLoadError(_ERROR)
        vertices = mesh.findall('vertices/vertex')
        triangles = mesh.findall('triangles/triangle')
        metadata = {m.attrib['key']: m.attrib['value'] for m in config_obj.findall('metadata')}
        source_metadata[oid] = metadata
        ranges = [(int(v.attrib['firstid']), int(v.attrib['lastid']), v) for v in volumes]
        end = 0
        for first, last, _ in sorted(ranges, key=lambda row: row[0]):
            if first != end or last < first or last >= len(triangles):
                raise ProfileLoadError(_ERROR)
            end = last + 1
        if end != len(triangles):
            raise ProfileLoadError(_ERROR)
        components = ET.Element('components')
        for first, last, volume in ranges:
            part_id = str(next_id)
            next_id += 1
            part_triangles = deepcopy(triangles[first:last + 1])
            used = sorted({int(tri.attrib[k]) for tri in part_triangles for k in ('v1', 'v2', 'v3')})
            if not used or used[0] < 0 or used[-1] >= len(vertices):
                raise ProfileLoadError(_ERROR)
            index_map = {old: new for new, old in enumerate(used)}
            part_obj = ET.Element('object', id=part_id, type='model')
            part_mesh = ET.SubElement(part_obj, 'mesh')
            part_vertices = ET.SubElement(part_mesh, 'vertices')
            part_vertices.extend(deepcopy(vertices[index]) for index in used)
            part_faces = ET.SubElement(part_mesh, 'triangles')
            for triangle in part_triangles:
                for key in ('v1', 'v2', 'v3'):
                    triangle.set(key, str(index_map[int(triangle.attrib[key])]))
                part_faces.append(triangle)
            resources.append(part_obj)
            ET.SubElement(components, 'component', objectid=part_id)
            values = {m.attrib['key']: m.attrib['value'] for m in volume.findall('metadata')}
            part_type = _VOLUME_TYPES[values.get('volume_type', 'ModelPart')]
            part = ET.Element('part', id=part_id, subtype=part_type)
            if 'name' in values:
                ET.SubElement(part, 'metadata', key='name', value=values['name'])
            slot = int(values.get('extruder', '0')) or int(metadata.get('extruder', '1')) or 1
            if slot < 1:
                raise ProfileLoadError(_ERROR)
            ET.SubElement(part, 'metadata', key='extruder', value=str(slot))
            definitions[part_id] = part
        if all(definitions[c.attrib['objectid']].get('subtype') == 'normal_part' for c in components):
            # Prusa gives later parts priority in overlaps. Orca's similar-area
            # tie-break favours the first region; keep that priority within the
            # same grouped object. Its separate area heuristic still applies.
            components[:] = reversed(components)
        obj.remove(mesh)
        obj.append(components)

    settings = _parse(settings_xml)
    # Components may alias a source object (Prusa uses this for repeated copies).
    # Attach metadata to each top-level object Orca loads, not only its source.
    for output_obj in settings.findall('object'):
        pending = [(output_obj.attrib['id'], ())]
        inherited = None
        while pending:
            oid, ancestors = pending.pop(0)
            if oid in ancestors or len(ancestors) > 256:
                raise ProfileLoadError(_ERROR)
            if oid in definitions:
                output_obj.append(deepcopy(definitions[oid]))
                continue
            if oid in source_metadata and inherited is None:
                inherited = source_metadata[oid]
            obj = objects[oid]
            pending.extend((component.attrib['objectid'], ancestors + (oid,))
                           for component in obj.findall('components/component'))
        if inherited and 'name' in inherited:
            ET.SubElement(output_obj, 'metadata', key='name', value=inherited['name'])
    return ET.tostring(model, encoding='unicode'), ET.tostring(settings, encoding='unicode')
