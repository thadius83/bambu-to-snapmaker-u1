"""Helpers for rewriting 3mf metadata sidecar files."""
from __future__ import annotations

import re
import zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

U1_TOOLHEADS_DEFAULT = 4


def minimal_model_settings(src_names: list[str], source_path: Path) -> str:
    """Generate a minimal model_settings.config for non-Orca source files."""
    obj_ids = _model_object_ids(src_names, source_path)
    build_ids = _build_object_ids(src_names, source_path)
    prusa_extruders = _prusa_object_extruders(src_names, source_path)

    n_filaments = _source_filament_count(src_names, source_path)
    filament_maps = ""
    if n_filaments > 1:
        maps = " ".join(str((i % U1_TOOLHEADS_DEFAULT) + 1) for i in range(n_filaments))
        filament_maps = f'  <metadata key="filament_maps" value="{maps}"/>\n'

    instance_lines = "\n".join(
        f'  <model_instance>\n'
        f'   <metadata key="object_id" value="{oid}"/>\n'
        f'   <metadata key="instance_id" value="0"/>\n'
        f'   <metadata key="identify_id" value="{oid}"/>\n'
        f'  </model_instance>'
        for oid in (build_ids or obj_ids)
    )
    obj_lines = "\n".join(
        f'  <object id="{oid}">\n'
        f'   <metadata key="extruder" value="{prusa_extruders.get(oid, "1")}"/>\n'
        f'  </object>'
        for oid in obj_ids
    )
    plate_block = (
        " <plate>\n"
        '  <metadata key="plater_id" value="1"/>\n'
        '  <metadata key="plater_name" value="plate-1"/>\n'
        '  <metadata key="locked" value="false"/>\n'
        '  <metadata key="filament_map_mode" value="Auto For Flush"/>\n'
        + filament_maps
        + (instance_lines + "\n" if instance_lines else "")
        + " </plate>\n"
    )
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        + plate_block
        + (obj_lines + "\n" if obj_lines else "")
        + "</config>\n"
    )


def translate_prusa_mmu_paint(model_xml: str) -> tuple[str, int]:
    """Convert Prusa MMU face painting to Orca/Bambu paint metadata."""
    count = model_xml.count("slic3rpe:mmu_segmentation")
    if not count:
        return model_xml, 0
    return (
        re.sub(r'\s+slic3rpe:mmu_segmentation="([^"]*)"', r' paint_color="\1"', model_xml),
        count,
    )


def minimal_slice_info(printer_model: str = "Snapmaker U1") -> str:
    """Minimal slice_info.config so Orca recognises the file as a project."""
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<config>\n"
        " <header>\n"
        '  <header_item key="X-BBL-Client-Type" value="slicer"/>\n'
        '  <header_item key="X-BBL-Client-Version" value="02.00.00.00"/>\n'
        " </header>\n"
        " <plate>\n"
        '  <metadata key="index" value="1"/>\n'
        f'  <metadata key="printer_model_id" value="{printer_model}"/>\n'
        " </plate>\n"
        "</config>\n"
    )


def rewrite_slice_info(xml_text: str, printer_model: str = "Snapmaker U1") -> str:
    """Swap printer_model_id in slice_info.config if it exists."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text

    for item in root.iter():
        if item.get("key") == "printer_model_id":
            item.set("value", printer_model)

    return ET.tostring(root, encoding="unicode", xml_declaration=False)


def rewrite_custom_gcode_per_layer(xml_text: str, pause_gcode: str) -> str:
    """Rewrite per-layer pause commands to use U1-compatible G-code."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text

    for layer in root.iter("layer"):
        if layer.get("type") == "1":
            layer.set("gcode", pause_gcode)
    return '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(root, encoding="unicode")


def _model_object_ids(src_names: list[str], source_path: Path) -> list[str]:
    if "3D/3dmodel.model" not in src_names:
        return []
    raw = _read_zip_text(source_path, "3D/3dmodel.model")
    return re.findall(r'<object\b[^>]*\bid=["\'](\d+)["\']', raw)


def _build_object_ids(src_names: list[str], source_path: Path) -> list[str]:
    if "3D/3dmodel.model" not in src_names:
        return []
    raw = _read_zip_text(source_path, "3D/3dmodel.model")
    return re.findall(r'<item\b[^>]*\bobjectid=["\'](\d+)["\']', raw)


def _prusa_object_extruders(src_names: list[str], source_path: Path) -> dict[str, str]:
    if "Metadata/Slic3r_PE_model.config" not in src_names:
        return {}
    prusa_xml = _read_zip_text(source_path, "Metadata/Slic3r_PE_model.config")
    return {
        m.group(1): m.group(2)
        for m in re.finditer(
            r'<object\s+id="(\d+)"[^>]*>.*?'
            r'<metadata\s+type="object"\s+key="extruder"\s+value="(\d+)"',
            prusa_xml,
            re.DOTALL,
        )
    }


def _source_filament_count(src_names: list[str], source_path: Path) -> int:
    if "Metadata/Slic3r_PE.config" not in src_names:
        return 0
    raw = _read_zip_text(source_path, "Metadata/Slic3r_PE.config")
    m = re.search(r'^; filament_settings_id = (.+)$', raw, re.MULTILINE)
    if not m:
        return 0
    return len([v for v in m.group(1).split(";") if v.strip()])


def _read_zip_text(path: Path, name: str) -> str:
    with zipfile.ZipFile(path) as zf:
        return zf.read(name).decode("utf-8", errors="replace")
