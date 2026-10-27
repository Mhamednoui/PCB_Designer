"""Print a footprint's real extent RELATIVE TO ITS ORIGIN, so you can place parts without guessing.

Why this exists: `placements()` in make_pcb.py positions a footprint by its **origin**, and the origin
is wherever the library author put it - it is NOT reliably the centre of the body. Two-pad THT parts
are the trap: `R_Axial_..._P10.16mm_Horizontal` has pad 1 at (0,0) and pad 2 at (+10.16, 0), so a
resistor "at x=47" actually occupies x=47..57.2 - about 5 mm further right than a centred part would.
Assuming centred origins put a mounting hole through a resistor pad in the blinky-555 build, which DRC
caught as `courtyards_overlap` + `pth_inside_courtyard`.

Read `origin` in the output as: "how far the part sticks out from the coordinate you place it at".
`centred: no` means the origin is off-centre by more than 0.5 mm - budget for it.

Usage:
    python tools/fp_bbox.py Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal
    python tools/fp_bbox.py Package_DIP:DIP-8_W7.62mm LED_THT:LED_D5.0mm
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boardgen.kicad_paths import FOOTPRINTS as KICAD_FOOTPRINTS  # noqa: E402


def _floats(pattern, text):
    return [(float(a), float(b)) for a, b in re.findall(pattern, text)]


def bbox(lib, name, project_dir=None):
    """(xmin, ymin, xmax, ymax) in mm relative to the footprint origin, from the courtyard if the
    footprint has one (that is what DRC actually tests) and from pads otherwise."""
    base = os.path.join(project_dir, "lib") if project_dir else KICAD_FOOTPRINTS
    path = os.path.join(base, lib + ".pretty", name + ".kicad_mod")
    if not os.path.isfile(path):
        raise SystemExit("no such footprint: %s" % path)
    text = open(path, encoding="utf-8").read()

    # Courtyard is the keep-out DRC actually compares between parts, so prefer it over the pad extent.
    # The layer is spelled "F.CrtYd"/"B.CrtYd" - NOT "Courtyard", which is what an earlier version of
    # this script looked for. It matched nothing, silently fell back to pads, and reported every part
    # as 0 mm tall. A filter that finds nothing must not look the same as a part with no courtyard.
    pts = []
    for chunk in text.split("(fp_")[1:]:
        body = chunk.split("(fp_")[0]
        if "CrtYd" not in body:
            continue
        got = _floats(r'\((?:start|end|center|mid|xy) ([-\d.]+) ([-\d.]+)\)', body)
        # A circle is stored as centre + a point on the rim, so its two stored points describe a
        # zero-height box. Expand it to the real disc, or a round part reports as flat.
        if chunk.startswith("circle") and len(got) >= 2:
            (cx0, cy0), (ex, ey) = got[0], got[1]
            r = ((ex - cx0) ** 2 + (ey - cy0) ** 2) ** 0.5
            got = [(cx0 - r, cy0 - r), (cx0 + r, cy0 + r)]
        pts += got
    if not pts and "CrtYd" in text:
        raise SystemExit("footprint has a courtyard layer but no geometry was parsed: " + path)

    pads = []
    for m in re.finditer(r'\(pad "([^"]*)"[^\n]*\n?[^\n]*?\(at ([-\d.]+) ([-\d.]+)', text):
        pads.append((m.group(1), float(m.group(2)), float(m.group(3))))
    if not pts:
        pts = [(x, y) for _, x, y in pads]
    if not pts:
        raise SystemExit("no courtyard and no pads in " + path)

    xs, ys = [p[0] for p in pts], [p[1] for p in pts]
    return (min(xs), min(ys), max(xs), max(ys)), pads


def report(spec, project_dir=None):
    lib, name = spec.split(":", 1)
    (x0, y0, x1, y1), pads = bbox(lib, name, project_dir)
    w, h = x1 - x0, y1 - y0
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    centred = abs(cx) <= 0.5 and abs(cy) <= 0.5

    print(spec)
    print("  size        %.2f x %.2f mm" % (w, h))
    print("  extent      x %+.2f .. %+.2f   y %+.2f .. %+.2f   (relative to the placement coordinate)"
          % (x0, x1, y0, y1))
    print("  centred     %s%s" % ("yes" if centred else "NO",
                                  "" if centred else "  <-- origin is off-centre by (%+.2f, %+.2f)" % (cx, cy)))
    if pads:
        print("  pads        " + ", ".join("%s@(%g,%g)" % p for p in pads[:8])
              + (" ..." if len(pads) > 8 else ""))
    print("  clearance   keep other parts' extents at least ~0.5 mm away from this box")
    print()


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    for spec in argv:
        if ":" not in spec:
            raise SystemExit("use lib:Footprint (got %r)" % spec)
        report(spec)


if __name__ == "__main__":
    main(sys.argv[1:])
