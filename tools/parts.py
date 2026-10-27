"""parts CLI (P1-T2): `parts new <LCSC id>` and `parts refresh [<id>|--all]`.  Spec: docs/design/P1_PARTS_REGISTRY.md.

  python tools/parts.py new C46749 [--id ne555p-dip8] [--dry-run] [--out FILE] [--offline]
  python tools/parts.py refresh [<id>|--all] [--offline]
  python tools/parts.py assist|bind|crosscheck|sign|audit ...    (tools/parts_sign.py, verification tiers)

`new` writes a DRAFT (status draft, verification unverified) from machine data only; human/datasheet-only
fields (pin class, abs_max, tht, polarity) are left out and listed as TODO. An existing id is only
filled where a field is missing, never overwritten. `refresh` updates stock/price/snapshot_date and
lcsc.class and nothing else, so signed fields and the hash are untouched. Offline (flag or network
failure) `refresh` changes nothing and says so (exit 2).
"""
import argparse
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardgen import parts, parts_cache as pc          # noqa: E402

MAKER = {"TI": "Texas Instruments", "ST": "STMicroelectronics", "ON": "onsemi"}
FP_SUGGEST = {"DIP-8": "Package_DIP:DIP-8_W7.62mm", "DIP-14": "Package_DIP:DIP-14_W7.62mm",
              "DIP-16": "Package_DIP:DIP-16_W7.62mm", "SOT-223": "Package_TO_SOT_SMD:SOT-223-3_TabPin2"}


def _maker(raw):
    s = re.sub(r"\(.*?\)", "", raw or "").strip()     # "TI(<chinese name>)" -> "TI"
    return MAKER.get(s, s) or None


def _slug(s):
    return re.sub(r"[^a-z0-9.]+", "-", s.lower()).strip("-")


def _suggest_symbol(mpn):
    """Exact-name symbol in an installed KiCad library, else None. A suggestion; the human confirms."""
    from boardgen import kicad_paths
    d = Path(kicad_paths.SYMBOLS)
    if d.is_dir():
        for f in sorted(d.glob("*.kicad_sym")):
            if '(symbol "%s"' % mpn in f.read_text(encoding="utf-8", errors="replace"):
                return "%s:%s" % (f.stem, mpn)
    return None


def _pad_copies(fp):
    """{pad name: count} for pad names that appear more than once in the KiCad footprint file."""
    if not fp or ":" not in fp:
        return None
    from boardgen import kicad_paths
    lib, name = fp.split(":", 1)
    f = Path(kicad_paths.FOOTPRINTS) / (lib + ".pretty") / (name + ".kicad_mod")
    if not f.exists():
        return None
    names = re.findall(r'\(pad "([^"]*)"', f.read_text(encoding="utf-8", errors="replace"))
    return {n: names.count(n) for n in sorted(set(names)) if n and names.count(n) > 1} or None


def _num(x):
    return int(float(x)) if float(x) == int(float(x)) else float(x)


def ratings_from(desc):
    r = {}
    m = re.search(r"(\d+(?:\.\d+)?)V~(\d+(?:\.\d+)?)V", desc)
    m2 = re.search(r"\s(\d+(?:\.\d+)?)V\s+(\d+(?:\.\d+)?)A\b", desc)
    if m:
        r["v_op"] = [_num(m.group(1)), _num(m.group(2))]
    elif m2:
        r["v_op"] = [None, _num(m2.group(1))]
    if m2:
        r["i_max"] = float(m2.group(2))
    t = re.search(r"([+-]?\d+)℃~\+?(\d+)℃", desc)
    if t:
        r["t_op_c"] = [int(t.group(1)), int(t.group(2))]
    return r


def pins_from(ee):
    """{pad: {name}} from EasyEDA symbol shapes. A later pad repeating a name (SOT-223 tab) becomes `also`."""
    pins, seen = {}, {}
    for s in ee["dataStr"]["shape"]:
        if not s.startswith("P~"):
            continue
        seg = s.split("^^")
        num, name = seg[0].split("~")[3], seg[3].split("~")[4]
        if name in seen:
            pins[seen[name]].setdefault("also", "EasyEDA pad %s has the same name (tab/duplicate pad)" % num)
        else:
            seen[name] = num
            pins[num] = {"name": name}
    return dict(sorted(pins.items(), key=lambda kv: (len(kv[0]), kv[0])))


