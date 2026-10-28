"""Parts stage (P1-T6): `check_parts.py <project-id> [--offline]`.  The network-backed complement of `lint`.

For every part a project declares through the parts registry (`registry_part`, docs/design/P1_PARTS_REGISTRY.md),
checks the record + the footprint actually used against live (or cached) LCSC / EasyEDA data:

    MPN    the LCSC id used in the BOM resolves (JLCPCB/LCSC detail MPN via the P1-T10 source chain, EasyEDA `Manufacturer Part`) to the record's MPN
    GEO    KiCad footprint pads vs EasyEDA footprint pads: pad count, pitch, row spacing, drill -> ERROR when they
           differ by more than 0.15 mm; pad SIZE differs legitimately between the two libraries -> WARN only (> 0.3 mm)
    PKG    record `package.lcsc_package` vs the package string LCSC lists (Chinese THT strings: WARN not judged)
    STOCK  stock vs boards x qty x 1.2, per ASSEMBLY mode of netlist.py: `hand` = INFO (LCSC stock), `pcba` = ERROR
           (JLCPCB assembly stock, source printed per part; spec section 9.4, P1-T10)
    FRESH  age of the data used (pcba: stock snapshot older than 7 days = ERROR), record status/lifecycle/snapshot_date

netlist.py settings (all optional): ASSEMBLY = "hand" | "pcba" (default hand), BOARDS = number of boards (default 5).
GEO is judged orientation-free (pad count, nearest-neighbour pitch, row spread perpendicular to the pitch axis -
pad CENTRES for through-hole, outer pad EDGES for SMD - and the sorted drill list), so rotated or mirrored libraries
and the SOT-223 tab pad need no pad-number mapping.

Offline (no network, or --offline / PARTS_OFFLINE=1): the cache is used. A rule that would pass is reported as
`WARN ... not judged (offline, cache age X d)`; with no cache `not judged (offline, no cache)`. It is never a silent
pass. A contradiction found in cached MPN/GEO/PKG data is still an ERROR (those facts do not drift nightly).

Output `ERROR|WARN|INFO rule target: message`, report projects/<id>/test/parts/parts.json (git-ignored), exit 1 on any
unwaived ERROR with `FAILED: ...`. Waivers: projects/<id>/waivers.json, {"check": "parts", "rule": "GEO", "refs": [..],
"why": ".."}. Run under system Python: python tools/boardgen/check_parts.py <project-id>"""
import json
import math
import os
import re
import sys
import time
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))                    # tools/
from boardgen import parts as _parts                          # noqa: E402
from boardgen import parts_cache as _cache                    # noqa: E402
from boardgen import project as _project                      # noqa: E402
from boardgen import waivers as _waivers                      # noqa: E402
from boardgen.sexp import parse, find_all, find               # noqa: E402

GEO_TOL_MM = 0.15            # pitch / row spacing / drill, spec section 3 PR-GEO
PAD_SIZE_WARN_MM = 0.3       # pad size differs legitimately between KiCad and EasyEDA: WARN only
EASYEDA_UNIT_MM = 0.254      # EasyEDA footprint coordinates are 10 mil
STOCK_MARGIN = 1.2           # spec section 9.4
DEFAULT_BOARDS = 5           # JLCPCB minimum order
STOCK_MAX_AGE_DAYS = _cache.STOCK_MAX_AGE_DAYS
RECORD_SNAPSHOT_WARN_DAYS = 90


class Finding:
    def __init__(self, sev, rule, target, msg, refs=()):
        self.sev, self.rule, self.target, self.msg, self.refs = sev, rule, target, msg, set(refs)
        self.waiver = None

    def line(self):
        tag = "WAIVED" if self.waiver is not None else self.sev
        tail = "  [waiver: %s]" % self.waiver["why"] if self.waiver is not None else ""
        return "%s %s %s: %s%s" % (tag, self.rule, self.target, self.msg, tail)

    def as_dict(self):
        return {"severity": "WAIVED" if self.waiver is not None else self.sev, "rule": self.rule,
                "target": self.target, "message": self.msg, "refs": sorted(self.refs)}


