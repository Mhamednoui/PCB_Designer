"""Resistive divider midpoint (P2-T3; docs/design/P2_ELECTRICAL_ANALYZER.md section 2.2). Pure functions, stdlib only.

A divider is *computable* iff:
  * exactly two resistors end on the midpoint net, and their far nets both have a known voltage interval, and
  * nothing else puts DC current into or out of the midpoint: the only other attachments are zero-current ones
    (capacitor, clamp/ESD diode, a MOSFET gate) or input/analog pins whose declared input leakage is <= 1 % of the
    divider current. Anything else (an output, an LED, a second divider, a connector, a pin with no declared leakage)
    -> not computable, with the reason; the answer is left to SPICE.

Midpoint voltage, with Ra to far net a and Rb to far net b (symmetric, no top/bottom ordering needed):

    Vmid = (Va*Rb + Vb*Ra) / (Ra + Rb)

The expression is linear in Va and Vb and monotone in each resistor for fixed other values, so its extremes over the box
[Va] x [Vb] x [Ra] x [Rb] are at the 16 corners; `midpoint()` evaluates all of them (worst case, no sampling).
Resistor tolerance is part of the input (`resistance()` widens a nominal by +-tol), never silently assumed here.
"""
LEAK_FRACTION = 0.01          # an input pin may load the midpoint by at most 1 % of the divider current

_UNIT_A = {"a": 1.0, "ma": 1e-3, "ua": 1e-6, "na": 1e-9, "pa": 1e-12}


def resistance(nominal_ohm, tol):
    """(lo, hi) of a resistor: nominal +- tol (tol as a fraction, 0.05 = 5 %)."""
    return (nominal_ohm * (1.0 - tol), nominal_ohm * (1.0 + tol))


def midpoint(va, vb, ra, rb):
    """Worst-case midpoint interval (lo, hi). va, vb: (lo, hi) volts of the far nets a and b; ra, rb: (lo, hi) ohms of
    the resistor from the midpoint to net a / net b. Raises ValueError on a non-positive resistance."""
    if min(ra[0], rb[0]) <= 0:
        raise ValueError("divider resistance must be > 0 (got %r, %r)" % (ra, rb))
    vals = [(a * rb_ + b * ra_) / (ra_ + rb_)
            for a in va for b in vb for ra_ in ra for rb_ in rb]
    return (min(vals), max(vals))


def leakage_a(datum):
    """Amperes from a record datum {max|typ, unit}. None when the datum is missing or has no usable number."""
    if not isinstance(datum, dict):
        return None
    v = datum.get("max")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        v = datum.get("typ")
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return None
    unit = str(datum.get("unit", "")).strip().lower()
    return float(v) * _UNIT_A[unit] if unit in _UNIT_A else None


def evaluate(edges, loads, v_of):
    """Decide whether a node is a computable divider midpoint and, if so, its interval.

    edges: list of {"ref", "far", "r": (lo, hi)} - the resistors on the node (far = the net at the other end).
    loads: list of {"term": "U1.5", "kind": "high_z" | "input" | "analog" | "other", "leak_a": float|None,
                    "why": text used when kind == "other"} - every other DC attachment on the node.
    v_of:  net name -> (lo, hi) or None (unknown).
    -> {"computable": bool, "interval": (lo, hi)|None, "reason": str, "far": [net, net], "current_a": float|None,
        "step": text}.   `reason` is always set when not computable."""
    def no(reason):
        return {"computable": False, "interval": None, "reason": "divider midpoint not computable: " + reason,
                "far": [], "current_a": None, "step": ""}

    if len(edges) != 2:
        return no("%d resistor(s) on the node (a divider needs exactly 2)" % len(edges))
    a, b = edges
    if a["far"] == b["far"]:
        return no("both resistors go to net %s (no divider)" % a["far"])
    va, vb = v_of(a["far"]), v_of(b["far"])
    for e, v in ((a, va), (b, vb)):
        if v is None:
            return no("far net %s of %s has no known voltage" % (e["far"], e["ref"]))
    other = [ld for ld in loads if ld["kind"] != "high_z"]
    i_min = max(0.0, _min_abs_diff(va, vb)) / (a["r"][1] + b["r"][1])
    leak = 0.0
    for ld in other:
        if ld["kind"] == "other":
            return no("%s also loads the node (%s)" % (ld["term"], ld.get("why") or "not a zero-current element"))
        la = ld.get("leak_a")
        if la is None:
            return no("%s is an input/analog pin with no declared input leakage in its record" % ld["term"])
        leak += la
    if leak > LEAK_FRACTION * i_min:
        return no("input leakage %.3g A > %d %% of the divider current %.3g A" % (leak, int(LEAK_FRACTION * 100), i_min))
    iv = midpoint(va, vb, a["r"], b["r"])
    return {"computable": True, "interval": iv, "reason": "", "far": [a["far"], b["far"]],
            "current_a": i_min,
            "step": "divider %s (%.4g..%.4g ohm) to %s %.4g..%.4g V and %s (%.4g..%.4g ohm) to %s %.4g..%.4g V: "
                    "Vmid = (Va*Rb + Vb*Ra)/(Ra+Rb) over all 16 tolerance corners = %.4g..%.4g V"
                    % (a["ref"], a["r"][0], a["r"][1], a["far"], va[0], va[1],
                       b["ref"], b["r"][0], b["r"][1], b["far"], vb[0], vb[1], iv[0], iv[1])}


def _min_abs_diff(va, vb):
    """Smallest |Va - Vb| over the two intervals (0 when they overlap)."""
    if va[0] > vb[1]:
        return va[0] - vb[1]
    if vb[0] > va[1]:
        return vb[0] - va[1]
    return 0.0
