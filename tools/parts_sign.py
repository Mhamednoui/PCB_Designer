"""Registry verification workflow (P1-T3): bind / assist / crosscheck / sign / audit.

Spec: docs/design/P1_PARTS_REGISTRY.md section 4 and 9.1.  Also reachable as `python tools/parts.py <cmd>`.

  python tools/parts_sign.py assist <id> [--offline]
  python tools/parts_sign.py bind <id> --symbol Lib:Sym --footprint Lib:Fp
  python tools/parts_sign.py crosscheck <id> --datasheet URL|FILE --page N [--rev R]
  python tools/parts_sign.py sign <id> --by NAME [--doc URL --page N --rev R] [--tier verified] [--i-am-the-owner]
  python tools/parts_sign.py audit
  python tools/parts_sign.py selftest

Tiers (spec 9.1):  unverified -> crosschecked -> verified.
  * `crosscheck` is the ONLY thing an agent may use to raise a tier. It sets `crosschecked` only when
    assist finds 0 diffs across KiCad symbol, KiCad footprint, EasyEDA symbol and EasyEDA footprint, and the
    cited datasheet page (if it can be read) names every pin. It writes evidence + signed_hash.
  * `sign` sets `verified`. It needs the owner: an interactive terminal where the owner types the answers, or
    the explicit --i-am-the-owner flag. Without either it refuses.
Every command takes --records-dir DIR (default parts/records) so mutations can run on a copy.
Exit codes: 0 ok, 1 diffs / refused, 2 source unavailable, 3 owner confirmation missing.
"""
import argparse
import collections
import datetime
import json
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from boardgen import parts as reg, parts_cache as pc, kicad_paths     # noqa: E402
import parts as cli                                                    # noqa: E402  (tools/parts.py: dumps, _pad_copies)
import sym_pins                                                        # noqa: E402

AGENT = "agent-crosscheck"


# --------------------------------------------------------------------------- records
def find(pid, rdir=None):
    d = Path(rdir) if rdir else reg.RECORDS_DIR
    for f in sorted(d.glob("*.json")):
        try:
            r = json.loads(f.read_text(encoding="utf-8"))
        except ValueError:
            continue
        if r.get("id") == pid:
            return f, r
    raise reg.RegistryError('no record with id "%s" in %s' % (pid, d))


def write(path, rec):
    problems = reg.validate(rec, path.name)
    if problems:
        raise reg.RegistryError("refusing to write an invalid record:\n" + "\n".join(problems))
    path.write_text(cli.dumps(rec), encoding="utf-8")


# --------------------------------------------------------------------------- name handling
def norm(name):
    """Case, KiCad overbars ~{}, '/', '~' and whitespace are not differences."""
    return re.sub(r"[~{}/\s]", "", str(name)).upper()


def accepted(pin):
    """Normalised names a source may use for this record pin: `name` plus comma-separated `alias`."""
    out = {norm(pin["name"])}
    for a in str(pin.get("alias", "")).split(","):
        if a.strip():
            out.add(norm(a))
    return out


# --------------------------------------------------------------------------- the four sources
def src_kicad_symbol(symbol):
    """({pin number: [raw names]}, reason). Reason is set (and the dict None) when unavailable."""
    if ":" not in symbol:
        return None, "symbol %r is not Lib:Name" % symbol
    lib, name = symbol.split(":", 1)
    try:
        found = sym_pins.pins(lib, name)
    except SystemExit as e:
        return None, str(e)
    d = collections.defaultdict(list)
    for num, nm, _t in found:
        d[num].append(nm)
    return (dict(d) if d else None), (None if d else "symbol %s defines no pins" % symbol)


def src_kicad_footprint(fp):
    """(Counter of pad names, reason). Unnamed pads (mounting holes) are not signal pads."""
    if ":" not in fp:
        return None, "footprint %r is not Lib:Name" % fp
    lib, name = fp.split(":", 1)
    f = Path(kicad_paths.FOOTPRINTS) / (lib + ".pretty") / (name + ".kicad_mod")
    if not f.exists():
        return None, "no footprint file %s" % f
    names = re.findall(r'\(pad "([^"]*)"', f.read_text(encoding="utf-8", errors="replace"))
    return collections.Counter(n for n in names if n), None


