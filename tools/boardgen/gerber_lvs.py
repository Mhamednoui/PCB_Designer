"""Gerber LVS: rebuild the board's connectivity from the files sent to the fab and diff it against netlist.py.

    python tools/boardgen/gerber_lvs.py <project-id> [--fab <fab-dir-or-zip>] [--quiet]

Why it exists. Every other check (ERC, DRC, parity, the CONNECTIONS.md cross-check) asks KiCad about its
OWN model of the board. If a track is lost between that model and the plot, or the plot disagrees with the
model, all of them still pass. This stage trusts none of that: connectivity comes only from the copper
gerbers and the drill file inside the zip the fab receives (default: out/fab/<id>_gerbers_JLCPCB.zip).

Algorithm
  1. Per copper layer, turn every flash/track/arc/region into a shapely polygon (honouring clear
     polarity), union them and split into islands (= electrically continuous copper on that layer).
  2. Union-find across layers: a PLATED drill hit joins every island (on every layer) that touches the
     hole; NPTH hits connect nothing.
  3. Each netlist pin is located on the board (pad positions come from the .kicad_pcb - the ONLY thing
     read from it - used purely for "where is pin X", never for who-is-connected). A pin's nodes are the
     islands under its pad centre. Pins sharing a union-find root are one extracted net.
  4. Extracted nets are compared with netlist.py as sets of (ref, pin): a netlist net split over several
     extracted nets is an OPEN, an extracted net holding pins of different netlist nets is a SHORT.
     Pads on refs that netlist.py does not manage are warnings unless they bridge managed nets.

Self-checks that stop a coordinate/origin mistake from silently producing a plausible-looking verdict:
every pad that has a hole in the .kicad_pcb must have a drill hit at the predicted spot (this proves the
aux-origin / Y-flip / rotation maths), and every pad must find copper under its centre.

Output: projects/<id>/out/lvs.json (git-ignored) and one verdict line. Exit 1 on any open or short.
Runs under SYSTEM python (needs the pinned gerbonara + shapely from requirements.txt), not KiCad's.
"""
import json
import math
import os
import re
import sys
import tempfile
import time
import warnings
import zipfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen import sexp  # noqa: E402
from boardgen.project import PROJECTS, load_netlist  # noqa: E402

try:
    from gerbonara import GerberFile
    from shapely.geometry import LineString, Point, Polygon
    from shapely.ops import unary_union
    from shapely.strtree import STRtree
    from shapely import make_valid
except ImportError as e:  # pragma: no cover
    raise SystemExit("FAILED: %s\n  install the pinned deps with: python -m pip install --user -r requirements.txt" % e)

POS_TOL = 0.01        # mm: drill hit vs predicted pad hole position
PROBE = 0.005         # mm: radius of the point probe used to find copper under a pad centre
ARC_ERR = 0.002       # mm: arc -> polyline approximation error
CIRCLE_SEGS = 16      # shapely quad_segs for round apertures


# ---------------------------------------------------------------- fab input
def stage_fab(fab):
    """Return (directory holding the gerbers/drill, label). A zip is extracted to a temp dir."""
    if os.path.isdir(fab):
        hits = [f for f in os.listdir(fab) if f.endswith(".zip")]
        if os.path.isdir(os.path.join(fab, "gerbers")):
            return os.path.join(fab, "gerbers"), fab + " (loose gerbers/)"
        if hits:
            fab = os.path.join(fab, hits[0])
        else:
            return fab, fab
    tmp = tempfile.mkdtemp(prefix="lvs_")
    with zipfile.ZipFile(fab) as z:
        z.extractall(tmp)
    return tmp, fab


def default_fab(project):
    base = os.path.join(PROJECTS, project, "out", "fab")
    zips = [f for f in os.listdir(base) if f.endswith(".zip")] if os.path.isdir(base) else []
    if zips:
        return os.path.join(base, zips[0])
    return base


