"""Parts cache (P1-T2): jlcsearch + EasyEDA JSON, cached under the git-ignored parts/.cache/.

Stdlib only. Every fetch returns a Fetched with explicit freshness flags: a network failure falls
back to the cache and sets .stale (never silent); no network and no cache raises CacheMiss.
Set PARTS_OFFLINE=1 (or pass offline=True) to force the offline path.

    from boardgen import parts_cache
    f = parts_cache.jlcsearch("C46749")      # Fetched(data=..., fetched_at=..., stale=False)
    parts_cache.verify_mpn(f.data["mfr"], "NE555P")
"""
import datetime
import json
import os
import re
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "parts" / ".cache"
BASE = "https://jlcsearch.tscircuit.com"
MAX_AGE_DAYS = 90          # spec section 6: geometry / MPN cache older than this = WARN
STOCK_MAX_AGE_DAYS = 7     # stock snapshot older than this = release error (pcba)
UA = "Mozilla/5.0 (compatible; pcb-parts-registry/1; polite, cache-first)"
# Undocumented, login-free endpoints (MV-T0). Env vars override the URLs (tests simulate a dead source with them).
JLCPCB_SMT_URL = ("https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList")
LCSC_DETAIL_URL = "https://wmsc.lcsc.com/ftps/wm/product/detail?productCode="
_last_call = [0.0]


class CacheMiss(RuntimeError):
    """Network unavailable and nothing cached."""


class MpnMismatch(ValueError):
    """The record returned for an LCSC id is not the requested MPN."""


class Fetched:
    def __init__(self, data, fetched_at, source, stale, error=None):
        self.data, self.fetched_at, self.source, self.stale, self.error = data, fetched_at, source, stale, error

    @property
    def age_days(self):
        return age_days(self.fetched_at)

    def flags(self):
        out = []
        if self.stale:
            out.append("STALE/OFFLINE (network failed: %s)" % self.error)
        if self.age_days is not None and self.age_days > MAX_AGE_DAYS:
            out.append("cache older than %d days" % MAX_AGE_DAYS)
        return out


def now_iso():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def age_days(iso):
    if not iso:
        return None
    t = datetime.datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() / 86400.0


def is_offline():
    return os.environ.get("PARTS_OFFLINE", "") not in ("", "0")


def _path(kind, lcsc):
    return CACHE_DIR / kind / lcsc / "entry.json"


def _read(kind, lcsc):
    p = _path(kind, lcsc)
    if p.exists():
        return json.loads(p.read_text(encoding="utf-8"))
    return None


def _http_json(url, timeout=20, body=None):
    wait = 0.5 - (time.time() - _last_call[0])   # etiquette: 0.5 s between calls
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    hdr = {"User-Agent": UA, "Accept": "application/json"}
    data = None
    if body is not None:                                      # POST JSON (JLCPCB assembly search)
        data, hdr["Content-Type"] = json.dumps(body).encode("utf-8"), "application/json"
    req = urllib.request.Request(url, data=data, headers=hdr)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch(kind, lcsc, url, pick, offline=None, body=None):
    """Network first (unless offline); on failure fall back to the cache with stale=True."""
    offline = is_offline() if offline is None else offline
    cached = _read(kind, lcsc)
    err = "offline mode" if offline else None
    if not offline:
        try:
            data = pick(_http_json(url, body=body))
            ent = {"fetched_at": now_iso(), "source": url, "status": "ok", "data": data}
            p = _path(kind, lcsc)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(json.dumps(ent, ensure_ascii=False, indent=1), encoding="utf-8")
            return Fetched(data, ent["fetched_at"], url, False)
        except Exception as e:                       # URLError, timeout, bad JSON, HTTP error
            err = "%s: %s" % (type(e).__name__, e)
    if cached is None:
        raise CacheMiss("%s %s: %s and no cache entry" % (kind, lcsc, err))
    return Fetched(cached["data"], cached["fetched_at"], cached.get("source", url), True, err)


def norm_lcsc(lcsc):
    s = str(lcsc).strip().upper()
    if not s.startswith("C") or not s[1:].isdigit():
        raise ValueError("LCSC id must look like C46749, got %r" % lcsc)
    return s


