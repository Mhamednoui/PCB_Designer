"""A .kicad_pcb file -> the `board` section of the design IR.

    from boardgen.ir import from_kicad_pcb
    board = from_kicad_pcb.parse_board("projects/blinky-555/blinky-555.kicad_pcb")

Pure stdlib (boardgen.sexp), runs under the system Python: no pcbnew, no kicad-cli. This module is the ONLY place in the
IR that knows the .kicad_pcb file format - when KiCad changes it (R16, docs/PLATFORM_PLAN.md section 3), this is the one
file to fix. Written against the KiCad 10 format (version 20260206): nets are referenced by name, `(net "GND")`; the older
`(net 5 "GND")` form is accepted too.

Fail closed (never guess): anything this parser does not understand raises IRError naming the item -
  - an unknown top-level element (known decorative ones are listed in _IGNORED),
  - a footprint without Reference/at/layer, a duplicated reference, an unknown pad type,
  - a malformed number, a missing or non-closing board outline, an outline made of unsupported items (gr_curve, fp_* on Edge.Cuts),
  - an arc inside a zone polygon (area would be wrong).

Coordinates are KiCad board mm, y down, rounded to 0.1 um. Absolute pad position = footprint (x, y) + the pad offset rotated
by the footprint angle (KiCad: x' = x cos + y sin, y' = y cos - x sin; back-side footprints are stored mirrored already).
"""
import math

from ..sexp import find, find_all, parse
from . import IRError, norm_net, natkey

MIN_VERSION = 20240108                      # KiCad 8; earlier files use another net model
NO_NET = "(no net)"                         # key used in `tracks` for copper that carries no net
PAD_TYPES = ("thru_hole", "smd", "np_thru_hole", "connect")
ARC_STEP_DEG = 5.0                          # outline arcs are tessellated at <= this angle (the polygon is an approximation)
CIRCLE_SEGMENTS = 72

_HANDLED = {"footprint", "segment", "arc", "via", "zone", "gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly",
            "gr_curve", "layers", "general", "setup", "version"}
_IGNORED = {"generator", "generator_version", "paper", "title_block", "gr_text", "gr_text_box", "gr_bbox",
            "embedded_fonts", "embedded_files", "net", "net_class", "dimension", "target", "image", "group",
            "generated", "property", "uuid", "tables", "table", "teardrops"}


def _n(x, what):
    try:
        v = float(str(x))
    except (TypeError, ValueError):
        raise IRError("%s: not a number: %r" % (what, x))
    if math.isnan(v) or math.isinf(v):
        raise IRError("%s: not finite: %r" % (what, x))
    return v


def _r(v):
    return round(v, 4) + 0.0                # +0.0 turns -0.0 into 0.0


def _xy(node, key, what):
    n = find(node, key)
    if n is None or len(n) < 3:
        raise IRError("%s: missing (%s x y)" % (what, key))
    return _n(n[1], what + " " + key + ".x"), _n(n[2], what + " " + key + ".y")


def _str(node, key, what, default=None):
    n = find(node, key)
    if n is None or len(n) < 2:
        if default is not None:
            return default
        raise IRError("%s: missing (%s ...)" % (what, key))
    return str(n[1])


def _net(node, what):
    """Net name (normalised like netlist.py) of a pad / segment / via / zone, or None for no net."""
    n = find(node, "net")
    if n is None:
        return None
    items = [x for x in n[1:] if not isinstance(x, list)]
    if len(items) == 1:
        name = str(items[0])
    elif len(items) == 2:
        name = str(items[1])
    else:
        raise IRError("%s: unreadable (net ...): %r" % (what, n))
    return norm_net(name)


def copper_order(name):
    return (0 if name == "F.Cu" else 2 if name == "B.Cu" else 1, natkey(name))


def _copper_layers(spec, copper, what):
    """Expand a layer list (wildcards allowed) to the board's copper layers, in stack order."""
    out = set()
    for s in spec:
        s = str(s)
        if s in ("*.Cu", "F&B.Cu"):
            out.update(copper if s == "*.Cu" else {c for c in copper if c in ("F.Cu", "B.Cu")})
        elif s.endswith(".Cu"):
            if s not in copper:
                raise IRError("%s: layer %s is not a copper layer of this board (%s)" % (what, s, ", ".join(copper)))
            out.add(s)
    return sorted(out, key=copper_order)


