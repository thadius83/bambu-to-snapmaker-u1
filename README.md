# Bambu → Snapmaker U1 3MF Converter

[![BuyMeACoffee](.github/bmc-yellow.svg)](https://www.buymeacoffee.com/jdau)

Self-hosted web app that converts Bambu Lab `.3mf` project files into
Snapmaker U1-compatible `.3mf` files. The converted file opens cleanly in
Snapmaker Orca ready for re-slicing — it preserves the creator's process
settings (layer height, walls, infill, speeds, filaments, etc.) while swapping
printer identity, custom G-code, and filament slot assignments.

If you've ever downloaded a Makerworld project and discovered it's locked to a
Bambu printer, this is the tool for you. Drop the `.3mf` in, get a U1-ready
`.3mf` out. No manual JSON editing, no profile rebuilding.

## Quick start

```bash
git clone https://github.com/thadius83/bambu-to-snapmaker-u1.git
cd bambu-to-snapmaker-u1
cp .env.example .env       # safe defaults; no editing needed for first run
docker compose up --build
```

Open **<http://localhost:8083>** in your browser. That's it.

No accounts, no database, no external dependencies beyond Docker.

## What it does

1. **Identity swap** — replaces hardware-only keys (`printer_model`,
   `printer_settings_id`, build volume, nozzle specs) from the selected U1
   reference profile. All print intent — layer heights, speeds, filament
   names, temperatures — flows from the source file unchanged.
2. **G-code swap** — replaces all 9 custom G-code blocks (start, end,
   layer-change, before-layer-change, change-filament, pause, timelapse, etc.)
   with U1 equivalents. Bambu's AMS-specific G-code would crash U1 firmware.
3. **Key filter** — drops Bambu-only keys not present in the U1 reference
   schema (~170 in a typical file).
4. **Speed / accel clamp** — enforces the U1 reference profile's values as
   ceilings. The reference itself is the source of truth — no hard-coded
   numbers.
5. **Filament rules** — YAML-based matching on filament name / vendor / type.
   Applies per-key overrides (speed, accel, temperature). Editable in the
   browser without a restart.
6. **Filament slot remap** — preserves Bambu's colour array order exactly
   (slot N stays at slot N). Painted-face colour assignments are preserved
   via `filament_maps`.
7. **Filament swap pauses** (auto-enabled for >4 colours) — detects when a
   physical toolhead must switch spools mid-print and inserts M600 pause
   elements one full layer before each swap, with a colour-coded swap guide
   in the post-conversion diff view.
8. **Slice cache strip** — removes `Metadata/plate_*.gcode` and
   `plate_*.json` so Snapmaker Orca is forced to re-slice rather than use
   stale Bambu output.

The diff view after conversion shows every change made before you download.

## Volumes

| Mount | Purpose |
|---|---|
| `./user_profiles` | Extra U1 reference `.3mf` files. Any file here with the same name as a bundled profile shadows it. |
| `./rules` | YAML filament-tuning rules. Editable live via the Rules page in the UI. |
| `./tmp` | Converted files retained for 5 minutes after the conversion completes. |

## Adding reference profiles

Export a print profile from Snapmaker Orca as a `.3mf` file (File → Export →
Export All Objects, or just save the project with a trivial test object).
Drop the file in `./user_profiles/`. It will appear in the profile dropdown
immediately — no restart needed.

Bundled profiles in `./profiles/` cover the full U1 layer-height range:

| Profile | Layer height |
|---|---|
| 0.08 High Quality | 0.08 mm |
| 0.12 Fine | 0.12 mm |
| 0.12 High Quality | 0.12 mm |
| 0.16 Optimal | 0.16 mm |
| 0.16 High Quality | 0.16 mm |
| 0.20 Standard | 0.20 mm (default) |
| 0.20 Strength | 0.20 mm |
| 0.24 Draft | 0.24 mm |
| 0.28 Extra Draft | 0.28 mm |

## Writing filament rules

Rules live as individual YAML files in `./rules/`. You can edit them in the
browser (Rules page) or directly on the filesystem. Changes are picked up on
the next conversion — no restart needed.

### Schema

```yaml
name: My Rule                          # required, unique
description: "What this does"
match:
  filament_settings_id_contains: Silk  # case-insensitive substring
  filament_vendor: "Bambu Lab"         # exact match (optional)
  filament_type: PLA                   # exact match (optional)
  base_profile_contains: "0.20mm"      # substring of print_settings_id (optional)
overrides:
  outer_wall_speed: 80                 # any process-settings key: value
  default_acceleration: 3000
priority: 10                           # higher number = applied later (wins)
enabled: true
```

**Matching logic:** all specified conditions must be true simultaneously
(AND). Multiple rules can match; they apply in ascending `priority` order so
higher-priority rules overwrite lower ones on conflicting keys.

**Scope:** rules apply globally to the process profile, not per-object.
Per-object scoping is a planned extension.

### Seed rules included

| File | Targets |
|---|---|
| `silk_pla.yaml` | Bambu PLA Silk+ — slower speeds, reduced accel |
| `petg_hf.yaml` | Bambu PETG HF — moderate speeds, 255°C nozzle |
| `petg_translucent.yaml` | Bambu PETG Translucent — conservative speeds for optical clarity |
| `pla.yaml` | Generic Bambu PLA Basic — balanced U1 speeds |
| `pla_matte.yaml` | Bambu PLA Matte — slightly reduced speeds |

Values are based on Bambu's published tuning guidance; adjust to your spool
via the web editor.

## Configuration

Configuration is via `.env` (copied from `.env.example` on first run). The
common knobs:

| Variable | Default | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | `200` | Upload size cap |
| `CLEANUP_TEMP_AFTER_SECONDS` | `300` | How long converted files stay available for download before being purged |
| `RETAIN_FAILED_FILES` | `false` | Keep failed conversion workdirs in `tmp_failed/` for debugging |
| `VITE_SITE_URL` | `http://localhost:8083` | Canonical URL baked into the frontend (SEO meta + privacy page) |
| `DOMAINHOST` | `localhost` | Hostname used for `robots.txt` and `sitemap.xml` |

Optional analytics (Google Analytics 4, Cloudflare Web Analytics) and
OpenTelemetry export are documented inline in `.env.example`. All default to
off; the CSP and privacy page adapt automatically to whatever you enable.

## Development

### Backend only (Python + FastAPI)

```bash
cd backend
pip install -r requirements-dev.txt
export U13MF_APP_ROOT=..
export U13MF_PROFILES=../profiles
export U13MF_USER_PROFILES=../user_profiles
export U13MF_RULES=../rules
export U13MF_TMP=../tmp
export U13MF_FRONTEND_DIST=../frontend/dist
uvicorn main:app --reload --port 8080
```

### Frontend only (Svelte + Vite)

```bash
cd frontend
npm install
npm run dev      # → http://localhost:5173 (proxies /api to :8080)
```

## Architecture

```
backend/
  main.py           FastAPI routes + job registry
  converter.py      Pipeline orchestrator (unzip → transform → rezip)
  models.py         Pydantic schemas (ConversionSettings, DiffReport, …)
  profile_loader.py Discover + read U1 reference profiles
  key_filter.py     Drop Bambu-only keys; clamp speed/accel ceilings
  gcode_swapper.py  Wholesale G-code block replacement
  rules_engine.py   YAML rule loading, matching, application
  diff_reporter.py  Accumulate per-stage events → DiffReport + UI sections
  swap_pauses.py    M600 pause insertion for >4 colour prints
  security.py       CSP composition + privacy-page conditional rendering

frontend/src/
  App.svelte        Root component — routing, theme, convert state machine
  lib/Upload.svelte Drag-drop zone
  lib/Settings.svelte  Profile dropdown, toggles, advanced overrides
  lib/DiffView.svelte  Post-conversion change summary + swap guide
  lib/RuleEditor.svelte  Rule list + CodeMirror YAML editor + test-match
  lib/api.ts        Typed fetch wrappers for every API endpoint

profiles/           Bundled U1 reference 3mf files (committed)
user_profiles/      Mounted volume — user reference overrides
rules/              Mounted volume — YAML filament rules
tmp/                Per-request working dirs, auto-cleaned
```

## Need a sample input?

Grab any Bambu Studio `.3mf` from [Makerworld](https://makerworld.com/) or
your own slicer history. Painted multi-colour models work — the converter
preserves Bambu's colour array order and inserts pause stops for
>4-colour prints.

## Known limitations

- U1 only, 0.4 mm nozzle only. Drop any Orca-exported `.3mf` in
  `user_profiles/` to target a different printer (works mechanically; not
  fully tested).
- No conversion history or re-download after the cleanup window.
- No in-app slicing — output must be re-sliced in Snapmaker Orca.

## Support the project

If this saves you a few hours, consider buying me a coffee: <https://buymeacoffee.com/jdau>.

## Bug reports and feature requests

Open an issue on [GitHub](https://github.com/thadius83/bambu-to-snapmaker-u1/issues).

## Credits

- U1 reference profiles are derived from Snapmaker Orca's bundled defaults.
- Thanks to the Snapmaker community for tuning guidance and bug reports.

## License

[PolyForm Noncommercial 1.0.0](LICENSE).

You may use, modify, and redistribute this software for any non-commercial
purpose — personal projects, hobbyist use, research, education, and
charitable / non-profit organisations are all explicitly allowed. Commercial
use (selling the software, running it as a paid service, integrating it into
commercial products) requires a separate license; contact the project
maintainer.
