"""Load U1 reference profiles from disk.

User profiles in /app/user_profiles take precedence over bundled profiles in
/app/profiles (same id => user wins). Each profile is a full Snapmaker Orca
.3mf export containing Metadata/project_settings.config.
"""
from __future__ import annotations

import json
import lzma
import re
import zipfile
import zlib
from pathlib import Path

from models import ProfileDescriptor

PROJECT_SETTINGS = "Metadata/project_settings.config"
MODEL_SETTINGS = "Metadata/model_settings.config"
MODEL_3D = "3D/3dmodel.model"

_PLATE_GCODE_RE = re.compile(r"^Metadata/plate_\d+\.gcode$")
# These members are read by exact name or synthesized by the output writer.
# A lone alias must not be copied alongside a newly generated canonical member.
_CANONICAL_MEMBERS = {
    name.casefold(): name for name in (
        PROJECT_SETTINGS, MODEL_SETTINGS, MODEL_3D,
        "Metadata/plate_1.json", "Metadata/slice_info.config",
    )
}
_ZIP_ERRORS = (zipfile.BadZipFile, EOFError, NotImplementedError, zlib.error, lzma.LZMAError)


class ProfileNotFoundError(Exception):
    pass


class ProfileLoadError(Exception):
    pass


def _validate_archive_members(zf: zipfile.ZipFile) -> None:
    """Reject ambiguous names before any archive member is interpreted.

    Output packages travel between case-sensitive and case-insensitive systems.
    Use portable keys for collision detection, but never silently rename members.
    """
    seen: set[str] = set()
    for member in zf.infolist():
        name = member.filename
        portable = name.replace("\\", "/")
        parts = [part for part in portable.split("/") if part not in ("", ".")]
        if (
            not parts or portable.startswith("/") or ".." in parts
            or re.match(r"^[A-Za-z]:", parts[0])
            or "\x00" in member.orig_filename
        ):
            raise ProfileLoadError("archive contains an unsafe member path")
        key = "/".join(parts).casefold()
        if key in seen:
            raise ProfileLoadError("archive contains duplicate member names")
        seen.add(key)
        canonical = _CANONICAL_MEMBERS.get(key)
        if canonical is not None and name != canonical:
            raise ProfileLoadError("archive contains a noncanonical reserved member name")
        if member.flag_bits & 1:
            raise ProfileLoadError("encrypted archive members are not supported")


def _decode_project_settings(raw: bytes, filename: str) -> dict:
    try:
        settings = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as err:
        raise ProfileLoadError(
            f"{filename} has malformed project_settings.config"
        ) from err
    if not isinstance(settings, dict):
        raise ProfileLoadError(f"{filename} project_settings.config must be a JSON object")
    return settings


def _read_archive_member(zf: zipfile.ZipFile, name: str) -> bytes:
    try:
        return zf.read(name)
    except OSError as err:
        # bz2 reports malformed streams as OSError without errno. Preserve
        # filesystem errors, including any failure while opening the archive.
        if zf.getinfo(name).compress_type != zipfile.ZIP_BZIP2 or err.errno is not None:
            raise
        raise ProfileLoadError("archive contains corrupt BZIP2 data") from err


def _profile_id_from_name(path: Path) -> str:
    # Filename stem, lower-cased, whitespace collapsed to '-'. We don't want
    # the id to depend on the extension or on case, so two files differing only
    # in case would collide (acceptable — the user can rename).
    stem = path.stem.strip().lower()
    return "-".join(stem.split())


def read_project_settings(profile_path: Path) -> dict:
    """Return parsed project_settings.config from a reference 3mf."""
    if not profile_path.exists():
        raise ProfileNotFoundError(str(profile_path))
    try:
        with zipfile.ZipFile(profile_path, "r") as zf:
            _validate_archive_members(zf)
            if PROJECT_SETTINGS not in zf.namelist():
                raise ProfileLoadError(
                    f"{profile_path.name} is missing {PROJECT_SETTINGS}"
                )
            return _decode_project_settings(_read_archive_member(zf, PROJECT_SETTINGS), profile_path.name)
    except _ZIP_ERRORS as err:
        raise ProfileLoadError(f"{profile_path.name} is not a valid zip") from err
    except UnicodeDecodeError as err:
        raise ProfileLoadError(f"{profile_path.name} has invalid archive text encoding") from err


