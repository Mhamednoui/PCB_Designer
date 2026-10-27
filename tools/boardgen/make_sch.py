"""Generate reflex-machine.kicad_sch from netlist.py.

Every connected pin gets a short wire + net label (or a power symbol for power nets);
every unused pin gets a no-connect flag. Parts are shelf-packed per functional group.
"""
import copy
import math
import os
import time
import sys

# Shared stage: the project comes from the argument or the working directory, not from where this
# file happens to live. See boardgen/project.py for why these scripts are no longer copied per project.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen import project as _project  # noqa: E402

HERE = _project.gen_dir(_project.project_id_from_argv(sys.argv))
NL = _project.load_netlist(_project.project_id_from_argv(sys.argv))
from boardgen.sexp import Sym, dumps, find, find_all, fmt, get_symbol, symbol_pins  # noqa: E402

ROOT = NL.uid("root")
POWER_SYMBOL = {"+12V": "power:+12V", "+5V": "power:+5V", "+3V3": "power:+3V3", "GND": "power:GND"}
PAGE_W = 1100.0
STUB = 2.54

_cache = {}


def lib_symbol(lib_id):
    if lib_id not in _cache:
        lib, name = lib_id.split(":")
        base = os.path.join(NL.PRJ_DIR, "lib") if lib in NL.PROJECT_LIBS else NL.KICAD_SYMBOLS
        _cache[lib_id] = get_symbol(os.path.join(base, lib + ".kicad_sym"), name)
    return _cache[lib_id]


def snap(v):
    return round(v / 2.54) * 2.54


def outward(rot):
    a = math.radians(rot)
    return (-int(round(math.cos(a))), int(round(math.sin(a))))


def body_bbox(sym):
    xs, ys = [], []

    def walk(node):
        for x in node:
            if isinstance(x, list) and x:
                if x[0] in ("property", "pin", "text"):
                    continue
                if x[0] in ("start", "end", "center", "mid", "xy") and len(x) >= 3:
                    try:
                        xs.append(float(x[1]))
                        ys.append(float(x[2]))
                    except ValueError:
                        pass
                walk(x)

    for sub in find_all(sym, "symbol"):
        walk(sub)
    for p in symbol_pins(sym):
        xs.append(p["x"])
        ys.append(p["y"])
    return min(xs), max(xs), min(ys), max(ys)


def extents(lib_id, pinmap):
    sym = lib_symbol(lib_id)
    minx, maxx, miny, maxy = body_bbox(sym)
    left, right, top, bottom = -minx, maxx, maxy, -miny
    for pin in symbol_pins(sym):
        net = pinmap.get(pin["number"])
        dx, dy = outward(pin["rot"])
        if net in POWER_SYMBOL:
            extra = STUB + 6.0
        elif net:
            extra = STUB + len(net) * 1.05 + 1.5
        else:
            extra = 1.0
        ex, ey = pin["x"] + dx * extra, -pin["y"] + dy * extra
        left, right = max(left, -ex), max(right, ex)
        top, bottom = max(top, -ey), max(bottom, ey)
    return left + 2.54, right + 2.54, top + 5.08, bottom + 5.08


