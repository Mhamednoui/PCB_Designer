"""Helpers for writing the optional `EXTERNAL` block in a project's gen/netlist.py (P2-T7; grammar: ir/elec.py).

    from boardgen import netlist_ext as X
    EXTERNAL = X.merge(
        X.pins("J1", [1], dir="supply", v=(9.0, 12.0), i=0.05, why="9-12 V DC from the user's supply"),
        X.pins("J2", [1, 2], dir="out", why="LED pair on a cable"),
        X.none("MH1"),                       # a connector that really has no external nets
    )

`pins(ref, pads, ...)` -> {"J1.1": {...}, ...}; the grammar itself (keys v, i, dir, why; dir in in|out|bidir|supply) is
validated when the IR is built, so a typo fails `python pipeline.py <id> --only ir`, not silently. `why` is mandatory here
(a declaration nobody can explain is worse than none). dir is from the OUTSIDE world's point of view:
    supply  the outside drives a power rail into the board      in    the outside drives a signal into the board
    out     the board drives something outside (load/receiver)  bidir both
"""


def pins(ref, pads, why, dir=None, v=None, i=None):
    """{"<ref>.<pad>": declaration} for each pad (pads: iterable of pad names/numbers)."""
    if not why or not str(why).strip():
        raise ValueError("EXTERNAL %s: a `why` is required" % ref)
    d = {"why": why}
    if dir is not None:
        d["dir"] = dir
    if v is not None:
        d["v"] = tuple(v)
    if i is not None:
        d["i"] = i
    return {"%s.%s" % (ref, p): dict(d) for p in pads}


def none(*refs):
    """Connectors with no external nets (e.g. an internal programming stub)."""
    return {r: "none" for r in refs}


def merge(*parts):
    """Union of several declaration dicts; declaring the same pin twice is an error."""
    out = {}
    for p in parts:
        for k, val in p.items():
            if k in out:
                raise ValueError("EXTERNAL %s declared twice" % k)
            out[k] = val
    return out