# --------------------------------------------------------------------------- geometry
class Pad:
    def __init__(self, name, x, y, w, h, rot, drill):
        self.name, self.x, self.y, self.w, self.h, self.rot, self.drill = name, x, y, w, h, rot, drill

    def half_extent(self, nx, ny):
        """Half the pad's width measured along unit vector (nx, ny) (rect rotated by self.rot)."""
        a = math.atan2(ny, nx) - math.radians(self.rot)
        return (abs(self.w * math.cos(a)) + abs(self.h * math.sin(a))) / 2.0


def kicad_pads(path):
    """Named pads of a .kicad_mod (mm). Unnamed and non-plated holes are skipped. None if the file is missing."""
    if not os.path.isfile(path):
        return None
    tree = parse(open(path, encoding="utf-8").read())
    out = []
    for p in find_all(tree, "pad"):
        name = str(p[1])
        if name == "" or str(p[2]) == "np_thru_hole":
            continue
        at, size, drill = find(p, "at"), find(p, "size"), find(p, "drill")
        dims = []
        for x in (drill[1:] if drill else []):
            try:
                dims.append(float(x))
            except (TypeError, ValueError):
                pass                                         # the word "oval"
        dims = [d for d in dims if d > 0]
        out.append(Pad(name, float(at[1]), float(at[2]), float(size[1]), float(size[2]),
                       float(at[3]) if len(at) > 3 else 0.0, min(dims) if dims else None))
    return out


def easyeda_pads(easyeda_json):
    """Pads of the EasyEDA footprint (mm) from `PAD~shape~cx~cy~w~h~layer~net~number~holeR~points~rot~id~holeLen~...`."""
    shapes = (((easyeda_json.get("packageDetail") or {}).get("dataStr") or {}).get("shape")) or []
    out = []
    for s in shapes:
        if not isinstance(s, str) or not s.startswith("PAD~"):
            continue
        f = s.split("~")
        num = f[8].strip() if len(f) > 8 else ""
        if num == "":
            continue
        u = EASYEDA_UNIT_MM
        r = float(f[9] or 0) * u if len(f) > 9 else 0.0
        slot = float(f[13] or 0) * u if len(f) > 13 else 0.0
        drill = None
        if r > 0:
            drill = 2 * r if slot <= 0 else min(2 * r, slot)
        out.append(Pad(num, float(f[2]) * u, float(f[3]) * u, float(f[4]) * u, float(f[5]) * u,
                       float(f[11] or 0) if len(f) > 11 else 0.0, drill))
    return out


def metrics(pads):
    """Orientation- and translation-free numbers: count, pitch, row spreads, drills, pad sizes."""
    n = len(pads)
    tht = any(p.drill for p in pads)
    pairs = []
    for i in range(n):
        for j in range(i + 1, n):
            d = math.hypot(pads[i].x - pads[j].x, pads[i].y - pads[j].y)
            if d > 0.05:                                     # overlapping copies (duplicate pad names) are not a pitch
                pairs.append((d, i, j))
    pitch, spreads = None, []
    if pairs:
        pitch = min(d for d, _i, _j in pairs)
        dirs = []
        for d, i, j in pairs:
            if d - pitch > 1e-3:
                continue
            ux, uy = (pads[j].x - pads[i].x) / d, (pads[j].y - pads[i].y) / d
            if ux < -1e-6 or (abs(ux) <= 1e-6 and uy < 0):
                ux, uy = -ux, -uy
            if not any(abs(ux - a) < 1e-2 and abs(uy - b) < 1e-2 for a, b in dirs):
                dirs.append((ux, uy))
        for ux, uy in dirs:
            nx, ny = -uy, ux                                 # perpendicular to the pitch axis
            lo = hi = None
            for p in pads:
                c = p.x * nx + p.y * ny
                e = 0.0 if tht else p.half_extent(nx, ny)    # THT: centre-to-centre, SMD: outer pad edges
                lo = c - e if lo is None else min(lo, c - e)
                hi = c + e if hi is None else max(hi, c + e)
            spreads.append(round(hi - lo, 3))
        spreads = sorted(set(spreads))
    return {"count": n, "tht": tht, "pitch": pitch, "row_spread": spreads,
            "drills": sorted(round(p.drill, 3) for p in pads if p.drill),
            "sizes": sorted((round(min(p.w, p.h), 3), round(max(p.w, p.h), 3)) for p in pads)}