class Out:
    def __init__(self):
        self.items = []
        self.n_pwr = 0
        self.n_flg = 0
        self.counter = 0

    def u(self, tag):
        self.counter += 1
        return NL.uid("sch", tag, str(self.counter))

    def wire(self, x1, y1, x2, y2):
        self.items.append('\t(wire (pts (xy %s %s) (xy %s %s)) (stroke (width 0) (type default)) (uuid "%s"))'
                          % (fmt(x1), fmt(y1), fmt(x2), fmt(y2), self.u("w")))

    def label(self, name, x, y, dx, dy):
        ang = {(1, 0): 0, (-1, 0): 180, (0, -1): 90, (0, 1): 270}[(dx, dy)]
        just = "left bottom" if ang in (0, 90) else "right bottom"
        self.items.append('\t(label "%s" (at %s %s %d) (effects (font (size 1.27 1.27)) (justify %s)) (uuid "%s"))'
                          % (name, fmt(x), fmt(y), ang, just, self.u("l")))

    def noconnect(self, x, y):
        self.items.append('\t(no_connect (at %s %s) (uuid "%s"))' % (fmt(x), fmt(y), self.u("nc")))

    def text(self, s, x, y, size=2.54):
        self.items.append('\t(text "%s" (exclude_from_sim no) (at %s %s 0) (effects (font (size %s %s) (bold yes)) (justify left bottom)) (uuid "%s"))'
                          % (s, fmt(x), fmt(y), fmt(size), fmt(size), self.u("t")))

    def symbol(self, lib_id, ref, value, x, y, rot=0, footprint="", lcsc="", in_bom=True, sym_uuid=None):
        sym = lib_symbol(lib_id)
        sym_uuid = sym_uuid or self.u("sym")
        minx, maxx, miny, maxy = body_bbox(sym)
        props = []
        for p in find_all(sym, "property"):
            node = copy.deepcopy(p)
            key = node[1]
            # `ki_fp_filters` is a LIBRARY-only hint (which footprints the chooser offers for this
            # symbol). Copying it onto a placed instance makes KiCad's schematic-parity check report
            # "Missing symbol field 'ki_fp_filters' in footprint" for every part on the board - 9
            # warnings on a 9-part board, which buries the parity problems that actually matter.
            if key in ("ki_fp_filters", "ki_locked"):
                continue
            at = find(node, "at")
            if key == "Reference":
                node[2] = ref
                at[1:4] = [x + maxx + 1.27, y - 1.27, 0] if not ref.startswith("#") else [x, y + 3.5, 0]
            elif key == "Value":
                node[2] = value
                at[1:4] = [x + maxx + 1.27, y + 1.27, 0] if not ref.startswith("#") else [x, y + 5.5, 0]
            else:
                if key == "Footprint" and footprint:
                    node[2] = footprint
                at[1:4] = [x, y, 0]
            if key in ("Reference", "Value") and not ref.startswith("#"):
                eff = find(node, "effects")
                if eff is not None:
                    j = find(eff, "justify")
                    if j is None:
                        eff.append([Sym("justify"), Sym("left")])
                    else:
                        j[1:] = [Sym("left")]
            at[1] = float(at[1])
            at[2] = float(at[2])
            props.append(node)
        if lcsc:
            ds = copy.deepcopy(next(p for p in props if p[1] == "Datasheet"))
            ds[1] = "LCSC"
            ds[2] = lcsc
            props.append(ds)
        lines = ['\t(symbol (lib_id "%s") (at %s %s %d) (unit 1) (exclude_from_sim no) (in_bom %s) (on_board yes) (dnp no) (uuid "%s")'
                 % (lib_id, fmt(x), fmt(y), rot, "yes" if in_bom else "no", sym_uuid)]
        for p in props:
            lines.append("\t\t" + dumps(p, 2))
        numbers = sorted({p["number"] for sub_unit in [1] for p in symbol_pins(sym, sub_unit)})
        for n in numbers:
            lines.append('\t\t(pin "%s" (uuid "%s"))' % (n, self.u("pin")))
        lines.append('\t\t(instances (project "%s" (path "/%s" (reference "%s") (unit 1))))' % (NL.PRJ_NAME, ROOT, ref))
        lines.append("\t)")
        self.items.append("\n".join(lines))

    def power(self, net, x, y, dx, dy):
        self.n_pwr += 1
        lib_id = POWER_SYMBOL[net]
        if net == "GND":
            rot = {(0, 1): 0, (1, 0): 90, (0, -1): 180, (-1, 0): 270}[(dx, dy)]
        else:
            rot = {(0, -1): 0, (-1, 0): 90, (0, 1): 180, (1, 0): 270}[(dx, dy)]
        self.symbol(lib_id, "#PWR%03d" % self.n_pwr, net, x, y, rot, in_bom=False)

    def connect_pins(self, lib_id, pinmap, x, y):
        for pin in symbol_pins(lib_symbol(lib_id)):
            px, py = x + pin["x"], y - pin["y"]
            net = pinmap.get(pin["number"])
            if not net:
                self.noconnect(px, py)
                continue
            dx, dy = outward(pin["rot"])
            sx, sy = px + dx * STUB, py + dy * STUB
            self.wire(px, py, sx, sy)
            if net in POWER_SYMBOL:
                self.power(net, sx, sy, dx, dy)
            else:
                self.label(net, sx, sy, dx, dy)