def src_easyeda(lcsc, offline):
    """(symbol {num: [names]}, footprint Counter, fetched_at, flags, reason)."""
    try:
        e = pc.easyeda(lcsc, True if offline else None)
    except (pc.CacheMiss, ValueError) as x:
        return None, None, None, [], str(x)
    ee = e.data["easyeda_json"]
    sym = collections.defaultdict(list)
    for s in ee["dataStr"]["shape"]:
        if s.startswith("P~"):
            seg = s.split("^^")
            sym[seg[0].split("~")[3]].append(seg[3].split("~")[4])
    fp = collections.Counter()
    for s in ee["packageDetail"]["dataStr"]["shape"]:
        if s.startswith("PAD~"):
            num = s.split("~")[8]
            if num:
                fp[num] += 1
    return dict(sym), fp, e.fetched_at, e.flags(), None


# --------------------------------------------------------------------------- assist
def assist(rec, offline=False):
    """Compare every source with the record's pin map. Returns a report dict; never raises on a missing source."""
    pins = rec["pins"]
    copies = rec["kicad"].get("fp_pad_copies") or {}
    want = {n: copies.get(n, 1) for n in pins}
    ok_names = {n: accepted(p) for n, p in pins.items()}
    kc_sym, kc_sym_why = src_kicad_symbol(rec["kicad"]["symbol"])
    kc_fp, kc_fp_why = src_kicad_footprint(rec["kicad"]["footprint"])
    ee_sym = ee_fp = ee_at = None
    ee_flags, ee_why = [], "record has no lcsc id"
    if (rec.get("lcsc") or {}).get("id"):
        ee_sym, ee_fp, ee_at, ee_flags, ee_why = src_easyeda(rec["lcsc"]["id"], offline)

    rows = {n: dict(pin=n, rec=pins[n]["name"] + ("/" + pins[n]["alias"] if pins[n].get("alias") else ""),
                    kc_sym=None, kc_fp=None, ee_sym=[], ee_fp=0, why=[]) for n in pins}
    extra = {}                                                    # row for things the record does not have

    def row(n):
        return rows[n] if n in rows else extra.setdefault(
            n, dict(pin=n + "?", rec="(none)", kc_sym=None, kc_fp=None, ee_sym=[], ee_fp=0, why=[]))

    if kc_sym is not None:
        for n in pins:
            rows[n]["kc_sym"] = kc_sym.get(n, [])
        for n, names in kc_sym.items():
            if n not in pins:
                row(n)["kc_sym"] = names
                row(n)["why"].append("KiCad symbol pin %s is not in the record" % n)
    if kc_fp is not None:
        for n in pins:
            rows[n]["kc_fp"] = kc_fp.get(n, 0)
        for n, c in kc_fp.items():
            if n not in pins:
                row(n)["kc_fp"] = c
                row(n)["why"].append("KiCad footprint has pad %s which the record does not" % n)

    ee_map = {}                                                   # EasyEDA pin number -> record pin number
    if ee_sym is not None:
        for num, names in sorted(ee_sym.items()):
            if num in pins:
                ee_map[num] = num
            else:                                                 # duplicate/tab pad: fold onto the same-named pin
                cand = [n for n in pins if want[n] > 1 and any(norm(x) in ok_names[n] for x in names)]
                ee_map[num] = cand[0] if cand else num
            tgt = row(ee_map[num])
            tgt["ee_sym"] += ["%s%s" % (x, "" if num == ee_map[num] else " [EE pad %s]" % num) for x in names]
            if ee_map[num] not in pins:
                tgt["why"].append("EasyEDA symbol pin %s (%s) is not in the record" % (num, "/".join(names)))
    if ee_fp is not None:
        for num, c in sorted(ee_fp.items()):
            tgt = row(ee_map.get(num, num))
            tgt["ee_fp"] += c
            if ee_map.get(num, num) not in pins:
                tgt["why"].append("EasyEDA footprint has pad %s which the record does not" % num)

    for n, r in rows.items():
        if kc_sym is not None:
            if not r["kc_sym"]:
                r["why"].append("KiCad symbol has no pin %s" % n)
            for x in r["kc_sym"]:
                if norm(x) not in ok_names[n]:
                    r["why"].append("KiCad symbol pin %s is %r, record says %r" % (n, x, pins[n]["name"]))
        if kc_fp is not None and r["kc_fp"] != want[n]:
            r["why"].append("KiCad footprint has %d pad(s) named %s, record expects %d" % (r["kc_fp"], n, want[n]))
        if ee_sym is not None:
            if not r["ee_sym"]:
                r["why"].append("EasyEDA symbol has no pin %s" % n)
            for x in r["ee_sym"]:
                if norm(x.split(" [EE")[0]) not in ok_names[n]:
                    r["why"].append("EasyEDA symbol pin %s is %r, record says %r" % (n, x, pins[n]["name"]))
        if ee_fp is not None and r["ee_fp"] != want[n]:
            r["why"].append("EasyEDA footprint has %d pad(s) for pin %s, record expects %d" % (r["ee_fp"], n, want[n]))
    all_rows = list(rows.values()) + list(extra.values())
    return dict(rows=all_rows, diffs=[w for r in all_rows for w in r["why"]],
                sources=dict(kicad_symbol=kc_sym is not None, kicad_footprint=kc_fp is not None,
                             easyeda_symbol=ee_sym is not None, easyeda_footprint=ee_fp is not None),
                missing={k: v for k, v in (("kicad_symbol", kc_sym_why), ("kicad_footprint", kc_fp_why),
                                           ("easyeda", ee_why)) if v},
                ee_fetched_at=ee_at, ee_flags=ee_flags)


