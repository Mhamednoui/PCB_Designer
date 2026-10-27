"""Parts registry loader (P1-T1). Stdlib only: importable from KiCad Python and system Python.

Spec: docs/design/P1_PARTS_REGISTRY.md.  Records: parts/records/*.json, schema: parts/schema.json.

    from boardgen import parts
    rec = parts.get("ne555p-dip8")
    PARTS.append(parts.registry_part("U1", "ne555p-dip8", "NE555P", {1: "GND", ...}, group))

Release rules key on `verification` (unverified / crosschecked / verified), not on `status`.
Self-test: python tools/boardgen/parts.py --selftest
"""
import copy
import hashlib
import json
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RECORDS_DIR = ROOT / "parts" / "records"
SCHEMA_PATH = ROOT / "parts" / "schema.json"

# Sections covered by signed_hash (spec section 1). Sourcing drift never breaks a signature.
SIGNED_FIELDS = ("mpn", "package", "kicad", "pins", "tht", "polarity")


class RegistryError(ValueError):
    """Raised for an invalid record or an unknown id. The message names file and field path."""


# --------------------------------------------------------------------------- validation
_TYPES = {"string": str, "boolean": bool, "object": dict, "array": list}


def _is_type(v, t):
    if t == "null":
        return v is None
    if t == "integer":
        return isinstance(v, int) and not isinstance(v, bool)
    if t == "number":
        return isinstance(v, (int, float)) and not isinstance(v, bool)
    return isinstance(v, _TYPES[t])


def _check(v, sch, path, errs):
    """Validate v against the JSON Schema subset used by parts/schema.json."""
    if "enum" in sch and v not in sch["enum"]:
        errs.append((path, "must be one of %s, got %r" % (sch["enum"], v)))
        return
    t = sch.get("type")
    if t is not None:
        ts = t if isinstance(t, list) else [t]
        if not any(_is_type(v, x) for x in ts):
            errs.append((path, "must be %s, got %s" % ("/".join(ts), type(v).__name__)))
            return
    if isinstance(v, str) and "pattern" in sch and not re.search(sch["pattern"], v):
        errs.append((path, "%r does not match %s" % (v, sch["pattern"])))
    if _is_type(v, "number") and "minimum" in sch and v < sch["minimum"]:
        errs.append((path, "%r is below minimum %r" % (v, sch["minimum"])))
    if isinstance(v, list):
        if "minItems" in sch and len(v) < sch["minItems"]:
            errs.append((path, "needs at least %d items" % sch["minItems"]))
        if "maxItems" in sch and len(v) > sch["maxItems"]:
            errs.append((path, "needs at most %d items" % sch["maxItems"]))
        if "items" in sch:
            for i, x in enumerate(v):
                _check(x, sch["items"], "%s[%d]" % (path, i), errs)
    if isinstance(v, dict):
        props = sch.get("properties", {})
        for r in sch.get("required", []):
            if r not in v:
                errs.append(("%s.%s" % (path, r) if path else r, "required field is missing"))
        pats = sch.get("patternProperties", {})
        addl = sch.get("additionalProperties", True)
        for k, x in v.items():
            p = "%s.%s" % (path, k) if path else k
            if k in props:
                _check(x, props[k], p, errs)
                continue
            hit = [s for pat, s in pats.items() if re.search(pat, k)]
            if hit:
                _check(x, hit[0], p, errs)
            elif addl is False:
                errs.append((p, "unknown field"))
            elif isinstance(addl, dict):
                _check(x, addl, p, errs)


_schema_cache = None


def schema():
    global _schema_cache
    if _schema_cache is None:
        _schema_cache = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    return _schema_cache