def compare_geometry(km, em):
    """-> list of (severity, text) from KiCad metrics km vs EasyEDA metrics em; empty = agree within tolerance."""
    out = []
    if km["count"] != em["count"]:
        return [("ERROR", "pad count %d (KiCad) vs %d (LCSC/EasyEDA)" % (km["count"], em["count"]))]
    if km["tht"] != em["tht"]:
        out.append(("ERROR", "KiCad footprint is %s but LCSC/EasyEDA footprint is %s"
                    % ("through-hole" if km["tht"] else "SMD", "through-hole" if em["tht"] else "SMD")))
    if km["pitch"] is not None and em["pitch"] is not None and abs(km["pitch"] - em["pitch"]) > GEO_TOL_MM:
        out.append(("ERROR", "pitch %.2f mm (KiCad) vs %.2f mm (LCSC), tolerance %.2f"
                    % (km["pitch"], em["pitch"], GEO_TOL_MM)))
    ks, es = km["row_spread"], em["row_spread"]
    if ks and es:
        if len(ks) != len(es):
            out.append(("WARN", "row structure ambiguous (%s vs %s), row spacing not judged" % (ks, es)))
        else:
            worst = max(zip(ks, es), key=lambda t: abs(t[0] - t[1]))
            if abs(worst[0] - worst[1]) > GEO_TOL_MM:
                out.append(("ERROR", "row spacing %.2f mm (KiCad) vs %.2f mm (LCSC), tolerance %.2f"
                            % (worst[0], worst[1], GEO_TOL_MM)))
    if km["drills"] and km["drills"] != em["drills"]:
        if len(km["drills"]) != len(em["drills"]):
            out.append(("ERROR", "%d drilled pads (KiCad) vs %d (LCSC)" % (len(km["drills"]), len(em["drills"]))))
        else:
            kd, ed = max(zip(km["drills"], em["drills"]), key=lambda t: abs(t[0] - t[1]))
            if abs(kd - ed) > GEO_TOL_MM:
                out.append(("ERROR", "drill %.2f mm (KiCad) vs %.2f mm (LCSC), tolerance %.2f" % (kd, ed, GEO_TOL_MM)))
    worst = max((max(abs(a[0] - b[0]), abs(a[1] - b[1])) for a, b in zip(km["sizes"], em["sizes"])), default=0.0)
    if worst > PAD_SIZE_WARN_MM:
        out.append(("WARN", "pad size differs by up to %.2f mm between KiCad and LCSC (libraries legitimately differ; "
                            "check the land pattern against the datasheet)" % worst))
    return out


# --------------------------------------------------------------------------- helpers
def norm_pkg(s):
    return re.sub(r"[^A-Z0-9]", "", (s or "").upper())


def lcsc_class(j):
    return "basic" if j.get("is_basic") else "preferred" if j.get("is_preferred") else "extended"


def fp_path(NL, fp_id):
    lib, name = fp_id.split(":", 1)
    base = os.path.join(NL.PRJ_DIR, "lib") if lib in getattr(NL, "PROJECT_LIBS", ()) else NL.KICAD_FOOTPRINTS
    return os.path.join(base, lib + ".pretty", name + ".kicad_mod")


