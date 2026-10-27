"""Fab limits + per-net current-based track widths, written as the project's `.kicad_dru`.

KiCad's DRC reads `<project>.kicad_dru` next to `<project>.kicad_pro` (custom rules). Generating it from
`netlist.py` makes the design intent (how much current a net carries) something DRC actually enforces,
instead of a netclass default that any router or hand edit can undercut silently.

    from boardgen import fab_rules
    fab_rules.write_rules(project_dir, NL)        # -> (path of the .kicad_dru, requirements)
    fab_rules.requirements(NL, pcb_path)          # -> [{net, i_max, dT, width, poured, layers}, ...]

Reads the optional `NL.NET_SPEC` (see ROADMAP.md, "NET_SPEC contract"):
    NET_SPEC = {"VCC": {"v": (9.0, 12.0), "i_max": 0.05, "dT": 20}, "GND": {"v": 0.0}}
Undeclared nets: voltage inferred from the name (GND=0, +5V=5, +3V3=3.3, +12V=12), i_max = 0.3 A.
Board-level knobs, also in netlist.py (all optional):
    COPPER_OZ = 1        outer copper weight, 1 or 2 oz (IPC-2221 thickness; 2 oz also raises the min track)
    TEMP_RISE_C = 10     allowed temperature rise; NET_SPEC[net]["dT"] overrides it for one net
Nets with a copper zone on the board carry their current in the pour, so their rule is a WARNING (listed
by fabreport for review, never dropped); stub-routed nets keep ERROR severity.

Pure Python, no pcbnew: importable from any stage, and from the unit test (`python fab_rules.py`).
"""
import math
import os
import re

# JLCPCB 2-layer standard service (https://jlcpcb.com/capabilities/pcb-capabilities). The fab's absolute
# minimum is in the comment; the value is what we enforce, chosen safer than the minimum.
LIMITS = {
    "track": 0.15,          # fab min 0.10 (1 oz)
    "clearance": 0.15,      # fab min 0.10
    "annular": 0.18,        # PTH pad ring: fab absolute min 0.18 (error)
    "annular_preferred": 0.25,   # PTH pad ring: recommended, warning only
    "via_annular": 0.10,    # via ring: fab allows a 0.25 mm via on a 0.15 drill; 0.6/0.3 vias (0.15) are normal
    "hole_to_hole": 0.45,   # PTH pad hole-to-hole; via-to-via is 0.20 (separate rule)
    "via_hole_to_hole": 0.20,
    "edge_clearance": 0.3,  # fab min 0.20 for a routed edge
    "silk_text": 1.0,       # text height; fab minimum
}
DEFAULT_I_MAX = 0.3         # A, for a net NET_SPEC does not declare
DEFAULT_COPPER_OZ = 1.0
DEFAULT_TEMP_RISE_C = 10.0
GLOBAL_NETS = ("+12V", "+5V", "+3V3", "GND")   # power-symbol nets have no "/" on the board (LESSONS s11)

_INFER_V = {"GND": 0.0, "+5V": 5.0, "+3V3": 3.3, "+12V": 12.0}


def ipc2221_width_mm(i_amps, rise_c=10.0, oz=1.0, external=True):
    """Minimum trace width in mm for i_amps, IPC-2221: I = k * dT^0.44 * A^0.725 (A in mil^2).
    k = 0.048 external, 0.024 internal; copper thickness 1.378 mil per oz (35 um)."""
    if i_amps <= 0:
        return 0.0
    k = 0.048 if external else 0.024
    area_mil2 = (i_amps / (k * rise_c ** 0.44)) ** (1.0 / 0.725)
    width_mil = area_mil2 / (1.378 * oz)
    return width_mil * 0.0254


def params(NL):
    """Board-level parameters from netlist.py (defaults when absent): copper weight (oz), temp rise (C)."""
    oz = float(getattr(NL, "COPPER_OZ", DEFAULT_COPPER_OZ))
    if oz not in (1.0, 2.0):
        raise ValueError("COPPER_OZ must be 1 or 2 (JLCPCB 2-layer outer copper), got %r" % oz)
    return {"oz": oz, "rise_c": float(getattr(NL, "TEMP_RISE_C", DEFAULT_TEMP_RISE_C))}


def min_width(oz):
    """Default track width / clearance we enforce. JLCPCB's 2 oz minimum is 0.16 mm, so use 0.20 there."""
    return LIMITS["track"] if oz <= 1.0 else 0.20