# ---------------------------------------------------------------- gerber -> shapely
def prim_to_poly(p):
    """gerbonara graphic primitive -> shapely geometry (None if degenerate)."""
    n = type(p).__name__
    if n == "Circle":
        return Point(p.x, p.y).buffer(p.r, quad_segs=CIRCLE_SEGS)
    if n == "Line":
        if math.hypot(p.x2 - p.x1, p.y2 - p.y1) < 1e-9:
            return Point(p.x1, p.y1).buffer(p.width / 2, quad_segs=CIRCLE_SEGS)
        return LineString([(p.x1, p.y1), (p.x2, p.y2)]).buffer(p.width / 2, quad_segs=CIRCLE_SEGS)
    if n == "Rectangle":
        c, s = math.cos(p.rotation), math.sin(p.rotation)
        pts = [(-p.w / 2, -p.h / 2), (p.w / 2, -p.h / 2), (p.w / 2, p.h / 2), (-p.w / 2, p.h / 2)]
        return Polygon([(p.x + x * c - y * s, p.y + x * s + y * c) for x, y in pts])
    if n == "Arc":
        poly = p.to_arc_poly()
        return prim_to_poly(poly)
    if n == "ArcPoly":
        pts = p.approximate_arcs(max_error=ARC_ERR).outline
        if len(pts) < 3:
            return None
        g = Polygon(pts)
        return g if g.is_valid else make_valid(g)
    raise ValueError("unhandled gerber primitive %s" % n)


def layer_geometry(gf):
    """Union of a gerber layer's copper (dark objects added, clear objects subtracted, in file order)."""
    cur = None
    pend, pend_dark = [], True

    def flush():
        nonlocal cur, pend
        if not pend:
            return
        u = unary_union(pend)
        if pend_dark:
            cur = u if cur is None else unary_union([cur, u])
        elif cur is not None:
            cur = cur.difference(u)
        pend = []

    for o in gf.objects:
        dark = bool(o.polarity_dark)
        if dark != pend_dark:
            flush()
            pend_dark = dark
        for prim in o.to_primitives("mm"):
            g = prim_to_poly(prim)
            if g is not None and not g.is_empty:
                pend.append(g)
    flush()
    return cur


def copper_files(gdir):
    """{layer_index: (filename, GerberFile)} for every Copper gerber, ordered top..bottom by X2 FileFunction."""
    found = []
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        for fn in sorted(os.listdir(gdir)):
            low = fn.lower()
            if low.endswith((".drl", ".gbrjob", ".txt", ".csv", ".md")) or fn.endswith("drl_map.gbr"):
                continue
            try:
                gf = GerberFile.open(os.path.join(gdir, fn))
            except Exception:
                continue
            ff = (gf.file_attrs or {}).get(".FileFunction") if hasattr(gf, "file_attrs") else None
            if ff and ff[0] == "Copper":
                m = re.match(r"L(\d+)", ff[1])
                found.append((int(m.group(1)) if m else 0, fn, gf))
    found.sort(key=lambda t: t[0])
    return found


def kicad_layer_names(n):
    if n == 1:
        return ["F.Cu"]
    return ["F.Cu"] + ["In%d.Cu" % i for i in range(1, n - 1)] + ["B.Cu"]


# ---------------------------------------------------------------- drill
def parse_drill(path):
    """Minimal KiCad-Excellon reader (decimal, absolute). -> [{'x','y','x2','y2','d','plated'}] in mm.
    Own parser because gerbonara does not read KiCad's per-tool Plated/NonPlated comments."""
    tools, hits = {}, []
    plated_hint, cur, scale = None, None, 1.0
    file_default = None
    with open(path, encoding="utf-8", errors="replace") as f:
        for line in f:
            line = line.strip()
            if line.startswith(";"):
                m = re.search(r"TA\.AperFunction,(Plated|NonPlated)", line)
                if m:
                    plated_hint = m.group(1) == "Plated"
                m = re.search(r"TF\.FileFunction,(\w+)", line)
                if m:
                    file_default = m.group(1) != "NonPlated"
                continue
            if line == "INCH":
                scale = 25.4
            elif line == "METRIC":
                scale = 1.0
            m = re.match(r"^T(\d+)C([\d.]+)", line)
            if m:
                tools[int(m.group(1))] = (float(m.group(2)) * scale,
                                          plated_hint if plated_hint is not None else (file_default is not False))
                plated_hint = None
                continue
            m = re.match(r"^T(\d+)$", line)
            if m:
                cur = int(m.group(1))
                continue
            m = re.match(r"^X(-?[\d.]+)Y(-?[\d.]+)(?:G85X(-?[\d.]+)Y(-?[\d.]+))?$", line)
            if m and cur in tools:
                d, plated = tools[cur]
                x, y = float(m.group(1)) * scale, float(m.group(2)) * scale
                h = {"x": x, "y": y, "d": d, "plated": plated}
                if m.group(3):
                    h["x2"], h["y2"] = float(m.group(3)) * scale, float(m.group(4)) * scale
                hits.append(h)
    return hits


