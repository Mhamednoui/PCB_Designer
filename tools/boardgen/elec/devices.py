"""Device data accessors for the electrical rules (P2-T6; spec docs/design/P2_ELECTRICAL_ANALYZER.md sections 2.2, 2.4, 3).

Pure functions over an IR part dict (its `electrical` block is the registry record's, status "ok" only).  Every accessor
returns a value or `(None, "<missing field name>")`-style information, never a guess: the caller turns a missing field
into NOT_JUDGED naming it.

    datum_value(d, prefer)          number from a record datum, `prefer` = ("max", "typ", "min") order
    vf(part)                        (lo, hi, typ) volts of a diode / LED, or None
    load_ma(part)                   {"typ": mA|None, "peak": mA|None} from electrical.load_ma, or None
    fet_rds_on(part, vgs_v)         (ohm, row) : the record row with the largest tested Vgs <= vgs_v, or None
    theta_ja(part)                  (K/W, row) : the LARGEST (most pessimistic) tabulated value, since the copper area of
                                    the datasheet test board is unknown - the caller must say so in the finding
    tj_max(part), p_max_mw(part)    number or None
    fuse(part)                      {"i_hold_ma", "r_max_ohm"} (either may be None)
    regulator(part)                 the record's regulator block or None
    dropout_v(rg, i_ma)             (volts, row, how) : dropout needed at i_ma from the tabulated rows
"""

PEAK_ORDER = ("max", "typ", "min")
TYP_ORDER = ("typ", "max", "min")


def _num(x):
    return float(x) if isinstance(x, (int, float)) and not isinstance(x, bool) else None


def electrical(part):
    return part.get("electrical") if part.get("electrical_status") == "ok" else None


def datum_value(d, prefer=PEAK_ORDER):
    if not isinstance(d, dict):
        return None
    for k in prefer:
        v = _num(d.get(k))
        if v is not None:
            return v
    return None


def vf(part):
    """(lo, hi, typ) of the record's `vf` rows: lo = smallest `min` (None when no min is recorded), hi = largest max/typ."""
    rows = (electrical(part) or {}).get("vf") or []
    his = [datum_value(r, ("max", "typ")) for r in rows]
    his = [h for h in his if h is not None]
    if not his:
        return None
    lows = [_num(r.get("min")) for r in rows if _num(r.get("min")) is not None]
    typs = [_num(r.get("typ")) for r in rows if _num(r.get("typ")) is not None]
    return (min(lows) if lows else None, max(his), (sum(typs) / len(typs)) if typs else None)


def load_ma(part):
    lm = (electrical(part) or {}).get("load_ma")
    if not isinstance(lm, dict):
        return None
    return {"typ": datum_value(lm.get("typ"), TYP_ORDER), "peak": datum_value(lm.get("peak"), PEAK_ORDER)}


def fet_rds_on(part, vgs_v):
    """The tabulated RDS(on) at the largest tested Vgs that does not exceed `vgs_v` (the gate drive we can show). A drive
    below every tested Vgs gives None: the record does not cover it."""
    rows = (electrical(part) or {}).get("rds_on") or []
    ok = []
    for r in rows:
        v = _num((r.get("at") or {}).get("vgs_v"))
        o = datum_value(r, ("max", "typ"))
        if v is not None and o is not None and v <= vgs_v + 1e-9:
            ok.append((v, o, r))
    if not ok:
        return None
    v, o, r = max(ok, key=lambda t: t[0])
    return o, r


def theta_ja(part):
    rows = (electrical(part) or {}).get("theta_ja") or []
    vals = [(datum_value(r, ("max", "typ")), r) for r in rows]
    vals = [(v, r) for v, r in vals if v is not None]
    return max(vals, key=lambda t: t[0]) if vals else None


def tj_max(part):
    return datum_value((electrical(part) or {}).get("tj_max"), ("max", "typ"))


def p_max_mw(part):
    return datum_value((electrical(part) or {}).get("p_max_mw"), ("max", "typ"))


def fuse(part):
    f = (electrical(part) or {}).get("fuse")
    if not isinstance(f, dict):
        return None
    return {"i_hold_ma": datum_value(f.get("i_hold_ma"), ("min", "typ", "max")), "r_max_ohm": datum_value(f.get("r_max_ohm"), ("max", "typ"))}


def regulator(part):
    return (electrical(part) or {}).get("regulator")


def dropout_v(rg, i_ma):
    """Dropout needed at i_ma. Rows are {typ,max,at:{i_ma}}. Take the smallest tabulated current >= i_ma (dropout rises with
    current); if the load is above every row, the largest row (and say so). Value = max else typ.
    -> (volts, row, how) or (None, None, why)."""
    rows = []
    for r in (rg or {}).get("dropout") or []:
        i = _num((r.get("at") or {}).get("i_ma"))
        v = datum_value(r, ("max", "typ"))
        if i is not None and v is not None:
            rows.append((i, v, r))
    if not rows:
        return None, None, "regulator.dropout (a row with at.i_ma)"
    rows.sort(key=lambda t: t[0])
    above = [t for t in rows if t[0] >= i_ma - 1e-9]
    if above:
        i, v, r = above[0]
        return v, r, "tabulated at %g mA (the load is %g mA; dropout only rises with current, so this is an upper bound)" % (i, i_ma)
    i, v, r = rows[-1]
    return v, r, "load %g mA is ABOVE the highest tabulated current %g mA: that row is a lower bound" % (i_ma, i)
