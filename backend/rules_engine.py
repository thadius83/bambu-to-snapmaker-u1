"""Filament-specific tuning rules.

Each rule is one YAML file in ``/rules`` with:

  name, description
  match:
    filament_settings_id_contains: "…"   # case-insensitive substring
    filament_vendor: "…"                  # exact (optional)
    filament_type: "…"                    # exact (optional)
    base_profile_contains: "…"            # exact substring of print_settings_id
  overrides:
    <any_process_key>: <value>
  priority: 10          # higher wins
  enabled: true

Matching:

* All specified conditions must be true simultaneously (AND). Missing
  conditions are ignored.
* The source 3mf's filament arrays may contain multiple filaments — a rule
  matches if *any* filament in the array satisfies the filament-scoped
  conditions. This keeps the v1 semantics simple (rules are global) while
  still being usable on painted multi-filament files.
* If multiple rules match, they are applied in ascending ``priority`` order;
  later rules overwrite earlier ones on conflicting keys.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from models import RuleDefinition, RuleMatch


class RuleLoadError(Exception):
    pass


@dataclass(frozen=True)
class FilamentContext:
    """Flattened view of the filament fields in the source 3mf."""

    settings_ids: tuple[str, ...]
    vendors: tuple[str, ...]
    types: tuple[str, ...]
    base_profile: str  # typically project_settings['print_settings_id']

    @classmethod
    def from_settings(cls, settings: dict[str, Any]) -> "FilamentContext":
        def _as_tuple(v: Any) -> tuple[str, ...]:
            if v is None:
                return ()
            if isinstance(v, list):
                return tuple(str(x) for x in v)
            return (str(v),)

        return cls(
            settings_ids=_as_tuple(settings.get("filament_settings_id")),
            vendors=_as_tuple(settings.get("filament_vendor")),
            types=_as_tuple(settings.get("filament_type")),
            base_profile=str(settings.get("print_settings_id", "")),
        )


# ---------------------------------------------------------------------------
# loading


def load_rule_file(path: Path) -> RuleDefinition:
    """Parse a single YAML rule file. Raises RuleLoadError on any problem."""
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as err:
        raise RuleLoadError(f"{path.name}: invalid YAML — {err}") from err
    if not isinstance(raw, dict):
        raise RuleLoadError(f"{path.name}: top-level must be a mapping")
    try:
        rule = RuleDefinition(**raw)
    except Exception as err:  # Pydantic ValidationError, TypeError, etc.
        raise RuleLoadError(f"{path.name}: {err}") from err
    return rule.model_copy(update={"source_path": str(path)})


def load_rules(rules_dir: Path) -> list[RuleDefinition]:
    """Load every ``*.yaml``/``*.yml`` in ``rules_dir``.

    A malformed rule raises — one bad file shouldn't silently disable the
    others, but we want the user to know immediately which file is broken.
    """
    rules: list[RuleDefinition] = []
    if not rules_dir.exists():
        return rules
    for p in sorted(rules_dir.iterdir()):
        if p.suffix.lower() not in (".yaml", ".yml"):
            continue
        rules.append(load_rule_file(p))
    return rules


def dump_rule(rule: RuleDefinition) -> str:
    """Serialise a rule back to YAML (for the web editor)."""
    payload = rule.model_dump(exclude={"source_path"})
    # Drop explicit nulls from ``match`` so saved files stay tidy.
    match = {k: v for k, v in (payload.get("match") or {}).items() if v is not None}
    payload["match"] = match
    return yaml.safe_dump(payload, sort_keys=False, allow_unicode=True)


# ---------------------------------------------------------------------------
# matching


def _rule_matches(rule: RuleDefinition, ctx: FilamentContext) -> dict[str, Any]:
    """Return the match evidence dict if ``rule`` matches, else empty dict.

    Evidence is what we record in the diff report so the user can see *why*
    the rule fired.
    """
    m = rule.match
    evidence: dict[str, Any] = {}

    if m.base_profile_contains:
        if m.base_profile_contains not in ctx.base_profile:
            return {}
        evidence["base_profile"] = ctx.base_profile

    # For per-filament conditions we match if ANY filament in the array
    # satisfies the condition. We look for a single filament that satisfies
    # all three simultaneously (so a rule asking for "Silk" + "Bambu Lab" +
    # "PLA" actually matches a real Bambu PLA Silk+ row, not a combination
    # across different rows).
    sid_needle = (m.filament_settings_id_contains or "").lower()
    want_vendor = m.filament_vendor
    want_type = m.filament_type

    filament_fields = (
        m.filament_settings_id_contains,
        m.filament_vendor,
        m.filament_type,
    )
    if any(f is not None for f in filament_fields):
        n = max(
            len(ctx.settings_ids),
            len(ctx.vendors),
            len(ctx.types),
        )
        matched_index: int | None = None
        for i in range(n):
            sid = ctx.settings_ids[i] if i < len(ctx.settings_ids) else ""
            ven = ctx.vendors[i] if i < len(ctx.vendors) else ""
            typ = ctx.types[i] if i < len(ctx.types) else ""
            if sid_needle and sid_needle not in sid.lower():
                continue
            if want_vendor is not None and ven != want_vendor:
                continue
            if want_type is not None and typ != want_type:
                continue
            matched_index = i
            break
        if matched_index is None:
            return {}
        evidence["filament_index"] = matched_index
        evidence["filament_settings_id"] = (
            ctx.settings_ids[matched_index]
            if matched_index < len(ctx.settings_ids)
            else None
        )
        if matched_index < len(ctx.vendors):
            evidence["filament_vendor"] = ctx.vendors[matched_index]
        if matched_index < len(ctx.types):
            evidence["filament_type"] = ctx.types[matched_index]

    # A rule with no conditions matches everything — support this for
    # "universal" rules but require it to be explicit (no evidence recorded
    # beyond the marker).
    if not evidence:
        evidence["matched"] = "unconditional"

    return evidence


def find_matches(
    rules: Iterable[RuleDefinition],
    ctx: FilamentContext,
) -> list[tuple[RuleDefinition, dict[str, Any]]]:
    """Return (rule, evidence) pairs for every matching enabled rule,
    ordered by ascending priority (later entries win)."""
    hits: list[tuple[RuleDefinition, dict[str, Any]]] = []
    for rule in rules:
        if not rule.enabled:
            continue
        evidence = _rule_matches(rule, ctx)
        if evidence:
            hits.append((rule, evidence))
    hits.sort(key=lambda pair: pair[0].priority)
    return hits


def apply_rules(
    settings: dict[str, Any],
    rules: Iterable[RuleDefinition],
    ctx: FilamentContext,
) -> tuple[dict[str, Any], list[RuleMatch]]:
    """Apply all matching rules to ``settings`` (non-mutating).

    Returns (new_settings, rule_match_events). Later (higher-priority) rules
    overwrite earlier ones on conflicting keys.
    """
    out = dict(settings)
    events: list[RuleMatch] = []
    for rule, evidence in find_matches(rules, ctx):
        applied: dict[str, Any] = {}
        for k, v in rule.overrides.items():
            # Orca settings are always JSON strings; coerce numeric overrides.
            if isinstance(v, (int, float)) and not isinstance(v, bool):
                v = str(v)
            out[k] = v
            applied[k] = v
        events.append(
            RuleMatch(
                rule_name=rule.name,
                priority=rule.priority,
                matched_on=evidence,
                overrides_applied=applied,
            )
        )
    return out, events