def _area(pts):
    a = 0.0
    for i in range(len(pts)):
        x0, y0 = pts[i]
        x1, y1 = pts[(i + 1) % len(pts)]
        a += x0 * y1 - x1 * y0
    return a / 2.0


def _pts(node, what):
    """[(x, y)] of a (pts (xy x y) ...) child; an arc in it is refused (the area would be wrong)."""
    p = find(node, "pts")
    if p is None:
        raise IRError("%s: missing (pts ...)" % what)
    out = []
    for c in p[1:]:
        if isinstance(c, list) and c and c[0] == "xy" and len(c) >= 3:
            out.append((_n(c[1], what), _n(c[2], what)))
        else:
            raise IRError("%s: unsupported element in (pts) : %s" % (what, c[0] if isinstance(c, list) and c else c))
    return out


def _rot(px, py, deg):
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return px * c + py * s, py * c - px * s


def _arc_points(start, mid, end, what):
    """Points along the 3-point arc start->mid->end (inclusive), at most ARC_STEP_DEG apart; plus the arc length."""
    (x1, y1), (x2, y2), (x3, y3) = start, mid, end
    d = 2 * (x1 * (y2 - y3) + x2 * (y3 - y1) + x3 * (y1 - y2))
    if abs(d) < 1e-12:
        raise IRError("%s: arc points are collinear" % what)
    ux = ((x1 * x1 + y1 * y1) * (y2 - y3) + (x2 * x2 + y2 * y2) * (y3 - y1) + (x3 * x3 + y3 * y3) * (y1 - y2)) / d
    uy = ((x1 * x1 + y1 * y1) * (x3 - x2) + (x2 * x2 + y2 * y2) * (x1 - x3) + (x3 * x3 + y3 * y3) * (x2 - x1)) / d
    r = math.hypot(x1 - ux, y1 - uy)
    a1, a2, a3 = (math.atan2(y - uy, x - ux) for (x, y) in (start, mid, end))
    ccw = (a2 - a1) % (2 * math.pi) < (a3 - a1) % (2 * math.pi)       # mid lies between start and end going counter-clockwise
    sweep = (a3 - a1) % (2 * math.pi) if ccw else -((a1 - a3) % (2 * math.pi))
    n = max(2, int(math.ceil(abs(math.degrees(sweep)) / ARC_STEP_DEG)))
    pts = [start] + [(ux + r * math.cos(a1 + sweep * i / n), uy + r * math.sin(a1 + sweep * i / n))
                     for i in range(1, n)] + [end]
    return pts, abs(sweep) * r


# --------------------------------------------------------------------------- sections
def _layers(root):
    ln = find(root, "layers")
    if ln is None:
        raise IRError("no (layers ...) section")
    copper = []
    for e in ln[1:]:
        if isinstance(e, list) and len(e) >= 3 and str(e[2]) in ("signal", "power", "mixed", "jumper"):
            if not str(e[1]).endswith(".Cu"):
                raise IRError("copper-type layer %r is not named *.Cu" % (e[1],))
            copper.append(str(e[1]))
    copper.sort(key=copper_order)
    if not copper:
        raise IRError("no copper layers in (layers ...)")
    return copper


def _stackup(root):
    thick = None
    g = find(root, "general")
    if g is not None and find(g, "thickness") is not None:
        thick = _r(_n(find(g, "thickness")[1], "general.thickness"))
    su = find(find(root, "setup") or [], "stackup")
    layers = None
    if su is not None:
        layers = []
        for e in find_all(su, "layer"):
            t = find(e, "thickness")
            typ, mat = find(e, "type"), find(e, "material")
            layers.append({"name": str(e[1]), "type": str(typ[1]) if typ else None,
                           "thickness_mm": _r(_n(t[1], "stackup %s thickness" % e[1])) if t else None,
                           "material": str(mat[1]) if mat else None})
    return {"thickness_mm": thick, "layers": layers}


