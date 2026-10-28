"""Parts registry loader (P1-T1). Stdlib only: importable from KiCad Python and system Python.

Spec: docs/design/P1_PARTS_REGISTRY.md.  Records: parts/records/*.json, schema: parts/schema.json.

    from boardgen import parts
    rec = parts.get("ne555p-dip8")
    PARTS.append(parts.registry_part("U1", "ne555p-dip8", "NE555P",
                                     {"GND": "GND", "TRIG": "TRIG", "OUT": "OUT", "RESET": "VCC", "CONT": "CV",
                                      "THRES": "TRIG", "DISCH": "DISCH", "VCC": "VCC"}, group))

Pins are connected BY FUNCTION (the record's pin name or alias): the pad numbers come from the record, so a part
swapped for one with another pinout renumbers by construction. Numbers stay accepted (and are required for generics
and connectors whose pin names are "~" / "Pin_1"). A name shared by several pins needs "GND#2" or the pad number.
Every pad the netlist leaves unconnected must be declared in `nc=[...]` (fail closed).

Environment: PARTS_RECORDS_DIR points the registry at another records directory (tests; replaces a sitecustomize hook).
Release rules key on `verification` (unverified / crosschecked / verified), not on `status`.
Self-test: python tools/boardgen/parts.py --selftest
"""
import copy
import hashlib
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_RECORDS_DIR = ROOT / "parts" / "records"
SCHEMA_PATH = ROOT / "parts" / "schema.json"

# Sections covered by signed_hash (spec section 1). Sourcing drift never breaks a signature.
SIGNED_FIELDS = ("mpn", "package", "kicad", "pins", "tht", "polarity")


class RegistryError(ValueError):
    """Raised for an invalid record or an unknown id. The message names file and field path."""


def records_dir():
    """The records directory: $PARTS_RECORDS_DIR if set (tests), else parts/records. Read at call time."""
    d = os.environ.get("PARTS_RECORDS_DIR")
    return Path(d) if d else DEFAULT_RECORDS_DIR


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


def _tier_problems(rec, who):
    """PR-TIER / PR-HASH messages for a schema-valid record ('who' = file name or record id)."""
    msgs = []
    if rec["verification"] != "unverified" and rec.get("signed_hash") is None:
        msgs.append("%s: signed_hash: tier %s needs a signed_hash, found none (PR-TIER)" % (who, rec["verification"]))
    if rec["verification"] != "unverified" and not rec.get("evidence"):
        msgs.append("%s: evidence: tier %s needs at least one evidence entry (PR-TIER)" % (who, rec["verification"]))
    if not hash_ok(rec):
        msgs.append("%s: signed_hash: signed fields changed since sign-off (PR-HASH)" % who)
    return msgs


def load_all(records_dir_=None, lenient=False):
    """Load and validate every record in records_dir_ (default records_dir(): $PARTS_RECORDS_DIR or parts/records).

    Default (fail closed): raise RegistryError listing ALL problems; returns {id: record}.
    lenient=True: never raises for a bad record; returns (records, problems) with problems = {record id (file name
    if unreadable): [messages]}. A schema-invalid record is left out; one with a broken hash/tier stays usable so
    lint can report it per use instead of crashing the netlist import. Release code uses the fail-closed form."""
    d = Path(records_dir_) if records_dir_ else records_dir()
    if not d.is_dir():
        raise RegistryError("records directory %s does not exist (PARTS_RECORDS_DIR=%r)"
                            % (d, os.environ.get("PARTS_RECORDS_DIR", "")))
    recs, problems, hard = {}, {}, []                  # hard = messages that make the fail-closed load raise
    for f in sorted(d.glob("*.json")):
        try:
            rec = json.loads(f.read_text(encoding="utf-8"))
        except ValueError as e:
            msg = "%s: (root): invalid JSON: %s" % (f.name, e)
            problems.setdefault(f.name, []).append(msg)
            hard.append(msg)
            continue
        errs = validate(rec, f.name)
        if errs:
            key = rec["id"] if isinstance(rec, dict) and isinstance(rec.get("id"), str) else f.name
            problems.setdefault(key, []).extend(errs)
            hard.extend(errs)
            continue
        pid = rec["id"]
        if pid in recs:
            msg = "%s: id: duplicate id %r" % (f.name, pid)
            problems.setdefault(pid, []).append(msg)
            hard.append(msg)
            continue
        recs[pid] = rec
        hard.extend(_tier_problems(rec, f.name))
        soft = _tier_problems(rec, pid)
        if soft:
            problems.setdefault(pid, []).extend(soft)
    if lenient:
        return recs, problems
    if hard:
        raise RegistryError("\n".join(hard))
    return recs