def validate(rec, source="<record>"):
    """Return a list of 'file: field.path: message' strings (empty = valid)."""
    errs = []
    _check(rec, schema(), "", errs)
    out = ["%s: %s: %s" % (source, p or "(root)", m) for p, m in errs]
    if isinstance(rec, dict) and not errs:
        if rec["kind"] in ("part", "generic") and rec["verification"] != "unverified" and not rec.get("evidence"):
            out.append("%s: evidence: tier %s needs at least one evidence entry (PR-TIER)" % (source, rec["verification"]))
        for pin, p in rec["pins"].items():
            vm = (p.get("abs_max") or {}).get("v_max")
            if isinstance(vm, str):
                ref = parse_v_max(vm)["pin"]
                if ref not in rec["pins"]:
                    out.append("%s: pins.%s.abs_max.v_max: refers to pin %s which does not exist" % (source, pin, ref))
    return out


# --------------------------------------------------------------------------- hash
def signed_hash(rec):
    """sha256 over the signed sections, canonical JSON (sorted keys, no whitespace)."""
    body = {k: rec.get(k) for k in SIGNED_FIELDS}
    blob = json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def hash_ok(rec):
    """True if the record is unsigned (no hash yet) or its signed fields still match signed_hash."""
    return rec.get("signed_hash") is None or rec["signed_hash"] == signed_hash(rec)


# --------------------------------------------------------------------------- relative v_max
_REL = re.compile(r"^pin:([A-Za-z0-9]+)([+-][0-9.]+)$")


def parse_v_max(v):
    """Parse an abs_max v_max. Returns {"abs": float} | {"pin": "8", "offset": 0.3} | None.
    A relative limit "pin:8+0.3" means 'voltage on pin 8 plus 0.3 V'."""
    if v is None:
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return {"abs": float(v)}
    m = _REL.match(v) if isinstance(v, str) else None
    if not m:
        raise RegistryError("bad v_max %r (want a number, null, or 'pin:<n>+<volts>')" % (v,))
    return {"pin": m.group(1), "offset": float(m.group(2))}


def resolve_v_max(v, pin_volts):
    """Absolute limit in volts for v_max given {pin: volts}; None if unbounded or the pin is unknown."""
    p = parse_v_max(v)
    if p is None:
        return None
    if "abs" in p:
        return p["abs"]
    base = pin_volts.get(p["pin"])
    return None if base is None else base + p["offset"]


# --------------------------------------------------------------------------- loading
_registry = None


def load_all(records_dir=None, strict=True):
    """Load and validate every record. Raises RegistryError listing ALL problems when strict."""
    d = Path(records_dir) if records_dir else RECORDS_DIR
    recs, problems = {}, []
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            problems.append("%s: (root): invalid JSON: %s" % (f.name, e))
            continue
        errs = validate(rec, f.name)
        if not errs and rec["id"] in recs:
            errs = ["%s: id: duplicate id %r" % (f.name, rec["id"])]
        if not errs and rec["verification"] != "unverified" and rec.get("signed_hash") is None:
            errs = ["%s: signed_hash: tier %s needs a signed_hash, found none (PR-TIER)" % (f.name, rec["verification"])]
        if not errs and rec["verification"] != "unverified" and not rec.get("evidence"):
            errs = ["%s: evidence: tier %s needs at least one evidence entry (PR-TIER)" % (f.name, rec["verification"])]
        if not errs and not hash_ok(rec):
            errs = ["%s: signed_hash: signed fields changed since sign-off (PR-HASH)" % f.name]
        if errs:
            problems.extend(errs)
        else:
            recs[rec["id"]] = rec
    if problems and strict:
        raise RegistryError("\n".join(problems))
    return recs


def registry():
    global _registry
    if _registry is None:
        _registry = load_all()
    return _registry


def get(part_id):
    """Record for an id; unknown id raises RegistryError with the nearest ids."""
    reg = registry()
    if part_id not in reg:
        import difflib
        near = difflib.get_close_matches(part_id, list(reg), n=3)
        raise RegistryError('part id "%s" not in registry (nearest: %s)' % (part_id, ", ".join(near) or "none"))
    return reg[part_id]