def _outline(root):
    loops, paths = [], []
    for kind in ("gr_line", "gr_arc", "gr_rect", "gr_circle", "gr_poly", "gr_curve"):
        for e in find_all(root, kind):
            lay = find(e, "layer")
            if lay is None or str(lay[1]) != "Edge.Cuts":
                continue
            what = "Edge.Cuts %s" % kind
            if kind == "gr_curve":
                raise IRError("%s: bezier outlines are not supported" % what)
            if kind == "gr_line":
                paths.append([_xy(e, "start", what), _xy(e, "end", what)])
            elif kind == "gr_arc":
                paths.append(_arc_points(_xy(e, "start", what), _xy(e, "mid", what), _xy(e, "end", what), what)[0])
            elif kind == "gr_rect":
                (x0, y0), (x1, y1) = _xy(e, "start", what), _xy(e, "end", what)
                loops.append([(x0, y0), (x1, y0), (x1, y1), (x0, y1)])
            elif kind == "gr_circle":
                (cx, cy), (ex, ey) = _xy(e, "center", what), _xy(e, "end", what)
                r = math.hypot(ex - cx, ey - cy)
                loops.append([(cx + r * math.cos(2 * math.pi * i / CIRCLE_SEGMENTS),
                               cy + r * math.sin(2 * math.pi * i / CIRCLE_SEGMENTS)) for i in range(CIRCLE_SEGMENTS)])
            else:
                loops.append(_pts(e, what))
    for fp in find_all(root, "footprint"):
        for k in ("fp_line", "fp_arc", "fp_rect", "fp_circle", "fp_poly", "fp_curve"):
            for e in find_all(fp, k):
                lay = find(e, "layer")
                if lay is not None and str(lay[1]) == "Edge.Cuts":
                    raise IRError("a footprint draws on Edge.Cuts (%s in %s): outline inside footprints is not supported"
                                  % (k, fp[1]))
    # chain open paths into closed loops; every rounded endpoint must be shared by exactly two path ends
    key = lambda p: (round(p[0], 3) + 0.0, round(p[1], 3) + 0.0)       # noqa: E731
    ends = {}
    for i, path in enumerate(paths):
        for end in (0, -1):
            ends.setdefault(key(path[end]), []).append((i, end))
    for k, v in sorted(ends.items()):
        if len(v) != 2:
            raise IRError("board outline is not closed: %d outline item(s) end at (%g, %g) (need exactly 2)"
                          % (len(v), k[0], k[1]))
    used = set()
    for i in range(len(paths)):
        if i in used:
            continue
        loop = []
        start_key = key(paths[i][0])
        pts = list(paths[i])
        used.add(i)
        while True:
            loop.extend(pts[:-1])
            nxt_key = key(pts[-1])
            if nxt_key == start_key:
                break
            nxt = [(j, e) for (j, e) in ends[nxt_key] if j not in used]
            if not nxt:
                raise IRError("board outline does not close near (%g, %g)" % nxt_key)
            j, e = nxt[0]
            used.add(j)
            pts = list(paths[j]) if e == 0 else list(reversed(paths[j]))
        loops.append(loop)
    if not loops:
        raise IRError("no board outline: nothing on Edge.Cuts")
    polys = []
    for lp in loops:
        if len(lp) < 3:
            raise IRError("outline loop with fewer than 3 points")
        lp = [(_r(x), _r(y)) for x, y in lp]
        if _area(lp) < 0:
            lp.reverse()
        k = min(range(len(lp)), key=lambda i: lp[i])
        polys.append(lp[k:] + lp[:k])
    polys.sort(key=lambda p: (-abs(_area(p)), p))
    outer, cutouts = polys[0], polys[1:]
    xs, ys = [p[0] for p in outer], [p[1] for p in outer]
    bbox = [min(xs), min(ys), max(xs), max(ys)]
    area = abs(_area(outer)) - sum(abs(_area(c)) for c in cutouts)
    return {"polygon": [list(p) for p in outer], "cutouts": [[list(p) for p in c] for c in cutouts],
            "bbox": bbox, "size_mm": [_r(bbox[2] - bbox[0]), _r(bbox[3] - bbox[1])], "area_mm2": _r(area)}


