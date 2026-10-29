# Snapmaker U1 3MF Converter

[![BuyMeACoffee](.github/bmc-yellow.svg)](https://www.buymeacoffee.com/jdau)

Self-hosted web app that converts MakerWorld and Bambu Studio projects, plus
OrcaSlicer, PrusaSlicer and Cura 3MF files, for the Snapmaker U1 printer.
The converter adapts available source settings to a selected U1 reference
profile, including printer identity, custom G-code and filament assignments.
Download the converted file, then review and re-slice it in Snapmaker Orca
before printing.

## Source file support

| Source format | Notes |
|---|---|
| Bambu Studio / Bambu Lab `.3mf` | Includes projects downloaded from MakerWorld. |
| Orca-format non-Bambu `.3mf` | Flashforge, Anycubic, Creality, and similar Orca-based exports use the same project structure. |
| PrusaSlicer `.3mf` | Imports supported settings, including nozzle/bed temperatures and first-layer height; preserves per-part colours, repeated instances and MMU face painting. Review the converted project in Snapmaker Orca. |
| Cura `.3mf` | Reads layer height from Cura user config where available; other settings use the selected U1 reference defaults. |
| Bare geometry `.3mf` | No slicer settings are available, so the converter defaults to the bundled `0.20 Standard` U1 profile. |
| Sliced `.gcode.3mf` without model geometry | Not supported. These files contain printer-specific plate G-code but no editable model data. Upload the original project `.3mf` instead. |

## Hosted Version

**<https://u1convert.com>**

## Quick start

```bash
git clone https://github.com/thadius83/bambu-to-snapmaker-u1.git
cd bambu-to-snapmaker-u1
cp .env.example .env
```

For local use, set `VITE_SITE_URL=http://localhost:8084` and
`DOMAINHOST=localhost` in `.env`. For a public deployment, replace the example
domain with your own URL and hostname before building.

```bash
docker compose up --build
```

Open **<http://localhost:8084>** in your browser.

No accounts, no database, no external dependencies beyond Docker.

## What it does

1. **Identity swap:** takes printer identity, build volume and nozzle specs
   from the selected U1 reference profile. Compatible source settings are
   retained where supported; reference defaults, tuning rules and conversion
   options can change the output. U1 standby cooling and advance preheating
   settings also come from the reference. Exclude objects is always enabled
   for U1 output, overriding source and advanced settings.
2. **G-code swap:** replaces the 9 configured custom G-code blocks (start,
   end, layer-change, before-layer-change, change-filament, pause, etc.) with
   reference equivalents, removing blocks absent from the reference.
3. **Key filter:** filters settings against the reference profile's keys,
   with exceptions for supported metadata and print settings.
4. **Speed / accel clamp:** when enabled, uses the U1 reference profile's
   positive values as ceilings for selected speed and acceleration settings,
   and clamps enabled process jerk to target machine limits.
5. **Filament rules:** YAML-based matching on filament name / vendor / type.
   Applies process-setting overrides. Maintain the YAML files directly;
   view rules and test matching in the browser. Numeric overrides act as
   ceilings, as described below.
6. **Filament slots:** keeps painted-face colours, object and part assignments,
   feature-specific filament settings and per-layer tool changes aligned
   with physical filament slot mappings.
7. **Filament swap pauses:** enabled automatically for non-painted projects
   with more than 4 colours. Uses source per-layer tool-change data to insert
   M600 pauses before spool swaps and produce a colour-coded swap guide.
   Projects without that data need manual swap planning.
8. **Slice cache strip:** removes cached plate G-code and slice metadata,
   then writes minimal plate metadata. Re-slice the converted project in
   Snapmaker Orca before printing.
9. **Sliced-only guard:** rejects `.gcode.3mf` uploads that contain plate
   G-code but no editable model geometry.

The results page shows the output printer, summarises recorded setting changes
and any swap guide, and warns when the detected source nozzle size changes.
Review the converted project in Snapmaker Orca before printing.

## Volumes

| Mount | Purpose |
|---|---|
| `./profiles` | Bundled U1 reference `.3mf` files. |
| `./user_profiles` | Extra U1 reference `.3mf` files. Any file here with the same profile ID as a bundled profile shadows it. |
| `./rules` | YAML filament-tuning rules. Maintain these files directly; the Rules page is read-only. |
| `./tmp` | Uploads and converted files, automatically cleaned after the configured download window (5 minutes by default). |
| `./tmp_failed` | Failed conversion files, retained only when `RETAIN_FAILED_FILES=true`. |
| `./feedback` | Saved feedback submissions. |

## Adding reference profiles

Save a project from Snapmaker Orca as a `.3mf` file containing a small model
and your chosen U1 printer and print settings. Drop it in `./user_profiles/`
and refresh the page to update the profile dropdown. No server restart is
needed.

The 10 bundled reference projects in `./profiles/` use a 0.4 mm nozzle and
cover these layer heights:

| Profile | Layer height |
|---|---|
| 0.08 High Quality | 0.08 mm |
| 0.12 Fine | 0.12 mm |
| 0.12 High Quality | 0.12 mm |
| 0.16 Optimal | 0.16 mm |
| 0.16 High Quality | 0.16 mm |
| 0.20 Standard | 0.20 mm (default) |
| 0.20 Standard (Cube lots of colours) | 0.20 mm |
| 0.20 Strength | 0.20 mm |
| 0.24 Draft | 0.24 mm |
| 0.28 Extra Draft | 0.28 mm |

## Writing filament rules

Rules live as individual YAML files in `./rules/`. Maintain these files directly
on the filesystem. Changes are picked up on the next conversion; no restart
is needed. The Rules page lets you view the shared rules and test matching against
a `.3mf` file.

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
priority: 10                           # higher number = applied later
enabled: true
```

**Matching logic:** all specified conditions must be true simultaneously
(AND). Filament conditions must match the same filament. Multiple rules can
match; they apply in ascending `priority` order.

**Override behaviour:** numeric values act as ceilings when the existing
value is also numeric. A later rule cannot raise a value already below its
ceiling. Missing settings are filled, and non-numeric overrides replace the
existing value.

**Scope:** rules apply globally to the process profile, not per-object.

### Seed rules included

| File | Targets |
|---|---|
| `silk_pla.yaml` | Bambu PLA Silk+: slower speeds, reduced accel |
| `petg_hf.yaml` | Bambu PETG HF: moderate speeds and reduced acceleration |
| `petg_translucent.yaml` | Bambu PETG Translucent: conservative speeds for optical clarity |
| `pla.yaml` | Generic Bambu PLA Basic: balanced U1 speeds |
| `pla_matte.yaml` | Bambu PLA Matte: slightly reduced speeds |

Values are based on Bambu's published tuning guidance; adjust the YAML files
to suit your spool.

## Configuration

Configure the service through `.env`. The defaults below apply when a
variable is unset; `.env.example` contains domain placeholders that need
replacing before building.

| Variable | Default | Description |
|---|---|---|
| `MAX_UPLOAD_MB` | `300` | Upload size cap |
| `CLEANUP_TEMP_AFTER_SECONDS` | `300` | How long converted files stay available for download before being purged |
| `RETAIN_FAILED_FILES` | `false` | Keep failed conversion workdirs in `tmp_failed/` for debugging |
| `VITE_SITE_URL` | `http://localhost:8084` | Canonical URL baked into the frontend (SEO meta + privacy page) |
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
  metadata_helpers.py  Sidecar XML/project metadata helpers
  models.py         Pydantic schemas (ConversionSettings, DiffReport, …)
  profile_loader.py Discover + read U1 reference profiles
  key_filter.py     Drop Bambu-only keys; clamp speed/accel ceilings
  gcode_swapper.py  Wholesale G-code block replacement
  rules_engine.py   YAML rule loading, matching, application
  diff_reporter.py  Accumulate per-stage events → DiffReport + UI sections
  swap_pauses.py    M600 pause insertion for >4 colour prints
  security.py       CSP composition + privacy-page conditional rendering

frontend/src/
  App.svelte        Root component: routing, theme, convert state machine
  lib/Upload.svelte Drag-drop zone
  lib/Settings.svelte  Profile dropdown, toggles, advanced overrides
  lib/DiffView.svelte  Post-conversion change summary + swap guide
  lib/RuleEditor.svelte  Rule list + read-only YAML view + test-match
  lib/api.ts        Typed fetch wrappers for every API endpoint

profiles/           Bundled U1 reference 3mf files (committed)
user_profiles/      Mounted volume: user reference overrides
rules/              Mounted volume: YAML filament rules
tmp/                Per-request working dirs, auto-cleaned
```

## Need a sample input?

Grab a Bambu Studio `.3mf` from [my MakerWorld profile](https://makerworld.com/en/@iprintstuffau) or your
own slicer history. You can also upload OrcaSlicer, PrusaSlicer, Cura, and
basic geometry `.3mf` files.

Paint data is retained or translated where supported. Check the colour
assignments in Snapmaker Orca, particularly after changing slot mappings.
Layer-based prints with more than 4 colours can use swap pauses when the
source contains per-layer tool-change data. Painted models with more than
4 colours need manual toolhead and spool-swap planning.

## Known limitations

- The main converter targets the U1. Bundled references use a 0.4 mm nozzle;
  the selected reference determines the output nozzle size. Other U1 nozzle
  sizes require a suitable reference project and review of layer heights
  and line widths. Arbitrary printer references are not supported in this flow.
- Sliced `.gcode.3mf` files without editable model geometry cannot be converted;
  upload the original project `.3mf`.
- Native colour mixing support is in development.
- PrusaSlicer and Cura imports do not preserve every source setting. Check
  temperatures, supports and filament assignments before slicing.
- Models are not automatically scaled to fit the U1 build plate. Review model
  and prime-tower placement, especially for larger source beds and multi-plate
  projects; manual arrangement may be required.

## Support the project

If this saves you a few hours, consider buying me a coffee: <https://buymeacoffee.com/jdau>.

## Bug reports and feature requests

Open an issue on [GitHub](https://github.com/thadius83/bambu-to-snapmaker-u1/issues).

## Credits

- U1 reference profiles are derived from Snapmaker Orca's bundled defaults.
- Thanks to the Snapmaker facebook community for tuning guidance and bug reports.

## License

[PolyForm Noncommercial 1.0.0](LICENSE).

You may use, modify, and redistribute this software for any non-commercial
purpose: personal projects, hobbyist use, research, education, and
charitable / non-profit organisations are all explicitly allowed. Commercial
use (selling the software, running it as a paid service, integrating it into
commercial products) requires a separate license; contact the project
maintainer.
