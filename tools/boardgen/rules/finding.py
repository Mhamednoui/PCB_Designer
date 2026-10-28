"""The one Finding object every checker shares (P2 design section 1.2; PA-7 finding taxonomy folded into P2-T1).

    Finding(rule, severity, why, where={ref,pin,net,xy,layer}, measured={value,unit,corner},
            limit={value,unit,source}, fix, doc, waived={why,by,date}|None)

severity is ERROR | WARN | INFO | NOT_JUDGED. NOT_JUDGED is a severity of its own (never a WARN string): the item could
not be judged for lack of data; it is counted and shown, and a waiver can never hide it. A waived finding keeps its
severity (ERROR) and carries `waived`; it is displayed as WAIVED.
measured/limit are typed numbers (unit string, corner min|typ|max for measured, a source string for limit) so a
report can sort and graph them. `line()` is the legacy one-line format `ERROR rule target: message`, kept
byte-for-byte so existing parsers keep working.
"""
import hashlib
import json
from numbers import Real

SEVERITIES = ("ERROR", "WARN", "INFO", "NOT_JUDGED")
CORNERS = ("min", "typ", "max")
WHERE_KEYS = ("ref", "pin", "net", "xy", "layer")


class FindingError(ValueError):
    """A Finding was built with an invalid field (a bug in the rule that built it)."""


def _num(v):
    return isinstance(v, Real) and not isinstance(v, bool)


class Finding:
    def __init__(self, rule, severity, why, where=None, measured=None, limit=None, fix="", doc="",
                 target=None, refs=(), nets=(), legacy_id=None):
        if severity not in SEVERITIES:
            raise FindingError("%s: severity %r not one of %s" % (rule, severity, SEVERITIES))
        where = dict(where or {})
        bad = sorted(set(where) - set(WHERE_KEYS))
        if bad:
            raise FindingError("%s: unknown where key(s) %s (allowed: %s)" % (rule, bad, WHERE_KEYS))
        if measured is not None:
            if not (_num(measured.get("value")) and isinstance(measured.get("unit"), str)
                    and measured.get("corner", "typ") in CORNERS):
                raise FindingError("%s: measured must be {value: number, unit: str, corner: min|typ|max}" % rule)
        if limit is not None:
            if not (_num(limit.get("value")) and isinstance(limit.get("unit"), str)
                    and isinstance(limit.get("source"), str) and limit["source"]):
                raise FindingError("%s: limit must be {value: number, unit: str, source: non-empty str}" % rule)
        self.rule, self.severity, self.why = rule, severity, why
        self.where, self.measured, self.limit = where, measured, limit
        self.fix, self.doc, self.waived = fix, doc, None
        self.legacy_id = legacy_id                           # the pre-engine rule name (printed, and matched by waivers)
        self.target = target if target is not None else self._default_target()
        self.refs = set(refs) | ({where["ref"]} if "ref" in where else set())
        self.nets = set(nets) | ({where["net"]} if "net" in where else set())

    def _default_target(self):
        w = self.where
        if "ref" in w:
            return "%s.%s" % (w["ref"], w["pin"]) if "pin" in w else w["ref"]
        return w.get("net", "")

    # -- legacy names, so lint_netlist.py and its waiver code keep working unchanged
    @property
    def sev(self):
        return self.severity

    @property
    def msg(self):
        return self.why

    @property
    def waiver(self):
        return self.waived

    @property
    def rule_ids(self):
        """Every name a waiver may use for this rule."""
        return (self.rule,) if not self.legacy_id else (self.rule, self.legacy_id)

    def fingerprint(self):
        """Stable id for waivers and run-to-run diffs: sha1(rule, where, limit.source)."""
        src = (self.limit or {}).get("source", "")
        blob = json.dumps([self.rule, self.where, src], sort_keys=True, separators=(",", ":"))
        return hashlib.sha1(blob.encode("utf-8")).hexdigest()[:12]

    def line(self):
        tag = "WAIVED" if self.waived is not None else self.severity
        tail = "  [waiver: %s]" % self.waived["why"] if self.waived is not None else ""
        return "%s %s %s: %s%s" % (tag, self.legacy_id or self.rule, self.target, self.why, tail)

    def to_dict(self):
        return {"rule": self.rule, "severity": self.severity, "state": "WAIVED" if self.waived else self.severity,
                "where": self.where, "target": self.target, "measured": self.measured, "limit": self.limit,
                "why": self.why, "fix": self.fix, "doc": self.doc, "waived": self.waived,
                "fingerprint": self.fingerprint(), "legacy_id": self.legacy_id}

    def __repr__(self):
        return "Finding(%s)" % self.line()