def describe_params(NL):
    p = params(NL)
    per_net = sorted(n for n, s in (getattr(NL, "NET_SPEC", {}) or {}).items() if "dT" in s)
    return "copper %g oz, temp rise %g C%s, IPC-2221 external layer" % (
        p["oz"], p["rise_c"], (" (per-net dT: %s)" % ", ".join(per_net)) if per_net else "")


def net_spec(NL):
    """Merged NET_SPEC for every net in the netlist: {net: {"v", "i_max" (A), "dT" (C)}} with defaults applied."""
    declared = getattr(NL, "NET_SPEC", {}) or {}
    rise = params(NL)["rise_c"]
    out = {}
    for n in sorted(NL.nets()):
        s = declared.get(n, {})
        v = s.get("v", _INFER_V.get(n, _INFER_V.get(n.upper())))
        out[n] = {"v": v, "i_max": float(s.get("i_max", DEFAULT_I_MAX)), "dT": float(s.get("dT", rise))}
    return out


def board_net_name(name, global_nets=GLOBAL_NETS):
    """Name on the .kicad_pcb: label nets carry eeschema's leading '/', power-symbol nets do not."""
    return name if name in global_nets else "/" + name


_ZONE = re.compile(r'\(zone\s+\(net "([^"]*)"\)\s+\(layers?\s+([^)]*)\)')


def pour_layers(pcb_path):
    """{board net name: [layers]} for every copper zone that has a net (rule areas have none).
    Read from the .kicad_pcb text, so it needs no pcbnew and works on any board."""
    out = {}
    if pcb_path and os.path.isfile(pcb_path):
        with open(pcb_path, encoding="utf-8") as f:
            text = f.read()
        for net, layers in _ZONE.findall(text):
            if net:
                out.setdefault(net, [])
                out[net] += [l for l in re.findall(r'"([^"]+)"', layers) if l not in out[net]]
    return out


def requirements(NL, pcb_path=None, global_nets=GLOBAL_NETS):
    """Nets that need more than the default track width, sorted by name:
    [{net, board_net, i_max, dT, width (mm, rounded UP to 0.01), poured, layers}].
    `poured` = the board has a copper zone on that net, so the pour carries the current, not each stub."""
    oz = params(NL)["oz"]
    poured = pour_layers(pcb_path)
    out = []
    for n, s in net_spec(NL).items():
        w = math.ceil(ipc2221_width_mm(s["i_max"], s["dT"], oz) * 100 - 1e-9) / 100.0
        if w > min_width(oz) + 1e-9:
            bn = board_net_name(n, global_nets)
            out.append(dict(net=n, board_net=bn, i_max=s["i_max"], dT=s["dT"], width=w,
                            poured=bn in poured, layers=poured.get(bn, [])))
    return out


def net_widths(NL, global_nets=GLOBAL_NETS):
    """{schematic net name: required width mm} - what the route stage should not undercut."""
    return {r["net"]: r["width"] for r in requirements(NL, None, global_nets)}


