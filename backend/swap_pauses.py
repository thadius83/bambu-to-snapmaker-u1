"""Insert M600 filament-swap pauses into custom_gcode_per_layer.xml.

When a source file has more colours than physical toolheads, multiple source
slots share one physical head.  The slicer cannot know it must pause and let
the user swap the physical spool before each colour transition.

Algorithm
---------
1. Build a full ext→phys mapping from the slot remap (all slots, not just
   conflicting ones).
2. Simulate the print sequence in layer order, tracking the slot currently
   loaded on each physical head.  Any type=2 entry where loaded_slot ≠
   requested_slot is a *swap event*.
3. Greedily batch swap events into the fewest pauses possible:
   a group can share one M600 if max(last_use_idx) < min(first_needed_idx).
4. Insert one M600 pause element AFTER the layer at max(last_use_idx) in each
   batch — so the pause fires after the last colour in the group finishes, well
   before the next colour starts, with no Z overlap.
"""
from __future__ import annotations

from xml.etree import ElementTree as ET

from models import SwapInstruction

_N_PHYSICAL = 4


def detect_conflicts(
    remap: dict[int, int],
    n_physical: int = _N_PHYSICAL,
) -> dict[int, list[int]]:
    """Return physical_head → [source extruders 1-based] for heads with >1 source."""
    groups: dict[int, list[int]] = {}
    for src_0, tgt_0 in remap.items():
        if tgt_0 < 0:
            continue
        phys = tgt_0 % n_physical
        groups.setdefault(phys, []).append(src_0 + 1)
    return {p: sorted(srcs) for p, srcs in groups.items() if len(srcs) > 1}


def insert_swap_pauses(
    xml_text: str,
    remap: dict[int, int],
    filament_colours: list[str],
    pause_gcode: str,
    n_physical: int = _N_PHYSICAL,
) -> tuple[str, list[SwapInstruction]]:
    """Rewrite XML inserting batched M600 pauses at optimal Z heights.

    Returns (modified_xml, instructions).
    """
    if not detect_conflicts(remap, n_physical):
        return xml_text, []

    # 1-based extruder → 0-based physical head (complete mapping).
    ext_to_phys: dict[int, int] = {
        src_0 + 1: tgt_0 % n_physical
        for src_0, tgt_0 in remap.items()
        if tgt_0 >= 0
    }

    # Initial loaded slot per physical head = lowest-numbered slot for that head.
    loaded_init: dict[int, int] = {}
    for src_0 in sorted(remap):
        tgt_0 = remap[src_0]
        if tgt_0 < 0:
            continue
        phys = tgt_0 % n_physical
        loaded_init.setdefault(phys, src_0 + 1)

    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return xml_text, []

    instructions: list[SwapInstruction] = []

    for plate in root.iter("plate"):
        layers = [c for c in plate if c.tag == "layer"]

        # Derive layer height from the smallest gap between consecutive top_z values.
        zs = sorted({float(l.get("top_z", 0)) for l in layers if l.get("top_z")})
        layer_height = min((b - a for a, b in zip(zs, zs[1:]) if b > a), default=0.2)

        # --- Pass 1: collect swap events with last-use context ---------------
        SwapDetail = dict
        swap_details: list[SwapDetail] = []
        loaded = dict(loaded_init)
        head_last_idx: dict[int, int] = {}  # phys → last layer idx used

        for i, layer in enumerate(layers):
            if layer.get("type") != "2":
                continue
            ext = int(layer.get("extruder", "0"))
            phys = ext_to_phys.get(ext)
            if phys is None:
                continue
            cur = loaded.get(phys)
            if cur != ext:
                from_colour = (
                    filament_colours[cur - 1]
                    if cur and cur <= len(filament_colours)
                    else ""
                )
                swap_details.append({
                    "first_needed_idx": i,
                    "last_use_idx": head_last_idx.get(phys, -1),
                    "phys": phys,
                    "from_slot": cur or ext,
                    "to_slot": ext,
                    "from_colour": from_colour,
                    "to_colour": layer.get("color", ""),
                })
                loaded[phys] = ext
            head_last_idx[phys] = i

        if not swap_details:
            continue

        # --- Pass 2: greedy batching -----------------------------------------
        # Merge into current batch while max(last_use) < min(first_needed).
        batches: list[list[SwapDetail]] = []
        current: list[SwapDetail] = []

        for sd in swap_details:
            if not current:
                current = [sd]
                continue
            mx = max(s["last_use_idx"] for s in current + [sd])
            mn = min(s["first_needed_idx"] for s in current + [sd])
            if mx < mn:
                current.append(sd)
            else:
                batches.append(current)
                current = [sd]
        batches.append(current)

        # --- Pass 3: build XML insertions ------------------------------------
        all_children = list(plate)
        to_insert: list[tuple[int, str, list[SwapDetail]]] = []

        for batch in batches:
            # Insert the pause exactly one layer before the first colour that
            # needs a fresh spool.  This lands on a distinct Orca layer from
            # both the preceding tool-change and the incoming colour-change.
            min_first = min(s["first_needed_idx"] for s in batch)
            first_needed = layers[min_first]
            first_z = float(first_needed.get("top_z", "0"))
            pause_z = f"{max(layer_height, first_z - layer_height):g}"
            after_idx = all_children.index(first_needed)

            to_insert.append((after_idx, pause_z, batch))
            for sd in batch:
                instructions.append(SwapInstruction(
                    z=float(pause_z),
                    toolhead=sd["phys"] + 1,
                    from_slot=sd["from_slot"],
                    to_slot=sd["to_slot"],
                    from_colour=sd["from_colour"],
                    to_colour=sd["to_colour"],
                    label=f"T{sd['phys'] + 1}: {sd['from_colour'] or '?'} → {sd['to_colour'] or '?'}",
                ))

        # Insert in reverse order so earlier indices stay valid.
        for after_idx, pause_z, _ in sorted(to_insert, key=lambda x: x[0], reverse=True):
            pause = ET.Element("layer")
            pause.set("top_z", pause_z)
            pause.set("type", "1")
            pause.set("extruder", "1")
            pause.set("color", "")
            pause.set("extra", "")
            pause.set("gcode", pause_gcode)
            plate.insert(after_idx, pause)
            all_children = list(plate)

    xml_out = '<?xml version="1.0" encoding="utf-8"?>\n' + ET.tostring(
        root, encoding="unicode"
    )
    return xml_out, instructions
