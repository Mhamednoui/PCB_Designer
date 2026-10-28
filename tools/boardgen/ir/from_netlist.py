"""netlist.py (+ parts registry) -> the non-board half of the design IR.

    from boardgen.ir import from_netlist
    ir = from_netlist.build("blinky-555")      # dict: meta (without the pcb hash), parts, nets, assembly, fab_profile

Stdlib only; no KiCad process. Reads: the project's gen/netlist.py (PARTS, NET_SPEC, POWER_FLAG_NETS and the optional
SOURCE / ASSEMBLY / BOARDS / FAB_PROFILE), and the registry record of every registry part for the pin names and classes.

Fail closed: an unknown SOURCE, an unsupported SOURCE, a bad ASSEMBLY, a malformed NET_SPEC entry, a registry part whose
pads do not match its record, or a part with no pins raises IRError - nothing is guessed.
NET_SPEC names a net that does not exist -> a warning on stderr only (lint reports it as WARN too); the entry is dropped.

Net class (power / ground / signal): NET_SPEC "class" if given; else ground = name matches GND/AGND/DGND/PGND/VSS/0V or its
declared voltage is 0 and it is in POWER_FLAG_NETS; power = in POWER_FLAG_NETS, or a voltage-style name (+5V, 3V3, +12V_IN),
or it touches a power_in/power_out pin of a registry record; everything else is signal.
"""
import hashlib
import json
import os
import re
import sys

from . import IRError, natkey, sha256_text_file

HERE = os.path.dirname(os.path.abspath(__file__))
TOOLS = os.path.dirname(os.path.dirname(HERE))
ROOT = os.path.dirname(TOOLS)

GROUND_RE = re.compile(r"^(GND|AGND|DGND|PGND|GNDA|GNDD|VSS|0V)$", re.I)      # same as lint_netlist.GROUND_RE
VOLT_RE = re.compile(r"^\+?(\d+)V(\d*)(?:_.*)?$", re.I)                       # +5V, +3V3, +12V_REG
POWER_PIN_CLASSES = ("power_in", "power_out")
VALID_NET_CLASSES = ("power", "ground", "signal")


def _load(project_id):
    from boardgen import parts as _parts
    from boardgen import project as _project
    _parts.begin_netlist_load()                              # fail closed: a bad registry_part() call raises
    sys.modules.pop("netlist", None)                          # a cached netlist module would skip registry_part() and lose the registry ids
    try:
        nl = _project.load_netlist(project_id)
    except _parts.RegistryError as e:
        raise IRError("netlist.py could not be built from the parts registry: %s" % str(e).replace("\n", "; "))
    return nl, _parts


def _volts(spec_v, net):
    if spec_v is None:
        return None
    if isinstance(spec_v, bool):
        raise IRError("NET_SPEC[%r]['v'] must be a number or (min, max), got %r" % (net, spec_v))
    if isinstance(spec_v, (int, float)):
        return [float(spec_v), float(spec_v)]
    if isinstance(spec_v, (tuple, list)) and len(spec_v) == 2 and all(
            isinstance(x, (int, float)) and not isinstance(x, bool) for x in spec_v) and spec_v[0] <= spec_v[1]:
        return [float(spec_v[0]), float(spec_v[1])]
    raise IRError("NET_SPEC[%r]['v'] must be a number or (min, max) with min <= max, got %r" % (net, spec_v))


def _net_class(name, v, spec_cls, flagged, touches_power_pin):
    if spec_cls is not None:
        if spec_cls not in VALID_NET_CLASSES:
            raise IRError("NET_SPEC[%r]['class'] must be one of %s, got %r" % (name, VALID_NET_CLASSES, spec_cls))
        return spec_cls
    if GROUND_RE.match(name) or (name in flagged and v is not None and v == [0.0, 0.0]):
        return "ground"
    if name in flagged or VOLT_RE.match(name) or touches_power_pin:
        return "power"
    return "signal"


def _git_commit():
    import subprocess
    try:
        r = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
        sha = r.stdout.strip()
        return sha if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40}", sha) else None
    except (OSError, subprocess.SubprocessError):
        return None