def _si(text):
    """'4.7k' / '100nF' / '10' -> float (units letters ignored)."""
    m = re.match(r"^\s*([0-9.]+)\s*([pnuµmkMG]?)", str(text))
    if not m:
        raise RegistryError("cannot parse value %r" % (text,))
    mult = {"p": 1e-12, "n": 1e-9, "u": 1e-6, "µ": 1e-6, "m": 1e-3, "": 1, "k": 1e3, "M": 1e6, "G": 1e9}
    return float(m.group(1)) * mult[m.group(2)]


def generic(part_id, value=None):
    """Record of a 'generic' family (resistor, capacitor, LED...). With value, check it is in value_range."""
    rec = get(part_id)
    if rec["kind"] != "generic":
        raise RegistryError('"%s" is kind %s, not generic' % (part_id, rec["kind"]))
    if value is not None and "value_range" in rec:
        lo, hi = rec["value_range"]
        if not lo <= _si(value) <= hi:
            raise RegistryError('"%s": value %s outside range %s..%s' % (part_id, value, lo, hi))
    return rec


# --------------------------------------------------------------------------- netlist.py path
def registry_part(ref, part_id, value, pins, group):
    """Return a dict in the exact shape of netlist.py's PARTS entries (ref, lib_id, value,
    footprint, pins, group, lcsc), derived from the registry record. Unknown pin numbers raise."""
    rec = get(part_id)
    extra = sorted(str(k) for k in pins if str(k) not in rec["pins"])
    if extra:
        raise RegistryError('%s: pin(s) %s not in registry record "%s" (has %s)'
                            % (ref, ", ".join(extra), part_id, ", ".join(rec["pins"])))
    return dict(ref=ref, lib_id=rec["kicad"]["symbol"], value=value, footprint=rec["kicad"]["footprint"],
                pins={str(k): v for k, v in pins.items() if v}, group=group,
                lcsc=(rec.get("lcsc") or {}).get("id", ""))


# --------------------------------------------------------------------------- self-test
_FIXTURE = {   # self-contained NE555P-like record; the selftest never reads parts/records
    "id": "ne555p-dip8", "kind": "part", "mpn": "NE555P", "status": "draft", "verification": "unverified",
    "lcsc": {"id": "C46749", "class": "extended"}, "sourcing": {"stock": 1, "price_1": 0.3, "snapshot_date": "2026-01-01"},
    "package": {"name": "DIP-8", "mount": "tht"}, "kicad": {"symbol": "Timer:NE555P", "footprint": "Package_DIP:DIP-8_W7.62mm"},
    "pins": {"1": {"name": "GND", "class": "power_in"}, "2": {"name": "TRIG", "class": "input"},
             "3": {"name": "OUT", "class": "output"}, "4": {"name": "RESET", "class": "input"},
             "5": {"name": "CONT", "class": "analog"}, "6": {"name": "THRES", "class": "input"},
             "7": {"name": "DISCH", "class": "open_collector"}, "8": {"name": "VCC", "class": "power_in"}},
    "evidence": [], "signed_hash": None}