def registry():
    """The fail-closed registry (cached): every record valid, consistent and signed as its tier requires."""
    global _registry
    if _registry is None:
        _registry = load_all()
    return _registry


def use_lenient_registry():
    """Install the lenient registry as the cache get()/registry() read (lint and the parts stage, which report
    record problems per use). Returns the per-record problems {id: [messages]}."""
    global _registry
    _registry, problems = load_all(lenient=True)
    return problems


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
# Registered-parts tracker. A netlist.py declares parts through registry_part(); lint and the parts stage need to
# know which refs those were. begin_netlist_load() resets the tracker, so call it right before importing a netlist.
_refs = {}                 # ref -> registry record id
_nc = {}                   # ref -> [pad numbers explicitly declared NC]
_bynum = {}                # ref -> [pad numbers the netlist typed as NUMBERS (not pin names)], PR-BYNAME
_build_problems = {}       # ref -> [messages], only filled in lenient build mode
_lenient_build = [False]


def begin_netlist_load(lenient=False):
    """Reset the registered-refs tracker before importing a netlist. lenient=True (lint): a pin/NC mistake in a
    registry_part() call is recorded (build_problems()) and the part is still built, so later rules can run and
    report every problem at once; the default raises RegistryError at the first bad call (fail closed)."""
    _refs.clear()
    _nc.clear()
    _bynum.clear()
    _build_problems.clear()
    _lenient_build[0] = bool(lenient)


def registered_refs():
    """{ref: registry record id} for every part declared through registry_part() since begin_netlist_load()."""
    return dict(_refs)


def registered_nc():
    """{ref: [pad numbers]} explicitly declared not-connected (nc=[...]) since begin_netlist_load()."""
    return {r: list(v) for r, v in _nc.items()}


def registered_bynumber():
    """{ref: [pad numbers]} of the pins registry_part() was given as pad NUMBERS rather than pin names/aliases."""
    return {r: list(v) for r, v in _bynum.items() if v}


def build_problems():
    """{ref: [messages]} recorded in lenient build mode (empty otherwise)."""
    return {r: list(v) for r, v in _build_problems.items()}


def _norm_name(n):
    return re.sub(r"[~{} ]", "", str(n)).upper()


def _padkey(k):
    return (len(k), k)


def _pad_names(rec):
    """{normalised name or alias: [pad numbers, sorted]} for a record."""
    out = {}
    for num, p in rec["pins"].items():
        for nm in {p["name"], p.get("alias") or p["name"]}:
            if _norm_name(nm):
                out.setdefault(_norm_name(nm), []).append(num)
    return {k: sorted(set(v), key=_padkey) for k, v in out.items()}


def _choices(rec):
    return "; ".join("%s=%s" % (num, p["name"]) for num, p in sorted(rec["pins"].items(), key=lambda kv: _padkey(kv[0])))


