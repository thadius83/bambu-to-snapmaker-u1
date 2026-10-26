import copy
import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import converter
from filament_colors import translate_filament_colors
from models import ConversionSettings


@pytest.fixture
def source():
    # Synthetic palettes covering more than the four physical toolheads.
    return {
        "printer_model": "Bambu Lab X1 Carbon",
        "filament_settings_id": [f"PLA {i}" for i in range(6)],
        "filament_colour": ["#112233", "#223344", "#334455", "#445566", "#556677", "#667788"],
        "filament_multi_colour": [
            "#112233", "#223344 #778899", "#334455", "#445566", "#556677 #8899AA", "#667788"
        ],
        "filament_colour_type": ["0", "1", "1", "1", "1", "1"],
        "layer_height": "0.16",
        "nozzle_temperature": ["210"] * 6,
    }


@pytest.fixture
def reference():
    return {
        "printer_model": "Snapmaker U1",
        "filament_settings_id": ["Generic PLA"] * 4,
        "filament_colour": ["#ABCDEF"] * 4,
        "filament_multi_colors": ["#ABCDEF"] * 4,
        "filament_colour_mode": ["1"] * 4,
        "layer_height": "0.20",
        "nozzle_temperature": ["200"] * 4,
    }


def pipeline(monkeypatch, source, reference, **options):
    """Run all config stages, intercepting archive I/O; never write a 3MF."""
    source_path = MagicMock(spec=Path)
    source_path.name = "source.3mf"
    source_path.stat.return_value.st_size = 1
    output_path = MagicMock(spec=Path)
    output_path.name = "result.3mf"
    output_path.stat.return_value.st_size = 1
    archive = MagicMock()
    archive.__enter__.return_value.namelist.return_value = [converter.PROJECT_SETTINGS, converter.MODEL_3D]
    monkeypatch.setattr(converter.zipfile, "ZipFile", lambda *args, **kwargs: archive)
    monkeypatch.setattr(converter, "read_source_settings", lambda path: (copy.deepcopy(source), None))
    monkeypatch.setattr(converter, "read_project_settings", lambda path: copy.deepcopy(reference))
    captured = {}
    monkeypatch.setattr(converter, "_write_output_archive", lambda **kwargs: captured.update(kwargs))
    bambu = options.pop("preserve_bambu_metadata", False)
    result = converter.convert(
        source_path=source_path,
        reference_path=Path("reference.3mf"),
        output_path=output_path,
        settings=ConversionSettings(reference_profile="reference", apply_rules=False, clamp_speeds=False, **options),
        rules=[],
        preserve_bambu_metadata=bambu,
    )
    return captured["new_project_settings"], result.diff


@pytest.mark.parametrize("old_reference", [False, True])
def test_dual_color_slots_survive_filter_and_reference_defaults(monkeypatch, source, reference, old_reference):
    if old_reference:
        del reference["filament_multi_colors"]
        del reference["filament_colour_mode"]
    original = copy.deepcopy(source)
    output, _ = pipeline(monkeypatch, source, reference)
    assert output["filament_multi_colors"] == [
        "#112233", "#223344|#778899", "#334455", "#445566", "#556677|#8899AA", "#667788"
    ]
    assert output["filament_colour_mode"] == ["1", "0", "0", "0", "0", "0"]
    assert output["filament_colour"] == source["filament_colour"]
    assert output["layer_height"] == "0.16"
    assert output["nozzle_temperature"] == ["210"] * 6
    assert output["printer_model"] == "Snapmaker U1"
    assert source == original


def test_secondary_colors_follow_slot_remap(monkeypatch, source, reference):
    output, _ = pipeline(monkeypatch, source, reference, slot_map={0: 2, 1: 0, 2: 3, 3: 3, 4: 1, 5: 2})
    assert output["filament_colour"] == ["#223344", "#556677", "#112233", "#334455"]
    assert output["filament_multi_colors"] == ["#223344|#778899", "#556677|#8899AA", "#112233", "#334455"]
    assert output["filament_colour_mode"] == ["0", "0", "1", "0"]


def test_gradient_and_whitespace(monkeypatch, source, reference):
    source["filament_multi_colour"][4] = "  #556677\t#8899AA   #112233 \n"
    source["filament_colour_type"][4] = "0"
    output, _ = pipeline(monkeypatch, source, reference)
    assert output["filament_multi_colors"][4] == "#556677|#8899AA|#112233"
    assert output["filament_colour_mode"][4] == "1"


