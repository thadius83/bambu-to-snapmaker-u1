"""FastAPI entrypoint — the thin HTTP layer around the converter pipeline.

Endpoints:

  POST   /api/convert              — upload + convert, returns diff + job id
  POST   /api/convert-bambu        — Bambu cross-printer convert
  GET    /api/download/{job_id}    — fetch the converted .3mf
  GET    /api/profiles             — list U1 reference profiles
  GET    /api/bambu-profiles       — list Bambu target profiles
  GET    /api/rules                — list YAML rules
  POST   /api/rules                — create a new rule
  GET    /api/rules/{name}         — fetch one rule (raw YAML)
  PUT    /api/rules/{name}         — update rule YAML
  DELETE /api/rules/{name}         — delete rule
  POST   /api/rules/test-match     — upload a 3mf, return matching rules

Static file serving for the built frontend lives at /.
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import tempfile
import threading
import time
import uuid
import zipfile
from pathlib import Path
from typing import Any

import yaml
from fastapi import (
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

import telemetry
from converter import convert, is_painted_model, _MULTIPLATE_SPAN_MM
from diff_reporter import summarise
from models import ConversionSettings, ProfileDescriptor, RuleDefinition
from profile_loader import (
    ProfileLoadError,
    ProfileNotFoundError,
    list_profiles,
    read_project_settings,
    resolve_profile,
    suggest_profile,
)
from rules_engine import (
    FilamentContext,
    RuleLoadError,
    dump_rule,
    find_matches,
    load_rule_file,
    load_rules,
)
from security import SECURITY_HEADERS, render_privacy_html

logger = logging.getLogger("u13mf")


class _DropHealthcheckAccessLogs(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return '"GET /api/health ' not in record.getMessage()


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
logging.getLogger("uvicorn.access").addFilter(_DropHealthcheckAccessLogs())

telemetry.setup()

# ---------------------------------------------------------------------------
# paths (overridable via env for tests / non-docker local runs)

APP_ROOT = Path(os.environ.get("U13MF_APP_ROOT", "/app"))
_MAX_TOOLHEADS = 4  # Snapmaker U1 physical toolhead count

PROFILES_DIR = Path(os.environ.get("U13MF_PROFILES", APP_ROOT / "profiles"))
USER_PROFILES_DIR = Path(
    os.environ.get("U13MF_USER_PROFILES", APP_ROOT / "user_profiles")
)
BAMBU_PROFILES_DIR = Path(
    os.environ.get("U13MF_BAMBU_PROFILES", APP_ROOT / "bambu_profiles")
)
RULES_DIR = Path(os.environ.get("U13MF_RULES", APP_ROOT / "rules"))
TMP_DIR = Path(os.environ.get("U13MF_TMP", APP_ROOT / "tmp"))
FAILED_TMP_DIR = Path(os.environ.get("U13MF_FAILED_TMP", APP_ROOT / "tmp_failed"))
FEEDBACK_DIR = Path(os.environ.get("U13MF_FEEDBACK", APP_ROOT / "feedback"))
FRONTEND_DIST = Path(
    os.environ.get("U13MF_FRONTEND_DIST", APP_ROOT / "frontend" / "dist")
)

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "100"))
CLEANUP_AFTER_SECONDS = int(os.environ.get("CLEANUP_TEMP_AFTER_SECONDS", "300"))
SITE_URL = "https://" + os.environ.get("DOMAINHOST", "u1convert.com").rstrip("/")
FAILED_CLEANUP_AFTER_SECONDS = int(
    os.environ.get("CLEANUP_FAILED_TEMP_AFTER_SECONDS", str(7 * 24 * 60 * 60))
)
RETAIN_FAILED_FILES = os.environ.get("RETAIN_FAILED_FILES", "false").lower() in ("1", "true", "yes")

for d in (PROFILES_DIR, USER_PROFILES_DIR, BAMBU_PROFILES_DIR, RULES_DIR, TMP_DIR, FAILED_TMP_DIR, FEEDBACK_DIR):
    d.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# job registry (in-memory — stateless restarts are fine; files expire)

_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _register_job(job_id: str, output_path: Path, diff_payload: dict) -> None:
    with _JOBS_LOCK:
        _JOBS[job_id] = {
            "output_path": output_path,
            "diff": diff_payload,
            "created_at": time.time(),
        }


def _get_job(job_id: str) -> dict[str, Any] | None:
    with _JOBS_LOCK:
        return _JOBS.get(job_id)


def _retain_failed_workdir(
    *,
    job_id: str,
    workdir: Path,
    endpoint: str,
    filename: str,
    reference_profile: str,
    detail: str,
    error_type: str,
    request_meta: dict[str, Any],
) -> None:
    if not workdir.exists():
        return
    if not RETAIN_FAILED_FILES:
        shutil.rmtree(workdir, ignore_errors=True)
        return
    failed_dir = FAILED_TMP_DIR / f"{int(time.time())}-{job_id}"
    try:
        shutil.move(str(workdir), str(failed_dir))
        payload = {
            "job_id": job_id,
            "endpoint": endpoint,
            "filename": filename,
            "reference_profile": reference_profile,
            "error_type": error_type,
            "detail": detail,
            "request_meta": request_meta,
            "retained_at": int(time.time()),
        }
        (failed_dir / "error.json").write_text(
            json.dumps(payload, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        logger.warning("retained failed upload  file=%s  reason=%s", payload.get("filename", "?"), payload.get("detail", "?"))
    except Exception:
        logger.exception("failed to retain workdir %s", workdir)
        shutil.rmtree(workdir, ignore_errors=True)


def _cleanup_tmp_dir(now: float) -> None:
    """Remove TMP_DIR subdirectories older than CLEANUP_AFTER_SECONDS.

    Covers both in-registry jobs and orphaned dirs from previous container
    sessions (which never appear in _JOBS after a restart).
    """
    with _JOBS_LOCK:
        known = set(_JOBS.keys())
    for workdir in TMP_DIR.iterdir():
        if not workdir.is_dir():
            continue
        # In-registry jobs are evicted by the main loop; skip them here so we
        # don't race with a download that's still in progress.
        if workdir.name in known:
            continue
        try:
            age = now - workdir.stat().st_mtime
        except FileNotFoundError:
            continue
        if age > CLEANUP_AFTER_SECONDS:
            shutil.rmtree(workdir, ignore_errors=True)
            logger.info("cleanup: removed orphaned workdir %s", workdir.name)


def _cleanup_loop() -> None:
    while True:
        time.sleep(30)
        now = time.time()
        to_delete: list[str] = []
        with _JOBS_LOCK:
            for jid, entry in _JOBS.items():
                if now - entry["created_at"] > CLEANUP_AFTER_SECONDS:
                    to_delete.append(jid)
            for jid in to_delete:
                entry = _JOBS.pop(jid)
                out = entry["output_path"]
                if isinstance(out, Path) and out.exists():
                    workdir = out.parent
                    shutil.rmtree(workdir, ignore_errors=True)
        _cleanup_tmp_dir(now)
        for workdir in FAILED_TMP_DIR.iterdir():
            if not workdir.is_dir():
                continue
            try:
                age = now - workdir.stat().st_mtime
            except FileNotFoundError:
                continue
            if age > FAILED_CLEANUP_AFTER_SECONDS:
                shutil.rmtree(workdir, ignore_errors=True)


threading.Thread(target=_cleanup_loop, daemon=True).start()


# ---------------------------------------------------------------------------
# app

app = FastAPI(title="Bambu → Snapmaker U1 3mf Converter", version="0.1.0")

if telemetry._otel_enabled():
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    FastAPIInstrumentor.instrument_app(app)


@app.middleware("http")
async def _security_headers(request: Request, call_next):
    response = await call_next(request)
    for header, value in SECURITY_HEADERS.items():
        response.headers[header] = value
    return response


@app.middleware("http")
async def _count_http_errors(request: Request, call_next):
    response = await call_next(request)
    if response.status_code >= 400:
        telemetry.http_errors_counter.add(
            1,
            {"status": str(response.status_code), "path": request.url.path},
        )
    return response


app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_RULE_NAME_RE = re.compile(r"^[A-Za-z0-9 _.\-]+$")


def _rule_filename(name: str) -> Path:
    if not _RULE_NAME_RE.fullmatch(name):
        raise HTTPException(400, detail="invalid rule name")
    safe = name.strip().replace(" ", "_")
    return RULES_DIR / f"{safe}.yaml"


# ---------------------------------------------------------------------------
# profiles


@app.get("/api/profiles", response_model=list[ProfileDescriptor])
def api_list_profiles() -> list[ProfileDescriptor]:
    return list_profiles(PROFILES_DIR, USER_PROFILES_DIR)


@app.get("/api/bambu-profiles")
def api_list_bambu_profiles() -> list[dict[str, str]]:
    """Return Bambu target printer options derived from bundled reference files."""
    profiles = list_profiles(BAMBU_PROFILES_DIR, BAMBU_PROFILES_DIR)
    result = []
    for p in profiles:
        try:
            cfg = read_project_settings(Path(p.path))
            printer_name = cfg.get("printer_model") or p.display_name
        except Exception:
            logger.warning("could not read printer_model from %s", p.path)
            printer_name = p.display_name
        result.append({"id": p.id, "name": printer_name})
    return result


# ---------------------------------------------------------------------------
# rules


class RulePayload(BaseModel):
    yaml_text: str


@app.get("/api/rules")
def api_list_rules() -> list[dict[str, Any]]:
    try:
        rules = load_rules(RULES_DIR)
    except RuleLoadError as err:
        raise HTTPException(500, detail=str(err)) from err
    return [
        {
            "name": r.name,
            "file_key": Path(r.source_path).stem if r.source_path else r.name.strip().replace(" ", "_"),
            "description": r.description,
            "enabled": r.enabled,
            "priority": r.priority,
            "match": r.match.model_dump(exclude_none=True),
            "overrides": r.overrides,
            "source_path": r.source_path,
        }
        for r in rules
    ]


@app.get("/api/rules/{name}")
def api_get_rule(name: str) -> dict[str, str]:
    path = _rule_filename(name)
    if not path.exists():
        raise HTTPException(404, detail="rule not found")
    return {"name": name, "yaml_text": path.read_text(encoding="utf-8")}


@app.put("/api/rules/{name}")
def api_put_rule(name: str, payload: RulePayload) -> dict[str, str]:
    # Validate by parsing before writing.
    try:
        rule = _parse_rule_yaml(payload.yaml_text)
    except RuleLoadError as err:
        raise HTTPException(400, detail=str(err)) from err
    if rule.name.strip() != name.strip():
        raise HTTPException(
            400, detail=f"yaml name {rule.name!r} doesn't match URL {name!r}"
        )
    path = _rule_filename(name)
    path.write_text(payload.yaml_text, encoding="utf-8")
    return {"status": "ok", "path": str(path)}


@app.post("/api/rules")
def api_create_rule(payload: RulePayload) -> dict[str, str]:
    try:
        rule = _parse_rule_yaml(payload.yaml_text)
    except RuleLoadError as err:
        raise HTTPException(400, detail=str(err)) from err
    path = _rule_filename(rule.name)
    if path.exists():
        raise HTTPException(409, detail="rule with that name already exists")
    path.write_text(payload.yaml_text, encoding="utf-8")
    return {"status": "ok", "name": rule.name, "path": str(path)}


@app.delete("/api/rules/{name}")
def api_delete_rule(name: str) -> dict[str, str]:
    path = _rule_filename(name)
    if not path.exists():
        raise HTTPException(404, detail="rule not found")
    path.unlink()
    return {"status": "deleted"}


@app.post("/api/rules/test-match")
async def api_test_match(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".3mf"):
        raise HTTPException(400, detail="expected a .3mf upload")
    with tempfile.TemporaryDirectory(dir=TMP_DIR) as td:
        src = Path(td) / file.filename
        _save_upload(file, src)
        from profile_loader import read_project_settings as _rps  # avoid cycle

        try:
            cfg = _rps(src)
        except ProfileLoadError as err:
            raise HTTPException(400, detail=str(err)) from err
        ctx = FilamentContext.from_settings(cfg)
    rules = load_rules(RULES_DIR)
    hits = find_matches(rules, ctx)
    return {
        "context": {
            "settings_ids": list(ctx.settings_ids),
            "vendors": list(ctx.vendors),
            "types": list(ctx.types),
            "base_profile": ctx.base_profile,
        },
        "matches": [
            {
                "rule_name": rule.name,
                "priority": rule.priority,
                "evidence": evidence,
                "overrides": rule.overrides,
            }
            for rule, evidence in hits
        ],
    }


def _parse_rule_yaml(yaml_text: str) -> RuleDefinition:
    try:
        raw = yaml.safe_load(yaml_text)
    except yaml.YAMLError as err:
        raise RuleLoadError(f"invalid YAML: {err}") from err
    if not isinstance(raw, dict):
        raise RuleLoadError("top-level must be a mapping")
    try:
        return RuleDefinition(**raw)
    except Exception as err:
        raise RuleLoadError(str(err)) from err


# ---------------------------------------------------------------------------
# suggest-profile


@app.post("/api/suggest-profile")
async def api_suggest_profile(file: UploadFile = File(...)) -> dict[str, Any]:
    if not file.filename or not file.filename.lower().endswith(".3mf"):
        telemetry.upload_errors_counter.add(1, {"reason": "bad_extension"})
        raise HTTPException(400, detail="expected a .3mf upload")
    job_id = uuid.uuid4().hex
    workdir = TMP_DIR / job_id
    workdir.mkdir(parents=True)
    src = workdir / file.filename
    _save_upload(file, src)
    try:
        try:
            cfg = read_project_settings(src)
        except ProfileLoadError as err:
            telemetry.upload_errors_counter.add(1, {"reason": "unrecognised_file"})
            _retain_failed_workdir(
                job_id=job_id,
                workdir=workdir,
                endpoint="/api/suggest-profile",
                filename=file.filename,
                reference_profile="",
                detail=str(err),
                error_type=type(err).__name__,
                request_meta={},
            )
            raise HTTPException(400, detail=str(err)) from err
        with zipfile.ZipFile(src) as _z:
            _names = _z.namelist()
            _model_xml = (
                _z.read("3D/3dmodel.model").decode("utf-8", errors="replace")
                if "3D/3dmodel.model" in _names else ""
            )
        profiles = list_profiles(PROFILES_DIR, USER_PROFILES_DIR)
        suggestion = suggest_profile(profiles, cfg)
        if suggestion is None:
            raise HTTPException(404, detail="no profiles available")
        source_printer = cfg.get("printer_model", "")
        already_converted = "snapmaker" in source_printer.lower()

        # Build per-slot filament info for the UI slot mapper.
        ids = cfg.get("filament_settings_id") or []
        types = cfg.get("filament_type") or []
        vendors = cfg.get("filament_vendor") or []
        colours = cfg.get("filament_colour") or []
        filaments = [
            {
                "index": i,
                "settings_id": ids[i] if i < len(ids) else None,
                "filament_type": types[i] if i < len(types) else None,
                "vendor": vendors[i] if i < len(vendors) else None,
                "colour": colours[i] if i < len(colours) else None,
            }
            for i in range(len(ids))
        ]

        n_filaments = len(ids)
        _painted = is_painted_model(_names, n_filaments)

        # Bed placement warnings
        import re as _re
        _transforms = _re.findall(r'transform="([^"]+)"', _model_xml)
        _txs, _tys = [], []
        for _t in _transforms:
            _v = _t.split()
            if len(_v) == 12:
                _txs.append(float(_v[9])); _tys.append(float(_v[10]))
        _is_multiplate = bool(_txs) and (
            (max(_txs) - min(_txs)) > _MULTIPLATE_SPAN_MM or
            (max(_tys) - min(_tys)) > _MULTIPLATE_SPAN_MM
        )
        _src_area = cfg.get("printable_area") or ["0x0"]
        _axs = [float(p.split("x")[0]) for p in _src_area]
        _ays = [float(p.split("x")[1]) for p in _src_area]
        _is_oversized = (max(_axs) - min(_axs)) > 270.0 or (max(_ays) - min(_ays)) > 270.0
        _is_colour_mixed = any(v == "1" for v in cfg.get("filament_is_mixed") or [])

        _NON_BAMBU: dict[str, str] = {
            "Metadata/creality.config": "Creality",
            "Metadata/prusa_slicer.ini": "PrusaSlicer",
            "Metadata/Cura_Profile.xml": "Cura",
        }
        _source_slicer = next(
            (name for sig, name in _NON_BAMBU.items() if sig in _names), None
        )

        logger.info(
            "SUGGEST %s  lh=%s  pid=%r  printer=%r  already_converted=%s  filaments=%d  painted=%s  → %s",
            file.filename,
            cfg.get("layer_height"),
            cfg.get("print_settings_id"),
            source_printer,
            already_converted,
            n_filaments,
            _painted,
            suggestion.display_name,
        )
        return {
            "profile_id": suggestion.id,
            "display_name": suggestion.display_name,
            "source_printer": source_printer,
            "already_converted": already_converted,
            "filaments": filaments,
            "is_painted_model": _painted,
            "is_multiplate": _is_multiplate,
            "is_oversized": _is_oversized,
            "is_colour_mixed": _is_colour_mixed,
            "source_slicer": _source_slicer,
            "matched_on": {
                "layer_height": cfg.get("layer_height"),
                "print_settings_id": cfg.get("print_settings_id"),
            },
        }
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# ---------------------------------------------------------------------------
# convert


@app.post("/api/convert")
async def api_convert(
    file: UploadFile = File(...),
    reference_profile: str = Form(...),
    apply_rules: bool = Form(True),
    clamp_speeds: bool = Form(True),
    preserve_color_painting: bool = Form(True),
    advanced_overrides: str = Form("{}"),
    slot_map: str = Form("{}"),
    insert_swap_pauses: str = Form("false"),
) -> JSONResponse:
    if not file.filename or not file.filename.lower().endswith(".3mf"):
        raise HTTPException(400, detail="expected a .3mf upload")

    try:
        overrides = yaml.safe_load(advanced_overrides) or {}
        if not isinstance(overrides, dict):
            raise ValueError("must be a mapping")
    except (ValueError, yaml.YAMLError) as err:
        raise HTTPException(400, detail=f"bad advanced_overrides: {err}") from err

    try:
        import json as _json
        _sm = (slot_map or "").strip()
        raw_slot_map = _json.loads(_sm) if _sm and _sm != "{}" else {}
        parsed_slot_map: dict[int, int] = {int(k): int(v) for k, v in raw_slot_map.items()}
    except (ValueError, TypeError) as err:
        raise HTTPException(400, detail=f"bad slot_map: {err}") from err
    if any(v < 0 or v >= _MAX_TOOLHEADS for v in parsed_slot_map.values()):
        raise HTTPException(400, detail="slot_map values must be 0–3")

    try:
        descriptor = resolve_profile(
            reference_profile, PROFILES_DIR, USER_PROFILES_DIR
        )
    except ProfileNotFoundError as err:
        raise HTTPException(404, detail=str(err)) from err

    job_id = uuid.uuid4().hex
    workdir = TMP_DIR / job_id
    workdir.mkdir(parents=True)

    src_path = workdir / file.filename
    _save_upload(file, src_path, size_limit_bytes=MAX_UPLOAD_MB * 1024 * 1024)

    output_name = f"{Path(file.filename).stem}-U1.3mf"
    out_path = workdir / output_name

    settings = ConversionSettings(
        reference_profile=descriptor.id,
        apply_rules=apply_rules,
        clamp_speeds=clamp_speeds,
        preserve_color_painting=preserve_color_painting,
        advanced_overrides=overrides,
        slot_map=parsed_slot_map,
        insert_swap_pauses=insert_swap_pauses.lower() == "true",
    )

    rules = load_rules(RULES_DIR)

    _src_kb = src_path.stat().st_size / 1024
    with zipfile.ZipFile(src_path) as _zf:
        _src_names = _zf.namelist()
        _src_cfg = (
            json.loads(_zf.read("Metadata/project_settings.config"))
            if "Metadata/project_settings.config" in _src_names else {}
        )
        _n_filaments = len(_src_cfg.get("filament_settings_id") or [])
        _src_printer = _src_cfg.get("printer_model", "unknown")
    _is_painted = is_painted_model(_src_names, _n_filaments)
    _has_vlh = "Metadata/layer_heights_profile.txt" in _src_names
    _already_converted = bool(_src_printer and "U1" in _src_printer)
    _t0 = time.monotonic()
    try:
        result = convert(
            source_path=src_path,
            reference_path=Path(descriptor.path),
            output_path=out_path,
            settings=settings,
            rules=rules,
        )
    except ProfileLoadError as err:
        telemetry.record_conversion(
            profile=reference_profile, status="error",
            duration_ms=(time.monotonic() - _t0) * 1000,
            file_size_kb=_src_kb, keys_dropped=0, rules_matched=0,
            is_painted=_is_painted, has_vlh=_has_vlh,
            source_printer=_src_printer, already_converted=_already_converted,
            error_reason="profile_load_error",
        )
        _retain_failed_workdir(
            job_id=job_id,
            workdir=workdir,
            endpoint="/api/convert",
            filename=file.filename,
            reference_profile=descriptor.id,
            detail=str(err),
            error_type=type(err).__name__,
            request_meta={
                "apply_rules": apply_rules,
                "clamp_speeds": clamp_speeds,
                "preserve_color_painting": preserve_color_painting,
                "slot_map": parsed_slot_map,
                "insert_swap_pauses": insert_swap_pauses.lower() == "true",
            },
        )
        raise HTTPException(400, detail=str(err)) from err
    except Exception as err:
        _retain_failed_workdir(
            job_id=job_id,
            workdir=workdir,
            endpoint="/api/convert",
            filename=file.filename,
            reference_profile=descriptor.id,
            detail=str(err),
            error_type=type(err).__name__,
            request_meta={
                "apply_rules": apply_rules,
                "clamp_speeds": clamp_speeds,
                "preserve_color_painting": preserve_color_painting,
                "slot_map": parsed_slot_map,
                "insert_swap_pauses": insert_swap_pauses.lower() == "true",
            },
        )
        telemetry.record_conversion(
            profile=reference_profile, status="error",
            duration_ms=(time.monotonic() - _t0) * 1000,
            file_size_kb=_src_kb, keys_dropped=0, rules_matched=0,
            is_painted=_is_painted, has_vlh=_has_vlh,
            source_printer=_src_printer, already_converted=_already_converted,
            error_reason=type(err).__name__.lower(),
        )
        logger.exception("conversion failed")
        raise HTTPException(500, detail=f"conversion failed: {err}") from err

    _counts = result.diff.counts()
    telemetry.record_conversion(
        profile=reference_profile,
        status="success",
        duration_ms=(time.monotonic() - _t0) * 1000,
        file_size_kb=_src_kb,
        keys_dropped=_counts.get("keys_dropped", 0),
        rules_matched=_counts.get("rules_matched", 0),
        is_painted=_is_painted,
        has_vlh=_has_vlh,
        n_slots=_n_filaments,
        swap_pauses_requested=settings.insert_swap_pauses,
        swap_pauses_inserted=_counts.get("swap_instructions", 0),
        swap_pauses_skipped=result.diff.swap_pauses_skipped_painted,
        source_printer=_src_printer,
        already_converted=_already_converted,
    )

    diff_payload = {
        "report": result.diff.model_dump(),
        "sections": summarise(result.diff),
        "counts": _counts,
    }
    _register_job(job_id, out_path, diff_payload)

    return JSONResponse(
        {
            "job_id": job_id,
            "download_name": output_name,
            "diff": diff_payload,
        }
    )


@app.post("/api/convert-bambu")
async def api_convert_bambu(
    file: UploadFile = File(...),
    reference_profile: str = Form(...),
    apply_rules: bool = Form(True),
    clamp_speeds: bool = Form(True),
    preserve_color_painting: bool = Form(True),
    advanced_overrides: str = Form("{}"),
    insert_swap_pauses: str = Form("false"),
) -> JSONResponse:
    """Convert a Bambu 3mf to a different Bambu printer target.

    The reference_profile must be a user-provided 3mf exported from Bambu
    Studio for the target printer (e.g. an H2S profile in user_profiles/).
    Bambu-specific metadata files are preserved; model_settings is not
    rewritten.  Use /api/convert for Snapmaker U1 output.
    """
    if not file.filename or not file.filename.lower().endswith(".3mf"):
        raise HTTPException(400, detail="expected a .3mf upload")

    try:
        overrides = yaml.safe_load(advanced_overrides) or {}
        if not isinstance(overrides, dict):
            raise ValueError("must be a mapping")
    except (ValueError, yaml.YAMLError) as err:
        raise HTTPException(400, detail=f"bad advanced_overrides: {err}") from err

    try:
        descriptor = resolve_profile(
            reference_profile, BAMBU_PROFILES_DIR, BAMBU_PROFILES_DIR
        )
    except ProfileNotFoundError as err:
        raise HTTPException(404, detail=str(err)) from err

    # Derive a clean output suffix from the reference printer_model.
    ref_cfg = read_project_settings(Path(descriptor.path))
    raw_model = ref_cfg.get("printer_model", descriptor.id)
    # Take the last space-separated token (e.g. "Bambu Lab H2S" → "H2S").
    suffix = raw_model.split()[-1] if raw_model else descriptor.id

    job_id = uuid.uuid4().hex
    workdir = TMP_DIR / job_id
    workdir.mkdir(parents=True)

    src_path = workdir / file.filename
    _save_upload(file, src_path, size_limit_bytes=MAX_UPLOAD_MB * 1024 * 1024)

    output_name = f"{Path(file.filename).stem}-{suffix}.3mf"
    out_path = workdir / output_name

    settings = ConversionSettings(
        reference_profile=descriptor.id,
        apply_rules=apply_rules,
        clamp_speeds=clamp_speeds,
        preserve_color_painting=preserve_color_painting,
        advanced_overrides=overrides,
        slot_map={},
        insert_swap_pauses=insert_swap_pauses.lower() == "true",
    )

    rules = load_rules(RULES_DIR)

    try:
        result = convert(
            source_path=src_path,
            reference_path=Path(descriptor.path),
            output_path=out_path,
            settings=settings,
            rules=rules,
            preserve_bambu_metadata=True,
        )
    except ProfileLoadError as err:
        _retain_failed_workdir(
            job_id=job_id,
            workdir=workdir,
            endpoint="/api/convert-bambu",
            filename=file.filename,
            reference_profile=descriptor.id,
            detail=str(err),
            error_type=type(err).__name__,
            request_meta={
                "apply_rules": apply_rules,
                "clamp_speeds": clamp_speeds,
                "preserve_color_painting": preserve_color_painting,
                "insert_swap_pauses": insert_swap_pauses.lower() == "true",
            },
        )
        raise HTTPException(400, detail=str(err)) from err
    except Exception as err:
        _retain_failed_workdir(
            job_id=job_id,
            workdir=workdir,
            endpoint="/api/convert-bambu",
            filename=file.filename,
            reference_profile=descriptor.id,
            detail=str(err),
            error_type=type(err).__name__,
            request_meta={
                "apply_rules": apply_rules,
                "clamp_speeds": clamp_speeds,
                "preserve_color_painting": preserve_color_painting,
                "insert_swap_pauses": insert_swap_pauses.lower() == "true",
            },
        )
        logger.exception("conversion failed")
        raise HTTPException(500, detail=f"conversion failed: {err}") from err

    diff_payload = {
        "report": result.diff.model_dump(),
        "sections": summarise(result.diff),
        "counts": result.diff.counts(),
    }
    _register_job(job_id, out_path, diff_payload)

    return JSONResponse(
        {
            "job_id": job_id,
            "download_name": output_name,
            "diff": diff_payload,
        }
    )


@app.get("/api/download/{job_id}")
def api_download(job_id: str) -> FileResponse:
    job = _get_job(job_id)
    if job is None:
        raise HTTPException(404, detail="job expired or not found")
    path: Path = job["output_path"]
    if not path.exists():
        raise HTTPException(410, detail="output file was cleaned up")
    return FileResponse(
        path,
        filename=path.name,
        media_type="application/octet-stream",
    )

# ---------------------------------------------------------------------------
# helpers

def _save_upload(
    file: UploadFile, dst: Path, *, size_limit_bytes: int | None = None
) -> None:
    written = 0
    with dst.open("wb") as fh:
        while True:
            chunk = file.file.read(1024 * 1024)
            if not chunk:
                break
            written += len(chunk)
            if size_limit_bytes is not None and written > size_limit_bytes:
                fh.close()
                dst.unlink(missing_ok=True)
                telemetry.upload_errors_counter.add(1, {"reason": "too_large"})
                raise HTTPException(413, detail="file too large")
            fh.write(chunk)


# ---------------------------------------------------------------------------
# health + static frontend

@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/robots.txt", include_in_schema=False)
def robots_txt():
    from fastapi.responses import PlainTextResponse
    content = f"User-agent: *\nAllow: /\nSitemap: {SITE_URL}/sitemap.xml\n"
    return PlainTextResponse(content, media_type="text/plain")


@app.get("/sitemap.xml", include_in_schema=False)
def sitemap_xml():
    from fastapi.responses import Response
    from datetime import date
    today = date.today().isoformat()
    content = f"""<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{SITE_URL}/</loc>
    <lastmod>{today}</lastmod>
    <changefreq>weekly</changefreq>
    <priority>1.0</priority>
  </url>
  <url>
    <loc>{SITE_URL}/privacy.html</loc>
    <lastmod>{today}</lastmod>
    <changefreq>monthly</changefreq>
    <priority>0.3</priority>
  </url>