def mount_from(ee):
    for s in ee["packageDetail"]["dataStr"]["shape"]:
        if s.startswith("PAD~"):
            f = s.split("~")
            if len(f) > 9 and f[9] not in ("", "0"):      # hole radius present
                return "tht"
    return "smd"


def body_from(ee):
    m = re.search(r"L(\d+(?:\.\d+)?)-W(\d+(?:\.\d+)?)(?:-H(\d+(?:\.\d+)?))?",
                  ee["packageDetail"]["dataStr"]["head"]["c_para"].get("3DModel", ""))
    return [float(x) for x in m.groups() if x] if m else None


def draft(lcsc, offline=None):
    """Build (record, flags, todo) from machine data. Raises MpnMismatch if the sources disagree."""
    j, e = pc.jlcsearch(lcsc, offline), pc.easyeda(lcsc, offline)
    flags = ["jlcsearch: " + f for f in j.flags()] + ["easyeda: " + f for f in e.flags()]
    ee = e.data["easyeda_json"]
    cp = ee["dataStr"]["head"]["c_para"]
    mpn = cp.get("Manufacturer Part") or j.data["mfr"]
    pc.verify_mpn(j.data["mfr"], mpn)
    pc.verify_mpn(ee.get("title"), mpn)
    pkg = j.data.get("package") or ""
    cls = "basic" if j.data.get("is_basic") else "preferred" if j.data.get("is_preferred") else "extended"
    rec = {"id": None, "kind": "part", "mpn": mpn}
    if _maker(cp.get("Manufacturer")):
        rec["manufacturer"] = _maker(cp["Manufacturer"])
    rec.update({"status": "draft", "verification": "unverified",
                "lcsc": {"id": pc.norm_lcsc(lcsc), "class": cls},
                "sourcing": {"stock": j.data["stock"], "price_1": j.data["price"],
                             "snapshot_date": j.fetched_at[:10]}})
    pk = {"name": pkg, "mount": mount_from(ee), "lcsc_package": pkg}
    if body_from(ee):
        pk["body_mm"] = body_from(ee)
    rec["package"] = pk
    sym, fp = _suggest_symbol(mpn), FP_SUGGEST.get(pkg)
    rec["kicad"] = {"symbol": sym or "TODO", "footprint": fp or "TODO"}
    copies = _pad_copies(fp)
    if copies:
        rec["kicad"]["fp_pad_copies"] = copies
    r = ratings_from(j.data.get("description", ""))
    if r:
        rec["ratings"] = r
    rec["pins"] = pins_from(ee)
    rec["evidence"] = []
    rec["signed_hash"] = None
    todo = ["pins.*.class and abs_max (datasheet only)", "tht.lead_mm / lead_d_mm (datasheet only)",
            "polarity (human)", "lifecycle (human/distributor)", "datasheet evidence and owner sign-off"]
    if not sym:
        todo.insert(0, "kicad.symbol (no exact-name symbol in installed libs)")
    if not fp:
        todo.insert(0, "kicad.footprint (no suggestion for package %r)" % pkg)
    rec["notes"] = ("DRAFT from machine data (jlcsearch + EasyEDA, %s). kicad symbol/footprint are tool suggestions. "
                    "TODO: %s. Nobody has checked this record against a datasheet (tier unverified)."
                    % (j.fetched_at[:10], "; ".join(todo)))
    return rec, flags, todo


def dumps(rec):
    """Stable layout: one top-level key per line; pins/evidence one entry per line."""
    one = lambda v: json.dumps(v, ensure_ascii=False)
    out = []
    for k, v in rec.items():
        if k in ("pins", "evidence") and v:
            isd = isinstance(v, dict)
            items = list(v.items()) if isd else [(None, x) for x in v]
            body = ",\n".join("    %s%s" % (one(a) + ": " if a is not None else "", one(b)) for a, b in items)
            out.append('  %s: %s\n%s\n  %s' % (one(k), "{" if isd else "[", body, "}" if isd else "]"))
        else:
            out.append("  %s: %s" % (one(k), one(v)))
    return "{\n" + ",\n".join(out) + "\n}\n"


def rec_path(pid):
    """Existing file whose record has this id (file name need not match the id), else <id>.json."""
    for f in sorted(parts.RECORDS_DIR.glob("*.json")):
        try:
            if json.loads(f.read_text(encoding="utf-8")).get("id") == pid:
                return f
        except ValueError:
            pass
    return parts.RECORDS_DIR / (pid + ".json")


