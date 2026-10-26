import asyncio
import copy
import io
import json
import sys
import zipfile
from unittest.mock import MagicMock

import pytest

from filament_colors import describe_filaments


@pytest.fixture
def project():
    return {
        "printer_model": "Bambu Lab X1 Carbon",
        "layer_height": "0.20",
        "filament_settings_id": ["Custom dual", "Custom silk", "Plain"],
        "filament_type": ["PLA"] * 3,
        "filament_vendor": ["Vendor A", "Vendor B", "Vendor C"],
        "filament_colour": ["#112233", "#223344", "#334455"],
        "filament_multi_colour": ["#112233 #445566", "#223344 #556677 #8899AA", ""],
        "filament_colour_type": ["1", "0", "1"],
    }


@pytest.mark.parametrize("native", [False, True])
def test_preview_preserves_palette_mode_and_slot_identity(project, native):
    if native:
        project["filament_multi_colors"] = ["#112233|#445566", "#223344|#556677|#8899AA", ""]
        project["filament_colour_mode"] = ["0", "1", "0"]
        del project["filament_multi_colour"]
        del project["filament_colour_type"]
    original = copy.deepcopy(project)
    filaments = describe_filaments(project)
    assert [f["colours"] for f in filaments] == [
        ["#112233", "#445566"], ["#223344", "#556677", "#8899AA"], ["#334455"],
    ]
    assert [f["colour_mode"] for f in filaments] == ["split", "gradient", "split"]
    assert [f["index"] for f in filaments] == [0, 1, 2]
    assert [f["colour"] for f in filaments] == project["filament_colour"]
    assert [f["vendor"] for f in filaments] == project["filament_vendor"]
    assert project == original


def test_native_preview_takes_precedence(project):
    project["filament_multi_colors"] = ["#AABBCC|#DDEEFF"] * 3
    project["filament_colour_mode"] = ["1"] * 3
    filaments = describe_filaments(project)
    assert all(f["colours"] == ["#AABBCC", "#DDEEFF"] for f in filaments)
    assert all(f["colour_mode"] == "gradient" for f in filaments)


def test_missing_or_invalid_palette_falls_back_to_primary(project):
    project["filament_multi_colors"] = [None, "url(https://example.invalid/image)"]
    project.pop("filament_colour_type")
    project["filament_colour"][2] = None
    filaments = describe_filaments(project)
    assert [f["colours"] for f in filaments] == [["#112233"], ["#223344"], []]
    assert all(f["colour_mode"] == "split" for f in filaments)


def test_suggest_profile_returns_complete_palettes(tmp_path, monkeypatch, project):
    # Import after configuring all writable paths; no real project data is used.
    monkeypatch.setenv("U13MF_APP_ROOT", str(tmp_path))
    monkeypatch.setenv("OTEL_ENABLED", "false")
    # Keep upload/HTTP behavior real; external observability is outside this test.
    telemetry = MagicMock()
    telemetry._otel_enabled.return_value = False
    monkeypatch.setitem(sys.modules, "telemetry", telemetry)
    import httpx
    import main

    profiles = main.PROFILES_DIR
    profiles.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(profiles / "0.20 Standard.3mf", "w") as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps({
            "printer_model": "Snapmaker U1", "layer_height": "0.20",
        }))
    data = io.BytesIO()
    with zipfile.ZipFile(data, "w") as archive:
        archive.writestr("Metadata/project_settings.config", json.dumps(project))
        archive.writestr("3D/3dmodel.model", '<model><resources/><build/></model>')

    async def upload():
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            return await client.post("/api/suggest-profile", files={
                "file": ("synthetic.3mf", data.getvalue(), "application/zip"),
            })

    response = asyncio.run(upload())
    assert response.status_code == 200, response.text
    filaments = response.json()["filaments"]
    assert filaments[0]["colours"] == ["#112233", "#445566"]
    assert filaments[0]["colour_mode"] == "split"
    assert filaments[1]["colours"] == ["#223344", "#556677", "#8899AA"]
    assert filaments[1]["colour_mode"] == "gradient"
    assert len(filaments) == 3