def _drill(pad, what):
    d = find(pad, "drill")
    if d is None:
        return None
    nums = [x for x in d[1:] if not isinstance(x, list)]
    if nums and str(nums[0]) == "oval" and len(nums) == 3:
        return [_r(_n(nums[1], what)), _r(_n(nums[2], what))]
    if len(nums) == 1:
        v = _n(nums[0], what)
        return _r(v) if v > 0 else None
    raise IRError("%s: unreadable (drill ...): %r" % (what, d))


def _footprints_and_pads(root, copper):
    fps, pads, seen = {}, {}, {}
    for fp in find_all(root, "footprint"):
        if len(fp) < 2 or not isinstance(fp[1], str):
            raise IRError("footprint without a library id")
        ref = None
        for p in find_all(fp, "property"):
            if len(p) >= 3 and str(p[1]) == "Reference":
                ref = str(p[2])
        if not ref:
            raise IRError("footprint %s has no Reference property" % fp[1])
        if ref in fps:
            raise IRError("duplicate footprint reference %s" % ref)
        side = {"F.Cu": "front", "B.Cu": "back"}.get(_str(fp, "layer", "footprint " + ref))
        if side is None:
            raise IRError("footprint %s is on layer %s (need F.Cu or B.Cu)" % (ref, _str(fp, "layer", ref)))
        x, y = _xy(fp, "at", "footprint " + ref)
        an = find(fp, "at")
        rot = _n(an[3], "footprint %s rotation" % ref) if len(an) > 3 else 0.0
        attr = find(fp, "attr")
        fps[ref] = {"lib_id": str(fp[1]), "x": _r(x), "y": _r(y), "rot": _r(rot), "side": side,
                    "attr": sorted(str(a) for a in (attr[1:] if attr else []) if not isinstance(a, list))}
        for pad in find_all(fp, "pad"):
            if len(pad) < 4:
                raise IRError("footprint %s: pad with fewer than 3 fields" % ref)
            num, ptype, shape = str(pad[1]), str(pad[2]), str(pad[3])
            what = "pad %s.%s" % (ref, num or "(unnumbered)")
            if ptype not in PAD_TYPES:
                raise IRError("%s: unknown pad type %r (known: %s)" % (what, ptype, ", ".join(PAD_TYPES)))
            px, py = _xy(pad, "at", what)
            dx, dy = _rot(px, py, rot)
            ln = find(pad, "layers")
            if ln is None:
                raise IRError("%s: missing (layers ...)" % what)
            k = (ref, num)
            seen[k] = seen.get(k, 0) + 1
            if num == "":
                key = "%s.~%d" % (ref, seen[k])
            else:
                key = "%s.%s" % (ref, num) if seen[k] == 1 else "%s.%s#%d" % (ref, num, seen[k])
            pads[key] = {"ref": ref, "pad": num, "type": ptype, "shape": shape, "x": _r(x + dx), "y": _r(y + dy),
                         "layers": _copper_layers(ln[1:], copper, what), "drill": _drill(pad, what),
                         "net": _net(pad, what)}
    return ({r: fps[r] for r in sorted(fps, key=natkey)},
            {k: pads[k] for k in sorted(pads, key=lambda k: (natkey(pads[k]["ref"]), natkey(pads[k]["pad"]), k))})


def _tracks_and_vias(root, copper):
    tracks, vias = {}, []
    for kind in ("segment", "arc"):
        for e in find_all(root, kind):
            what = kind
            w = _n(_str(e, "width", what), what + " width")
            lay = _str(e, "layer", what)
            if lay not in copper:
                raise IRError("%s on layer %s which is not a copper layer" % (kind, lay))
            if kind == "segment":
                (x0, y0), (x1, y1) = _xy(e, "start", what), _xy(e, "end", what)
                length = math.hypot(x1 - x0, y1 - y0)
            else:
                length = _arc_points(_xy(e, "start", what), _xy(e, "mid", what), _xy(e, "end", what), what)[1]
            net = _net(e, what) or NO_NET
            t = tracks.setdefault(net, {"segments": 0, "arcs": 0, "min_width_mm": w, "total_length_mm": 0.0, "layers": set()})
            t["segments" if kind == "segment" else "arcs"] += 1
            t["min_width_mm"] = min(t["min_width_mm"], w)
            t["total_length_mm"] += length
            t["layers"].add(lay)
    for t in tracks.values():
        t["min_width_mm"] = _r(t["min_width_mm"])
        t["total_length_mm"] = _r(t["total_length_mm"])
        t["layers"] = sorted(t["layers"], key=copper_order)
    for v in find_all(root, "via"):
        x, y = _xy(v, "at", "via")
        ln = find(v, "layers")
        if ln is None:
            raise IRError("via at (%g, %g): missing (layers ...)" % (x, y))
        d = find(v, "drill")
        if d is None or len(d) < 2:
            raise IRError("via at (%g, %g): missing (drill ...)" % (x, y))
        vias.append({"x": _r(x), "y": _r(y), "net": _net(v, "via"), "size": _r(_n(_str(v, "size", "via"), "via size")),
                     "drill": _r(_n(d[1], "via drill")), "layers": _copper_layers(ln[1:], copper, "via")})
    vias.sort(key=lambda v: (v["x"], v["y"], v["net"] or "", v["size"], v["drill"]))
    return {n: tracks[n] for n in sorted(tracks, key=natkey)}, vias