def render(rec, rep):
    def cell(v, na="n/a"):
        if v is None:
            return na
        return ",".join(v) if isinstance(v, list) else str(v)
    head = ("pin", "record", "KiCad sym", "KiCad fp pads", "EasyEDA sym", "EasyEDA fp pads", "")
    lines = [head]
    for r in rep["rows"]:
        lines.append((r["pin"], r["rec"], cell(r["kc_sym"]), cell(r["kc_fp"]), cell(r["ee_sym"] or None, "-")
                      if rep["sources"]["easyeda_symbol"] else "n/a",
                      str(r["ee_fp"]) if rep["sources"]["easyeda_footprint"] else "n/a", "DIFF" if r["why"] else "ok"))
    w = [max(len(l[i]) for l in lines) for i in range(len(head))]
    print("%s  (%s, %s)" % (rec["id"], rec["kicad"]["symbol"], rec["kicad"]["footprint"]))
    for l in lines:
        print("  " + "  ".join(c.ljust(w[i]) for i, c in enumerate(l)).rstrip())
    for k, v in rep["missing"].items():
        print("  source unavailable: %s: %s" % (k, v))
    for f in rep["ee_flags"]:
        print("  note: EasyEDA cache: " + f)
    for d in rep["diffs"]:
        print("  DIFF: " + d)
    print("  %d diff(s); sources present: %s" % (len(rep["diffs"]), ", ".join(k for k, v in rep["sources"].items() if v) or "none"))


def cmd_assist(a):
    _, rec = find(a.id, a.records_dir)
    rep = assist(rec, a.offline)
    render(rec, rep)
    return 1 if rep["diffs"] else 0


# --------------------------------------------------------------------------- bind
def cmd_bind(a):
    path, rec = find(a.id, a.records_dir)
    if not a.symbol and not a.footprint:
        print("ERROR: give --symbol and/or --footprint")
        return 1
    new = dict(rec["kicad"])
    if a.symbol:
        new["symbol"] = a.symbol
    if a.footprint:
        new["footprint"] = a.footprint
    for what, (val, why) in (("symbol", src_kicad_symbol(new["symbol"])), ("footprint", src_kicad_footprint(new["footprint"]))):
        if val is None:
            print("ERROR: cannot bind %s: %s" % (what, why))
            return 1
    copies = cli._pad_copies(new["footprint"])
    new.pop("fp_pad_copies", None)
    if copies:
        new["fp_pad_copies"] = copies
    if new != rec["kicad"]:
        rec["kicad"] = new
        if rec.get("signed_hash") is not None or rec["verification"] != "unverified":
            print("NOTE: kicad binding is a signed field; tier %s -> unverified, signature cleared" % rec["verification"])
            rec["verification"], rec["status"], rec["signed_hash"] = "unverified", "draft", None
        write(path, rec)
        print("bound %s: %s + %s%s" % (a.id, new["symbol"], new["footprint"], " (pad copies %s)" % copies if copies else ""))
    else:
        print("binding unchanged")
    rep = assist(rec, a.offline)
    render(rec, rep)
    return 1 if rep["diffs"] else 0


