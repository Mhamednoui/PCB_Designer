"""Manufacturing + documentation outputs into out/fab and out/docs.

- Gerbers + drill (zipped for JLCPCB upload)
- JLCPCB BOM (Comment, Designator, Footprint, LCSC Part #) and CPL (SMD parts only)
- Full BOM (every part incl. hand-soldered)
- STEP 3D model, 3D renders, schematic PDF
"""
import csv
import os
import shutil
import subprocess
import sys
import zipfile

# Shared stage: the project comes from the argument or the working directory, not from where this
# file happens to live. See boardgen/project.py for why these scripts are no longer copied per project.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen import project as _project  # noqa: E402

HERE = _project.gen_dir(_project.project_id_from_argv(sys.argv))
NL = _project.load_netlist(_project.project_id_from_argv(sys.argv))

from boardgen.kicad_paths import CLI  # noqa: E402  - resolved once, see kicad_paths.py
PCB = os.path.join(NL.PRJ_DIR, NL.PRJ_NAME + ".kicad_pcb")
SCH = os.path.join(NL.PRJ_DIR, NL.PRJ_NAME + ".kicad_sch")
FAB = os.path.join(NL.PRJ_DIR, "out", "fab")
DOCS = os.path.join(NL.PRJ_DIR, "out", "docs")
GERB = os.path.join(FAB, "gerbers")


FAILED = []


def run(args):
    r = subprocess.run([CLI] + args, capture_output=True, text=True)
    if r.returncode != 0:
        FAILED.append(" ".join(args[:3]))
    status = "ok" if r.returncode == 0 else "FAILED (%d) %s" % (r.returncode, (r.stdout + r.stderr).strip()[-400:])
    print("%-12s %s" % (args[1] if args[0] == "sch" else args[2], status))
    return r


for d in (GERB,):
    shutil.rmtree(d, ignore_errors=True)
for d in (FAB, DOCS, GERB):
    os.makedirs(d, exist_ok=True)

def copper_layers():
    """The board's real copper layers, in order.

    This MUST come from the board, never from a hardcoded list. An earlier version named
    "F.Cu,B.Cu,..." literally, which silently produced a fab package with NO INNER COPPER for any
    4-layer board - the gerbers would look fine, upload fine, and come back as the wrong board.
    Verified on a 4-layer test board: KiCad emits In1_Cu as `.g1` and In2_Cu as `.g2`.
    """
    import pcbnew
    b = pcbnew.LoadBoard(PCB)
    n = b.GetCopperLayerCount()
    inner = ["In%d.Cu" % i for i in range(1, n - 1)]
    return ["F.Cu"] + inner + ["B.Cu"]


LAYERS = copper_layers() + ["F.Paste", "B.Paste", "F.Silkscreen", "B.Silkscreen",
                            "F.Mask", "B.Mask", "Edge.Cuts"]
print("copper layers: %s" % ", ".join(copper_layers()))

# Gerbers + drill
run(["pcb", "export", "gerbers", "-o", GERB, "--layers", ",".join(LAYERS),
     "--subtract-soldermask", "--use-drill-file-origin", PCB])
run(["pcb", "export", "drill", "-o", GERB + os.sep, "--format", "excellon", "--excellon-units", "mm",
     "--drill-origin", "plot", "--generate-map", "--map-format", "gerberx2", PCB])
zpath = os.path.join(FAB, NL.PRJ_NAME + "_gerbers_JLCPCB.zip")
with zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as z:
    for fn in sorted(os.listdir(GERB)):
        z.write(os.path.join(GERB, fn), fn)
print("zip          ", zpath)

# Position file -> JLCPCB CPL (SMD parts that have an LCSC number)
pos_csv = os.path.join(FAB, "positions_raw.csv")
run(["pcb", "export", "pos", "-o", pos_csv, "--format", "csv", "--units", "mm", "--side", "both",
     "--smd-only", "--use-drill-file-origin", PCB])
lcsc = {p["ref"]: p for p in NL.PARTS}
cpl_rows = []
with open(pos_csv, newline="", encoding="utf-8") as f:
    for row in csv.DictReader(f):
        ref = row["Ref"]
        if ref in lcsc and lcsc[ref]["lcsc"]:
            cpl_rows.append([ref, row["PosX"] + "mm", row["PosY"] + "mm",
                             "Top" if row["Side"].lower().startswith("top") else "Bottom", row["Rot"]])
with open(os.path.join(FAB, "CPL_JLCPCB.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Designator", "Mid X", "Mid Y", "Layer", "Rotation"])
    w.writerows(sorted(cpl_rows, key=lambda r: r[0]))
smd_refs = {r[0] for r in cpl_rows}

# BOMs
def natural(ref):
    head = ref.rstrip("0123456789")
    return head, int(ref[len(head):] or 0)


groups = {}
for p in NL.PARTS:
    key = (p["value"], p["footprint"], p["lcsc"])
    groups.setdefault(key, []).append(p["ref"])
with open(os.path.join(FAB, "BOM_JLCPCB.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Comment", "Designator", "Footprint", "LCSC Part #"])
    for (value, fp, part_no), refs in sorted(groups.items(), key=lambda kv: natural(sorted(kv[1], key=natural)[0])):
        refs = [r for r in refs if r in smd_refs]
        if refs:
            w.writerow([value, ",".join(sorted(refs, key=natural)), fp.split(":")[1], part_no])
with open(os.path.join(DOCS, "BOM_full.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.writer(f)
    w.writerow(["Qty", "Value", "Designators", "Footprint", "LCSC", "Assembly"])
    for (value, fp, part_no), refs in sorted(groups.items(), key=lambda kv: natural(sorted(kv[1], key=natural)[0])):
        refs = sorted(refs, key=natural)
        how = "JLCPCB (SMD)" if all(r in smd_refs for r in refs) else "hand solder / plug-in"
        w.writerow([len(refs), value, ",".join(refs), fp.split(":")[1], part_no, how])

# 3D + docs
run(["pcb", "export", "step", "-f", "--subst-models", "-o", os.path.join(DOCS, NL.PRJ_NAME + ".step"), PCB])
run(["sch", "export", "pdf", "-o", os.path.join(DOCS, NL.PRJ_NAME + "_schematic.pdf"), SCH])
for name, extra in (("top", ["--side", "top"]), ("bottom", ["--side", "bottom"]),
                    ("iso", ["--side", "top", "--rotate", "-50,0,25", "--perspective", "--zoom", "0.85"])):
    run(["pcb", "render", "-o", os.path.join(DOCS, "render_%s.png" % name), "-w", "2000", "-h", "1800",
         "--quality", "high", "--floor"] + extra + [PCB])
print("done ->", FAB, "and", DOCS)
if FAILED:
    sys.exit("FAILED: %d export(s) failed: %s" % (len(FAILED), "; ".join(FAILED)))