def build(project_id):
    nl, _parts = _load(project_id)
    source = str(getattr(nl, "SOURCE", "netlist"))
    if source != "netlist":
        raise IRError("SOURCE = %r: only 'netlist' is implemented (the drawn-schematic adapter is PA-11)" % source)

    reg_refs = _parts.registered_refs()
    reg_nc = _parts.registered_nc()
    reg = {}
    out_parts = {}
    for p in nl.PARTS:
        ref = p["ref"]
        if ref in out_parts:
            raise IRError("duplicate reference %s in netlist.py PARTS" % ref)
        if not p["pins"] and not reg_nc.get(ref):
            raise IRError("%s has no pins" % ref)
        rid = reg_refs.get(ref)
        rec = _parts.get(rid) if rid else None
        if rec is not None:
            reg[ref] = rec
        pins = {}
        for pad in sorted(p["pins"], key=natkey):
            net = p["pins"][pad]
            if not isinstance(net, str) or not net:
                raise IRError("%s pad %s: net must be a non-empty string, got %r" % (ref, pad, net))
            rp = rec["pins"].get(str(pad)) if rec else None
            if rec is not None and rp is None:
                raise IRError("%s pad %s is not a pad of registry record %r" % (ref, pad, rid))
            pins[str(pad)] = {"name": rp["name"] if rp else None, "net": net, "class": rp.get("class") if rp else None}
        out_parts[ref] = {
            "ref": ref, "registry": rid, "kind": rec["kind"] if rec else "unregistered",
            "lib_id": p["lib_id"], "footprint": p["footprint"], "value": str(p["value"]),
            "lcsc": str(p.get("lcsc") or ""), "group": p.get("group"),
            "pins": pins, "nc": sorted((str(x) for x in reg_nc.get(ref, [])), key=natkey),
        }
    out_parts = {r: out_parts[r] for r in sorted(out_parts, key=natkey)}

    # ---- nets
    members = {}
    for ref, part in out_parts.items():
        for pad, pin in part["pins"].items():
            members.setdefault(pin["net"], []).append((ref, pad))
    spec = getattr(nl, "NET_SPEC", {}) or {}
    if not isinstance(spec, dict):
        raise IRError("NET_SPEC must be a dict")
    for name in sorted(spec):
        if name not in members:
            print("WARN ir: NET_SPEC names net %r which no part uses (typo?) - entry dropped" % name, file=sys.stderr)
    flagged = set(getattr(nl, "POWER_FLAG_NETS", []) or [])
    out_nets = {}
    for name in sorted(members, key=natkey):
        s = spec.get(name, {})
        if not isinstance(s, dict):
            raise IRError("NET_SPEC[%r] must be a dict, got %s" % (name, type(s).__name__))
        unknown = sorted(set(s) - {"v", "i_max", "class"})
        if unknown:
            raise IRError("NET_SPEC[%r] has unknown key(s) %s (allowed: v, i_max, class)" % (name, unknown))
        v = _volts(s.get("v"), name)
        i = s.get("i_max")
        if i is not None and (isinstance(i, bool) or not isinstance(i, (int, float)) or i < 0):
            raise IRError("NET_SPEC[%r]['i_max'] must be a number >= 0, got %r" % (name, i))
        pins = sorted(members[name], key=lambda rp: (natkey(rp[0]), natkey(rp[1])))
        touches = any(out_parts[r]["pins"][pad]["class"] in POWER_PIN_CLASSES for r, pad in pins)
        out_nets[name] = {"v": v, "i_max": None if i is None else float(i),
                          "class": _net_class(name, v, s.get("class"), flagged, touches),
                          "pins": ["%s.%s" % rp for rp in pins]}

    # ---- assembly / fab profile (declared in netlist.py or reported as undeclared; never assumed, ADR 0012)
    mode = getattr(nl, "ASSEMBLY", None)
    if mode is not None:
        mode = str(mode).lower()
        if mode not in ("pcba", "hand"):
            raise IRError("ASSEMBLY must be 'pcba' or 'hand', got %r" % mode)
    boards = getattr(nl, "BOARDS", None)
    if boards is not None and (isinstance(boards, bool) or not isinstance(boards, int) or boards < 1):
        raise IRError("BOARDS must be an integer >= 1, got %r" % (boards,))
    fab = getattr(nl, "FAB_PROFILE", None)
    gen_dir = os.path.join(ROOT, "projects", project_id, "gen")
    hashes = {"projects/%s/gen/netlist.py" % project_id: sha256_text_file(os.path.join(gen_dir, "netlist.py"))}
    for rid in sorted({r["registry"] for r in out_parts.values() if r["registry"]}):
        hashes["parts/records/%s" % rid] = hashlib.sha256(          # whole record (lcsc/sourcing too), not signed_hash
            json.dumps(_parts.get(rid), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()
    return {
        "meta": {"project": project_id, "source": source, "git_commit": _git_commit(), "input_hashes": hashes},
        "parts": out_parts, "nets": out_nets,
        "assembly": {"mode": mode, "boards": boards},
        "fab_profile": {"name": str(fab) if fab else "jlcpcb", "declared": bool(fab)},
    }
