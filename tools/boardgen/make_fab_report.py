"""Manufacturing report: everything a PCB fab's order form or price calculator will ask, in one file.

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/boardgen/make_fab_report.py <project-id>

Writes projects/<id>/MANUFACTURING.md. Every number is MEASURED from the real .kicad_pcb (and the drill
file actually sent to the fab), never restated from a README - a report that copies numbers goes stale
the first time the board changes, which is exactly when someone orders it.

Covers: size (mm and cm, as calculators ask), layer count and whether the board could be single-sided,
the stackup (thickness, copper weight, mask/silk colour), every copper layer's contents, all holes by
size and plating (cross-checked against the .drl file), vias, slots, annular rings, the tightest
geometry against typical fab limits, components (THT/SMD, sides, solder joints, BOM), DRC status, and
the order-form answers.
"""
import collections
import json
import os
import re
import subprocess
import sys
import tempfile
import time

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen.project import PROJECTS  # noqa: E402
from boardgen.kicad_paths import CLI as KICAD_CLI  # noqa: E402

NM = 1e6  # pcbnew internal units are nanometres


def mm(v):
    return v / NM


def f2(v):
    return ("%.2f" % v).rstrip("0").rstrip(".")


def f3(v):
    """For limits - 0.127 must not print as 0.13, that reads as 'passes by a hair'."""
    return ("%.3f" % v).rstrip("0").rstrip(".")


# Typical JLCPCB standard-service limits (2-layer, 1 oz). They change - the report says to confirm.
FAB_LIMITS = {
    "track": 0.127, "clearance": 0.127, "pth_drill": 0.3, "npth_drill": 0.5, "max_drill": 6.3,
    "via_drill": 0.3, "annular": 0.13, "hole_to_hole": 0.5, "edge_clearance": 0.3,
    "silk_text": 1.0, "silk_line": 0.153,
}


def find_pcb(project):
    base = os.path.join(PROJECTS, project)
    preferred = os.path.join(base, project + ".kicad_pcb")
    if os.path.isfile(preferred):
        return preferred
    hits = sorted(f for f in os.listdir(base) if f.endswith(".kicad_pcb")
                  and "-routed" not in f and "-backup" not in f)
    if not hits:
        raise SystemExit("no .kicad_pcb in %s" % base)
    return os.path.join(base, hits[0])


def read_stackup(pcb_path):
    """The stackup isn't reachable through the SWIG API in KiCad 10 (GetStackupDescriptor returns an
    opaque SwigPyObject), so read the (stackup ...) block from the file. None = not defined, i.e.
    KiCad's defaults apply."""
    text = open(pcb_path, encoding="utf-8").read()
    start = text.find("(stackup")
    if start < 0:
        return None
    depth, i = 0, start
    while True:
        if text[i] == "(":
            depth += 1
        elif text[i] == ")":
            depth -= 1
            if depth == 0:
                break
        i += 1
    block = text[start:i]
    layers = []
    for m in re.finditer(r'\(layer "([^"]+)"(.*?)\n\t\t\t\)', block, re.S):
        body = m.group(2)
        get = lambda k: (re.search(r'\(%s "?([^")]+)"?\)' % k, body) or [None, None])[1]  # noqa: E731
        layers.append({"name": m.group(1), "type": get("type"), "thickness": get("thickness"),
                       "material": get("material"), "color": get("color")})
    finish = re.search(r'\(copper_finish "([^"]+)"\)', block)
    return {"layers": layers, "finish": finish.group(1) if finish else None,
            "castellated": "(castellated_pads yes)" in block, "edge_plating": "(edge_plating yes)" in block}