class Fetch:
    """One cached lookup: .f (parts_cache.Fetched or None), .why (reason it is missing), .offline (cache fallback)."""
    def __init__(self, fn, lcsc, offline):
        self.f, self.why = None, None
        try:
            self.f = fn(lcsc, offline=offline)
        except _cache.CacheMiss:
            self.why = "offline, no cache"
        except Exception as e:                               # bad id, bad JSON
            self.why = "lookup failed: %s: %s" % (type(e).__name__, e)

    @property
    def data(self):
        return self.f.data if self.f else None

    @property
    def offline(self):
        return bool(self.f and self.f.stale)

    def not_judged(self):
        """The reason text for a 'not judged' WARN, or None when the data is live."""
        if self.f is None:
            return self.why
        if self.f.stale:
            return "offline, cache age %.1f d" % (self.f.age_days or 0)
        return None


# --------------------------------------------------------------------------- the checks
def run_checks(NL, reg_refs, offline_flag, assembly, boards):
    findings, report_parts = [], []
    refs_by_lcsc_need = {}
    groups = OrderedDict()                                    # (record id, lcsc used, footprint used) -> [refs]
    unjudged_refs, no_lcsc = set(), []
    parts_by_ref = {p["ref"]: p for p in NL.PARTS}
    for ref in sorted(reg_refs):
        p, rec = parts_by_ref.get(ref), _parts.registry().get(reg_refs[ref])
        if p is None or rec is None:
            continue
        lcsc = (p.get("lcsc") or (rec.get("lcsc") or {}).get("id") or "").strip()
        if not lcsc:
            no_lcsc.append(ref)
            unjudged_refs.add(ref)
            findings.append(Finding("WARN" if assembly == "pcba" else "INFO", "MPN", ref,
                                    "record %s has no LCSC id, nothing to check against LCSC (not judged)" % rec["id"], [ref]))
            continue
        groups.setdefault((rec["id"], lcsc, p["footprint"]), []).append(ref)
        refs_by_lcsc_need[lcsc] = refs_by_lcsc_need.get(lcsc, 0) + 1

    jl_cache, ee_cache, sr_cache = {}, {}, {}
    for (rid, lcsc, fp), refs in groups.items():
        rec, who = _parts.registry()[rid], "%s (%s)" % (",".join(refs), rid)
        entry = {"record": rid, "lcsc": lcsc, "refs": refs, "mpn": rec["mpn"], "footprint": fp, "rules": {}}
        report_parts.append(entry)
        if lcsc not in jl_cache:
            jl_cache[lcsc] = Fetch(_cache.jlcsearch, lcsc, offline_flag)
            ee_cache[lcsc] = Fetch(_cache.easyeda, lcsc, offline_flag)
            sr_cache[lcsc] = Fetch(_cache.sourcing, lcsc, offline_flag)
            if sr_cache[lcsc].f is not None and not offline_flag:         # a failed/reshaped source is named, never silent
                for w in sr_cache[lcsc].f.warns:
                    findings.append(Finding("WARN", "STOCK", "%s (%s)" % (",".join(refs), lcsc), "source fallthrough: " + w, refs))
        jl, ee, sr = jl_cache[lcsc], ee_cache[lcsc], sr_cache[lcsc]

        def add(sev, rule, msg, judged=True):
            findings.append(Finding(sev, rule, who, msg, refs))
            entry["rules"].setdefault(rule, []).append({"severity": sev, "message": msg})
            if not judged:
                unjudged_refs.update(refs)

        def nj(rule, fetch, extra=""):
            add("WARN", rule, "not judged (%s)%s" % (fetch.not_judged(), extra), judged=False)

        rec_lcsc = (rec.get("lcsc") or {}).get("id")
        if rec_lcsc and rec_lcsc != lcsc:
            add("WARN", "MPN", "BOM uses %s but record %s says %s" % (lcsc, rid, rec_lcsc))

        # ---- MPN
        jd, ed = jl.data, ee.data
        sources = []
        if sr.data is not None and sr.data.get("mpn"):                       # authoritative: JLCPCB / LCSC detail
            sources.append(("%s MPN" % sr.f.src["mpn"], sr.data["mpn"]))
        if ed is not None:
            if _cache.easyeda_mpn(ed):
                sources.append(("EasyEDA Manufacturer Part", _cache.easyeda_mpn(ed)))
        if not sources:
            nj("MPN", sr if sr.not_judged() else ee)
        else:
            bad = False
            for label, val in sources:
                try:
                    _cache.verify_mpn(val, rec["mpn"])
                except _cache.MpnMismatch:
                    bad = True
                    add("ERROR", "MPN", '%s is "%s" on LCSC (%s), record says "%s"' % (lcsc, val, label, rec["mpn"]))
            if not bad:
                sr_stale = sr.f is not None and sr.f.is_stale("mpn")
                if sr_stale or ee.offline:
                    nj("MPN", sr if sr_stale else ee)
                else:
                    entry["rules"].setdefault("MPN", []).append({"severity": "OK", "message": "%s = %s" % (lcsc, rec["mpn"])})

        # ---- PKG
        want = (rec["package"] or {}).get("lcsc_package")
        if not want:
            add("WARN", "PKG", "record %s has no package.lcsc_package (not judged)" % rid, judged=False)
        elif jd is None:
            nj("PKG", jl)
        else:
            have = jd.get("package") or ""
            if norm_pkg(have) == norm_pkg(want):
                if jl.offline:
                    nj("PKG", jl)
                else:
                    entry["rules"].setdefault("PKG", []).append({"severity": "OK", "message": have})
            elif any(ord(ch) > 127 for ch in have):
                add("WARN", "PKG", 'LCSC lists package "%s" (no normalisation for it), record says "%s" (not judged)'
                    % (have, want), judged=False)
            else:
                add("ERROR", "PKG", 'LCSC lists %s, record says %s' % (have, want))

        # ---- GEO
        kp = kicad_pads(fp_path(NL, fp))
        if kp is None:
            add("WARN", "GEO", "footprint %s not found, geometry not judged" % fp, judged=False)
        elif ed is None:
            nj("GEO", ee)
        else:
            ep = easyeda_pads(ed.get("easyeda_json") or {})
            if not ep:
                add("WARN", "GEO", "LCSC/EasyEDA has no footprint pads for %s (not judged)" % lcsc, judged=False)
            else:
                km, em = metrics(kp), metrics(ep)
                entry["geometry"] = {"kicad": km, "easyeda": em}
                diffs = compare_geometry(km, em)
                for sev, text in diffs:
                    add(sev, "GEO", text, judged=not text.startswith("row structure"))
                if not any(s == "ERROR" for s, _t in diffs):
                    if ee.offline:
                        nj("GEO", ee)
                    elif not diffs:
                        entry["rules"].setdefault("GEO", []).append({"severity": "OK", "message":
                            "pads %d, pitch %.2f/%.2f, rows %s/%s, drill %s/%s" % (
                                km["count"], km["pitch"] or 0, em["pitch"] or 0, km["row_spread"], em["row_spread"],
                                km["drills"][:1], em["drills"][:1])})

        # ---- FRESH (record side)
        if rec.get("status") == "obsolete":
            add("ERROR", "FRESH", "record %s is obsolete" % rid)
        elif rec.get("status") == "draft":
            add("INFO", "FRESH", "record %s is draft (NEW in the release report)" % rid)
        lc = (rec.get("sourcing") or {}).get("lifecycle")
        if lc and lc.lower() not in ("active", "ok"):
            add("ERROR" if assembly == "pcba" else "WARN", "FRESH", "lifecycle is %s" % lc)
        snap = (rec.get("sourcing") or {}).get("snapshot_date")
        if snap:
            try:
                days = _cache.age_days(snap + "T00:00:00Z") if len(snap) == 10 else None
            except ValueError:
                days = None
            if days is not None and days > RECORD_SNAPSHOT_WARN_DAYS:
                add("WARN", "FRESH", "record sourcing snapshot %s is %d days old" % (snap, days))
        if jl.f is not None and (jl.f.age_days or 0) > _cache.MAX_AGE_DAYS:
            add("WARN", "FRESH", "cached LCSC data is %.0f days old (limit %d)" % (jl.f.age_days, _cache.MAX_AGE_DAYS))
        if ee.f is not None and (ee.f.age_days or 0) > _cache.MAX_AGE_DAYS:
            add("WARN", "FRESH", "cached EasyEDA data is %.0f days old (limit %d)" % (ee.f.age_days, _cache.MAX_AGE_DAYS))

    # ---- STOCK / FRESH(stock): one verdict per LCSC id, need summed over every ref using it
    stock_report = []
    for lcsc, qty in sorted(refs_by_lcsc_need.items()):
        sr = sr_cache.get(lcsc)
        refs = sorted(r for g, rs in groups.items() if g[1] == lcsc for r in rs)
        need = int(math.ceil(boards * qty * STOCK_MARGIN))
        who = "%s (%s)" % (",".join(refs), lcsc)
        ent = {"lcsc": lcsc, "refs": refs, "need": need, "boards": boards, "qty_per_board": qty, "assembly": assembly}
        stock_report.append(ent)

        def add(sev, rule, msg, judged=True):
            findings.append(Finding(sev, rule, who, msg, refs))
            ent.setdefault("findings", []).append({"severity": sev, "rule": rule, "message": msg})
            if not judged:
                unjudged_refs.update(refs)
        if sr is None or sr.data is None:
            add("WARN", "STOCK", "not judged (%s)" % (sr.not_judged() if sr else "no lookup"), judged=False)
            continue
        # pcba -> JLCPCB assembly stock; hand (you buy the parts) -> LCSC stock (P1-T10)
        field = "jlc_stock" if assembly == "pcba" else "lcsc_stock"
        label = "JLCPCB assembly stock" if assembly == "pcba" else "LCSC stock"
        d, src = sr.data, sr.f.src
        stock, age = d.get(field), sr.f.field_age(field) or 0
        stale = bool(stock is not None and sr.f.is_stale(field))
        ent.update(stock=stock, stock_field=field, stock_source=src.get(field), cache_age_days=round(age, 2), offline=stale,
                   stock_jlc=d.get("jlc_stock"), stock_jlc_source=src.get("jlc_stock"),
                   stock_lcsc=d.get("lcsc_stock"), stock_lcsc_source=src.get("lcsc_stock"), class_source=src.get("class"))
        cls, rec_cls = d.get("class"), None
        for g in groups:
            if g[1] == lcsc:
                rec_cls = (_parts.registry()[g[0]].get("lcsc") or {}).get("class")
        if rec_cls and cls and cls != rec_cls:
            add("WARN", "STOCK", "class changed: record says %s, %s lists %s%s" % (
                rec_cls, src.get("class"), cls, " (extended parts add a feeder fee at assembly)" if cls == "extended" else ""))
        if stock is None:
            why = "; ".join(sr.f.warns) if sr.f.warns else "no source returned it"
            add("WARN", "STOCK", "%s unknown: not judged (%s)" % (label, why), judged=False)
            continue
        if stale:
            add("WARN", "STOCK", "not judged (offline, cache age %.1f d): last known %s %s [%s] vs need %d" % (
                age, label, stock, src.get(field), need), judged=False)
            if assembly == "pcba" and age > STOCK_MAX_AGE_DAYS:
                add("ERROR", "FRESH", "stock snapshot is %.1f days old (limit %d for a pcba release)" % (age, STOCK_MAX_AGE_DAYS))
            continue
        if stock < need:
            msg = "%s %d < need %d (%d boards x %d per board x %.1f margin) [%s]" % (
                label, stock, need, boards, qty, STOCK_MARGIN, src.get(field))
            add("ERROR" if assembly == "pcba" else "INFO", "STOCK", msg + ("" if assembly == "pcba" else " (hand-assembled: informational)"))
        else:
            add("INFO", "STOCK", "%s %d >= need %d (%s) [%s]" % (label, stock, need, assembly, src.get(field)))
    return findings, report_parts, stock_report, groups, unjudged_refs


