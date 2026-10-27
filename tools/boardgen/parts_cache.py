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
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "parts" / ".cache"
BASE = "https://jlcsearch.tscircuit.com"
MAX_AGE_DAYS = 90          # spec section 6: geometry / MPN cache older than this = WARN
STOCK_MAX_AGE_DAYS = 7     # stock snapshot older than this = release error (pcba)
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


def _http_json(url, timeout=20):
    wait = 0.5 - (time.time() - _last_call[0])   # etiquette: 0.5 s between calls
    if wait > 0:
        time.sleep(wait)
    _last_call[0] = time.time()
    req = urllib.request.Request(url, headers={"User-Agent": "pcb-parts-registry/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def _fetch(kind, lcsc, url, pick, offline=None):
    """Network first (unless offline); on failure fall back to the cache with stale=True."""
    offline = is_offline() if offline is None else offline
    cached = _read(kind, lcsc)
    err = "offline mode" if offline else None
    if not offline:
        try:
            data = pick(_http_json(url))
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