# --------------------------------------------------------------------------- datasheet page text (assist only)
def datasheet_page_check(rec, ds, page, cache_id):
    """Fetch the cited PDF, extract the cited page with pdftotext, and check each pin name appears as a word.
    Returns (state, detail): state in ok / missing / unavailable."""
    exe = shutil.which("pdftotext")
    if not exe:
        return "unavailable", "pdftotext not installed"
    p = Path(ds)
    if not p.exists():
        d = pc.CACHE_DIR / "datasheets" / cache_id
        d.mkdir(parents=True, exist_ok=True)
        p = d / (re.sub(r"[^A-Za-z0-9._-]", "_", ds.rsplit("/", 1)[-1]) or "datasheet.pdf")
        if not p.suffix:
            p = p.with_suffix(".pdf")
        if not p.exists():
            try:
                import urllib.request
                req = urllib.request.Request(ds, headers={"User-Agent": "Mozilla/5.0 pcb-parts-registry/1"})
                with urllib.request.urlopen(req, timeout=40) as r:
                    p.write_bytes(r.read())
            except Exception as e:
                return "unavailable", "download failed: %s: %s" % (type(e).__name__, e)
    r = subprocess.run([exe, "-f", str(page), "-l", str(page), "-layout", str(p), "-"], capture_output=True)
    text = r.stdout.decode("utf-8", "replace")
    if r.returncode != 0 or not text.strip():
        return "unavailable", "pdftotext could not read page %s of %s" % (page, p.name)
    words = set(re.findall(r"[A-Z0-9]+", text.upper()))
    missing = [n for n, pin in rec["pins"].items() if not (accepted(pin) & words)]
    if missing:
        return "missing", "page %s of %s does not mention pin(s) %s" % (page, p.name, ", ".join(
            "%s %s" % (n, rec["pins"][n]["name"]) for n in missing))
    return "ok", "page %s of %s names all %d pins" % (page, p.name, len(rec["pins"]))


# --------------------------------------------------------------------------- crosscheck
def cmd_crosscheck(a):
    path, rec = find(a.id, a.records_dir)
    if rec["kind"] != "part":
        print("REFUSED: crosscheck is for kind=part records (this is %s)" % rec["kind"])
        return 1
    if rec["verification"] == "verified" and reg.hash_ok(rec) and rec.get("signed_hash"):
        print("%s is already verified by the owner; nothing to do." % a.id)
        return 0
    rep = assist(rec, a.offline)
    render(rec, rep)
    refuse = []
    refuse += ["assist reports %d diff(s)" % len(rep["diffs"])] if rep["diffs"] else []
    refuse += ["source not available: " + k for k, v in rep["sources"].items() if not v]
    if not a.datasheet or not a.page:
        refuse.append("--datasheet and --page are required")
    state, detail = datasheet_page_check(rec, a.datasheet, a.page, (rec.get("lcsc") or {}).get("id", rec["id"]))
    if state == "missing":
        refuse.append("datasheet check: " + detail)
    print("  datasheet page text: %s: %s" % (state, detail))
    if refuse:
        print("REFUSED: %s stays %s. Reason: %s" % (a.id, rec["verification"], "; ".join(refuse)))
        return 1
    srcs = [k.replace("_", " ") for k in rep["sources"]]
    rec["evidence"] = [e for e in rec.get("evidence", []) if e.get("verified_by") != AGENT]
    ev = {"section": "pins", "doc_url": a.datasheet, "page": a.page,
          "method": "crosscheck: pin/pad diff of %s against the record, 0 diffs; datasheet page text %s" % (", ".join(srcs), state),
          "verified_by": AGENT, "date": datetime.date.today().isoformat(),
          "notes": "Scope: pin numbers, pin names and pad multiset ONLY. NOT checked: pin class, abs_max, ratings, tht lead size, "
                   "polarity (those need the owner). EasyEDA data fetched %s (%s). %s. A person has not read the datasheet."
                   % (rep["ee_fetched_at"], rec["lcsc"]["id"], detail)}
    if a.rev:
        ev["rev"] = a.rev
    rec["evidence"].append(ev)
    rec["verification"] = "crosschecked"
    rec["signed_hash"] = reg.signed_hash(rec)
    write(path, rec)
    print("OK: %s -> crosschecked (hash %s...). status stays %r; the release lists it as an open human-check item."
          % (a.id, rec["signed_hash"][:12], rec["status"]))
    return 0