def save(rec):
    rec_path(rec["id"]).write_text(dumps(rec), encoding="utf-8")


def merge_missing(old, new, prefix=""):
    """Fill keys absent/null in `old` from `new`; never overwrite. Returns changed paths."""
    changed = []
    for k, v in new.items():
        if k not in old or (old[k] is None and v is not None):
            old[k] = v
            changed.append(prefix + k)
        elif isinstance(old[k], dict) and isinstance(v, dict) and k != "pins":
            changed += merge_missing(old[k], v, prefix + k + ".")
    return changed


def cmd_new(a):
    rec, flags, todo = draft(a.lcsc, True if a.offline else None)
    rec["id"] = a.id or "%s-%s" % (_slug(rec["mpn"]), _slug(rec["package"]["name"]).replace("-", ""))
    for f in flags:
        print("WARNING:", f)
    if a.out or a.dry_run:
        if a.out:
            Path(a.out).write_text(dumps(rec), encoding="utf-8")
            print("wrote", a.out)
        else:
            print(dumps(rec))
        return 2 if flags else 0
    p = rec_path(rec["id"])
    if p.exists():
        old = json.loads(p.read_text(encoding="utf-8"))
        ch = merge_missing(old, rec)
        parts.validate(old, str(p))
        if ch:
            save(old)
        print("%s exists: kept every existing field; filled missing: %s" % (rec["id"], ch or "nothing"))
    else:
        parts.validate(rec, rec["id"])
        save(rec)
        print("wrote", p)
    print("TODO (human):", "; ".join(todo))
    return 2 if flags else 0


def cmd_refresh(a):
    ids = sorted(json.loads(f.read_text(encoding="utf-8"))["id"] for f in parts.RECORDS_DIR.glob("*.json")) if a.all else [a.id]
    rc = 0
    for pid in ids:
        p = rec_path(pid)
        if not p.exists():
            print("ERROR: no record", pid)
            rc = 1
            continue
        rec = json.loads(p.read_text(encoding="utf-8"))
        if not rec.get("lcsc"):
            print("%s: no lcsc id, skipped" % pid)
            continue
        try:
            j = pc.jlcsearch(rec["lcsc"]["id"], True if a.offline else None)
            if rec.get("mpn"):
                pc.verify_mpn(j.data["mfr"], rec["mpn"])
        except (pc.MpnMismatch, pc.CacheMiss) as e:
            print("ERROR %s: %s" % (pid, e))
            rc = 1
            continue
        d = j.data
        if j.stale:
            print("%s: NOT REFRESHED, %s. Cache is %.1f days old (stock %s on %s). Record unchanged."
                  % (pid, j.flags()[0], j.age_days, d["stock"], j.fetched_at[:10]))
            rc = max(rc, 2)
            continue
        s = rec.setdefault("sourcing", {})
        before = (dict(s), rec["lcsc"].get("class"))
        cls = "basic" if d.get("is_basic") else "preferred" if d.get("is_preferred") else "extended"
        s.update({"stock": d["stock"], "price_1": d["price"], "snapshot_date": j.fetched_at[:10]})
        rec["lcsc"]["class"] = cls
        if (s, cls) != before:
            save(rec)
        print("%s: stock %s -> %s, price_1 %s -> %s, class %s -> %s, snapshot %s" % (
            pid, before[0].get("stock"), s["stock"], before[0].get("price_1"), s["price_1"],
            before[1], cls, s["snapshot_date"]))
    return rc


SIGN_CMDS = ("assist", "bind", "crosscheck", "sign", "audit", "selftest")   # implemented in parts_sign.py (P1-T3)


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv and argv[0] in SIGN_CMDS:
        import parts_sign
        return parts_sign.main(argv)
    ap = argparse.ArgumentParser(prog="parts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("lcsc")
    n.add_argument("--id")
    n.add_argument("--dry-run", action="store_true")
    n.add_argument("--out")
    n.add_argument("--offline", action="store_true", help="use the cache only (flagged stale)")
    r = sub.add_parser("refresh")
    r.add_argument("id", nargs="?")
    r.add_argument("--all", action="store_true")
    r.add_argument("--offline", action="store_true")
    a = ap.parse_args(argv)
    try:
        if a.cmd == "new":
            return cmd_new(a)
        if not a.id and not a.all:
            ap.error("refresh needs <id> or --all")
        return cmd_refresh(a)
    except (pc.CacheMiss, pc.MpnMismatch, parts.RegistryError, ValueError) as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
