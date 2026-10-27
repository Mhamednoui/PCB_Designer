"""Connection list in plain words: every pin of every part, and where its copper goes.

    "C:\\Program Files\\KiCad\\10.0\\bin\\python.exe" tools/boardgen/make_connections.py <project-id>

Writes projects/<id>/CONNECTIONS.md for someone who does NOT read PCB layouts. "Q1 leg G -> R11 leg 2"
can be compared against a datasheet picture or a real part in your hand.

Two sources, on purpose:
  - WHERE each pin goes comes from the .kicad_pcb - the copper the factory actually makes.
  - WHAT each pin is called (G/D/S, VIN, IO16) comes from the schematic, exported by kicad-cli.
Every pin is then cross-checked between the two, which is an independent check that the board is the
schematic. Parts drawn for this project (project-local libraries) are flagged first: those are the ones
no library maintainer has ever checked against the real part.
"""
import collections
import os
import re
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET

import pcbnew

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen.project import PROJECTS  # noqa: E402
from boardgen.kicad_paths import CLI as KICAD_CLI  # noqa: E402
from boardgen.make_fab_report import find_pcb  # noqa: E402

RAIL_NAMES = {"GND": "ground", "+5V": "5 V supply", "+12V": "12 V supply", "+3V3": "3.3 V supply",
              "VCC": "supply (VCC)"}
BIG_NET = 8          # more pins than this: summarise instead of listing every one
KIND_BY_PREFIX = {"R": "resistor", "C": "capacitor", "D": "diode / LED", "Q": "transistor", "U": "IC / module",
                  "J": "connector / terminal", "A": "plug-in board", "F": "fuse", "SW": "switch", "H": "mounting hole",
                  "L": "inductor", "Y": "crystal", "K": "relay"}


def clean(net):
    return net.lstrip("/") if net else ""


def natural(ref):
    m = re.match(r"([A-Za-z]+)(\d+)", ref)
    return (m.group(1), int(m.group(2))) if m else (ref, 0)


def pin_key(num):
    return (0, int(num), "") if num.isdigit() else (1, 0, num)


def schematic_pins(sch_path):
    """{(ref, pin): (pin name, pin type, net)} and {ref: description} from kicad-cli's XML netlist."""
    out = os.path.join(tempfile.gettempdir(), "connections_netlist.xml")
    subprocess.run([KICAD_CLI, "sch", "export", "netlist", "--format", "kicadxml", "-o", out, sch_path],
                   capture_output=True, timeout=300)
    if not os.path.isfile(out):
        return {}, {}
    root = ET.parse(out).getroot()
    os.remove(out)
    pins, desc = {}, {}
    for comp in root.iter("comp"):
        lib = comp.find("libsource")
        d = comp.findtext("description") or (lib.get("description") if lib is not None else "") or ""
        desc[comp.get("ref")] = d
    for net in root.iter("net"):
        for node in net.iter("node"):
            num = node.get("pin")
            # KiCad 10 reports pinfunction as "<name>_<number>" (e.g. "G_1", "D2_INT0_D2") - strip the
            # glued-on number so the list reads like a datasheet.
            name = re.sub(r"_%s$" % re.escape(num), "", node.get("pinfunction") or "")
            name = re.sub(r"~\{([^}]*)\}", r"\1 (active-low)", name)   # KiCad overbar markup
            pins[(node.get("ref"), num)] = (name.replace("_", " "), node.get("pintype") or "",
                                            clean(net.get("name")))
    return pins, desc


def project_libs(project_dir):
    table = os.path.join(project_dir, "fp-lib-table")
    if not os.path.isfile(table):
        return set()
    return set(re.findall(r'\(lib \(name "([^"]+)"\)', open(table, encoding="utf-8").read()))