# --------------------------------------------------------------------------- sign (owner only)
TICKS = ["the pin table on the cited datasheet page matches every pin of this record (number AND function)",
         "the absolute-max values in the record (if any) match the datasheet",
         "the lead size / pad geometry was read from the package drawing, not guessed",
         "pin 1 / polarity marker in the record matches the footprint"]


def cmd_sign(a):
    if a.tier != "verified":
        print("REFUSED: `sign` only sets tier `verified`. Use `crosscheck` for `crosschecked`.")
        return 1
    interactive = sys.stdin.isatty() and sys.stdout.isatty()
    if not interactive and not a.i_am_the_owner:
        print("REFUSED: tier `verified` is set by the owner only (spec 9.1). Run this in a terminal and answer the\n"
              "tick list yourself, or pass --i-am-the-owner. Agents must not do either.")
        return 3
    path, rec = find(a.id, a.records_dir)
    rep = assist(rec, a.offline)
    render(rec, rep)
    if rep["diffs"]:
        print("REFUSED: assist reports %d diff(s); fix the record or the binding first." % len(rep["diffs"]))
        return 1
    last = next((e for e in reversed(rec.get("evidence", [])) if e.get("doc_url")), {})
    doc, page = a.doc or last.get("doc_url"), a.page or last.get("page")
    if not (a.by and doc and page):
        print("REFUSED: need --by NAME and a datasheet (--doc URL --page N), or an existing crosscheck evidence entry.")
        return 1
    if interactive and not a.i_am_the_owner:
        print("\nOwner tick list for %s (datasheet %s page %s). Type y to confirm each:" % (a.id, doc, page))
        for t in TICKS:
            if input("  I confirm %s [y/N] " % t).strip().lower() != "y":
                print("REFUSED: not confirmed; nothing written.")
                return 3
    rec["evidence"].append({"section": "pins,tht,polarity", "doc_url": doc, "page": page,
                            **({"rev": a.rev} if a.rev else {}),
                            "method": "owner sign-off after assist 0 diffs (%s)" % (
                                "--i-am-the-owner flag" if a.i_am_the_owner else "interactive tick list"),
                            "verified_by": a.by, "date": datetime.date.today().isoformat()})
    rec["verification"], rec["status"] = "verified", "verified"
    rec["signed_hash"] = reg.signed_hash(rec)
    write(path, rec)
    print("OK: %s -> verified by %s (hash %s...)" % (a.id, a.by, rec["signed_hash"][:12]))
    return 0


# --------------------------------------------------------------------------- audit
def audit(rdir=None):
    """Tier claims a hand-edit could fake: crosschecked/verified needs a signature that matches, and evidence
    by the right kind of signer. (parts.load_all only checks a hash that is present.)"""
    d = Path(rdir) if rdir else reg.RECORDS_DIR
    out = []
    for f in sorted(d.glob("*.json")):
        r = json.loads(f.read_text(encoding="utf-8"))
        t = r.get("verification")
        if t in ("crosschecked", "verified"):
            if not r.get("signed_hash"):
                out.append("%s: tier %s but no signed_hash (hand-edited tier?)" % (f.name, t))
            who = [e.get("verified_by") for e in r.get("evidence", [])]
            if t == "crosschecked" and AGENT not in who:
                out.append("%s: tier crosschecked but no %s evidence entry" % (f.name, AGENT))
            if t == "verified" and not [w for w in who if w and w != AGENT]:
                out.append("%s: tier verified but all evidence is by %s" % (f.name, AGENT))
    return out