</urlset>"""
    return Response(content=content, media_type="application/xml")


@app.post("/api/feedback")
async def api_feedback(
    page: str = Form(...),
    message: str = Form(""),
    email: str = Form(""),
) -> JSONResponse:
    import json as _json, datetime as _dt
    entry = {
        "ts": _dt.datetime.utcnow().isoformat(),
        "page": page[:64],
        "message": message[:2000],
        "email": email[:200],
    }
    feedback_file = FEEDBACK_DIR / "feedback.jsonl"
    with open(feedback_file, "a", encoding="utf-8") as fh:
        fh.write(_json.dumps(entry) + "\n")
    return JSONResponse({"ok": True})

@app.middleware("http")
async def _log_requests(request: Request, call_next):
    start = time.monotonic()
    response = await call_next(request)
    if request.url.path == "/api/health":
        return response
    logger.info(
        "%s %s -> %d (%.1f ms)",
        request.method,
        request.url.path,
        response.status_code,
        (time.monotonic() - start) * 1000,
    )
    return response


@app.get("/privacy.html", response_class=HTMLResponse, include_in_schema=False)
def privacy_page() -> HTMLResponse:
    path = FRONTEND_DIST / "privacy.html"
    if not path.exists():
        raise HTTPException(404, detail="not found")
    return HTMLResponse(render_privacy_html(path.read_text(encoding="utf-8")))


# Mount the built frontend last so it doesn't shadow /api routes.
if FRONTEND_DIST.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