def read_drill_files(fab_dir):
    """Hole counts from the Excellon file(s) the fab will actually drill - the ground truth."""
    out = []
    gerbers = os.path.join(fab_dir, "gerbers")
    if not os.path.isdir(gerbers):
        return out
    for name in sorted(os.listdir(gerbers)):
        if not name.endswith(".drl"):
            continue
        tools, counts, slots, kind, current = {}, collections.Counter(), collections.Counter(), {}, None
        pending = None
        for line in open(os.path.join(gerbers, name), encoding="utf-8", errors="replace"):
            line = line.strip()
            m = re.match(r"; #@! TA\.AperFunction,(\w+),(\w+)", line)
            if m:
                pending = m.group(1)            # Plated / NonPlated
                continue
            m = re.match(r"^T(\d+)C([\d.]+)", line)
            if m:
                tools[m.group(1)] = float(m.group(2))
                kind[m.group(1)] = pending or "?"
                continue
            m = re.match(r"^T(\d+)$", line)
            if m:
                current = m.group(1)
                continue
            if current and line.startswith(("X", "Y")):
                if "G85" in line or line.startswith("G00"):
                    slots[current] += 1
                else:
                    counts[current] += 1
            elif current and line.startswith("G00"):
                slots[current] += 1
        rows = [{"tool": t, "dia": tools[t], "plating": kind[t], "holes": counts[t], "slots": slots[t]}
                for t in sorted(tools, key=lambda t: tools[t])]
        out.append({"file": name, "rows": rows})
    return out


def run_drc(pcb_path, has_sch):
    report = os.path.join(tempfile.gettempdir(), "fab_report_drc.json")
    cmd = [KICAD_CLI, "pcb", "drc", "--format", "json", "-o", report]
    if has_sch:
        cmd.append("--schematic-parity")
    subprocess.run(cmd + [pcb_path], capture_output=True, timeout=600)
    if not os.path.isfile(report):
        return None
    data = json.load(open(report, encoding="utf-8"))
    os.remove(report)
    res = {}
    for group in ("violations", "unconnected_items", "schematic_parity"):
        c = collections.Counter(i.get("severity", "?") for i in data.get(group, []) or [])
        res[group] = dict(c)
    return res


def outline_info(board):
    poly = pcbnew.SHAPE_POLY_SET()
    # False = don't invent an outline from the copper if Edge.Cuts is broken - report it instead
    closed = board.GetBoardPolygonOutlines(poly, False)
    bbox = poly.BBox()
    shapes = [d for d in board.GetDrawings() if d.GetLayer() == pcbnew.Edge_Cuts]
    kinds = collections.Counter(d.ShowShape() for d in shapes)
    perimeter = sum(mm(d.GetLength()) for d in shapes if hasattr(d, "GetLength"))
    holes = sum(poly.HoleCount(i) for i in range(poly.OutlineCount()))
    is_rect = (poly.OutlineCount() == 1 and holes == 0
               and abs(poly.Area() - bbox.GetWidth() * bbox.GetHeight()) < 1e-3 * poly.Area())
    return {"w": mm(bbox.GetWidth()), "h": mm(bbox.GetHeight()), "area": poly.Area() / NM ** 2,
            "outlines": poly.OutlineCount(), "cutouts": holes, "closed": bool(closed),
            "perimeter": perimeter, "shapes": dict(kinds), "rect": is_rect}


def pad_size(pad, layer):
    try:
        return pad.GetSize(layer)
    except TypeError:
        return pad.GetSize()