def apply_waivers(project_id, findings):
    ws, problems = _waivers.load(project_id, "parts")
    extra = [Finding("ERROR", "waiver", t, m) for t, m in problems]
    for i, w in ws:
        used = False
        for f in findings:
            if f.sev == "ERROR" and f.waiver is None and _waivers.matches(w, f.rule, f.refs, ()):
                f.waiver, used = w, True
        if not used:
            extra.append(Finding("WARN", "waiver", "waivers.json[%d]" % i, "unused waiver (rule %r, %s)"
                                 % (w.get("rule"), _waivers.describe(w))))
    return extra


def main(argv):
    pid = _project.project_id_from_argv(["x"] + argv[1:])
    if not pid:
        raise SystemExit("usage: check_parts.py <project-id> [--offline]")
    offline = True if ("--offline" in argv or _cache.is_offline()) else None
    _parts.use_lenient_registry()               # record problems are reported by lint (PR-HASH/PR-TIER), not here
    _parts.begin_netlist_load()                 # fail closed: a bad registry_part() call aborts the stage
    try:
        NL = _project.load_netlist(pid)
    except _parts.RegistryError as e:
        print("ERROR REF netlist.py: could not be built from the registry: %s" % e)
        print("FAILED: 1 parts error (netlist.py could not be built from the registry; run lint)")
        return 1
    assembly = str(getattr(NL, "ASSEMBLY", "hand")).lower()
    boards = int(getattr(NL, "BOARDS", DEFAULT_BOARDS))
    all_refs = [p["ref"] for p in NL.PARTS]
    reg_refs = _parts.registered_refs()
    skipped = [r for r in all_refs if r not in reg_refs]
    findings, rparts, stock, groups, unjudged = [], [], [], {}, set()
    if reg_refs:
        findings, rparts, stock, groups, unjudged = run_checks(NL, reg_refs, offline, assembly, boards)
        findings += apply_waivers(pid, findings)
    for f in findings:
        print(f.line())
    errors = [f for f in findings if f.sev == "ERROR" and f.waiver is None]
    warns = [f for f in findings if f.sev == "WARN"]
    if not reg_refs:
        print("0 registry parts: nothing to check (%d parts skipped, not declared through the registry)" % len(skipped))
    else:
        print("parts: %d examined (registry), %d skipped (not registry), %d unjudged (some rule could not be judged); "
              "assembly=%s, boards=%d" % (len(reg_refs), len(skipped), len(unjudged), assembly, boards))
    outdir = os.path.join(_project.PROJECTS, pid, "test", "parts")
    os.makedirs(outdir, exist_ok=True)
    report = {"project": pid, "generated": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "assembly": assembly, "boards": boards,
              "offline_requested": bool(offline),
              "counts": {"examined": len(reg_refs), "skipped_not_registry": len(skipped), "unjudged": len(unjudged),
                         "errors": len(errors), "warnings": len(warns)},
              "parts": rparts, "stock": stock, "findings": [f.as_dict() for f in findings]}
    with open(os.path.join(outdir, "parts.json"), "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1, ensure_ascii=False)
    if errors:
        print("FAILED: %d parts errors" % len(errors))
        return 1
    print("parts OK: %s (%d registry parts, %d warnings, %d waived)" % (
        pid, len(reg_refs), len(warns), sum(1 for f in findings if f.waiver is not None)))
    return 0


if __name__ == "__main__":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")   # LCSC strings contain CJK / degree signs
    except (AttributeError, ValueError):
        pass
    sys.exit(main(sys.argv))