def jlcsearch(lcsc, offline=None):
    """Exact-id lookup (free-text search is unreliable, spec section 5). Data = the component dict."""
    lcsc = norm_lcsc(lcsc)

    def pick(j):
        comps = j.get("components") or []
        hits = [c for c in comps if c.get("lcsc") == int(lcsc[1:])]
        if not hits:
            raise ValueError("no exact match for %s in %d results" % (lcsc, len(comps)))
        return hits[0]
    return _fetch("jlcsearch", lcsc, "%s/api/search?q=%s" % (BASE, lcsc), pick, offline)


def easyeda(lcsc, offline=None):
    """EasyEDA component JSON (symbol shapes, footprint pads, c_para incl. Manufacturer Part)."""
    lcsc = norm_lcsc(lcsc)
    return _fetch("easyeda", lcsc, "%s/api/easyeda_components/%s" % (BASE, lcsc),
                  lambda j: j["easyeda_component_details"], offline)


def norm_mpn(s):
    return "".join(ch for ch in (s or "").upper() if ch.isalnum())


def verify_mpn(found, expected):
    """Raise MpnMismatch unless the MPNs agree (case/punctuation-insensitive)."""
    if norm_mpn(found) != norm_mpn(expected):
        raise MpnMismatch("LCSC returned MPN %r but %r was requested" % (found, expected))


def easyeda_mpn(data):
    """The manufacturer part number in an EasyEDA component dict: its `Manufacturer Part` field (spec section 9,
    decision 11). The component TITLE is not usable: EasyEDA appends the LCSC id (`PC817C_C20612594`).
    Falls back to the title with a trailing `_C<digits>` removed when the field is absent; None if neither exists."""
    ee = (data or {}).get("easyeda_json") or {}
    cp = ((ee.get("dataStr") or {}).get("head") or {}).get("c_para") or {}
    if cp.get("Manufacturer Part"):
        return cp["Manufacturer Part"]
    title = ee.get("title")
    return re.sub(r"_C\d+$", "", title) if title else None


# ---------------------------------------------------------------- P1-T10: stock source chain
# JLCPCB assembly stock + basic/extended: jlcpcb smtGood first. LCSC stock / MPN / datasheet: LCSC detail.
# jlcsearch is the last resort. Every field records which source answered; a failing or reshaped source is
# a WARN naming it and the chain falls through. A value no source gave stays None, never invented.
def _tier1(tiers):
    for t in tiers or []:
        if t.get("startNumber") == 1 and isinstance(t.get("productPrice"), (int, float)):
            return t["productPrice"]
    return None


def jlcpcb_smt(lcsc, offline=None):
    """JLCPCB assembly library entry for an exact LCSC id: stockCount, componentLibraryType, model, datasheet."""
    lcsc = norm_lcsc(lcsc)
    url = os.environ.get("PARTS_JLCPCB_URL") or JLCPCB_SMT_URL

    def pick(j):
        lst = (((j.get("data") or {}).get("componentPageInfo") or {}).get("list"))
        if lst is None or j.get("code") != 200:
            raise ValueError("unexpected response shape (code=%r)" % j.get("code"))
        hits = [c for c in lst if c.get("componentCode") == lcsc]
        if not hits:
            raise ValueError("no exact match for %s in %d results (not in the JLCPCB assembly library)" % (lcsc, len(lst)))
        c = hits[0]
        if not isinstance(c.get("stockCount"), int):
            raise ValueError("no integer stockCount")
        return {"stock": c["stockCount"], "library_type": c.get("componentLibraryType"),
                "preferred": bool(c.get("preferredComponentFlag")), "mpn": c.get("componentModelEn"),
                "datasheet": c.get("dataManualUrl") or None, "price_1": _tier1(c.get("componentPrices"))}
    body = {"keyword": lcsc, "currentPage": 1, "pageSize": 10, "searchSource": "search"}
    return _fetch("jlcpcb_smt", lcsc, url, pick, offline, body)