def hole_geom(h):
    if "x2" in h:
        return LineString([(h["x"], h["y"]), (h["x2"], h["y2"])]).buffer(h["d"] / 2, quad_segs=CIRCLE_SEGS)
    return Point(h["x"], h["y"]).buffer(h["d"] / 2, quad_segs=CIRCLE_SEGS)


# ---------------------------------------------------------------- board file: pad positions only
def read_pads(pcb_path):
    """-> (aux_origin, pads) ; pad = dict(ref, num, x, y, layers, drill(bool), kind). x/y absolute, KiCad coords."""
    with open(pcb_path, encoding="utf-8") as f:
        tree = sexp.parse(f.read())
    setup = sexp.find(tree, "setup")
    aux = sexp.find(setup, "aux_axis_origin") if setup else None
    origin = (float(aux[1]), float(aux[2])) if aux else (0.0, 0.0)
    pads = []
    for fp in sexp.find_all(tree, "footprint"):
        ref = None
        for pr in sexp.find_all(fp, "property"):
            if pr[1] == "Reference":
                ref = pr[2]
        at = sexp.find(fp, "at")
        fx, fy = float(at[1]), float(at[2])
        ang = math.radians(float(at[3])) if len(at) > 3 else 0.0
        c, s = math.cos(ang), math.sin(ang)
        for pad in sexp.find_all(fp, "pad"):
            pat = sexp.find(pad, "at")
            px, py = float(pat[1]), float(pat[2])
            layers = sexp.find(pad, "layers")
            lyr = [str(x) for x in layers[1:]] if layers else []
            pads.append({
                "ref": ref, "num": str(pad[1]), "kind": str(pad[2]),
                "x": fx + px * c + py * s, "y": fy - px * s + py * c,
                "layers": lyr, "drill": sexp.find(pad, "drill") is not None,
            })
    return origin, pads


def to_gerber(origin, x, y):
    """KiCad board coords -> gerber/drill coords: aux-origin shift and Y flip."""
    return x - origin[0], -(y - origin[1])


def find_pcb(project):
    base = os.path.join(PROJECTS, project)
    p = os.path.join(base, project + ".kicad_pcb")
    if os.path.isfile(p):
        return p
    hits = sorted(f for f in os.listdir(base) if f.endswith(".kicad_pcb") and "-routed" not in f)
    if not hits:
        raise SystemExit("FAILED: no .kicad_pcb in %s" % base)
    return os.path.join(base, hits[0])


# ---------------------------------------------------------------- union-find
class UF:
    def __init__(self):
        self.p = {}

    def find(self, a):
        self.p.setdefault(a, a)
        while self.p[a] != a:
            self.p[a] = self.p[self.p[a]]
            a = self.p[a]
        return a

    def union(self, a, b):
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[ra] = rb