def main():
    o = Out()
    by_group = {}
    for p in NL.PARTS:
        by_group.setdefault(p["group"], []).append(p)

    x0 = 25.4
    cy = 30.48
    for gkey, title in NL.GROUPS:
        o.text(title, x0, cy, 3.0)
        cy += 7.62
        rx, row_h = x0, 0.0
        for p in by_group.get(gkey, []):
            l, r, t, b = extents(p["lib_id"], p["pins"])
            if rx + l + r > PAGE_W - 25 and rx > x0:
                cy += row_h + 5.08
                rx, row_h = x0, 0.0
            ox, oy = snap(rx + l), snap(cy + t)
            o.symbol(p["lib_id"], p["ref"], p["value"], ox, oy, 0, p["footprint"], p["lcsc"],
                     sym_uuid=NL.uid("sym", p["ref"]))
            o.connect_pins(p["lib_id"], p["pins"], ox, oy)
            rx = ox + r + 5.08
            row_h = max(row_h, oy + b - cy)
        cy += row_h + 15.24

    # power flags
    o.text("POWER FLAGS", x0, cy, 3.0)
    cy += 10.16
    fx = x0 + 10.16
    for net in NL.POWER_FLAG_NETS:
        o.n_flg += 1
        x, y = snap(fx), snap(cy)
        o.symbol("power:PWR_FLAG", "#FLG%02d" % o.n_flg, "PWR_FLAG", x, y, 0, in_bom=False)
        o.wire(x, y, x, y + STUB)
        if net in POWER_SYMBOL:
            o.power(net, x, y + STUB, 0, 1)
        else:
            o.label(net, x, y + STUB, 0, 1)
        fx += 25.4
    cy += 25.4

    used = sorted({p["lib_id"] for p in NL.PARTS} | set(POWER_SYMBOL.values()) | {"power:PWR_FLAG"})
    libsyms = []
    for lib_id in used:
        s = copy.deepcopy(lib_symbol(lib_id))
        s[1] = lib_id
        libsyms.append("\t\t" + dumps(s, 2))

    height = max(841.0, cy + 40)
    paper = '(paper "User" %s %s)' % (fmt(PAGE_W + 60), fmt(snap(height)))
    head = [
        "(kicad_sch",
        "\t(version 20250114)",
        '\t(generator "eeschema")',
        '\t(generator_version "10.0")',
        '\t(uuid "%s")' % ROOT,
        "\t" + paper,
        # Title block comes from netlist.py so this script stays board-agnostic (it was hardcoded to
        # the Reflex Machine before this project reused it).
        '\t(title_block (title "%s") (date "%s") (rev "%s") '
        '(comment 1 "%s") '
        '(comment 2 "Generated from gen/netlist.py - firmware pin map unchanged"))' % (
            getattr(NL, "SCH_TITLE", NL.PRJ_NAME),
            getattr(NL, "SCH_DATE", time.strftime("%Y-%m-%d")),
            getattr(NL, "SCH_REV", "1.0"),
            getattr(NL, "SCH_SUBTITLE", ""),
        ),
        "\t(lib_symbols",
    ]
    text = "\n".join(head + libsyms + ["\t)"] + o.items +
                     ['\t(sheet_instances (path "/" (page "1")))', "\t(embedded_fonts no)", ")"]) + "\n"
    path = os.path.join(NL.PRJ_DIR, NL.PRJ_NAME + ".kicad_sch")
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)
    print("wrote %s (%d items, sheet %.0fx%.0f mm)" % (path, len(o.items), PAGE_W + 60, height))


if __name__ == "__main__":
    main()
