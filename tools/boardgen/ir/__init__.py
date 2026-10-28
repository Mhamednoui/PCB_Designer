"""Design IR (PA-1): one validated, deterministic description of a board, built once by the `ir` stage.

    tools/boardgen/ir/schema.json        JSON Schema of out/design.json (ir_version 2)
    tools/boardgen/ir/from_netlist.py    netlist.py + parts registry  ->  meta, parts, nets, assembly, fab_profile
    tools/boardgen/ir/from_kicad_pcb.py  .kicad_pcb                   ->  board (stdlib parser; the ONLY place that
                                                                          knows the .kicad_pcb file format = R16 firewall)
    tools/boardgen/ir/build.py           python tools/boardgen/ir/build.py <project-id>  -> projects/<id>/out/design.json

Spec: docs/PLATFORM_PLAN.md sections 10, 10.1, 11.1, 11.2 and docs/adr/0009. Everything here is stdlib and runs under
the system Python (no pcbnew, no kicad-cli).
"""
import hashlib
import json
import re

IR_VERSION = 2


class IRError(Exception):
    """The IR cannot be built or is inconsistent. The message is meant for a human."""


def natkey(s):
    """Natural sort key: 'R2' < 'R10', pad '2' < '10' < 'A1' (digits compare as numbers)."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t) for t in re.split(r"(\d+)", str(s)) if t != ""]


def norm_net(name):
    """KiCad net name -> the name netlist.py uses: strip ONE leading hierarchical '/'. Returns None for no net or
    KiCad's auto-generated 'unconnected-(...)' placeholder nets."""
    if not name:
        return None
    if name.startswith("unconnected-("):
        return None
    return name[1:] if name.startswith("/") else name


def sha256_text_file(path):
    """sha256 of a text file with CRLF folded to LF, so the hash does not depend on autocrlf."""
    with open(path, "rb") as f:
        data = f.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(data).hexdigest()


def canonical_json(obj):
    """The one serialisation of an IR: sorted keys, 1-space indent, LF, trailing newline, no timestamps."""
    return json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=False, allow_nan=False) + "\n"