# ---------------------------------------------------------------- main check
def run(project, fab=None, quiet=False):
    t0 = time.time()
    NL = load_netlist(project)
    fab = fab or default_fab(project)
    gdir, label = stage_fab(fab)
    pcb_path = find_pcb(project)
    origin, pcb_pads = read_pads(pcb_path)

    cu = copper_files(gdir)
    if not cu:
        raise SystemExit("FAILED: no copper gerbers found in %s" % label)
    names = kicad_layer_names(len(cu))
    layer_islands, layer_trees = {}, {}
    uf = UF()
    for name, (_, fn, gf) in zip(names, cu):
        g = layer_geometry(gf)
        isl = [] if g is None else (list(g.geoms) if hasattr(g, "geoms") else [g])
        isl = [i for i in isl if not i.is_empty and i.area > 0]
        layer_islands[name] = isl
        layer_trees[name] = STRtree(isl)
        for i in range(len(isl)):
            uf.find((name, i))

    def islands_at(name, geom):
        return [int(i) for i in layer_trees[name].query(geom, predicate="intersects")]

    # plated holes join the copper they pierce; NPTH joins nothing
    drills = []
    for fn in sorted(os.listdir(gdir)):
        if fn.lower().endswith(".drl"):
            drills += parse_drill(os.path.join(gdir, fn))
    n_plated = 0
    for h in drills:
        if not h["plated"]:
            continue
        n_plated += 1
        geom = hole_geom(h)
        nodes = [(name, i) for name in names for i in islands_at(name, geom)]
        for a in nodes[1:]:
            uf.union(nodes[0], a)

    # pad -> nodes ; self-checks on the coordinate maths
    problems, warns = [], []
    ref_in_nl = {p["ref"] for p in NL.PARTS}
    want_pin_net = {}
    for net, pins in NL.nets().items():
        for pin in pins:
            want_pin_net[pin] = net

    hit_index = {}
    for h in drills:
        hit_index.setdefault((round(h["x"] / POS_TOL), round(h["y"] / POS_TOL)), []).append(h)

    def drilled_at(gx, gy):
        kx, ky = round(gx / POS_TOL), round(gy / POS_TOL)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for h in hit_index.get((kx + dx, ky + dy), []):
                    if math.hypot(h["x"] - gx, h["y"] - gy) <= POS_TOL * 1.5:
                        return h
        # slotted holes: pad centre is the slot centre
        for h in drills:
            if "x2" in h and math.hypot((h["x"] + h["x2"]) / 2 - gx, (h["y"] + h["y2"]) / 2 - gy) <= POS_TOL * 1.5:
                return h
        return None

    pin_nodes = {}      # (ref, num) -> set of nodes
    all_pads = []       # (ref, num) for every pad that should carry copper
    pad_checked = 0
    for pad in pcb_pads:
        if not pad["ref"] or pad["kind"] == "np_thru_hole":
            continue
        gx, gy = to_gerber(origin, pad["x"], pad["y"])
        key = (pad["ref"], pad["num"])
        all_pads.append(key)
        pad_checked += 1
        if pad["drill"] and drilled_at(gx, gy) is None:
            problems.append("pad %s.%s has a hole in the board file but no drill hit at (%.3f, %.3f) "
                            "- origin/flip/rotation mismatch or hole missing from the .drl" % (key + (gx, gy)))
        probe = Point(gx, gy).buffer(PROBE)
        want_layers = names if any(l.endswith(".Cu") and l.startswith("*") for l in pad["layers"]) else \
            [l for l in pad["layers"] if l in names]
        if pad["kind"] == "thru_hole" and not want_layers:
            want_layers = names
        found = set()
        for nm in want_layers:
            for i in islands_at(nm, probe):
                found.add((nm, i))
        if not found:
            problems.append("pad %s.%s: no copper under its centre (%.3f, %.3f) on %s"
                            % (key + (gx, gy, "/".join(want_layers) or "?")))
        elif pad["kind"] == "smd" and not {n for n, _ in found} >= set(want_layers):
            problems.append("pad %s.%s: copper missing on %s" % (key + ("/".join(sorted(set(want_layers) - {n for n, _ in found})),)))
        pin_nodes.setdefault(key, set()).update(found)

    # extracted nets: group pads by union-find root. A pad lying on several roots (should not happen
    # for a drilled pad, can for a pad whose barrel is missing) merges those roots' pads via the pad itself.
    pad_uf = UF()
    for key, nodes in pin_nodes.items():
        pad_uf.find(("pad",) + key)
        for n in nodes:
            pad_uf.union(("pad",) + key, ("root", uf.find(n)))
    groups = {}
    for key in pin_nodes:
        groups.setdefault(pad_uf.find(("pad",) + key), set()).add(key)

    # compare with netlist.py
    opens, shorts, extra = [], [], []
    expected = {}
    for net, pins in NL.nets().items():
        expected[net] = set(pins)
    pin_group = {}
    for gid, members in groups.items():
        for m in members:
            pin_group[m] = gid
    for net, pins in sorted(expected.items()):
        gids = {}
        for pin in pins:
            if pin in pin_group:
                gids.setdefault(pin_group[pin], []).append(pin)
            else:
                problems.append("netlist pin %s.%s (net %s) has no pad in the board file" % (pin + (net,)))
        if len(gids) > 1:
            parts = sorted(gids.values(), key=lambda m: -len(m))
            opens.append({"net": net, "fragments": [sorted("%s.%s" % p for p in m) for m in parts]})
    for gid, members in groups.items():
        nets = {}
        unmanaged = []
        for m in members:
            if m in want_pin_net:
                nets.setdefault(want_pin_net[m], []).append(m)
            elif m[0] in ref_in_nl:
                nets.setdefault(None, []).append(m)          # managed part, pin deliberately unconnected
            else:
                unmanaged.append(m)
        if len(nets) > 1:
            shorts.append({"nets": sorted(str(n) for n in nets),
                           "pins": {str(n): sorted("%s.%s" % p for p in ps) for n, ps in nets.items()}})
        if unmanaged:
            warns.append("pads of refs not in netlist.py share copper with %s: %s" % (
                sorted(str(n) for n in nets) or "no netlist pin",
                ", ".join(sorted("%s.%s" % p for p in unmanaged))))

    dt = time.time() - t0
    result = {
        "project": project, "fab": label, "seconds": round(dt, 1), "layers": names,
        "islands": {n: len(i) for n, i in layer_islands.items()},
        "drill_hits": len(drills), "plated_hits": n_plated, "pads_checked": pad_checked,
        "netlist_nets": len(expected), "extracted_nets": len(groups),
        "opens": opens, "shorts": shorts, "problems": problems, "warnings": warns,
    }
    out = os.path.join(PROJECTS, project, "out", "lvs.json")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=1)

    n_open, n_short = len(opens), len(shorts)
    if not quiet:
        for o in opens:
            print("OPEN  %s splits into %d fragments:" % (o["net"], len(o["fragments"])))
            for fr in o["fragments"]:
                print("        " + " ".join(fr[:12]) + (" ..." if len(fr) > 12 else ""))
        for s in shorts:
            print("SHORT " + " + ".join(s["nets"]))
            for n, ps in s["pins"].items():
                print("        %s: %s" % (n, " ".join(ps[:12]) + (" ..." if len(ps) > 12 else "")))
        for p in problems:
            print("PROBLEM " + p)
        for w in warns:
            print("warn  " + w)
    if n_open or n_short or problems:
        extra_txt = (", %d unresolved problems" % len(problems)) if problems else ""
        print("FAILED: %d opens, %d shorts%s  [%s, %d nets, %.1fs]" % (n_open, n_short, extra_txt, project, len(expected), dt))
        return 1
    print("OK: gerber LVS %s - 0 opens, 0 shorts (%d nets, %d pads, %d holes, %d layers, %.1fs)%s" % (
        project, len(expected), pad_checked, len(drills), len(names), dt,
        ", %d warnings" % len(warns) if warns else ""))
    return 0


def main(argv):
    args = [a for a in argv[1:] if not a.startswith("--")]
    fab = None
    if "--fab" in argv:
        fab = argv[argv.index("--fab") + 1]
        args = [a for a in args if a != fab]
    if not args:
        raise SystemExit(__doc__)
    return run(args[0], fab, quiet="--quiet" in argv)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