def lcsc_detail(lcsc, offline=None):
    """LCSC product detail: stockNumber (LCSC warehouse, not JLC assembly), productModel (MPN), pdfUrl."""
    lcsc = norm_lcsc(lcsc)
    base = os.environ.get("PARTS_LCSC_URL") or LCSC_DETAIL_URL

    def pick(j):
        r = j.get("result")
        if not isinstance(r, dict) or r.get("productCode") != lcsc or not isinstance(r.get("stockNumber"), int):
            raise ValueError("unexpected response shape or id not found (code=%r)" % j.get("code"))
        return {"stock": r["stockNumber"], "mpn": r.get("productModel"), "datasheet": r.get("pdfUrl") or None}
    return _fetch("lcsc_detail", lcsc, base + lcsc, pick, offline)


class Sourcing:
    """Merged per-field view: .data[field] = value, .src[field] = which source answered, .warns = source failures."""
    def __init__(self):
        self.data, self.src, self.warns, self.fetched, self.stale = {}, {}, [], {}, False
        self.stale_srcs = []

    def put(self, field, value, source, f):
        if field not in self.data and value is not None:
            self.data[field], self.src[field] = value, source
            self.fetched[field] = f.fetched_at

    def field_age(self, field):
        return age_days(self.fetched.get(field))

    @property
    def age_days(self):                      # oldest field: lets check_parts treat this like a Fetched
        ages = [age_days(v) for v in self.fetched.values()]
        return max(ages) if ages else None

    @property
    def fetched_at(self):
        return min(self.fetched.values()) if self.fetched else None

    def is_stale(self, field):
        return self.src.get(field, "").endswith("(stale cache)")


def sourcing(lcsc, offline=None):
    """Run the source chain for one LCSC id. Never raises for a source failure (WARN in .warns); raises CacheMiss
    only when no source produced anything at all. A source that failed live but has a cache entry contributes its
    cached values only after every live source was tried, flagged stale (never silent)."""
    lcsc = norm_lcsc(lcsc)
    sr, stale_pool = Sourcing(), []
    results = {}

    def run(name, fn):
        try:
            f = fn(lcsc, offline)
        except CacheMiss as e:
            sr.warns.append("%s: unavailable (%s)" % (name, e))
            return
        except Exception as e:                       # bad id etc.
            sr.warns.append("%s: %s: %s" % (name, type(e).__name__, e))
            return
        if f.stale:
            sr.warns.append("%s: live fetch failed (%s); cached %s used, %.1f d old" % (
                name, f.error, f.fetched_at[:10], f.age_days or 0))
            stale_pool.append((name, f))
        else:
            results[name] = f
    run("jlcpcb_smt", jlcpcb_smt)
    run("lcsc_detail", lcsc_detail)
    if "jlcpcb_smt" not in results or "lcsc_detail" not in results:
        run("jlcsearch", jlcsearch)              # last resort only: spare the community API when both primaries answered
    for name, f in list(results.items()) + stale_pool:   # live sources first, then stale caches
        d = f.data
        tag = name + (" (stale cache)" if f.stale else "")
        if f.stale and name not in sr.stale_srcs:
            sr.stale_srcs.append(name)
        if name == "jlcpcb_smt":
            sr.put("jlc_stock", d["stock"], tag, f)
            lt = d["library_type"]
            sr.put("class", "basic" if lt == "base" else ("preferred" if d["preferred"] else "extended") if lt == "expand" else lt, tag, f)
            sr.put("mpn", d["mpn"], tag, f)
            sr.put("datasheet", d["datasheet"], tag, f)
            sr.put("price_1", d.get("price_1"), tag, f)
        elif name == "lcsc_detail":
            sr.put("lcsc_stock", d["stock"], tag, f)
            sr.put("mpn", d["mpn"], tag, f)
            sr.put("datasheet", d["datasheet"], tag, f)
        else:
            sr.put("lcsc_stock", d.get("stock"), tag, f)
            sr.put("price_1", d.get("price"), tag, f)
            sr.put("class", "basic" if d.get("is_basic") else "preferred" if d.get("is_preferred") else "extended", tag, f)
            sr.put("mpn", d.get("mfr"), tag, f)
    if not sr.data:
        raise CacheMiss("sourcing %s: no source answered (%s)" % (lcsc, "; ".join(sr.warns)))
    sr.stale = bool(sr.stale_srcs)
    return sr
