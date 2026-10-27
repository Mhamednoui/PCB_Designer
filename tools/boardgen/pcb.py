"""Shared core of every project's `gen/make_pcb.py` (place / route / finish / check / render).

Before this existed each project carried its own ~700-line copy, 19 of 25 functions byte-identical and
the rest drifting apart (docs/LESSONS_LEARNED.md section 13). A project's make_pcb.py is now only its
board-specific data - `placements()`, board size, mounting holes, silkscreen text - plus optional hooks:

    import netlist as NL
    from boardgen import pcb
    pcb.main(NL, placements, OX=100.0, OY=50.0, BW=70.0, BH=45.0, MOUNTING_HOLES=[...], TEXTS=[...])

Run with KiCad's Python (it imports pcbnew):  python make_pcb.py place | route | finish | check | render
Board-local coordinates are mm, origin = top-left corner of the board, +Y down.

Hooks, all optional, all called with the live pcb module state already configured (use pcb.add_text,
pcb.add_track, pcb.add_zone, pcb.V ...):
    extra_silk(board)                 extra silkscreen text beyond TEXTS / SECTIONS
    extra_routes(board, P, net)       pre-routed tracks; P = placements, net(name) -> NETINFO_ITEM
    extra_pours(board, nets, inset)   extra zones; nets = {name: net} for the global nets on the board
    post_place_report(board)          debug output at the end of `place`

Caller requirements: the project's gen dir must already be first on sys.path (so `import netlist`
resolves to the project's own) and `tools/` must be on sys.path (so `boardgen` imports).
"""
import json
import math
import os
import subprocess
import sys

import pcbnew
from boardgen.kicad_paths import CLI  # one place for the KiCad location, see kicad_paths.py
from boardgen.make_sch import lib_symbol
from boardgen.sexp import find, find_all, symbol_pins

_TOOLS_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FREEROUTING = os.path.join(_TOOLS_ROOT, "tools", "freerouting", "freerouting", "freerouting.exe")

# Set by configure(). Module-level on purpose: V(), local(), add_text() ... are called from dozens of
# places and from project hooks, and all of them need the board origin.
NL = None
PCB = ROUTED = OUT = None
OX = OY = 0.0
BW = BH = 0.0
GLOBAL_NETS = ("+12V", "+5V", "+3V3", "GND")   # power-symbol nets; label nets get "/" like eeschema
MOUNTING_HOLES = []
SHOW_REF_PREFIX = ("U", "J", "D", "R", "C")
# Refs whose value/reference text must NOT be auto-placed at the pad centroid. That trick only makes
# sense for a small part; for something like a shield header whose pads span the whole board, the
# centroid is the middle of the board and the text lands on top of everything else.
SKIP_VALUE_SILK = ()
BOARD_OUTLINE = None   # list of (x1, y1, x2, y2) with y NEGATIVE (flipped at draw time); None = BW x BH rectangle
TEXTS = []             # (text, x, y, size)
SECTIONS = []          # (text, x, y, size)
_placements = None
_hooks = {}


def configure(nl, placements, OX, OY, BW, BH, MOUNTING_HOLES=(), SHOW_REF_PREFIX=("U", "J", "D", "R", "C"),
              SKIP_VALUE_SILK=(), BOARD_OUTLINE=None, TEXTS=(), SECTIONS=(), GLOBAL_NETS=None, **hooks):
    """Bind this module to one project. Called once by main()."""
    g = globals()
    unknown = set(hooks) - {"extra_silk", "extra_routes", "extra_pours", "post_place_report"}
    if unknown:
        raise TypeError("unknown pcb hook(s): %s" % sorted(unknown))
    g["NL"], g["_placements"], g["_hooks"] = nl, placements, hooks
    g["OX"], g["OY"], g["BW"], g["BH"] = OX, OY, BW, BH
    g["MOUNTING_HOLES"], g["SHOW_REF_PREFIX"] = list(MOUNTING_HOLES), tuple(SHOW_REF_PREFIX)
    g["SKIP_VALUE_SILK"], g["TEXTS"], g["SECTIONS"] = tuple(SKIP_VALUE_SILK), list(TEXTS), list(SECTIONS)
    if GLOBAL_NETS is not None:
        g["GLOBAL_NETS"] = tuple(GLOBAL_NETS)
    g["BOARD_OUTLINE"] = BOARD_OUTLINE if BOARD_OUTLINE is not None else [
        (0.0, 0.0, BW, 0.0), (BW, 0.0, BW, -BH), (BW, -BH, 0.0, -BH), (0.0, -BH, 0.0, 0.0)]
    g["PCB"] = os.path.join(nl.PRJ_DIR, nl.PRJ_NAME + ".kicad_pcb")
    # Routed board without pours. Deleting zones through the SWIG API corrupts the board object,
    # so routing works on this copy and `finish` writes the final PCB from it.
    g["ROUTED"] = os.path.join(nl.PRJ_DIR, nl.PRJ_NAME + "-routed.kicad_pcb")
    g["OUT"] = os.path.join(nl.PRJ_DIR, "out")
    os.makedirs(OUT, exist_ok=True)