def selftest():
    fails = []

    def ok(cond, what):
        print(("PASS  " if cond else "FAIL  ") + what)
        if not cond:
            fails.append(what)

    global _registry
    tmp = Path(tempfile.mkdtemp(prefix="parts_selftest_"))
    (tmp / "ne555p.json").write_text(json.dumps(_FIXTURE), encoding="utf-8")
    recs = load_all(tmp)
    r = recs.get("ne555p-dip8")
    saved, _registry = _registry, recs          # get()/registry_part() read the fixture, never the live records
    ok(r is not None and r["verification"] == "unverified", "load ok: fixture ne555p-dip8 present, tier unverified")
    ok(get("ne555p-dip8") == r, "get(id) returns the loaded record")
    try:
        get("ne555")
        ok(False, "unknown id raises")
    except RegistryError as e:
        ok("ne555p-dip8" in str(e), "unknown id raises, suggests nearest")

    bad = copy.deepcopy(r)
    bad["pins"]["2"]["class"] = "inptu"
    errs = validate(bad, "ne555p.json")
    ok(any(e.startswith("ne555p.json: pins.2.class:") for e in errs), "bad field error names file + path: %s" % (errs[:1],))
    bad = copy.deepcopy(r)
    del bad["kicad"]["footprint"]
    ok(any("kicad.footprint" in e for e in validate(bad, "x.json")), "missing required field named by path")

    shuffled = {k: r[k] for k in reversed(list(r))}
    shuffled["pins"] = {k: dict(reversed(list(v.items()))) for k, v in reversed(list(r["pins"].items()))}
    ok(signed_hash(r) == signed_hash(shuffled), "hash stable across key order")
    ok(signed_hash(r) == signed_hash(json.loads(json.dumps(r, indent=4))), "hash stable across whitespace")
    changed = copy.deepcopy(r)
    changed["pins"]["2"]["name"], changed["pins"]["6"]["name"] = "THRES", "TRIG"
    ok(signed_hash(changed) != signed_hash(r), "hash changes when pin map changes")
    sourcing = copy.deepcopy(r)
    sourcing["sourcing"]["stock"] = 0
    ok(signed_hash(sourcing) == signed_hash(r), "hash ignores sourcing drift")

    ok(parse_v_max("pin:8+0.3") == {"pin": "8", "offset": 0.3}, "relative v_max parses")
    ok(parse_v_max(18) == {"abs": 18.0} and parse_v_max(None) is None, "absolute / null v_max parse")
    ok(abs(resolve_v_max("pin:8+0.3", {"8": 5.0}) - 5.3) < 1e-9, "relative v_max resolves against pin voltage")

    e = registry_part("U1", "ne555p-dip8", "NE555P", {1: "GND", 8: "VCC", 4: None}, "G")
    ok(e["lib_id"] == "Timer:NE555P" and e["lcsc"] == "C46749" and e["pins"] == {"1": "GND", "8": "VCC"}
       and sorted(e) == sorted(["ref", "lib_id", "value", "footprint", "pins", "group", "lcsc"]),
       "registry_part gives the legacy PARTS dict shape")
    try:
        registry_part("U1", "ne555p-dip8", "NE555P", {9: "X"}, "G")
        ok(False, "unknown pin raises")
    except RegistryError:
        ok(True, "unknown pin raises")

    for tier, mut, what in (("crosschecked", {"evidence": [{"verified_by": "t"}]}, "needs a signed_hash"),
                            ("verified", {"signed_hash": "0" * 64, "evidence": []}, "evidence entry")):
        bad = copy.deepcopy(_FIXTURE)
        bad.update(mut)
        bad["verification"] = tier
        (tmp / "ne555p.json").write_text(json.dumps(bad), encoding="utf-8")
        try:
            load_all(tmp)
            ok(False, "PR-TIER: %s without %s rejected" % (tier, what))
        except RegistryError as e:
            ok("PR-TIER" in str(e) and what in str(e), "PR-TIER: %s without %s rejected" % (tier, what))
    good = copy.deepcopy(_FIXTURE)
    good.update(verification="crosschecked", evidence=[{"verified_by": "t"}])
    good["signed_hash"] = signed_hash(good)
    (tmp / "ne555p.json").write_text(json.dumps(good), encoding="utf-8")
    ok("ne555p-dip8" in load_all(tmp), "crosschecked with hash + evidence loads")
    _registry = saved
    shutil.rmtree(tmp, ignore_errors=True)
    print("\nselftest: %s" % ("FAILED (%d)" % len(fails) if fails else "all passed"))
    return 1 if fails else 0


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    print(__doc__)