def build(project):
    pcb_path = find_pcb(project)
    pdir = os.path.dirname(pcb_path)
    sch_path = os.path.splitext(pcb_path)[0] + ".kicad_sch"
    sch, desc = schematic_pins(sch_path) if os.path.isfile(sch_path) else ({}, {})
    custom_libs = project_libs(pdir)
    board = pcbnew.LoadBoard(pcb_path)

    # Copper truth: which pads share each net on the real board.
    fps = sorted(board.GetFootprints(), key=lambda f: natural(f.GetReference()))
    net_pads = collections.defaultdict(list)
    for fp in fps:
        for p in fp.Pads():
            if p.GetNumber() and p.GetNetname():
                net_pads[clean(p.GetNetname())].append((fp.GetReference(), p.GetNumber()))

    def pin_label(ref, num):
        name = sch.get((ref, num), ("", "", ""))[0]
        return "%s pin %s" % (ref, num) + (" (%s)" % name if name and name != num else "")

    mismatches = []
    sections = []
    for fp in fps:
        ref = fp.GetReference()
        pads = sorted({p.GetNumber(): p for p in fp.Pads() if p.GetNumber()}.values(),
                      key=lambda p: pin_key(p.GetNumber()))
        if not pads:
            continue                     # mounting holes etc. - nothing to connect
        lib = str(fp.GetFPID().GetLibNickname())
        prefix = re.match(r"[A-Za-z]+", ref).group(0)
        rows = []
        for p in pads:
            num = p.GetNumber()
            net = clean(p.GetNetname())
            name, ptype, sch_net = sch.get((ref, num), ("", "", ""))
            unconnected = not net or net.startswith("unconnected-")
            if sch and not unconnected and sch_net and sch_net != net:
                mismatches.append("%s pin %s: schematic says %s, board copper says %s" % (ref, num, sch_net, net))
            if unconnected:
                where = "*not connected (free pin)*"
            else:
                others = [x for x in net_pads[net] if x != (ref, num)]
                if not others:
                    where = "**%s - goes nowhere else!**" % net
                elif len(others) > BIG_NET:
                    where = "**%s** - %s, shared with %d other pins" % (
                        net, RAIL_NAMES.get(net, "a shared line"), len(others))
                else:
                    where = "**%s** → %s" % (net, ", ".join(pin_label(r, n) for r, n in others))
            rows.append("| %s | %s | %s |" % (num, name if name and name != num else "", where))
        custom = lib in custom_libs
        check_first = custom or prefix in ("Q", "U", "A")
        title = "### %s - %s" % (ref, fp.GetValue())
        info = "%s · footprint `%s:%s`%s" % (
            KIND_BY_PREFIX.get(prefix, KIND_BY_PREFIX.get(prefix[:1], "part")), lib, fp.GetFPID().GetLibItemName(),
            " · %s" % desc[ref] if desc.get(ref) else "")
        flag = ""
        if custom:
            flag = ("> **Not from KiCad's standard library** (project library `%s` - drawn here or downloaded). "
                    "Nobody at KiCad has checked it: compare every pin below with a photo or the pinout of "
                    "YOUR real part." % lib)
        elif check_first:
            flag = "> Compare the pin order with the part's datasheet picture."
        body = [title, "", info, ""] + ([flag, ""] if flag else []) + \
               ["| Pin | Name | Goes to |", "|---|---|---|"] + rows + [""]
        sections.append((0 if custom else 1 if check_first else 2, natural(ref), body))

    L = ["# %s - every connection, in plain words" % project, "",
         "_Generated %s by `tools/boardgen/make_connections.py` from the real board copper "
         "(`%s`), with pin names from the schematic. Regenerate: `python pipeline.py %s --only connections`._"
         % (time.strftime("%Y-%m-%d %H:%M"), os.path.basename(pcb_path), project), "",
         "## How to use this file", "",
         "You don't need to read the PCB. Each part below lists its pins and where each pin's copper goes.",
         "",
         "1. Start with **Check these first** - parts where a wrong pin order would really matter.",
         "2. For each, open the datasheet picture (or look at your real part) and confirm the pin names match: "
         "e.g. a MOSFET's pin 1 really is G (gate).",
         "3. When the board arrives, use a multimeter in beep mode: two pins listed as connected must beep.",
         "   Two pins that are NOT listed together must not beep.",
         "",
         "## Automatic cross-check", ""]
    if sch:
        if mismatches:
            L.append("**%d pin(s) differ between the schematic and the board copper - do not order:**" % len(mismatches))
            L += ["- %s" % m for m in mismatches]
        else:
            L.append("Every pin on the board copper goes to the same net as in the schematic: "
                     "**%d pins checked, 0 differences.**" % sum(1 for k in sch))
    else:
        L.append("No schematic found - pin names and the cross-check are unavailable.")
    L.append("")
    groups = {0: "## Check these first - parts not from KiCad's standard library", 1: "## Check these next - transistors, ICs, modules",
              2: "## Everything else"}
    for level in (0, 1, 2):
        chunk = [s for s in sections if s[0] == level]
        if chunk:
            L += [groups[level], ""]
            for _, _, body in sorted(chunk, key=lambda s: s[1]):
                L += body
    out = os.path.join(pdir, "CONNECTIONS.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(L))
    print("wrote %s" % out)
    print("  %d parts, %d pins cross-checked, %d mismatches, %d parts from project-local libraries"
          % (len(sections), len(sch), len(mismatches), sum(1 for s in sections if s[0] == 0)))
    return 1 if mismatches else 0


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: make_connections.py <project-id>")
    sys.exit(build(sys.argv[1]))