def render(reqs, oz=1.0, rise_c=10.0):
    """The .kicad_dru text. Deterministic (no timestamps) so a regenerated file never dirties git."""
    mw = min_width(oz)
    L = ["(version 1)",
         "# GENERATED by tools/boardgen/fab_rules.py - do not edit; change NET_SPEC / COPPER_OZ / TEMP_RISE_C",
         "# in gen/netlist.py. JLCPCB 2-layer limits (safer than the fab minimum) + per-net minimum track",
         "# width from NET_SPEC i_max via IPC-2221 (external layer, %g C rise, %g oz). KiCad's board-setup" % (rise_c, oz),
         "# minimums in the .kicad_pro still apply on top: no custom rule can loosen them.",
         ""]

    def rule(name, constraint, condition=None, severity="error"):
        # Explicit severity: board-setup defaults can be "warning" (hole_to_hole is, in our .kicad_pro),
        # and a fab limit that only warns would not gate `check`.
        L.append('(rule "%s"' % name)
        L.append("  (severity %s)" % severity)
        if condition:
            L.append('  (condition "%s")' % condition)
        L.append("  (constraint %s))" % constraint)

    rule("jlc_min_track", "track_width (min %gmm)" % mw)
    rule("jlc_min_clearance", "clearance (min %gmm)" % mw)
    rule("jlc_annular_min", "annular_width (min %gmm)" % LIMITS["annular"], condition="A.Type == 'Pad'")
    rule("jlc_via_annular_min", "annular_width (min %gmm)" % LIMITS["via_annular"], condition="A.Type == 'Via'")
    rule("jlc_annular_preferred", "annular_width (min %gmm)" % LIMITS["annular_preferred"],
         condition="A.Type == 'Pad'", severity="warning")
    rule("jlc_hole_to_hole", "hole_to_hole (min %gmm)" % LIMITS["hole_to_hole"],
         condition="A.Type != 'Via' || B.Type != 'Via'")
    rule("jlc_via_hole_to_hole", "hole_to_hole (min %gmm)" % LIMITS["via_hole_to_hole"],
         condition="A.Type == 'Via' && B.Type == 'Via'")
    rule("jlc_copper_to_edge", "edge_clearance (min %gmm)" % LIMITS["edge_clearance"])
    rule("jlc_silk_text_height", "text_height (min %gmm)" % LIMITS["silk_text"],
         condition="A.Layer == 'F.Silkscreen' || A.Layer == 'B.Silkscreen'", severity="warning")
    if reqs:
        L.append("")
        L.append("# Current-carrying nets: minimum track width = IPC-2221 for NET_SPEC i_max.")
        L.append("# A net with a copper pour on the board carries its total current in the pour, not in every")
        L.append("# stub, so its rule is only a WARNING. fabreport lists those nets for review; they are not dropped.")
    for r in sorted(reqs, key=lambda r: r["net"]):
        bn = r["board_net"]
        if "'" in bn:
            raise ValueError("net name with a quote cannot be used in a DRC condition: %r" % bn)
        if r["poured"]:
            L.append("# %s: i_max %g A, poured on %s -> warning" % (r["net"], r["i_max"], "+".join(r["layers"])))
        rule("current_%s" % re.sub(r"[^A-Za-z0-9_]", "_", r["net"]), "track_width (min %gmm)" % r["width"],
             condition="A.NetName == '%s'" % bn, severity="warning" if r["poured"] else "error")
    return "\n".join(L) + "\n"


def write_rules(project_dir, NL, global_nets=GLOBAL_NETS):
    """Write `<project>.kicad_dru` in project_dir, reading the board's zones to tell poured nets from
    stub-routed ones. Returns (path, requirements)."""
    p = params(NL)
    pcb_path = os.path.join(project_dir, NL.PRJ_NAME + ".kicad_pcb")
    reqs = requirements(NL, pcb_path, global_nets)
    path = os.path.join(project_dir, NL.PRJ_NAME + ".kicad_dru")
    text = render(reqs, p["oz"], p["rise_c"])
    old = None
    if os.path.exists(path):
        with open(path, encoding="utf-8", newline="") as f:
            old = f.read()
    if old != text:                       # leave the mtime alone when nothing changed
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
    return path, reqs


def _selftest():
    w1 = ipc2221_width_mm(1.0)
    assert abs(w1 - 0.30) < 0.01, w1                      # 1 A, 10 C, 1 oz, external ~ 0.30 mm
    assert ipc2221_width_mm(2.0) > 2 * w1 * 0.9           # width grows faster than linearly with I (I^1.38)
    assert ipc2221_width_mm(1.0, external=False) > w1     # internal layers need more copper
    assert ipc2221_width_mm(1.0, oz=2.0) < w1             # thicker copper needs less width
    assert ipc2221_width_mm(1.0, rise_c=20.0) < w1        # a hotter trace may be narrower

    class _NL:
        PRJ_NAME = "t"
        NET_SPEC = {"VCC": {"i_max": 1.0}, "SIG": {"i_max": 0.05}, "HOT": {"i_max": 1.0, "dT": 30.0}}

        @staticmethod
        def nets():
            return ["GND", "VCC", "SIG", "+5V", "HOT"]
    rq = {r["net"]: r for r in requirements(_NL)}
    assert sorted(rq) == ["HOT", "VCC"], rq                # GND/+5V default 0.3 A -> 0.06 mm < 0.15, SIG too
    assert rq["HOT"]["width"] < rq["VCC"]["width"]         # per-net dT override
    txt = render(list(rq.values()))
    assert "A.NetName == '/VCC'" in txt and "A.NetName == '+5V'" not in txt   # label net carries the '/'
    rq["VCC"]["poured"], rq["VCC"]["layers"] = True, ["F.Cu"]
    t2 = render(list(rq.values()))
    assert t2.count("(severity warning)") == txt.count("(severity warning)") + 1   # poured -> warning
    print("fab_rules selftest OK: 1 A -> %.3f mm; widths %s" % (w1, {n: r["width"] for n, r in rq.items()}))


if __name__ == "__main__":
    _selftest()
