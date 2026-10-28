"""Electrical data for the design IR (ir_version 2, task P2-T2): resolve a registry record's `electrical` block into the
per-part / per-pin fields of the IR, and read the optional `EXTERNAL` declaration from netlist.py.

Pure functions over plain dicts (stdlib only), so the IR stays deterministic.

Pin resolution, per pad of a registry part (later wins, per field family):
  class   : electrical.pins[pad].class > record pins[pad].class > None
  abs_max : electrical.pins[pad].abs_max > electrical.pin_defaults[class].abs_max > legacy pins[pad].abs_max (cited=false)
            An electrical abs_max REPLACES the legacy one as a whole (it was read from a datasheet, the legacy one is agent
            read/illustrative), so a datasheet that gives no voltage rating leaves v_max null instead of silently keeping an
            uncited number.
  io      : electrical.pin_defaults[class] merged under electrical.pins[pad] (vih/vil/voh/vol/i_out_max_ma/i_in_leak/
            supply_pin/tristate/note); None when neither gives anything.

EXTERNAL grammar (netlist.py, optional):
    EXTERNAL = {
        "J1.1": {"v": (4.4, 5.25), "i": 0.5, "dir": "supply", "why": "USB host VBUS"},   # a connector pin, in PARTS pad naming
        "J1.2": {"dir": "in", "why": "..."},
        "J2": "none",                                                                        # connector with no external nets
    }
    EXTERNAL = {}  means "declared: nothing is external"; no EXTERNAL at all means "not declared" (P2 treats every connector
    as NOT_JUDGED). v = (min, max) volts, i = amperes, dir in in|out|bidir|supply. Unknown pin or ref = IRError.
"""
import copy

from . import IRError

PIN_IO_KEYS = ("supply_pin", "tristate", "vih", "vil", "voh", "vol", "i_out_max_ma", "i_in_leak", "note")
PART_SKIP = ("pins", "pin_defaults", "value_match")
EXT_DIRS = ("in", "out", "bidir", "supply")


def part_electrical(rec, value):
    """(status, block) for a part with this netlist value. status in none | ok | value_not_covered (block is then only
    the record's role and gaps, so coverage knows what the part would need)."""
    el = rec.get("electrical") if rec else None
    if not el:
        return "none", None
    vm = el.get("value_match")
    if vm is not None and str(value) not in vm:
        return "value_not_covered", {k: copy.deepcopy(el[k]) for k in ("role", "gaps") if k in el}
    return "ok", {k: copy.deepcopy(v) for k, v in el.items() if k not in PART_SKIP}


def resolve_pin(rec, pad, status):
    """(class, abs_max|None, io|None) of one pad. status = part_electrical()'s status (value_not_covered -> record data only)."""
    legacy = rec["pins"][pad]
    el = rec.get("electrical") if status == "ok" else None
    ep = (el or {}).get("pins", {}).get(pad, {})
    cls = ep.get("class") or legacy.get("class")
    dflt = (el or {}).get("pin_defaults", {}).get(cls, {}) if cls else {}
    am_src = ep.get("abs_max") or dflt.get("abs_max")
    if am_src is not None:
        abs_max = {"v_min": am_src.get("v_min"), "v_max": am_src.get("v_max"), "i_ma": am_src.get("i_ma"), "cited": True}
        if am_src.get("src"):
            abs_max["src"] = am_src["src"]
        if am_src.get("note"):
            abs_max["note"] = am_src["note"]
    elif legacy.get("abs_max"):
        lm = legacy["abs_max"]
        abs_max = {"v_min": lm.get("v_min"), "v_max": lm.get("v_max"), "i_ma": lm.get("i_ma"), "cited": False}
    else:
        abs_max = None
    io = {}
    for src in (dflt, ep):
        for k in PIN_IO_KEYS:
            if k in src:
                io[k] = copy.deepcopy(src[k])
    return cls, abs_max, (io or None)


def parse_external(nl, parts):
    """The IR `external` section from netlist.py's optional EXTERNAL. parts = IR parts {ref: {"pins": {...}, "kind"}}."""
    raw = getattr(nl, "EXTERNAL", None)
    if raw is None:
        return {"declared": False, "pins": {}, "none": []}
    if not isinstance(raw, dict):
        raise IRError("EXTERNAL must be a dict, got %s" % type(raw).__name__)
    pins, none = {}, []
    for key in sorted(raw, key=str):
        val = raw[key]
        ref, dot, pad = str(key).partition(".")
        if ref not in parts:
            raise IRError("EXTERNAL[%r]: no part %s in netlist.py" % (key, ref))
        if not dot:
            if val != "none":
                raise IRError("EXTERNAL[%r]: a bare reference must be the string 'none' (a connector with no external nets), got %r" % (key, val))
            none.append(ref)
            continue
        if pad not in parts[ref]["pins"]:
            raise IRError("EXTERNAL[%r]: part %s has no pad %s" % (key, ref, pad))
        if not isinstance(val, dict):
            raise IRError("EXTERNAL[%r] must be a dict, got %r" % (key, val))
        unknown = sorted(set(val) - {"v", "i", "dir", "why"})
        if unknown:
            raise IRError("EXTERNAL[%r] has unknown key(s) %s (allowed: v, i, dir, why)" % (key, unknown))
        v = val.get("v")
        if v is not None:
            if not (isinstance(v, (tuple, list)) and len(v) == 2 and all(
                    isinstance(x, (int, float)) and not isinstance(x, bool) for x in v) and v[0] <= v[1]):
                raise IRError("EXTERNAL[%r]['v'] must be (min, max) with min <= max, got %r" % (key, v))
            v = [float(v[0]), float(v[1])]
        i = val.get("i")
        if i is not None and (isinstance(i, bool) or not isinstance(i, (int, float)) or i < 0):
            raise IRError("EXTERNAL[%r]['i'] must be a number >= 0 (amperes), got %r" % (key, i))
        d = val.get("dir")
        if d is not None and d not in EXT_DIRS:
            raise IRError("EXTERNAL[%r]['dir'] must be one of %s, got %r" % (key, EXT_DIRS, d))
        why = val.get("why", "")
        if not isinstance(why, str):
            raise IRError("EXTERNAL[%r]['why'] must be a string" % (key,))
        pins["%s.%s" % (ref, pad)] = {"v": v, "i": None if i is None else float(i), "dir": d, "why": why}
    return {"declared": True,
            "pins": {k: pins[k] for k in sorted(pins, key=lambda p: [x for x in p.split(".", 1)])},
            "none": sorted(none)}