def test_missing_mode_uses_split_instead_of_reference_gradient(monkeypatch, source, reference):
    del source["filament_colour_type"]
    output, _ = pipeline(monkeypatch, source, reference)
    assert output["filament_colour_mode"] == ["0"] * 6


def test_native_fields_take_precedence(monkeypatch, source, reference):
    source["filament_multi_colors"] = ["#112233|#445566"] * 6
    source["filament_colour_mode"] = ["1"] * 6
    output, _ = pipeline(monkeypatch, source, reference)
    assert output["filament_multi_colors"] == source["filament_multi_colors"]
    assert output["filament_colour_mode"] == source["filament_colour_mode"]


def test_advanced_color_override_still_wins(monkeypatch, source, reference):
    output, _ = pipeline(monkeypatch, source, reference, advanced_overrides={
        "filament_multi_colors": ["#010203|#040506"] * 6,
        "filament_colour_mode": ["1"] * 6,
    })
    assert output["filament_multi_colors"] == ["#010203|#040506"] * 6
    assert output["filament_colour_mode"] == ["1"] * 6


def test_bambu_target_retains_bambu_format(monkeypatch, source, reference):
    reference.pop("filament_multi_colors")
    reference.pop("filament_colour_mode")
    reference["filament_multi_colour"] = ["#ABCDEF"] * 4
    reference["filament_colour_type"] = ["1"] * 4
    output, _ = pipeline(monkeypatch, source, reference, preserve_bambu_metadata=True)
    assert output["filament_multi_colour"] == source["filament_multi_colour"]
    assert output["filament_colour_type"] == source["filament_colour_type"]
    assert "filament_multi_colors" not in output
    assert "filament_colour_mode" not in output


def test_plain_project_without_color_extensions_is_unmodified():
    source = {"filament_colour": ["#112233"]}
    assert translate_filament_colors(source) == source


@pytest.mark.parametrize("invalid", [None, 12, "#112233 #445566", [None], [123]])
def test_malformed_color_array_is_not_translated(invalid):
    source = {"filament_multi_colour": invalid}
    assert translate_filament_colors(source) == source


def test_palette_survives_archive_round_trip(tmp_path, source, reference):
    """Exercise actual 3MF reads and writes using only synthetic project data."""
    source_path = tmp_path / "source.3mf"
    reference_path = tmp_path / "reference.3mf"
    output_path = tmp_path / "output.3mf"
    model = b'''<model xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02" unit="millimeter">
      <resources><object id="1" type="model"><mesh>
        <vertices><vertex x="0" y="0" z="0"/><vertex x="1" y="0" z="0"/>
        <vertex x="0" y="1" z="0"/></vertices>
        <triangles><triangle v1="0" v2="1" v3="2"/></triangles>
      </mesh></object></resources><build><item objectid="1"/></build>
    </model>'''
    with zipfile.ZipFile(source_path, "w") as archive:
        archive.writestr(converter.PROJECT_SETTINGS, json.dumps(source))
        archive.writestr(converter.MODEL_3D, model)
    with zipfile.ZipFile(reference_path, "w") as archive:
        archive.writestr(converter.PROJECT_SETTINGS, json.dumps(reference))
    original_bytes = source_path.read_bytes()

    converter.convert(
        source_path=source_path,
        reference_path=reference_path,
        output_path=output_path,
        settings=ConversionSettings(reference_profile="reference", apply_rules=False, clamp_speeds=False),
        rules=[],
    )

    with zipfile.ZipFile(output_path) as archive:
        output = json.loads(archive.read(converter.PROJECT_SETTINGS))
        assert archive.read(converter.MODEL_3D) == model
    assert source_path.read_bytes() == original_bytes
    assert output["filament_multi_colors"][1] == "#223344|#778899"
    assert output["filament_multi_colors"][4] == "#556677|#8899AA"
    assert output["filament_colour_mode"] == ["1", "0", "0", "0", "0", "0"]
    assert output["filament_colour"] == source["filament_colour"]
    assert "filament_multi_colour" not in output
    assert "filament_colour_type" not in output