def collect(board):
    fps = list(board.GetFootprints())
    copper = [board.GetLayerName(l) for l in board.GetEnabledLayers().CuStack()]
    layer_items = {name: {"tracks": 0, "length": 0.0, "widths": set(), "zones": 0, "zone_area": 0.0,
                          "pads": 0} for name in copper}
    tracks, vias = [], []
    holes = []                                # (x, y, radius, what) of every drilled hole, in mm
    for t in board.GetTracks():
        if isinstance(t, pcbnew.PCB_VIA):
            vias.append(t)
        else:
            tracks.append(t)
            li = layer_items.get(t.GetLayerName())
            if li is not None:
                li["tracks"] += 1
                li["length"] += mm(t.GetLength())
                li["widths"].add(round(mm(t.GetWidth()), 3))
    for z in board.Zones():
        for layer in z.GetLayerSet().Seq():
            li = layer_items.get(board.GetLayerName(layer))
            if li is not None:
                li["zones"] += 1
                li["zone_area"] += z.GetFilledArea() / NM ** 2 / max(1, len(z.GetLayerSet().Seq()))

    pads = {"PTH": 0, "NPTH": 0, "SMD": 0, "other": 0}
    drills = collections.Counter()           # (dia, plated, shape) -> count
    min_annular, slots = None, 0
    parts = []
    for fp in fps:
        attrs = fp.GetAttributes()
        fp_pads = list(fp.Pads())
        for p in fp_pads:
            a = p.GetAttribute()
            key = {pcbnew.PAD_ATTRIB_PTH: "PTH", pcbnew.PAD_ATTRIB_NPTH: "NPTH",
                   pcbnew.PAD_ATTRIB_SMD: "SMD"}.get(a, "other")
            pads[key] += 1
            for layer in p.GetLayerSet().CuStack():
                name = board.GetLayerName(layer)
                if name in layer_items:
                    layer_items[name]["pads"] += 1
            if a in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH):
                d = p.GetDrillSize()
                pos = p.GetPosition()
                holes.append((mm(pos.x), mm(pos.y), mm(max(d.x, d.y)) / 2, ("%s pad %s" % (fp.GetReference(), p.GetNumber())) if p.GetNumber() else "%s hole" % fp.GetReference()))
                oblong = p.GetDrillShape() == pcbnew.PAD_DRILL_SHAPE_OBLONG and d.x != d.y
                slots += oblong
                label = "%sx%s" % (f2(mm(d.x)), f2(mm(d.y))) if oblong else f2(mm(d.x))
                drills[(label, key, "slot" if oblong else "round")] += 1
                if a == pcbnew.PAD_ATTRIB_PTH:
                    s = pad_size(p, pcbnew.F_Cu)
                    ring = (min(s.x, s.y) - max(d.x, d.y)) / 2
                    min_annular = ring if min_annular is None else min(min_annular, ring)
        kind = ("mechanical" if not any(p.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_SMD)
                                        for p in fp_pads)
                else "THT" if attrs & pcbnew.FP_THROUGH_HOLE else "SMD" if attrs & pcbnew.FP_SMD else "other")
        parts.append({"ref": fp.GetReference(), "value": fp.GetValue(), "kind": kind,
                      "side": "bottom" if fp.IsFlipped() else "top",
                      "footprint": str(fp.GetFPID().GetLibItemName()),
                      "joints": sum(1 for p in fp_pads if p.GetAttribute() in
                                    (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_SMD)),
                      "bom": not (attrs & pcbnew.FP_EXCLUDE_FROM_BOM) and kind != "mechanical",
                      "dnp": fp.IsDNP()})
    via_sizes = collections.Counter((f2(mm(v.GetDrillValue())), f2(mm(v.GetWidth(pcbnew.F_Cu)))) for v in vias)
    for v in vias:
        pos = v.GetPosition()
        holes.append((mm(pos.x), mm(pos.y), mm(v.GetDrillValue()) / 2, "via on %s" % (v.GetNetname() or "no net")))
        ring = (v.GetWidth(pcbnew.F_Cu) - v.GetDrillValue()) / 2
        min_annular = ring if min_annular is None else min(min_annular, ring)

    silk_text, silk_line = [], []
    silk_layers = (pcbnew.F_SilkS, pcbnew.B_SilkS)
    items = list(board.GetDrawings())
    for fp in fps:
        items += [fp.Reference(), fp.Value()] + list(fp.GraphicalItems())
    for it in items:
        if it.GetLayer() not in silk_layers:
            continue
        if isinstance(it, pcbnew.PCB_TEXT) or it.GetClass() in ("PCB_TEXT", "PCB_FIELD"):
            if getattr(it, "IsVisible", lambda: True)():
                silk_text.append(mm(it.GetTextHeight()))
        elif it.GetClass() == "PCB_SHAPE":
            silk_line.append(mm(it.GetWidth()))
    return {"copper": copper, "layers": layer_items, "tracks": tracks, "vias": via_sizes,
            "via_count": len(vias), "pads": pads, "drills": drills, "slots": slots,
            "min_annular": mm(min_annular) if min_annular is not None else None,
            "parts": parts, "silk_text": silk_text, "silk_line": silk_line,
            "nets": board.GetNetCount() - 1, "hole_gap": min_hole_gap(holes)[0],
            "hole_gap_where": min_hole_gap(holes)[1],
            "silk_bottom": any(it.GetLayer() == pcbnew.B_SilkS for it in items)}