def read_source_settings(source_path: Path) -> tuple[dict, str | None]:
    """Read settings from any supported 3mf format.

    Returns (settings_dict, detected_slicer) where detected_slicer is:
      None         — Orca/Bambu format (caller checks printer_model for Bambu vs other)
      "PrusaSlicer" — Metadata/Slic3r_PE.config present
      "Cura"        — Cura/ directory present
      "Unknown"     — valid 3mf but no recognised slicer config
    Raises ProfileLoadError if the file is not a valid zip.
    """
    try:
        with zipfile.ZipFile(source_path, "r") as zf:
            _validate_archive_members(zf)
            names = zf.namelist()
            _reject_sliced_gcode_without_geometry(source_path.name, zf, names)

            if PROJECT_SETTINGS in names:
                return _decode_project_settings(_read_archive_member(zf, PROJECT_SETTINGS), source_path.name), None

            if "Metadata/Slic3r_PE.config" in names:
                raw = _read_archive_member(zf, "Metadata/Slic3r_PE.config").decode("utf-8")
                cfg: dict = {}
                m = re.search(r"^; layer_height = ([0-9.]+)$", raw, re.MULTILINE)
                if m:
                    cfg["layer_height"] = m.group(1).strip()
                # Parse semicolon-delimited filament arrays from INI comments.
                for ps_key, orca_key in (
                    ("filament_settings_id", "filament_settings_id"),
                    ("filament_type", "filament_type"),
                ):
                    fm = re.search(rf'^; {ps_key} = (.+)$', raw, re.MULTILINE)
                    if fm:
                        raw_val = fm.group(1).strip()
                        entries = [v.strip().strip('"') for v in raw_val.split(";")]
                        cfg[orca_key] = entries
                # extruder_colour has real per-slot colours set by the user.
                # filament_colour is an orange placeholder PrusaSlicer writes by default.
                # Prefer extruder_colour; fall back to filament_colour only if non-placeholder.
                _PLACEHOLDER = {"#FF8000", "#FF8000FF", ""}
                for colour_key in ("extruder_colour", "filament_colour"):
                    fm = re.search(rf'^; {colour_key} = (.+)$', raw, re.MULTILINE)
                    if fm:
                        entries = [v.strip().strip('"') for v in fm.group(1).strip().split(";")]
                        if any(e not in _PLACEHOLDER for e in entries):
                            cfg["filament_colour"] = entries
                            break
                for ps_key, orca_key in (
                    ("single_extruder_multi_material", "single_extruder_multi_material"),
                    ("wipe_tower", "enable_prime_tower"),
                ):
                    fm = re.search(rf"^; {ps_key} = (.+)$", raw, re.MULTILINE)
                    if fm:
                        cfg[orca_key] = fm.group(1).strip()
                return cfg, "PrusaSlicer"

            cura_cfgs = [n for n in names if n.startswith("Cura/") and n.endswith(".cfg")]
            if cura_cfgs:
                lh = None
                for cura_cfg in cura_cfgs:
                    raw = _read_archive_member(zf, cura_cfg).decode("utf-8")
                    m = re.search(r"^layer_height\s*=\s*([0-9.]+)$", raw, re.MULTILINE)
                    if m:
                        lh = m.group(1).strip()
                        break
                return ({"layer_height": lh} if lh else {}), "Cura"

            if "3D/3dmodel.model" in names:
                return {}, "Unknown"

    except _ZIP_ERRORS as err:
        raise ProfileLoadError(f"{source_path.name} is not a valid zip") from err
    except UnicodeDecodeError as err:
        raise ProfileLoadError(f"{source_path.name} has invalid archive text encoding") from err

    raise ProfileLoadError(f"{source_path.name}: unrecognised 3mf format")


def _reject_sliced_gcode_without_geometry(
    filename: str,
    zf: zipfile.ZipFile,
    names: list[str],
) -> None:
    """Reject sliced G-code 3MF packages that no longer contain editable geometry."""
    if not any(_PLATE_GCODE_RE.match(n) for n in names):
        return

    has_external_object = any(
        n.startswith("3D/Objects/") and n.endswith(".model") for n in names
    )
    if has_external_object:
        return

    model_xml = (
        _read_archive_member(zf, MODEL_3D).decode("utf-8", errors="replace")
        if MODEL_3D in names else ""
    )
    has_model_geometry = bool(
        re.search(r"<(?:\w+:)?object\b", model_xml)
        or re.search(r"<(?:\w+:)?mesh\b", model_xml)
        or re.search(r"<(?:\w+:)?item\b", model_xml)
    )
    if has_model_geometry:
        return

    raise ProfileLoadError(
        f"{filename} appears to be a sliced G-code 3MF with no model geometry. "
        "Upload the original project .3mf instead; if you only have STL/model files, "
        "open them in a slicer and export a project .3mf first."
    )


