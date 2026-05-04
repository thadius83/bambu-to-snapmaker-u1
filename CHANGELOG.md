# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.1.0] - 2026-05-05

### Added

- Initial public release.
- Bambu Lab `.3mf` → Snapmaker U1 `.3mf` conversion pipeline:
  identity swap, custom G-code swap, Bambu-only key filter, speed/accel
  clamp from reference, YAML filament rule engine, filament slot remap,
  M600 swap pauses for >4 colour prints, slice cache strip.
- 9 bundled U1 reference profiles spanning 0.08 mm to 0.28 mm layer heights.
- 5 seed filament rules (Silk PLA+, PETG HF, PETG Translucent, PLA Basic,
  PLA Matte).
- Web UI with profile auto-detection, settings panel, post-conversion diff
  view, in-browser YAML rule editor (CodeMirror), and feedback widget.
- Privacy page that renders honestly based on the operator's tracking config.
- Optional Google Analytics 4 and Cloudflare Web Analytics support, off by
  default and env-controlled.
- Pytest suite covering the converter pipeline and per-stage transforms.
- Single-command Docker deploy via `docker compose up --build`.

[Unreleased]: https://github.com/thadius83/bambu-to-snapmaker-u1/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/thadius83/bambu-to-snapmaker-u1/releases/tag/v0.1.0