def resolve_pin(rec, key):
    """Pad number for a pin key: a pad number, or the pin name/alias (case-insensitive, ~{} ignored), or "NAME#n"
    (n-th pad with that name, 1-based, by pad number). Raises RegistryError (no ref prefix) on unknown/ambiguous."""
    s = str(key).strip()
    if s in rec["pins"]:
        return s
    m = re.match(r"^(.*?)#(\d+)$", s)
    base, idx = (m.group(1), int(m.group(2))) if m else (s, None)
    cands = _pad_names(rec).get(_norm_name(base))
    if not cands:
        raise RegistryError('pin %s is neither a pad number nor a pin name of record "%s" (pins: %s)'
                            % (s, rec["id"], _choices(rec)))
    if idx is not None:
        if not 1 <= idx <= len(cands):
            raise RegistryError('pin %s: record "%s" has %d pin(s) named %s (pads %s)'
                                % (s, rec["id"], len(cands), base, ",".join(cands)))
        return cands[idx - 1]
    if len(cands) > 1:
        raise RegistryError('pin name "%s" is ambiguous in record "%s": %s; write "%s#<n>" or the pad number'
                            % (s, rec["id"], ", ".join("%s#%d = pad %s" % (s, i + 1, c) for i, c in enumerate(cands)), s))
    return cands[0]


def registry_part(ref, part_id, value, pins, group, nc=(), lcsc=None):
    """Return a dict in the exact shape of netlist.py's PARTS entries (ref, lib_id, value, footprint, pins, group,
    lcsc), derived from the registry record.

    pins  {key: net}; key = pin FUNCTION (record pin name or alias, "GND#2" for the 2nd pin of that name) or a pad
          number. Pad numbers are derived from the record, so swapping the record for another pinout renumbers
          correctly. Generics/connectors (names "~" / "Pin_1") use numbers. A net of None/"" declares the pin NC.
    nc    pins explicitly not connected: a key or list of keys (same forms), or "rest" = every pad not otherwise
          mentioned (only for connector/mechanical records, e.g. a shield with 90 spare pins).
    lcsc  per-instance LCSC id (generic records carry none: a 10k and a 1M resistor are the same record). A ref-level
          id WINS over the record's; "" says "no LCSC id for this ref"; None (default) takes the record's.
    Fail closed: an unknown or ambiguous key, a pad given twice, or a pad of the record that is neither connected
    nor declared NC raises RegistryError (lint mode records it instead, see begin_netlist_load)."""
    rec = get(part_id)
    errs, out, listed_nc, typed_numbers = [], {}, [], []

    def bad(msg):
        errs.append("%s: %s" % (ref, msg))

    for k, net in pins.items():
        try:
            pad = resolve_pin(rec, k)
        except RegistryError as e:
            bad(str(e))
            if net:
                out.setdefault(str(k), net)                 # best effort so lint can keep going
            continue
        if str(k).strip() in rec["pins"]:
            typed_numbers.append(pad)
        if pad in out or pad in listed_nc:
            bad("pad %s of record \"%s\" is given twice (key %s)" % (pad, part_id, k))
        elif net:
            out[pad] = net
        else:
            listed_nc.append(pad)
    rest = False
    for k in ([nc] if isinstance(nc, (str, int)) else list(nc)):
        if k == "rest":
            if rec["kind"] not in ("connector", "mechanical"):
                bad('nc="rest" is only allowed for connector/mechanical records, "%s" is a %s: list its NC pins'
                    % (part_id, rec["kind"]))
            rest = True
            continue
        try:
            pad = resolve_pin(rec, k)
        except RegistryError as e:
            bad("nc: " + str(e))
            continue
        if pad in out:
            bad("pad %s of record \"%s\" is both connected (net %s) and declared NC" % (pad, part_id, out[pad]))
        elif pad not in listed_nc:
            listed_nc.append(pad)
    if not rest and not errs:
        left = sorted((p for p in rec["pins"] if p not in out and p not in listed_nc), key=_padkey)
        if left:
            bad('pin(s) %s of record "%s" are neither connected nor declared NC (add nc=[...])'
                % (", ".join("%s (%s)" % (p, rec["pins"][p]["name"]) for p in left), part_id))
    if errs:
        if not _lenient_build[0]:
            raise RegistryError("\n".join(errs))
        _build_problems.setdefault(ref, []).extend(errs)
    if rest:
        listed_nc += [p for p in sorted(rec["pins"], key=_padkey) if p not in out and p not in listed_nc]
    _refs[ref] = part_id
    _nc[ref] = sorted(listed_nc, key=_padkey)
    _bynum[ref] = sorted(typed_numbers, key=_padkey)
    return dict(ref=ref, lib_id=rec["kicad"]["symbol"], value=value, footprint=rec["kicad"]["footprint"],
                pins=out, group=group, lcsc=(rec.get("lcsc") or {}).get("id", "") if lcsc is None else str(lcsc).strip())