def min_hole_gap(holes):
    """Closest edge-to-edge distance between any two drilled holes - measured, not the DRC rule.
    Sorted sweep on x so a board with ~1000 holes stays fast."""
    best, pair = None, None
    pts = sorted(holes)
    for i, (x1, y1, r1, a) in enumerate(pts):
        for x2, y2, r2, b in pts[i + 1:]:
            if best is not None and x2 - x1 - r1 - r2 > best:
                break
            gap = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5 - r1 - r2
            if gap > -1e-6 and (best is None or gap < best):   # skip a hole paired with itself
                best, pair = gap, "%s (%.2f, %.2f) and %s (%.2f, %.2f)" % (a, x1, y1, b, x2, y2)
    return best, pair


def verdict(value, limit, higher_is_better=True):
    if value is None:
        return "-"
    ok = value >= limit - 1e-6 if higher_is_better else value <= limit + 1e-6
    return "OK" if ok else "**CHECK**"


def build(project):
    pcb_path = find_pcb(project)
    pdir = os.path.dirname(pcb_path)
    try:
        board = pcbnew.LoadBoard(pcb_path)
    except Exception as e:
        raise SystemExit("FAILED: cannot read board %s: %s" % (pcb_path, e))
    if board is None:
        raise SystemExit("FAILED: cannot read board %s" % pcb_path)
    ds = board.GetDesignSettings()
    nc = ds.m_NetSettings.GetDefaultNetclass()
    stack = read_stackup(pcb_path)
    o = outline_info(board)
    c = collect(board)
    fab_dir = os.path.join(pdir, "out", "fab")
    drl = read_drill_files(fab_dir)
    has_sch = os.path.isfile(os.path.splitext(pcb_path)[0] + ".kicad_sch")
    drc = run_drc(pcb_path, has_sch)

    n_cu = board.GetCopperLayerCount()
    used_cu = [n for n, li in c["layers"].items() if li["tracks"] or li["zones"]]
    thickness = mm(ds.GetBoardThickness())
    cu_um = {}
    mask_color = silk_color = material = None
    if stack:
        for l in stack["layers"]:
            if l["type"] == "copper" and l["thickness"]:
                cu_um[l["name"]] = float(l["thickness"]) * 1000
            if "Mask" in (l["type"] or "") and l["color"]:
                mask_color = l["color"]
            if "Silk" in (l["type"] or "") and l["color"]:
                silk_color = l["color"]
            material = material or l["material"]
    oz = lambda um: "%s oz" % f2(um / 35.0)  # noqa: E731  35 um = 1 oz
    outer_um = cu_um.get("F.Cu", 35.0)
    real_parts = [p for p in c["parts"] if p["kind"] != "mechanical"]
    smd = [p for p in real_parts if p["kind"] == "SMD"]
    tht = [p for p in real_parts if p["kind"] == "THT"]
    bottom = [p for p in real_parts if p["side"] == "bottom"]
    mech = [p for p in c["parts"] if p["kind"] == "mechanical"]
    total_holes = sum(c["drills"].values()) + c["via_count"]
    single_ok = len(used_cu) <= 1 and not smd and c["via_count"] == 0

    min_track = min((mm(t.GetWidth()) for t in c["tracks"]), default=None)
    min_drill = min([float(k[0].split("x")[0]) for k in c["drills"]] +
                    [float(k[0]) for k in c["vias"]], default=None)
    max_drill = max([float(k[0].split("x")[0]) for k in c["drills"]], default=None)
    min_npth = min([float(k[0].split("x")[0]) for k in c["drills"] if k[1] == "NPTH"], default=None)
    min_via = min([float(k[0]) for k in c["vias"]], default=None)
    min_silk = min(c["silk_text"], default=None)
    min_silk_line = min(c["silk_line"], default=None)
    clearance = mm(nc.GetClearance())

    L = []
    w = L.append
    w("# %s - manufacturing details" % project)
    w("")
    w("_Generated %s by `tools/boardgen/make_fab_report.py` from `%s` - measured from the real board and "
      "drill file, not copied from other docs. Regenerate after any board change: "
      "`python pipeline.py %s --only fabreport`._" % (time.strftime("%Y-%m-%d %H:%M"),
                                                     os.path.basename(pcb_path), project))
    w("")
    w("## Quick answers (what a PCB price calculator asks)")
    w("")
    w("| Question | Answer |")
    w("|---|---|")
    w("| Width | **%s cm** (%s mm) |" % (f2(o["w"] / 10), f2(o["w"])))
    w("| Height | **%s cm** (%s mm) |" % (f2(o["h"] / 10), f2(o["h"])))
    w("| Layers | **%d** (copper on: %s) |" % (n_cu, ", ".join(used_cu) or "none"))
    w("| Can it be made single-sided (one layer)? | %s |" % (
        "**Yes** - all copper is on one layer, no vias, no SMD" if single_ok else
        "**No** - it has %s. A one-layer fab can't make it without a redesign." % ", ".join(
            x for x in ["copper on %d layers" % len(used_cu) if len(used_cu) > 1 else "",
                        "%d vias" % c["via_count"] if c["via_count"] else "",
                        "%d SMD parts" % len(smd) if smd else ""] if x)))
    w("| Solder mask | **Yes, both sides** (%s) |" % (mask_color or "colour not set in design - green is the cheap default"))
    w("| Silkscreen | Yes, top%s (%s) |" % (" and bottom" if c["silk_bottom"] else " only",
                                            silk_color or "white"))
    w("| Board thickness | %s mm |" % f2(thickness))
    w("| Copper weight | %s (%s um outer) |" % (oz(outer_um), f2(outer_um)))
    w("| Surface finish | %s |" % (stack["finish"] if stack and stack["finish"] else
      "not set in design - **HASL lead-free** is the cheap default and fine for hand soldering"))
    w("| Material | %s |" % (material or "FR-4 (KiCad default)"))
    w("| Board area | %s cm² (outline %s) |" % (f2(o["area"] / 100), "rectangle" if o["rect"] else "custom shape"))
    w("| Total holes to drill | %d (%d component/mounting + %d vias) |" % (
        total_holes, sum(c["drills"].values()), c["via_count"]))
    w("| Components | %d (%d through-hole, %d SMD) + %d mechanical (mounting holes etc.) |" % (
        len(real_parts), len(tht), len(smd), len(mech)))
    w("| Assembly needed from the fab? | %s |" % (
        "No - all through-hole, hand solderable" if not smd else
        "Optional - %d SMD parts could be assembled by the fab (BOM + CPL in out/fab)" % len(smd)))
    w("")

    w("## Board outline")
    w("")
    w("| | |")
    w("|---|---|")
    w("| Size | %s x %s mm |" % (f2(o["w"]), f2(o["h"])))
    w("| Area | %s mm² |" % f2(o["area"]))
    w("| Shape | %s, drawn with %s |" % ("rectangle" if o["rect"] else "custom outline", ", ".join(
        "%d %s%s" % (n, k.lower(), "" if n == 1 else "s") for k, n in o["shapes"].items())))
    w("| Perimeter (routing length) | %s mm |" % f2(o["perimeter"]))
    w("| Separate boards / internal cut-outs | %d / %d |" % (o["outlines"], o["cutouts"]))
    w("| Outline closed | %s |" % ("yes" if o["closed"] and o["outlines"] else "**NO - the fab will reject it**"))
    w("")

    w("## Layers (size and thickness of each)")
    w("")
    w("Every layer covers the full board outline (%s x %s mm)." % (f2(o["w"]), f2(o["h"])))
    w("")
    if stack:
        w("Stackup as defined in the design:")
        w("")
        w("| Layer | Type | Thickness | Material / colour |")
        w("|---|---|---|---|")
        for l in stack["layers"]:
            t = l["thickness"]
            w("| %s | %s | %s | %s |" % (l["name"], l["type"] or "", ("%s mm" % t) if t else "-",
                                          l["material"] or l["color"] or "-"))
    else:
        w("No stackup is defined in the design, so KiCad's standard %s-layer build applies:" % n_cu)
        w("")
        w("| Layer | Type | Thickness |")
        w("|---|---|---|")
        w("| F.Silkscreen | top legend | - |")
        w("| F.Mask | top solder mask | ~0.01 mm |")
        w("| F.Cu | copper | 0.035 mm (1 oz) |")
        core = thickness - 0.035 * n_cu - 0.02
        if n_cu == 2:
            w("| core | FR-4 dielectric | %s mm |" % f2(core))
        else:
            w("| inner layers + prepreg/core | FR-4 + %d copper layers | ~%s mm total |" % (n_cu - 2, f2(core)))
        w("| B.Cu | copper | 0.035 mm (1 oz) |")
        w("| B.Mask | bottom solder mask | ~0.01 mm |")
        w("| B.Silkscreen | bottom legend | - |")
        w("| **Total** | | **%s mm** |" % f2(thickness))
    w("")
    w("What is on each copper layer:")
    w("")
    w("| Copper layer | Tracks | Track length | Track widths used | Pour zones | Poured area | Pads |")
    w("|---|---|---|---|---|---|---|")
    for name in c["copper"]:
        li = c["layers"][name]
        w("| %s | %d | %s mm | %s | %d | %s mm² (%s%% of board) | %d |" % (
            name, li["tracks"], f2(li["length"]),
            ", ".join("%s mm" % f2(x) for x in sorted(li["widths"])) or "-", li["zones"],
            f2(li["zone_area"]), f2(100 * li["zone_area"] / o["area"]) if o["area"] else "0", li["pads"]))
    w("")
    w("Silkscreen: %d text items (smallest %s mm high), %d lines/shapes (thinnest %s mm)." % (
        len(c["silk_text"]), f2(min_silk) if min_silk else "-", len(c["silk_line"]),
        f2(min_silk_line) if min_silk_line else "-"))
    w("")

    w("## Holes")
    w("")
    w("From the design (%d holes in total):" % total_holes)
    w("")
    w("| Diameter (mm) | Plated? | Shape | Count |")
    w("|---|---|---|---|")
    for (dia, plating, shape), n in sorted(c["drills"].items(), key=lambda kv: float(kv[0][0].split("x")[0])):
        w("| %s | %s | %s | %d |" % (dia, "yes (PTH)" if plating == "PTH" else "no (NPTH)", shape, n))
    for (drill, dia), n in sorted(c["vias"].items()):
        w("| %s | yes (via, %s mm pad) | round | %d |" % (drill, dia, n))
    w("")
    w("- Plated pads: %d through-hole, %d SMD; non-plated holes: %d; slots: %d" % (
        c["pads"]["PTH"], c["pads"]["SMD"], c["pads"]["NPTH"], c["slots"]))
    w("- Smallest hole %s mm, largest %s mm" % (f2(min_drill) if min_drill else "-",
                                                  f2(max_drill) if max_drill else "-"))
    if drl:
        for d in drl:
            drl_total = sum(r["holes"] + r["slots"] for r in d["rows"])
            match = "matches the design" if drl_total == total_holes else \
                "**does NOT match the design (%d) - regenerate the fab files**" % total_holes
            w("")
            w("Cross-check against the drill file the fab receives, `out/fab/gerbers/%s`: **%d holes**, %s." % (
                d["file"], drl_total, match))
            w("")
            w("| Tool | Diameter (mm) | Plating | Holes | Slots |")
            w("|---|---|---|---|---|")
            for r in d["rows"]:
                w("| T%s | %s | %s | %d | %d |" % (r["tool"], f2(r["dia"]), r["plating"], r["holes"], r["slots"]))
    else:
        w("")
        w("No drill file in `out/fab/gerbers` yet - run `python pipeline.py %s --only outputs`." % project)
    w("")

    w("## Tightest geometry vs. typical fab limits")
    w("")
    w("Limits are typical JLCPCB standard 2-layer values - confirm on the fab's capabilities page before ordering.")
    w("")
    w("| Item | This board | Typical limit | |")
    w("|---|---|---|---|")
    rows = [
        ("Thinnest track", min_track, FAB_LIMITS["track"], True),
        ("Copper clearance (DRC rule, enforced)", clearance, FAB_LIMITS["clearance"], True),
        ("Smallest plated hole", min([float(k[0].split("x")[0]) for k in c["drills"] if k[1] == "PTH"] + ([min_via] if min_via else []), default=None), FAB_LIMITS["pth_drill"], True),
        ("Smallest non-plated hole", min_npth, FAB_LIMITS["npth_drill"], True),
        ("Largest hole", max_drill, FAB_LIMITS["max_drill"], False),
        ("Smallest via drill", min_via, FAB_LIMITS["via_drill"], True),
        ("Smallest annular ring", c["min_annular"], FAB_LIMITS["annular"], True),
        ("Closest two holes (edge to edge, measured)", c["hole_gap"], FAB_LIMITS["hole_to_hole"], True),
        ("Copper to board edge (DRC rule)", mm(ds.m_CopperEdgeClearance), FAB_LIMITS["edge_clearance"], True),
        ("Smallest silkscreen text", min_silk, FAB_LIMITS["silk_text"], True),
        ("Thinnest silkscreen line", min_silk_line, FAB_LIMITS["silk_line"], True),
    ]
    for label, value, limit, hib in rows:
        w("| %s | %s | %s %s mm | %s |" % (label, ("%s mm" % f3(value)) if value is not None else "-",
                                            ">=" if hib else "<=", f3(limit), verdict(value, limit, hib)))
    w("")
    if c["hole_gap_where"]:
        w("Closest two holes: %s." % c["hole_gap_where"])
        w("")
    w("How to read a **CHECK**: a copper or hole row is a real risk - fix it or ask the fab. A *silkscreen* "
      "row is cosmetic: the fab still prints it, just fainter or blurrier (KiCad's own footprint outlines are "
      "0.12 mm, so nearly every KiCad board shows that one). A *DRC rule* row only means the rule would allow "
      "something tighter than the fab; the measured rows show what the board really uses.")
    w("")

    w("## Components")
    w("")
    w("| | Count |")
    w("|---|---|")
    w("| Parts to place | %d |" % len(real_parts))
    w("| Through-hole / SMD | %d / %d |" % (len(tht), len(smd)))
    w("| On top / on bottom | %d / %d |" % (len(real_parts) - len(bottom), len(bottom)))
    w("| Mechanical (mounting holes, logos) | %d |" % len(mech))
    w("| Solder joints | %d |" % sum(p["joints"] for p in real_parts))
    w("| Unique part types (BOM lines) | %d |" % len({(p["value"], p["footprint"]) for p in real_parts if p["bom"]}))
    w("| Do-not-populate | %d |" % sum(p["dnp"] for p in real_parts))
    w("| Nets | %d |" % c["nets"])
    w("")
    w("| Qty | Value | Footprint | Type | Side | References |")
    w("|---|---|---|---|---|---|")
    groups = collections.defaultdict(list)
    for p in real_parts:
        groups[(p["value"], p["footprint"], p["kind"], p["side"])].append(p["ref"])

    def natural(ref):
        m = re.match(r"([A-Za-z]+)(\d+)", ref)
        return (m.group(1), int(m.group(2))) if m else (ref, 0)
    for (value, fpn, kind, side), refs in sorted(groups.items(), key=lambda kv: natural(sorted(kv[1], key=natural)[0])):
        refs = sorted(refs, key=natural)
        w("| %d | %s | %s | %s | %s | %s |" % (len(refs), value, fpn, kind, side, ", ".join(refs)))
    if mech:
        w("")
        w("Mechanical: %s." % ", ".join("%s (%s)" % (p["ref"], p["footprint"])
                                        for p in sorted(mech, key=lambda p: natural(p["ref"]))))
    w("")

    w("## Design check status")
    w("")
    if drc:
        errors = sum(v for k, v in drc["violations"].items() if k == "error")
        warns = sum(v for k, v in drc["violations"].items() if k != "error")
        w("| Check | Result |")
        w("|---|---|")
        w("| DRC errors | %s |" % ("**0**" if errors == 0 else "**%d - fix before ordering**" % errors))
        w("| DRC warnings | %d |" % warns)
        w("| Unconnected items | %d |" % sum(drc["unconnected_items"].values()))
        if has_sch:
            w("| Schematic vs board differences | %d |" % sum(drc["schematic_parity"].values()))
    else:
        w("DRC could not be run (kicad-cli produced no report).")
    w("")

    w("## Order form (JLCPCB-style) - suggested answers")
    w("")
    w("| Field | Answer |")
    w("|---|---|")
    for field, ans in [
        ("Base material", material or "FR-4"),
        ("Layers", str(n_cu)),
        ("Dimensions", "%s x %s mm" % (f2(o["w"]), f2(o["h"]))),
        ("PCB quantity", "your choice (5 is the usual minimum)"),
        ("Different designs", "1"),
        ("Delivery format", "single PCB"),
        ("PCB thickness", "%s mm" % f2(thickness)),
        ("PCB colour", mask_color or "Green (cheapest, fastest)"),
        ("Silkscreen", silk_color or "White"),
        ("Surface finish", (stack and stack["finish"]) or "HASL (with lead) or LeadFree HASL"),
        ("Outer copper weight", oz(outer_um)),
        ("Via covering", "Tented" if c["via_count"] else "n/a (no vias)"),
        ("Min via hole size / diameter", ("%s / %s mm" % sorted(c["vias"])[0]) if c["vias"] else "n/a"),
        ("Board outline tolerance", "±0.2 mm (regular)"),
        ("Castellated holes", "Yes" if stack and stack["castellated"] else "No"),
        ("Edge plating", "Yes" if stack and stack["edge_plating"] else "No"),
        ("Gold fingers", "No"),
        ("Impedance control", "No"),
        ("Remove order number", "No = fab prints a small order code somewhere; 'Specify a location' = add the text JLCJLCJLCJLC to the silkscreen where you want it; Yes = extra cost"),
        ("PCB assembly", "No - all through-hole, solder yourself" if not smd else "optional - %d SMD parts" % len(smd)),
    ]:
        w("| %s | %s |" % (field, ans))
    w("")

    w("## Files to send")
    w("")
    if os.path.isdir(fab_dir):
        w("| File | Size | Use |")
        w("|---|---|---|")
        use = {".zip": "**upload this** - gerbers + drill", "BOM": "assembly only", "CPL": "assembly only",
               "positions": "raw placement data (not needed for bare boards)"}
        for name in sorted(os.listdir(fab_dir)):
            full = os.path.join(fab_dir, name)
            if os.path.isfile(full):
                purpose = next((v for k, v in use.items() if k in name), "")
                w("| `out/fab/%s` | %s KB | %s |" % (name, f2(os.path.getsize(full) / 1024), purpose))
    else:
        w("No `out/fab` yet - run `python pipeline.py %s --only outputs`." % project)
    w("")
    out = os.path.join(pdir, "MANUFACTURING.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("wrote %s" % out)
    print("  %s x %s mm, %d layers, %d holes (%d vias), %d parts (%d THT / %d SMD), DRC errors: %s" % (
        f2(o["w"]), f2(o["h"]), n_cu, total_holes, c["via_count"], len(real_parts), len(tht), len(smd),
        sum(v for k, v in drc["violations"].items() if k == "error") if drc else "?"))
    for d in drl:
        drl_total = sum(r["holes"] + r["slots"] for r in d["rows"])
        print("  drill file %s: %d holes (%s)" % (d["file"], drl_total,
                                                  "matches" if drl_total == total_holes else "MISMATCH"))
    return [d["file"] for d in drl
            if sum(r["holes"] + r["slots"] for r in d["rows"]) != total_holes]


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_fab_report.py <project-id>")
    bad = build(sys.argv[1])
    if bad:
        raise SystemExit("FAILED: drill hole count disagrees with the design in %s "
                         "(see MANUFACTURING.md)" % ", ".join(bad))