def cmd_audit(a):
    reg.load_all(a.records_dir)
    problems = audit(a.records_dir)
    for p in problems:
        print("AUDIT: " + p)
    print("audit: %s" % ("%d problem(s)" % len(problems) if problems else "records and tiers consistent"))
    return 1 if problems else 0


# --------------------------------------------------------------------------- selftest (mutations on a copy)
def cmd_selftest(a):
    fails = []

    def ok(c, what):
        print(("PASS  " if c else "FAIL  ") + what)
        if not c:
            fails.append(what)
    tmp = Path(tempfile.mkdtemp(prefix="parts_sign_"))
    try:
        for f in reg.RECORDS_DIR.glob("*.json"):
            shutil.copy(f, tmp / f.name)
        pid = "ne555p-dip8"
        path, rec = find(pid, tmp)
        rec["pins"]["2"]["name"], rec["pins"]["6"]["name"] = rec["pins"]["6"]["name"], rec["pins"]["2"]["name"]
        write(path, rec)
        rep = assist(rec, a.offline)
        ok(any("pin 2" in d and "THRES" in d for d in rep["diffs"]) and any("pin 6" in d for d in rep["diffs"]),
           "swapped pins 2/6 -> assist names both: %s" % rep["diffs"][:2])
        ns = argparse.Namespace(id=pid, records_dir=str(tmp), offline=a.offline, datasheet="x", page=1, rev=None)
        before = find(pid, tmp)[1]
        ok(cmd_crosscheck(ns) == 1 and find(pid, tmp)[1] == before, "crosscheck refuses the swapped record and writes nothing")
        try:
            reg.load_all(tmp)
            ok(False, "stale signature on the swapped record trips PR-HASH in load_all")
        except reg.RegistryError as e:
            ok("PR-HASH" in str(e), "stale signature on the swapped record trips PR-HASH in load_all")
        ns = argparse.Namespace(id=pid, records_dir=str(tmp), by="x", doc="d", page=1, rev=None, tier="verified",
                                i_am_the_owner=False, offline=a.offline)
        ok(cmd_sign(ns) == 3, "sign --tier verified without the owner flag refuses (non-interactive)")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("selftest: %s" % ("FAILED %d" % len(fails) if fails else "all passed"))
    return 1 if fails else 0


# --------------------------------------------------------------------------- CLI
def build(sub):
    def common(p, **kw):
        p.add_argument("id", **kw)
        p.add_argument("--records-dir")
        p.add_argument("--offline", action="store_true", help="use the EasyEDA cache only")
        return p
    common(sub.add_parser("assist", help="per-pin diff of KiCad / EasyEDA / record; exit 1 on any diff"))
    b = common(sub.add_parser("bind", help="set kicad.symbol / kicad.footprint, then run assist"))
    b.add_argument("--symbol")
    b.add_argument("--footprint")
    c = common(sub.add_parser("crosscheck", help="agent path to tier crosschecked"))
    c.add_argument("--datasheet", required=True)
    c.add_argument("--page", required=True, type=int)
    c.add_argument("--rev")
    s = common(sub.add_parser("sign", help="owner path to tier verified"))
    s.add_argument("--by")
    s.add_argument("--doc")
    s.add_argument("--page", type=int)
    s.add_argument("--rev")
    s.add_argument("--tier", default="verified")
    s.add_argument("--i-am-the-owner", action="store_true", help="confirm non-interactively. Agents must not pass this.")
    au = sub.add_parser("audit", help="tier claims must match signature and evidence")
    au.add_argument("--records-dir")
    se = sub.add_parser("selftest", help="mutation checks on a temp copy")
    se.add_argument("--offline", action="store_true")


CMDS = {"assist": cmd_assist, "bind": cmd_bind, "crosscheck": cmd_crosscheck, "sign": cmd_sign,
        "audit": cmd_audit, "selftest": cmd_selftest}


def main(argv=None):
    ap = argparse.ArgumentParser(prog="parts_sign", description=__doc__.split("\n")[0])
    build(ap.add_subparsers(dest="cmd", required=True))
    a = ap.parse_args(argv)
    try:
        return CMDS[a.cmd](a)
    except (reg.RegistryError, pc.CacheMiss, ValueError) as e:
        print("ERROR:", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