# --------------------------------------------------------------------------- package family matching
_FAMILY_RX = (r"DIP-?(\d+)", r"SOIC-?(\d+)", r"SOT-?(223|23(?:-\d)?)", r"(?<![A-Z])TO-?(\d{2,3})(?!\d)", r"SIP-?(\d+)")


def _squash(t):
    return re.sub(r"[-_ .]", "", str(t)).lower()


def pkg_family(text):
    """Normalised package family of a record package name or a KiCad footprint name: 'DIP8', 'SOIC8', 'SOT223',
    'TO220' (TO-220AB and TO-220-3_Vertical agree), 'TO92' ... or None when the text names no known family."""
    t = str(text).upper()
    for rx in _FAMILY_RX:
        m = re.search(rx, t)
        if m:
            return re.sub(r"[^A-Z0-9]", "", t[m.start():m.end()])
    return None


def judge_package(rec, fp_name):
    """Does the record's package match the footprint (library prefix already removed)? -> (verdict, text) with verdict
    'ok' | 'mismatch' | 'unjudged'. Order: package.name is a token of the footprint name; any footprint_aliases entry
    (unsigned record field) is; if aliases are declared and none is, MISMATCH; both sides name a known family
    (DIP/SOIC/SOT/TO/SIP): equal = ok, different = mismatch; otherwise UNJUDGED (never a silent pass)."""
    name, fp = (rec.get("package") or {}).get("name", ""), _squash(fp_name)
    if name and _squash(name) in fp:
        return "ok", name
    aliases = rec.get("footprint_aliases") or []
    for a in aliases:
        if _squash(a) in fp:
            return "ok", a
    if aliases:
        return "mismatch", 'footprint name %s has none of the record\'s footprint_aliases %s' % (fp_name, ", ".join(aliases))
    fr, ff = pkg_family(name), pkg_family(fp_name)
    if fr and ff:
        return ("ok", fr) if fr == ff else ("mismatch", 'footprint name %s is family %s, record package "%s" is %s' % (fp_name, ff, name, fr))
    return "unjudged", ('cannot relate record package "%s" to footprint %s: add footprint_aliases to the record' % (name, fp_name))


def judge_lcsc_package(rec, lcsc_package):
    """LCSC's package string vs the record: package.lcsc_package (exact, normalised) or lcsc_package_aliases (substrings).
    -> 'ok' | 'mismatch' | 'unjudged'. Used for generic records, whose LCSC id is per instance."""
    have = re.sub(r"[^A-Z0-9]", "", str(lcsc_package or "").upper())
    want = (rec.get("package") or {}).get("lcsc_package")
    cands = ([want] if want else []) + list(rec.get("lcsc_package_aliases") or [])
    if not cands:
        return "unjudged"
    for c in cands:
        c = re.sub(r"[^A-Z0-9]", "", c.upper())
        if c and (c == have or c in have):
            return "ok"
    return "mismatch"


def by_name_required(rec):
    """PR-BYNAME: a kind=part record with >= 3 pins that all have meaningful (non-empty, non-'~', non-numeric) names
    must be wired by pin NAME, because a pad number typed against a library pinout is the R1 trap."""
    if rec.get("kind") != "part" or len(rec["pins"]) < 3:
        return False
    names = [p["name"] for p in rec["pins"].values()]
    return all(_norm_name(n) and not _norm_name(n).isdigit() for n in names) and len({_norm_name(n) for n in names}) >= 3