def _zones(root, copper):
    out = []
    for z in find_all(root, "zone"):
        what = "zone"
        net = _net(z, what)
        if net is None and find(z, "net_name") is not None:
            net = norm_net(str(find(z, "net_name")[1]))
        name = find(z, "name")
        what = "zone %s" % (net or (name[1] if name else "(unnamed)"))
        lay = find(z, "layer") or find(z, "layers")
        if lay is None:
            raise IRError("%s: missing (layer ...)" % what)
        polys = find_all(z, "polygon")
        if len(polys) != 1:
            raise IRError("%s: expected exactly one (polygon ...), found %d" % (what, len(polys)))
        fills = find_all(z, "filled_polygon")
        out.append({"net": net, "name": str(name[1]) if name else None,
                    "layers": _copper_layers(lay[1:], copper, what),
                    "keepout": find(z, "keepout") is not None, "filled": bool(fills),
                    "filled_area_mm2": _r(sum(abs(_area(_pts(f, what + " fill"))) for f in fills)),
                    "outline_area_mm2": _r(abs(_area(_pts(polys[0], what))))})
    out.sort(key=lambda z: (z["net"] or "", z["layers"], z["name"] or "", z["outline_area_mm2"]))
    return out


def _holes(pads, vias):
    count = {}
    for p in pads.values():
        if p["drill"] is not None:
            k = ("pad", p["type"] != "np_thru_hole", tuple(p["drill"]) if isinstance(p["drill"], list) else (p["drill"],))
            count[k] = count.get(k, 0) + 1
    for v in vias:
        k = ("via", True, (v["drill"],))
        count[k] = count.get(k, 0) + 1
    return [{"diameter": list(k[2]) if len(k[2]) == 2 else k[2][0], "plated": k[1], "kind": k[0], "count": n}
            for k, n in sorted(count.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2]))]


def parse_board(path):
    with open(path, encoding="utf-8") as f:
        text = f.read()
    try:
        root = parse(text)
    except (ValueError, IndexError) as e:
        raise IRError("%s: cannot parse S-expression: %s" % (path, e))
    if not isinstance(root, list) or not root or str(root[0]) != "kicad_pcb":
        raise IRError("%s: not a kicad_pcb file" % path)
    ver = find(root, "version")
    if ver is None or int(_n(ver[1], "version")) < MIN_VERSION:
        raise IRError("%s: file format version %s is older than %d (KiCad 8)" % (path, ver[1] if ver else "?", MIN_VERSION))
    for el in root[1:]:
        if not isinstance(el, list) or not el:
            raise IRError("%s: stray token %r at top level" % (path, el))
        if str(el[0]) not in _HANDLED and str(el[0]) not in _IGNORED:
            raise IRError("%s: unknown top-level element (%s ...) - extend from_kicad_pcb.py or the file is from a newer "
                          "KiCad" % (path, el[0]))
    copper = _layers(root)
    fps, pads = _footprints_and_pads(root, copper)
    tracks, vias = _tracks_and_vias(root, copper)
    return {"layers": {"copper": copper, "count": len(copper)}, "stackup": _stackup(root), "outline": _outline(root),
            "footprints": fps, "pads": pads, "zones": _zones(root, copper), "tracks": tracks, "vias": vias,
            "holes": _holes(pads, vias)}