def main(nl, placements, argv=None, **cfg):
    """Entry point for a project's make_pcb.py. `cfg` = configure() keywords and hooks."""
    configure(nl, placements, **cfg)
    argv = sys.argv if argv is None else argv
    stages = {"place": stage_place, "route": stage_route, "finish": stage_finish,
              "check": stage_check, "render": stage_render}
    stage = argv[1] if len(argv) > 1 else "place"
    if stage not in stages:
        raise SystemExit("unknown stage %r - use one of: %s" % (stage, " | ".join(stages)))
    stages[stage]()


def sync_routed_project():
    import shutil
    shutil.copyfile(os.path.join(NL.PRJ_DIR, NL.PRJ_NAME + ".kicad_pro"),
                    os.path.join(NL.PRJ_DIR, NL.PRJ_NAME + "-routed.kicad_pro"))


def pcb_net_name(name):
    return name if name in GLOBAL_NETS else "/" + name


def V(x, y):
    return pcbnew.VECTOR2I(pcbnew.FromMM(x + OX), pcbnew.FromMM(y + OY))


def mm(v):
    return pcbnew.FromMM(v)


def local(vec):
    return pcbnew.ToMM(vec.x) - OX, pcbnew.ToMM(vec.y) - OY


def load_fp(fpid):
    lib, name = fpid.split(":")
    base = os.path.join(NL.PRJ_DIR, "lib") if lib in NL.PROJECT_LIBS else NL.KICAD_FOOTPRINTS
    fp = pcbnew.FootprintLoad(os.path.join(base, lib + ".pretty"), name)
    if fp is None:
        raise RuntimeError("footprint not found: " + fpid)
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def set_field(fp, name, value):
    try:
        fp.SetField(name, value)
        f = fp.GetField(name) if hasattr(fp, "GetField") else fp.GetFieldByName(name)
        f.SetVisible(False)
        f.SetLayer(pcbnew.F_Fab)
        return True
    except Exception:
        pass
    try:
        f = pcbnew.PCB_FIELD(fp, 0, name)
        f.SetText(value)
        f.SetVisible(False)
        f.SetLayer(pcbnew.F_Fab)
        fp.Add(f)
        return True
    except Exception as e:  # pragma: no cover
        print("could not set field", name, e)
        return False


def add_text(board, s, x, y, size=1.0, layer=None, rot=0):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s)
    t.SetPosition(V(x, y))
    t.SetLayer(pcbnew.F_SilkS if layer is None else layer)
    t.SetTextSize(pcbnew.VECTOR2I(mm(size), mm(size)))
    t.SetTextThickness(mm(max(0.15, size * 0.16)))
    if rot:
        t.SetTextAngleDegrees(rot)
    board.Add(t)


def add_line(board, x1, y1, x2, y2, layer, width=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(x1, y1))
    s.SetEnd(V(x2, y2))
    s.SetLayer(layer)
    s.SetWidth(mm(width))
    board.Add(s)


def add_track(board, pts, width, net, layer=pcbnew.F_Cu):
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        t = pcbnew.PCB_TRACK(board)
        t.SetStart(V(x1, y1))
        t.SetEnd(V(x2, y2))
        t.SetWidth(mm(width))
        t.SetLayer(layer)
        t.SetNet(net)
        board.Add(t)