# --------------------------------------------------------------------------- self-test
_FIXTURE = {   # self-contained NE555P-like record; the selftest never reads parts/records
    "id": "ne555p-dip8", "kind": "part", "mpn": "NE555P", "status": "draft", "verification": "unverified",
    "lcsc": {"id": "C46749", "class": "extended"}, "sourcing": {"stock": 1, "price_1": 0.3, "snapshot_date": "2026-01-01"},
    "package": {"name": "DIP-8", "mount": "tht"}, "kicad": {"symbol": "Timer:NE555P", "footprint": "Package_DIP:DIP-8_W7.62mm"},
    "pins": {"1": {"name": "GND", "class": "power_in"}, "2": {"name": "TRIG", "class": "input"},
             "3": {"name": "OUT", "class": "output"}, "4": {"name": "RESET", "alias": "~RST", "class": "input"},
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

    # ---- registry_part: pins by function, NC policy (fail closed), registered-refs tracker
    begin_netlist_load()
    by_name = {"GND": "GND", "TRIG": "T", "OUT": "O", "RESET": "VCC", "CONT": "CV", "THRES": "T", "DISCH": "D", "VCC": "VCC"}
    want = {"1": "GND", "2": "T", "3": "O", "4": "VCC", "5": "CV", "6": "T", "7": "D", "8": "VCC"}
    e = registry_part("U1", "ne555p-dip8", "NE555P", by_name, "G")
    ok(e["lib_id"] == "Timer:NE555P" and e["lcsc"] == "C46749" and e["pins"] == want
       and sorted(e) == sorted(["ref", "lib_id", "value", "footprint", "pins", "group", "lcsc"]),
       "registry_part by function derives pad numbers and keeps the legacy PARTS dict shape")
    ok(registry_part("U1", "ne555p-dip8", "NE555P", by_name, "G", lcsc="C1")["lcsc"] == "C1"
       and registry_part("U1", "ne555p-dip8", "NE555P", by_name, "G", lcsc="")["lcsc"] == ""
       and registry_part("U1", "ne555p-dip8", "NE555P", by_name, "G")["lcsc"] == "C46749",
       "ref-level lcsc wins over the record's; '' blanks it; None takes the record's")
    ok(registry_part("U1", "ne555p-dip8", "NE555P", {int(k): v for k, v in want.items()}, "G")["pins"] == want
       and registry_part("U1", "ne555p-dip8", "NE555P", {"gnd": "GND", "TRIG": "T", "OUT": "O", "RST": "VCC", "CONT": "CV",
                                                       "THRES": "T", "DISCH": "D", "vcc": "VCC"}, "G")["pins"] == want,
       "numeric keys, alias (RST = ~RST), and case-insensitive names all resolve")

    def raises(fn, *needles):
        try:
            fn()
        except RegistryError as ex:
            return all(n in str(ex) for n in needles)
        return False
    ok(raises(lambda: registry_part("U1", "ne555p-dip8", "NE555P", dict(by_name, **{"9": "X"}), "G"), "U1:", "pin 9", "neither a pad number nor a pin name"),
       "unknown pin raises, names the pin")
    ok(raises(lambda: registry_part("U1", "ne555p-dip8", "NE555P", {"GND": "GND", "VCC": "VCC"}, "G"),
              "U1:", "2 (TRIG)", "5 (CONT)", "nc=["), "unconnected pins that are not declared NC raise, naming each pad")
    ok(registry_part("U1", "ne555p-dip8", "NE555P", {"GND": "GND", "VCC": "VCC"}, "G",
                     nc=["TRIG", 3, "RESET", "CONT", "THRES", "DISCH"])["pins"] == {"1": "GND", "8": "VCC"}
       and registered_nc()["U1"] == ["2", "3", "4", "5", "6", "7"], "nc=[names or numbers] declares pins not connected")
    ok(registry_part("U1", "ne555p-dip8", "NE555P", dict(by_name, RESET=None), "G")["pins"].get("4") is None
       and registered_nc()["U1"] == ["4"], "a net of None declares that pin NC")
    ok(raises(lambda: registry_part("U1", "ne555p-dip8", "NE555P", by_name, "G", nc=["OUT"]), "both connected", "NC"),
       "a pin that is connected AND in nc raises")
    ok(raises(lambda: registry_part("U1", "ne555p-dip8", "NE555P", dict(by_name, **{"1": "X"}), "G"), "given twice"),
       "the same pad given twice (name and number) raises")
    ok(raises(lambda: registry_part("U1", "ne555p-dip8", "NE555P", {"GND": "GND"}, "G", nc="rest"), "only allowed for connector"),
       'nc="rest" is refused for a part record')

    for rid, order in (("q-ebc", "EBC"), ("q-cbe", "CBE")):      # same part, two pinouts (2N3904 vs BC547)
        q = copy.deepcopy(r)
        q["id"], q["pins"] = rid, {str(i + 1): {"name": n, "class": "passive"} for i, n in enumerate(order)}
        recs[rid] = q
    fn = {"E": "GND", "B": "OUT", "C": "LED_A"}
    ok(registry_part("Q1", "q-ebc", "x", fn, "G")["pins"] == {"1": "GND", "2": "OUT", "3": "LED_A"}
       and registry_part("Q1", "q-cbe", "x", fn, "G")["pins"] == {"3": "GND", "2": "OUT", "1": "LED_A"},
       "same functions on a record with another pinout renumber the pads (wrong-pinout class impossible)")

    dual = copy.deepcopy(r)                      # two pins named GND (pads 1 and 4)
    dual["id"] = "dual-gnd"
    dual["pins"]["4"].pop("alias", None)
    dual["pins"]["4"]["name"] = "GND"
    recs["dual-gnd"] = dual
    rest = {k: "N" for k in ("TRIG", "OUT", "CONT", "THRES", "DISCH", "VCC")}
    ok(raises(lambda: registry_part("U2", "dual-gnd", "x", dict(rest, GND="GND"), "G"),
              "ambiguous", "GND#1 = pad 1", "GND#2 = pad 4", "pad number"),
       "a duplicated pin name is ambiguous: error lists GND#1/GND#2 with their pads")
    ok(registry_part("U2", "dual-gnd", "x", dict(rest, **{"GND#1": "GND", "GND#2": "GND"}), "G")["pins"]["4"] == "GND"
       and registry_part("U2", "dual-gnd", "x", dict(rest, **{"1": "GND", "GND#2": "GND"}), "G")["pins"]["1"] == "GND",
       "GND#n and pad numbers disambiguate")
    ok(raises(lambda: registry_part("U2", "dual-gnd", "x", dict(rest, **{"GND#3": "GND", "1": "G"}), "G"), "2 pin(s) named GND"),
       "GND#3 beyond the pins with that name raises")
    conn = copy.deepcopy(r)
    conn["id"], conn["kind"] = "conn8", "connector"
    recs["conn8"] = conn
    ok(registry_part("J1", "conn8", "c", {"GND": "GND"}, "G", nc="rest")["pins"] == {"1": "GND"}
       and registered_nc()["J1"] == ["2", "3", "4", "5", "6", "7", "8"], 'nc="rest" allowed for a connector record')

    ok(set(registered_refs()) == {"U1", "Q1", "U2", "J1"} and registered_refs()["J1"] == "conn8", "registered_refs() tracks every call")
    # ---- PR-BYNAME / package family helpers
    begin_netlist_load()
    registry_part("U9", "ne555p-dip8", "x", dict(by_name, GND="GND"), "G")
    registry_part("U8", "ne555p-dip8", "x", {int(k): v for k, v in want.items()}, "G")
    ok(registered_bynumber() == {"U8": ["1", "2", "3", "4", "5", "6", "7", "8"]}, "registered_bynumber() lists only pins typed as numbers")
    ok(by_name_required(r) and not by_name_required(conn) and not by_name_required({"kind": "part", "pins": {"1": {"name": "~"}, "2": {"name": "~"}, "3": {"name": "~"}}}),
       "by_name_required: kind=part with >= 3 meaningful names only (not connectors, not '~' pins)")
    ok(pkg_family("TO-220AB") == pkg_family("TO-220-3_Vertical") == "TO220" and pkg_family("DIP-8_W7.62mm") == "DIP8"
       and pkg_family("SOIC-8_3.9x4.9mm_P1.27mm") == "SOIC8" and pkg_family("R_Axial_DIN0207") is None, "pkg_family normalises")
    ok(judge_package(r, "DIP-8_W7.62mm")[0] == "ok" and judge_package(r, "SOIC-8_3.9x4.9mm_P1.27mm")[0] == "mismatch",
       "judge_package: DIP-8 record on a DIP-8 footprint ok, on SOIC-8 mismatch")
    gen = {"package": {"name": "Axial DIN0207 1/4 W, 10.16 mm pitch"}}
    ok(judge_package(gen, "R_Axial_DIN0207_L6.3mm")[0] == "unjudged" and judge_package(gen, "Diode_x")[0] == "unjudged",
       "judge_package: unknown mapping is UNJUDGED, never ok")
    gen["footprint_aliases"] = ["R_Axial_DIN0207"]
    ok(judge_package(gen, "R_Axial_DIN0207_L6.3mm")[0] == "ok" and judge_package(gen, "C_Disc_D5.0mm")[0] == "mismatch",
       "judge_package: footprint_aliases match, and a declared alias that does not match is a mismatch")
    ok(judge_lcsc_package({"package": {}}, "x") == "unjudged"
       and judge_lcsc_package({"package": {}, "lcsc_package_aliases": ["D=5mm"]}, "插件,D=5mm") == "ok"
       and judge_lcsc_package({"package": {}, "lcsc_package_aliases": ["D=5mm"]}, "插件,D=3mm") == "mismatch",
       "judge_lcsc_package: aliases match substrings of LCSC's string, none declared = unjudged")
    begin_netlist_load()
    ok(registered_refs() == {} and registered_nc() == {} and build_problems() == {}, "begin_netlist_load() resets the tracker")
    begin_netlist_load(lenient=True)
    d = registry_part("U1", "ne555p-dip8", "NE555P", {"GND": "GND", "BOGUS": "X"}, "G")
    ok("U1" in build_problems() and registered_refs() == {"U1": "ne555p-dip8"} and d["pins"]["1"] == "GND"
       and any("BOGUS" in m for m in build_problems()["U1"]),
       "lenient build mode records the problem and still builds the part")
    begin_netlist_load()

    # ---- $PARTS_RECORDS_DIR and lenient loading
    saved_env = os.environ.get("PARTS_RECORDS_DIR")
    try:
        os.environ["PARTS_RECORDS_DIR"] = str(tmp)
        ok(records_dir() == tmp, "PARTS_RECORDS_DIR redirects records_dir()")
        (tmp / "ne555p.json").write_text(json.dumps(_FIXTURE), encoding="utf-8")
        ok("ne555p-dip8" in load_all(), "load_all() with no argument reads $PARTS_RECORDS_DIR")
        tam = copy.deepcopy(_FIXTURE)
        tam.update(verification="crosschecked", evidence=[{"verified_by": "t"}])
        tam["signed_hash"] = signed_hash(tam)
        tam["mpn"] = "NE555Q"
        (tmp / "ne555p.json").write_text(json.dumps(tam), encoding="utf-8")
        lrecs, lprob = load_all(lenient=True)
        ok("ne555p-dip8" in lrecs and any("PR-HASH" in m for m in lprob.get("ne555p-dip8", [])),
           "load_all(lenient=True) returns (records, problems): tampered record kept, PR-HASH reported per record")
        ok(raises(load_all, "PR-HASH"), "load_all() (fail closed) raises on the same tampered record")
        os.environ["PARTS_RECORDS_DIR"] = str(tmp / "nope")
        ok(raises(load_all, "does not exist"), "a missing PARTS_RECORDS_DIR raises instead of loading zero records")
    finally:
        if saved_env is None:
            os.environ.pop("PARTS_RECORDS_DIR", None)
        else:
            os.environ["PARTS_RECORDS_DIR"] = saved_env
        (tmp / "ne555p.json").write_text(json.dumps(_FIXTURE), encoding="utf-8")

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
