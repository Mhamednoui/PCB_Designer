"""Decoupling-distance check on the ROUTED board (called from pcb.stage_check, needs pcbnew).

For every IC supply pin (power_in, non-ground net - same logic as lint_netlist.ic_supply_pins) find the
nearest decoupling capacitor pad on the same net (cap other side on ground) and measure pad centre to pin
centre. Unlike kicad-happy's analyzer this uses real pad positions, so it is not blind at any rotation.

Limits: 5 mm for a through-hole IC pin, 3 mm for an SMD pin. Overrides in netlist.py:
  DECAP_MAX_MM = 6.0                      # board-wide, replaces both defaults
  NET_SPEC["+5V"]["decap_max_mm"] = 8.0   # per supply net
Waive with projects/<id>/waivers.json: {"check":"check","rule":"decap-distance","refs":["U1"],"why":"..."}.
Returns (violations, examined); the caller prints the examined count so a check that looked at 0 pins is visible."""
import math
import os

import pcbnew

from boardgen import lint_netlist as L
from boardgen import waivers as _waivers

THT_MM, SMD_MM = 5.0, 3.0
RULE = "decap-distance"
MODULE_PREFIXES = ("Converter_",)       # DC-DC modules are not ICs to decouple; examined count excludes them


def _pads(board, ref, nums):
    fp = board.FindFootprintByReference(ref)
    out = []
    if fp is None:
        return out
    for n in nums:
        out += [p for p in fp.Pads() if p.GetNumber() == n]
    return out


def _limit(NL, net, pad):
    spec = (getattr(NL, "NET_SPEC", {}) or {}).get(net)
    if isinstance(spec, dict) and "decap_max_mm" in spec:
        return float(spec["decap_max_mm"])
    if getattr(NL, "DECAP_MAX_MM", None) is not None:
        return float(NL.DECAP_MAX_MM)
    return THT_MM if pad.GetAttribute() in (pcbnew.PAD_ATTRIB_PTH, pcbnew.PAD_ATTRIB_NPTH) else SMD_MM


def run(board, NL, project_id):
    """-> (examined supply pins, violation lines (unwaived), info lines)."""
    M = L.Model(NL)
    caps = [c for c in L.decoupling_caps(M) if any(M.is_ground(n) for n in c["pins"].values())]
    ws, problems = _waivers.load(project_id, "check")
    ws = [(i, w) for i, w in ws if w.get("rule") == RULE]
    used = set()
    examined, bad, info = 0, [], []
    for ref, net, pins, note in L.ic_supply_pins(M):
        if note or M.parts[ref]["lib_id"].startswith(MODULE_PREFIXES):
            continue                                              # modules carry their own input caps
        for ics in _pads(board, ref, pins):
            examined += 1
            best = None                                           # (distance mm, cap ref)
            for c in caps:
                nums = [k for k, n in c["pins"].items() if n == net]
                for cp in _pads(board, c["ref"], nums):
                    d = math.hypot(cp.GetPosition().x - ics.GetPosition().x,
                                   cp.GetPosition().y - ics.GetPosition().y) / 1e6   # nm -> mm
                    if best is None or d < best[0]:
                        best = (d, c["ref"])
            lim = _limit(NL, net, ics)
            where = "%s pin %s (%s)" % (ref, ics.GetNumber(), net)
            if best is None:
                line, ok = "%s: no decoupling capacitor pad found on the board" % where, False
            else:
                ok = best[0] <= lim
                line = "%s <- %s: %.2f mm (limit %.1f mm)" % (where, best[1], best[0], lim)
            hit = None
            if not ok:
                for i, w in ws:
                    if _waivers.matches(w, RULE, [ref] + ([best[1]] if best else []), [net]):
                        hit = (i, w)
                        used.add(i)
                        break
            if ok:
                info.append("  ok    " + line)
            elif hit:
                info.append("  WAIVED " + line + "  [waiver: %s]" % hit[1]["why"])
            else:
                bad.append("  FAIL  " + line)
    for i, w in ws:
        if i not in used:
            info.append("  WARN unused waiver waivers.json[%d] (rule %r, %s)" % (i, RULE, _waivers.describe(w)))
    bad += ["  FAIL  waivers: %s %s" % t for t in problems]
    return examined, bad, info