def add_zone(board, net, layer, pts, priority=0, clearance=0.25, rule_area=False):
    z = pcbnew.ZONE(board)
    z.SetLayer(layer)
    if rule_area:
        z.SetIsRuleArea(True)
        z.SetDoNotAllowZoneFills(True) if hasattr(z, "SetDoNotAllowZoneFills") else z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowVias(False)
        z.SetDoNotAllowTracks(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
    else:
        z.SetNet(net)
        z.SetAssignedPriority(priority)
        z.SetLocalClearance(mm(clearance))
        z.SetMinThickness(mm(0.2))
        z.SetThermalReliefGap(mm(0.4))
        z.SetThermalReliefSpokeWidth(mm(0.5))
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
        z.SetIslandRemovalMode(0)                       # 0 == always remove isolated islands
    ol = z.Outline()
    ol.NewOutline()
    for x, y in pts:
        ol.Append(mm(x + OX), mm(y + OY))
    board.Add(z)
    return z



# ── stages ─────────────────────────────────────────────────
def stage_place():
    board = pcbnew.NewBoard(PCB) if hasattr(pcbnew, "NewBoard") else pcbnew.BOARD()
    nets = {}

    def net(name):
        name = pcb_net_name(name)
        if name not in nets:
            ni = pcbnew.NETINFO_ITEM(board, name)
            board.Add(ni)
            nets[name] = ni
        return nets[name]

    for n in sorted(NL.nets()):
        net(n)

    P = _placements()
    missing = [p["ref"] for p in NL.PARTS if p["ref"] not in P]
    if missing:
        raise SystemExit("no placement for: %s" % missing)

    for p in NL.PARTS:
        fp = load_fp(p["footprint"])
        fp.SetReference(p["ref"])
        fp.SetValue(p["value"])
        x, y, rot = P[p["ref"]]
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        fp.SetPath(pcbnew.KIID_PATH("/" + NL.uid("sym", p["ref"])))
        for meth, val in (("SetSheetname", "/"), ("SetSheetfile", NL.PRJ_NAME + ".kicad_sch")):
            if hasattr(fp, meth):
                getattr(fp, meth)(val)
        if p["lcsc"]:
            set_field(fp, "LCSC", p["lcsc"])
        # print the value on the silkscreen, centred on the part, so the board can be
        # populated without the BOM in hand
        pads = [pad.GetPosition() for pad in fp.Pads()]
        # How far above/below the part centre the value and reference go. A fixed 2.2/2.6 mm works for
        # a flat axial part but lands INSIDE a tall one (the 10uF electrolytic on blinky-555 produced
        # 56 of 60 silk_overlap warnings on its own). Derive the offset from the footprint's real
        # courtyard instead, so it scales with the part.
        try:
            cyd = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
            half = max(cyd.GetHeight() // 2, mm(1.2))
        except Exception:
            half = mm(1.2)
        val_dy, ref_dy = half + mm(0.9), half + mm(1.3)
        if pads and p["ref"] not in SKIP_VALUE_SILK:
            cx = sum(q.x for q in pads) // len(pads)
            cy = sum(q.y for q in pads) // len(pads)
            val = fp.Value()
            val.SetVisible(True)
            val.SetLayer(pcbnew.F_SilkS)
            # 0.8 mm is KiCad's default DRC minimum text height; 0.7 violates it on every part.
            val.SetTextSize(pcbnew.VECTOR2I(mm(0.9), mm(0.9)))
            val.SetTextThickness(mm(0.12))
            val.SetPosition(pcbnew.VECTOR2I(cx, cy - val_dy))
            val.SetTextAngleDegrees(0)
        if not p["ref"].startswith(SHOW_REF_PREFIX):
            fp.Reference().SetVisible(False)
        else:
            ref_text = fp.Reference()
            ref_text.SetTextSize(pcbnew.VECTOR2I(mm(1.0), mm(1.0)))
            ref_text.SetTextThickness(mm(0.15))
            # Put the reference BELOW the part, since the value went above it. The footprint's own
            # default reference position also sits above the body, so leaving it there stacked the two
            # texts on top of each other ("R1" printed through "330R").
            if pads and p["ref"] not in SKIP_VALUE_SILK:
                ref_text.SetPosition(pcbnew.VECTOR2I(cx, cy + ref_dy))
                ref_text.SetTextAngleDegrees(0)
        pin_names = {pp["number"]: pp["name"] for pp in symbol_pins(lib_symbol(p["lib_id"]))}
        for pad in fp.Pads():
            num = pad.GetNumber()
            n = p["pins"].get(num)
            if n:
                pad.SetNet(net(n))
            elif num in pin_names:   # same name eeschema gives an unconnected pin
                nm = pin_names[num]
                show = nm and nm != "~" and nm != num
                nm = (nm or "").replace("/", "{slash}")
                nc = "unconnected-(%s-%sPad%s)" % (p["ref"], (nm + "-") if show else "", num)
                if nc not in nets:
                    ni = pcbnew.NETINFO_ITEM(board, nc)
                    board.Add(ni)
                    nets[nc] = ni
                pad.SetNet(nets[nc])
        board.Add(fp)

    for i, (x, y) in enumerate(MOUNTING_HOLES):
        fp = load_fp("MountingHole:MountingHole_3.2mm_M3")
        fp.SetReference("H%d" % (i + 1))
        fp.SetPosition(V(x, y))
        fp.SetBoardOnly(True)
        fp.SetExcludedFromBOM(True)
        fp.SetExcludedFromPosFiles(True)
        fp.Reference().SetVisible(False)
        board.Add(fp)

    # outline - BOARD_OUTLINE stores y negative and is flipped here (see configure())
    for (x1, y1, x2, y2) in BOARD_OUTLINE:
        add_line(board, x1, y1 + BH, x2, y2 + BH, pcbnew.Edge_Cuts, 0.1)

    # silkscreen: nothing may be smaller than 0.8 mm (KiCad's default DRC minimum text height)
    for s, x, y, size in TEXTS:
        add_text(board, s, x, y, size)
    for title, tx, ty, ts in SECTIONS:
        add_text(board, title, tx, ty, ts)
    if _hooks.get("extra_silk"):
        _hooks["extra_silk"](board)

    # Pre-routed links for pads the autorouter/pours cannot reach (docs/LESSONS_LEARNED.md lessons 22-23).
    if _hooks.get("extra_routes"):
        _hooks["extra_routes"](board, P, net)

    if _hooks.get("post_place_report"):
        _hooks["post_place_report"](board)

    pcbnew.SaveBoard(PCB, board)
    sync_routed_project()
    pcbnew.SaveBoard(ROUTED, board)
    print("placed %d footprints -> %s" % (len(board.GetFootprints()), PCB))


def _require_freerouting():
    if not os.path.isfile(FREEROUTING):
        raise SystemExit("Freerouting not found at %s - see README (the autorouter is expected "
                         "extracted at tools\\freerouting\\freerouting; installer: downloads\\freerouting-*.msi)"
                         % FREEROUTING)


def stage_route(passes=40):
    _require_freerouting()
    sync_routed_project()
    board = pcbnew.LoadBoard(ROUTED)       # no pours / stitching here; previous routes kept
    fanout_gnd(board)                      # GND vias first, so the router respects them
    pcbnew.SaveBoard(ROUTED, board)
    # Detach GND: every GND pad (+ its fan-out track/via) gets its own one-pad net, so the
    # router keeps clearance around it but never tries to route GND (the pours do that).
    tracks = list(board.GetTracks())
    n_dummy = 0
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != "GND":
                continue
            n_dummy += 1
            ni = pcbnew.NETINFO_ITEM(board, "GNDX_%d" % n_dummy)
            board.Add(ni)
            pad.SetNet(ni)
            for t in tracks:
                if t.Type() == pcbnew.PCB_VIA_T or t.GetNetname() != "GND" or not pad.HitTest(t.GetStart()):
                    continue
                t.SetNet(ni)
                for v in tracks:
                    if v.Type() == pcbnew.PCB_VIA_T and v.GetNetname() == "GND" \
                            and v.GetPosition().x == t.GetEnd().x and v.GetPosition().y == t.GetEnd().y:
                        v.SetNet(ni)
    dsn = os.path.join(OUT, "route.dsn")
    ses = os.path.join(OUT, "route.ses")
    if os.path.exists(ses):
        os.remove(ses)
    ok = pcbnew.ExportSpecctraDSN(board, dsn)
    print("DSN export:", ok, dsn)
    cmd = [FREEROUTING, "-de", dsn, "-do", ses, "-mp", str(passes), "--gui.enabled=false"]
    print("running:", " ".join(cmd))
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    tail = (r.stdout + r.stderr).strip().splitlines()[-25:]
    print("\n".join(tail))
    if not os.path.exists(ses):
        raise SystemExit("freerouting produced no session file")
    board = pcbnew.LoadBoard(ROUTED)       # reload with GND intact, then import routes
    for k in range(1, n_dummy + 1):
        board.Add(pcbnew.NETINFO_ITEM(board, "GNDX_%d" % k))
    ok = pcbnew.ImportSpecctraSES(board, ses)
    gnd = board.FindNet("GND")
    remapped = 0
    for t in board.GetTracks():
        if t.GetNetname().startswith("GNDX_"):
            t.SetNet(gnd)
            remapped += 1
    board.RemoveUnusedNets(None)
    left = [n for n in board.GetNetsByName().keys() if str(n).startswith("GNDX_")]
    print("SES import: %s, %d tracks/vias, %d restored to GND, leftover dummy nets: %d"
          % (ok, len(board.GetTracks()), remapped, len(left)))
    pcbnew.SaveBoard(ROUTED, board)
    strip_unused_dummy_nets()


def strip_unused_dummy_nets(path=None):
    import re
    path = path or ROUTED
    with open(path, encoding="utf-8") as f:
        text = f.read()
    decl = re.compile(r'^\s*\(net (?:\d+ )?"GNDX_\d+"\)\s*\n', re.M)
    n_decl = len(decl.findall(text))
    if n_decl and text.count('"GNDX_') == n_decl:
        with open(path, "w", encoding="utf-8") as f:
            f.write(decl.sub("", text))
        print("stripped %d unused dummy net declarations" % n_decl)
    elif n_decl:
        print("dummy nets still referenced: %d refs / %d decls" % (text.count('"GNDX_'), n_decl))


def _free(board, x, y, radius, net_code, ignore=()):
    """True if a disc at (x,y) keeps `radius` mm clearance from other-net copper."""
    c = V(x, y)
    r = mm(radius)
    if not (1.0 < x < BW - 1.0 and 1.0 < y < BH - 1.0):
        return False
    for t in board.GetTracks():
        if t.GetNetCode() == net_code:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            d = math.hypot(t.GetPosition().x - c.x, t.GetPosition().y - c.y) - t.GetWidth(pcbnew.F_Cu) / 2
        else:
            a, b = t.GetStart(), t.GetEnd()
            vx, vy = b.x - a.x, b.y - a.y
            L2 = vx * vx + vy * vy
            u = 0 if L2 == 0 else max(0, min(1, ((c.x - a.x) * vx + (c.y - a.y) * vy) / L2))
            d = math.hypot(a.x + u * vx - c.x, a.y + u * vy - c.y) - t.GetWidth() / 2
        if d < r:
            return False
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad in ignore or (pad.GetNetCode() == net_code and pad.GetNetCode() != 0):
                continue
            bb = pad.GetBoundingBox()
            dx = max(bb.GetLeft() - c.x, 0, c.x - bb.GetRight())
            dy = max(bb.GetTop() - c.y, 0, c.y - bb.GetBottom())
            if math.hypot(dx, dy) < r:
                return False
    return True


def _free_on(board, x, y, radius, net_code, layer, ignore=()):
    """Like _free, but only copper on `layer` counts (vias/THT pads always count)."""
    c = V(x, y)
    r = mm(radius)
    if not (1.0 < x < BW - 1.0 and 1.0 < y < BH - 1.0):
        return False
    for t in board.GetTracks():
        if t.GetNetCode() == net_code:
            continue
        if t.Type() == pcbnew.PCB_VIA_T:
            d = math.hypot(t.GetPosition().x - c.x, t.GetPosition().y - c.y) - t.GetWidth(pcbnew.F_Cu) / 2
        else:
            if t.GetLayer() != layer:
                continue
            a, b = t.GetStart(), t.GetEnd()
            vx, vy = b.x - a.x, b.y - a.y
            L2 = vx * vx + vy * vy
            u = 0 if L2 == 0 else max(0, min(1, ((c.x - a.x) * vx + (c.y - a.y) * vy) / L2))
            d = math.hypot(a.x + u * vx - c.x, a.y + u * vy - c.y) - t.GetWidth() / 2
        if d < r:
            return False
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad in ignore or (pad.GetNetCode() == net_code and pad.GetNetCode() != 0):
                continue
            if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD and not pad.IsOnLayer(layer):
                continue
            bb = pad.GetBoundingBox()
            dx = max(bb.GetLeft() - c.x, 0, c.x - bb.GetRight())
            dy = max(bb.GetTop() - c.y, 0, c.y - bb.GetBottom())
            if math.hypot(dx, dy) < r:
                return False
    return True


def connect_orphans(board, gnd):
    """Route a short escape track from any GND pad the pours failed to reach."""
    board.BuildConnectivity()
    conn = board.GetConnectivity()
    # Seed from whichever footprint has the most GND pads - that's the board's main ground anchor
    # (here the shield header). The Reflex Machine version hardcoded its power connector "J1", which
    # simply doesn't exist on other boards and raised StopIteration.
    gnd_pads = [pad for fp in board.GetFootprints() for pad in fp.Pads() if pad.GetNetname() == "GND"]
    if not gnd_pads:
        return 0
    by_fp = {}
    for pad in gnd_pads:
        by_fp.setdefault(pad.GetParentFootprint().GetReference(), []).append(pad)
    seed = max(by_fp.values(), key=len)[0]
    live = {i.m_Uuid.AsString() for i in conn.GetConnectedItems(seed)}
    both = (pcbnew.B_Cu, pcbnew.F_Cu)
    targets = [(local(t.GetPosition()), both) for t in board.GetTracks()
               if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "GND" and t.m_Uuid.AsString() in live]
    targets += [(local(pad.GetPosition()),
                 (pad.GetLayer(),) if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD else both)
                for fp in board.GetFootprints() for pad in fp.Pads()
                if pad.GetNetname() == "GND" and pad.m_Uuid.AsString() in live]
    orphans = [pad for fp in board.GetFootprints() for pad in fp.Pads()
               if pad.GetNetname() == "GND" and pad.m_Uuid.AsString() not in live]

    def clear_path(pts, layer, ignore):
        for (ax, ay), (bx, by) in zip(pts, pts[1:]):
            steps = max(2, int(math.hypot(bx - ax, by - ay) / 0.25))
            for i in range(steps + 1):
                if not _free_on(board, ax + (bx - ax) * i / steps, ay + (by - ay) * i / steps,
                                0.2 + 0.25, gnd.GetNetCode(), layer, ignore):
                    return False
        return True

    fixed, failed = 0, []
    for pad in orphans:
        px, py = local(pad.GetPosition())
        starts = [((px, py), (pad.GetLayer(),) if pad.GetAttribute() == pcbnew.PAD_ATTRIB_SMD else both)]
        for t in board.GetTracks():
            if t.Type() == pcbnew.PCB_VIA_T and t.GetNetname() == "GND" \
                    and math.hypot(*[a - b for a, b in zip(local(t.GetPosition()), (px, py))]) < 3.0:
                starts.append((local(t.GetPosition()), both))
        done = False
        for (sx, sy), slayers in starts:
            near = sorted(targets, key=lambda tg: math.hypot(tg[0][0] - sx, tg[0][1] - sy))[:40]
            for (tx, ty), tlayers in near:
                if math.hypot(tx - sx, ty - sy) > 30 or math.hypot(tx - sx, ty - sy) < 0.5:
                    continue
                for layer in [l for l in slayers if l in tlayers]:
                    for pts in ([(sx, sy), (tx, ty)], [(sx, sy), (sx, ty), (tx, ty)], [(sx, sy), (tx, sy), (tx, ty)]):
                        if clear_path(pts, layer, (pad,)):
                            add_track(board, pts, 0.4, gnd, layer)
                            fixed, done = fixed + 1, True
                            break
                    if done:
                        break
                if done:
                    break
            if done:
                break
        if not done:
            failed.append("%s.%s@%.1f,%.1f" % (pad.GetParentFootprint().GetReference(), pad.GetNumber(), px, py))
    print("orphan GND pads: %d, escape tracks added: %d, unresolved: %s" % (len(orphans), fixed, failed))
    return fixed


def stage_finish():
    sync_routed_project()
    board = pcbnew.LoadBoard(ROUTED)       # routed, no pours yet -> final PCB is written to PCB
    gnd = board.FindNet("GND")

    fanout_gnd(board)   # retry any SMD GND pad still without a via

    # copy symbol fields (Description, Datasheet, ki_keywords, ...) so PCB <-> schematic parity is clean
    parts = {p["ref"]: p for p in NL.PARTS}
    for fp in board.GetFootprints():
        p = parts.get(fp.GetReference())
        if not p:
            continue
        sym = lib_symbol(p["lib_id"])
        for node in find_all(sym, "property"):
            if node[1] not in ("Reference", "Value", "Footprint") and node[2]:
                set_field(fp, node[1], node[2])
        filters = find(sym, "fp_filters")
        if filters is not None:
            set_field(fp, "ki_fp_filters", " ".join(str(x) for x in filters[1:]))

    # board origin for drill/place files, so the JLCPCB CPL uses board coordinates
    board.GetDesignSettings().SetAuxOrigin(V(0, 0))

    inset = 0.4
    whole = [(inset, inset), (BW - inset, inset), (BW - inset, BH - inset), (inset, BH - inset)]
    add_zone(board, gnd, pcbnew.B_Cu, whole, priority=0)
    add_zone(board, gnd, pcbnew.F_Cu, whole, priority=0)
    # Extra pours (e.g. a power rail zone) go on top of the GND pours, before they are filled.
    if _hooks.get("extra_pours"):
        nets = {n: board.FindNet(n) for n in GLOBAL_NETS if board.FindNet(n)}
        _hooks["extra_pours"](board, nets, inset)
    _stitch_and_fill(board, gnd)


def fanout_gnd(board):
    gnd = board.FindNet("GND")
    added = 0
    failed = []
    gnd_tracks = [t for t in board.GetTracks() if t.GetNetname() == "GND" and t.Type() != pcbnew.PCB_VIA_T]
    for fp in board.GetFootprints():
        for pad in fp.Pads():
            if pad.GetNetname() != "GND" or pad.GetAttribute() != pcbnew.PAD_ATTRIB_SMD:
                continue
            if any(pad.HitTest(t.GetStart()) or pad.HitTest(t.GetEnd()) for t in gnd_tracks):
                continue   # already fanned out
            px, py = local(pad.GetPosition())
            done = False
            for dist in (1.3, 1.7, 2.2, 2.8):
                for ang in range(0, 360, 30):
                    vx = px + dist * math.cos(math.radians(ang))
                    vy = py + dist * math.sin(math.radians(ang))
                    if not _free(board, vx, vy, 0.4 + 0.3, gnd.GetNetCode(), ignore=(pad,)):
                        continue
                    # track corridor check (midpoints)
                    if not all(_free(board, px + (vx - px) * f, py + (vy - py) * f, 0.2 + 0.25, gnd.GetNetCode(), ignore=(pad,))
                               for f in (0.35, 0.6, 0.85)):
                        continue
                    via = pcbnew.PCB_VIA(board)
                    via.SetPosition(V(vx, vy))
                    via.SetWidth(mm(0.8))
                    via.SetDrill(mm(0.4))
                    via.SetNet(gnd)
                    board.Add(via)
                    add_track(board, [(px, py), (vx, vy)], 0.4, gnd, pad.GetLayer() if pad.IsOnLayer(pcbnew.F_Cu) else pcbnew.B_Cu)
                    added += 1
                    done = True
                    break
                if done:
                    break
            if not done:
                failed.append("%s.%s" % (fp.GetReference(), pad.GetNumber()))
    print("GND fan-out vias: %d added, failed: %s" % (added, failed))
    return failed


def _stitch_and_fill(board, gnd):
    # Fill first, then add vias only where BOTH GND pours exist, then make sure every pour
    # fragment holds a via, then refill. Nothing is ever removed (SWIG removal is unsafe).
    fill = pcbnew.ZONE_FILLER(board)
    fill.Fill(board.Zones())
    gnd_zones = [z for z in board.Zones() if z.GetNetname() == "GND"]
    vias = [local(t.GetPosition()) for t in board.GetTracks() if t.Type() == pcbnew.PCB_VIA_T]
    holes = [(local(pad.GetPosition()), pcbnew.ToMM(max(pad.GetDrillSize().x, pad.GetDrillSize().y)))
             for fp in board.GetFootprints() for pad in fp.Pads() if pad.GetDrillSize().x > 0]
    gnd_pth = [pad.GetPosition() for fp in board.GetFootprints() for pad in fp.Pads()
               if pad.GetNetname() == "GND" and pad.GetDrillSize().x > 0]

    def in_both(pos):
        return all(any(z.GetLayer() == layer and z.HitTestFilledArea(layer, pos) for z in gnd_zones)
                   for layer in (pcbnew.F_Cu, pcbnew.B_Cu))

    def spacing_ok(x, y):
        if any(math.hypot(x - vx, y - vy) < 1.3 for vx, vy in vias):
            return False
        return all(math.hypot(x - hx, y - hy) >= d / 2 + 0.2 + 0.35 for (hx, hy), d in holes)

    def add_via(x, y):
        via = pcbnew.PCB_VIA(board)
        via.SetPosition(V(x, y))
        via.SetWidth(mm(0.8))
        via.SetDrill(mm(0.4))
        via.SetNet(gnd)
        board.Add(via)
        vias.append((x, y))

    grid = 0
    for i in range(30):
        for j in range(28):
            gx, gy = 2.0 + 4.0 * i, 2.0 + 4.0 * j
            if gx > BW - 2 or gy > BH - 2:
                continue
            if in_both(V(gx, gy)) and spacing_ok(gx, gy) and _free(board, gx, gy, 0.4 + 0.45, gnd.GetNetCode()):
                add_via(gx, gy)
                grid += 1
    print("grid stitching vias:", grid)

    island_vias, stuck = 0, []
    for z in gnd_zones:
        layer = z.GetLayer()
        polys = z.GetFilledPolysList(layer)
        for k in range(polys.OutlineCount()):
            if any(polys.Contains(V(vx, vy), k) for vx, vy in vias) or any(polys.Contains(p, k) for p in gnd_pth):
                continue
            bb = polys.Outline(k).BBox()
            x0, y0 = local(pcbnew.VECTOR2I(bb.GetLeft(), bb.GetTop()))
            x1, y1 = local(pcbnew.VECTOR2I(bb.GetRight(), bb.GetBottom()))
            done = False
            y = y0
            while y <= y1 and not done:
                x = x0
                while x <= x1:
                    if polys.Contains(V(x, y), k) and in_both(V(x, y)) and spacing_ok(x, y) \
                            and _free(board, x, y, 0.4 + 0.3, gnd.GetNetCode()):
                        add_via(x, y)
                        island_vias += 1
                        done = True
                        break
                    x += 0.25
                y += 0.25
            if not done:
                stuck.append("%s#%d (%.1f,%.1f)-(%.1f,%.1f)" % ("F" if layer == pcbnew.F_Cu else "B", k, x0, y0, x1, y1))
    print("island vias: %d, fragments still without via: %d %s" % (island_vias, len(stuck), stuck[:10]))
    fill.Fill(board.Zones())
    if connect_orphans(board, gnd):
        fill.Fill(board.Zones())
    pcbnew.SaveBoard(PCB, board)
    strip_unused_dummy_nets(PCB)
    print("zones filled and saved")



def stage_check():
    """DRC incl. schematic parity. Exits 1 on any DRC error, unconnected item or parity difference.
    Warnings (silkscreen) are reported but do not fail the gate."""
    rpt = os.path.join(OUT, "drc.json")
    if os.path.exists(rpt):
        os.remove(rpt)          # never judge a stale report if kicad-cli fails to write a new one
    r = subprocess.run([CLI, "pcb", "drc", "--format", "json", "--severity-all", "--schematic-parity",
                        "-o", rpt, PCB], capture_output=True, text=True)
    if not os.path.exists(rpt):
        print("kicad-cli produced no DRC report (exit %s): %s" % (r.returncode, (r.stdout + r.stderr).strip()[-400:]))
        sys.exit(1)
    with open(rpt, encoding="utf-8") as f:
        d = json.load(f)
    for section in ("violations", "unconnected_items", "schematic_parity"):
        items = d.get(section, [])
        counts = {}
        for v in items:
            key = (v.get("severity"), v.get("type"))
            counts[key] = counts.get(key, 0) + 1
            if counts[key] <= (12 if section == "unconnected_items" else 4):
                where = "; ".join("%s @(%.1f,%.1f)" % (i.get("description", ""), i.get("pos", {}).get("x", 0) - OX,
                                                       i.get("pos", {}).get("y", 0) - OY) for i in v.get("items", []))
                print("  [%s] %s: %s" % (section, v.get("type"), where))
        print("%s: %d  %s" % (section, len(items), {"%s/%s" % k: c for k, c in sorted(counts.items())}))
    errors = sum(1 for v in d.get("violations", []) if v.get("severity") == "error")
    unconnected = len(d.get("unconnected_items", []))
    parity = len(d.get("schematic_parity", []))
    warnings = sum(1 for v in d.get("violations", []) if v.get("severity") == "warning")
    print("DRC gate: %d errors, %d unconnected, %d parity, %d warnings -> %s"
          % (errors, unconnected, parity, warnings, "FAIL" if errors or unconnected or parity else "PASS"))
    if errors or unconnected or parity:
        sys.exit(1)


def stage_render():
    for side, extra in (("top", []), ("bottom", []), ("iso", ["--rotate", "-45,0,30", "--perspective", "--zoom", "0.9"])):
        out = os.path.join(OUT, "render_%s.png" % side)
        args = [CLI, "pcb", "render", "-o", out, "-w", "1800", "-h", "1600", "--quality", "high"]
        args += ["--side", "top"] if side == "iso" else ["--side", side]
        r = subprocess.run(args + extra + [PCB], capture_output=True, text=True)
        print(side, "->", out, r.returncode, r.stderr.strip()[-300:])