def read_model_settings(profile_path: Path) -> str | None:
    """Return raw model_settings.config text, or None if absent."""
    if not profile_path.exists():
        raise ProfileNotFoundError(str(profile_path))
    with zipfile.ZipFile(profile_path, "r") as zf:
        if MODEL_SETTINGS not in zf.namelist():
            return None
        return _read_archive_member(zf, MODEL_SETTINGS).decode("utf-8")


def _descriptor(path: Path, source: str) -> ProfileDescriptor:
    try:
        settings = read_project_settings(path)
    except (ProfileLoadError, ProfileNotFoundError):
        settings = {}
    return ProfileDescriptor(
        id=_profile_id_from_name(path),
        display_name=_clean_display_name(path.stem),
        path=str(path),
        source=source,
        layer_height=_as_str(settings.get("layer_height")),
        printer_variant=_as_str(settings.get("printer_variant")),
    )


_MODEL_SUFFIX_RE = re.compile(r"\s+-\s+\w[\w\s]*$")


def _clean_display_name(stem: str) -> str:
    """Strip trailing ' - ModelName' from profile file stems.

    Profile .3mf files are often exported from a test model (e.g. a cube),
    leaving ' - Cube' in the filename. The quality label is everything before
    the first ' - <Word>' suffix.
    """
    return _MODEL_SUFFIX_RE.sub("", stem).strip()


def _as_str(v: object) -> str | None:
    if v is None:
        return None
    if isinstance(v, list):
        return ",".join(str(x) for x in v)
    return str(v)


def list_profiles(
    bundled_dir: Path, user_dir: Path | None = None
) -> list[ProfileDescriptor]:
    """Discover all .3mf reference profiles, user-dir shadowing bundled."""
    out: dict[str, ProfileDescriptor] = {}
    for p in sorted(bundled_dir.glob("*.3mf")):
        d = _descriptor(p, source="bundled")
        out[d.id] = d
    if user_dir is not None and user_dir.exists():
        for p in sorted(user_dir.glob("*.3mf")):
            d = _descriptor(p, source="user")
            out[d.id] = d  # user overrides bundled at matching id
    return sorted(out.values(), key=lambda d: d.display_name)


_QUALITY_KEYWORDS = (
    "extra draft", "draft", "fine", "high quality", "optimal",
    "strength", "standard",
)


def suggest_profile(
    profiles: list[ProfileDescriptor],
    source_settings: dict,
) -> ProfileDescriptor | None:
    """Return the best-matching U1 profile for the given source project_settings.

    Matching priority:
      1. Same layer_height AND quality keyword present in print_settings_id
      2. Same layer_height, any quality
      3. Closest layer_height (fallback)
    """
    if not profiles:
        return None

    src_lh_raw = source_settings.get("layer_height")
    try:
        src_lh = round(float(src_lh_raw), 4) if src_lh_raw is not None else None
    except (TypeError, ValueError):
        src_lh = None

    src_pid = str(source_settings.get("print_settings_id") or "").lower()
    src_quality = next((q for q in _QUALITY_KEYWORDS if q in src_pid), None)

    lh_matches = []
    for p in profiles:
        try:
            plh = round(float(p.layer_height), 4) if p.layer_height else None
        except (TypeError, ValueError):
            plh = None
        if src_lh is not None and plh == src_lh:
            lh_matches.append(p)

    if lh_matches:
        if src_quality:
            quality_match = next(
                (p for p in lh_matches if src_quality in p.display_name.lower()),
                None,
            )
            if quality_match:
                return quality_match
        return lh_matches[0]

    # Fallback: closest layer height.
    if src_lh is not None:
        def _dist(p: ProfileDescriptor) -> float:
            try:
                return abs(float(p.layer_height or 0) - src_lh)
            except (TypeError, ValueError):
                return 999.0
        return min(profiles, key=_dist)

    # No layer height at all (bare geometry / unknown format) — default to 0.20 Standard.
    default = next(
        (p for p in profiles
         if (p.layer_height or "").startswith("0.2") and "standard" in p.display_name.lower()),
        profiles[0],
    )
    return default


def resolve_profile(
    profile_id: str,
    bundled_dir: Path,
    user_dir: Path | None = None,
) -> ProfileDescriptor:
    """Look up a single profile by id, user-dir first."""
    profiles = list_profiles(bundled_dir, user_dir)
    for d in profiles:
        if d.id == profile_id:
            return d
    # Fallback: accept the raw filename stem for lenient requests.
    fallback = profile_id.strip().lower()
    for d in profiles:
        if d.display_name.strip().lower() == fallback:
            return d
    raise ProfileNotFoundError(
        f"no reference profile with id {profile_id!r} "
        f"(have: {[d.id for d in profiles]})"
    )
