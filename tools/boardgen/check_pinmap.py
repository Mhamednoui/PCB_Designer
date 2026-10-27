"""Generic firmware <-> board pin cross-check for any Arduino-style MCU board.

    python check_pinmap.py <project-id>

netlist.py declares what to check (all paths relative to the project directory):

    FIRMWARE = {
        "files":   ["firmware/sketch.ino"],      # sketches to scan
        "mcu_ref": "A1",                         # reference of the MCU part on the board
        # --- all optional ---
        "analog_base": 54,                       # numeric pin >= this means A(n-base) (Mega 54, Uno 14)
        "fixed": {"D18": "MEGA_TX1"},            # pads used by hardware (Serial1...), value = expected net or None
        "pad_to_pin": {"25": "16"},              # non-Arduino pad naming (pad -> firmware pin id), e.g. ESP32 GPIO
        "signals": {"BTN_SPEED1": "BTN_S1",      # firmware symbol -> expected net name (exact check)
                    "PWM_PINS": ["MAG1_PWM"]},   # an array symbol -> list of net names, in order
        "pin_regex": r"(^|_)PIN\\d*$",           # extra #define/const names that are pins even if never passed to pinMode()
        "wokwi": False,                          # skip the diagram.json comparison for this MCU
        "wokwi_part": "mega",                    # id of the MCU in test/wokwi/diagram.json (default: first wokwi-arduino-*)
        "also": [ {...same keys...} ],           # more MCUs (e.g. an ESP32 sharing the board)
    }

Errors (exit 1, "FAILED: ..."): a pin the firmware uses is not wired to anything but the MCU, or lands
on a different net than "signals" says. Warnings: a pad the board wires that the firmware never
uses; a Wokwi diagram that wires different MCU pins. Waivers: waivers.json, "check": "pinmap",
rules "unwired-pin", "net-mismatch", "unknown-pin".
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from boardgen import project as _project  # noqa: E402
from boardgen import waivers as _waivers  # noqa: E402

PID = _project.project_id_from_argv(sys.argv)
NL = _project.load_netlist(PID)
PID = PID or os.path.basename(NL.PRJ_DIR)

PIN_FUNCS = r"(?:pinMode|digitalWrite|digitalRead|analogWrite|analogRead|attachInterrupt|digitalPinToInterrupt|tone|noTone|pulseIn|shiftOut|shiftIn)"
VALUE = r"(A\d+|\d+)"
# Names that count as pins when they sit in a { ... } initialiser (e.g. a button table) rather than
# being passed straight to pinMode(); keeps PWM_ON / counters out of the used-pin set.
PINISH = r"PIN|BTN|BUTTON|LED|SW\d|SEG_|COIN|RELAY|BUZZ|TRIG|ECHO|SERVO|MOTOR|SENSOR"


def strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", " ", src)


def scan_firmware(files, pin_regex):
    """-> (set of pin ids used, {symbol: pin id}, {array: [pin ids]})"""
    src = "\n".join(strip_comments(open(os.path.join(NL.PRJ_DIR, f), encoding="utf-8", errors="replace").read())
                    for f in files)
    syms = {}
    for m in re.finditer(r"^[ \t]*#define\s+(\w+)\s+" + VALUE + r"\b(?!\s*[UuLl.]|\s*[*+/-])", src, re.M):
        syms[m.group(1)] = m.group(2)
    for m in re.finditer(r"\b(?:static\s+)?const\s+(?:static\s+)?(?:int|uint8_t|byte|unsigned\s+int|short|uint16_t)\s+(\w+)\s*=\s*"
                         + VALUE + r"\s*;", src):
        syms[m.group(1)] = m.group(2)
    arrays = {}
    for m in re.finditer(r"\b(\w+)\s*\[[^\]]*\]\s*=\s*\{([^}]*)\}", src):
        items = [i.strip() for i in m.group(2).split(",") if i.strip()]
        vals = [syms.get(i, i) for i in items]
        if vals and all(re.fullmatch(VALUE, v) for v in vals):
            arrays[m.group(1)] = vals

    used = set()

    def add(tok):
        tok = tok.strip()
        if re.fullmatch(VALUE, tok):
            used.add(tok)
        elif tok in syms:
            used.add(syms[tok])
        elif tok in arrays:
            used.update(arrays[tok])

    for m in re.finditer(PIN_FUNCS + r"\s*\(((?:[^()]|\([^()]*\))*)\)", src):
        first = m.group(1).split(",")[0].strip()
        first = re.sub(r"^.*digitalPinToInterrupt\s*\(", "", first)
        am = re.match(r"(\w+)\s*\[", first)
        add(am.group(1) if am else first)
    for m in re.finditer(r"\{([^{}]*)\}", src):                 # struct / array initialisers: { BTN_PIN, HIGH, ... }
        for tok in re.split(r"[,\s]+", m.group(1)):
            if tok in syms and re.search(PINISH, tok):
                used.add(syms[tok])
    if pin_regex:
        for name, val in syms.items():
            if re.search(pin_regex, name):
                used.add(val)
    return used, syms, arrays


def norm_pin(pin, analog_base):
    pin = str(pin)
    if analog_base and pin.isdigit() and int(pin) >= int(analog_base):
        return "A%d" % (int(pin) - int(analog_base))
    return pin


def pad_for(pin, cfg):
    p2p = cfg.get("pad_to_pin")
    if p2p:
        inv = {str(v): str(k) for k, v in p2p.items()}
        return inv.get(pin)
    return pin if pin.startswith("A") else "D" + pin


def pin_for(pad, cfg):
    p2p = cfg.get("pad_to_pin")
    if p2p:
        return str(p2p[pad]) if pad in p2p else None
    pad = str(pad)
    if re.fullmatch(r"D\d+", pad):
        return pad[1:]
    return pad if re.fullmatch(r"A\d+", pad) else None


def wokwi_pins(cfg):
    path = os.path.join(NL.PRJ_DIR, "test", "wokwi", "diagram.json")
    if not os.path.isfile(path):
        return None
    try:
        d = json.load(open(path, encoding="utf-8"))
    except ValueError:
        return None
    if cfg.get("wokwi") is False:
        return None
    part = cfg.get("wokwi_part")
    if not part:
        part = next((p["id"] for p in d.get("parts", []) if str(p.get("type", "")).startswith("wokwi-arduino")), None)
    if not part:
        return None
    pins = set()
    for c in d.get("connections", []):
        for end in c[:2]:
            if isinstance(end, str) and end.startswith(part + ":"):
                label = end.split(":", 1)[1].split(".")[0]
                if re.fullmatch(r"A?\d+", label):
                    pins.add(norm_pin(label, cfg.get("analog_base")))
    return pins


def check_mcu(cfg, nets_by_pad, waive, errors, warns, report):
    ref = cfg["mcu_ref"]
    part = next((p for p in NL.PARTS if p["ref"] == ref), None)
    if part is None:
        errors.append("mcu_ref %s is not a part in netlist.py" % ref)
        return
    members = NL.nets()
    pins = {str(k): v for k, v in part["pins"].items()}

    def connected_elsewhere(net):
        return any(r != ref for r, _ in members.get(net, ()))

    used, syms, arrays = scan_firmware(cfg["files"], cfg.get("pin_regex"))
    used = {norm_pin(u, cfg.get("analog_base")) for u in used}
    for pad in (cfg.get("fixed") or {}):
        pin = pin_for(pad, cfg)
        if pin:
            used.add(pin)

    for pin in sorted(used, key=lambda x: (x[0] == "A", int(re.sub(r"\D", "", x) or 0))):
        pad = pad_for(pin, cfg)
        net = pins.get(pad) if pad else None
        if pad is None or pad not in pins and not any(str(p) == pad for p in pins):
            msg = "%s: firmware uses pin %s but the board has no pad %s on the MCU" % (ref, pin, pad)
            if not waive("unknown-pin", [ref], []):
                errors.append(msg)
        elif not net or not connected_elsewhere(net):
            msg = "%s: firmware uses pin %s (pad %s) but the board wires it to %s" % (
                ref, pin, pad, "nothing" if not net else "net %s with no other part" % net)
            if not waive("unwired-pin", [ref], [net] if net else []):
                errors.append(msg)

    # exact net checks (optional "signals" / "fixed")
    want = []                                           # (label, pin, expected net)
    for sym, net in (cfg.get("signals") or {}).items():
        if isinstance(net, list):
            vals = arrays.get(sym)
            if vals is None or len(vals) != len(net):
                errors.append("signals: array %s not found in firmware or length differs (%s vs %d)"
                              % (sym, None if vals is None else len(vals), len(net)))
                continue
            want += [("%s[%d]" % (sym, i), norm_pin(v, cfg.get("analog_base")), n) for i, (v, n) in enumerate(zip(vals, net))]
        elif sym in syms:
            want.append((sym, norm_pin(syms[sym], cfg.get("analog_base")), net))
        else:
            errors.append("signals: symbol %s not found in firmware" % sym)
    for pad, net in (cfg.get("fixed") or {}).items():
        if net:
            want.append(("fixed " + pad, pin_for(pad, cfg), net))
    for label, pin, net in want:
        pad = pad_for(pin, cfg) if pin else None
        got = pins.get(pad)
        ok = got == net
        report.append("  %-22s firmware pin %-4s board pad %-4s net %-12s %s" % (
            label, pin, pad, got or "--", "OK" if ok else "<-- expected %s" % net))
        if not ok and not waive("net-mismatch", [ref], [net, got or ""]):
            errors.append("%s: %s -> pin %s is on net %s, expected %s" % (ref, label, pin, got, net))

    # board wires it, firmware never uses it (warn only)
    for pad, net in sorted(pins.items()):
        pin = pin_for(pad, cfg)
        if pin is None or pin in used or not connected_elsewhere(net):
            continue
        warns.append("%s: pad %s (net %s) is wired to a part but the firmware never uses pin %s" % (ref, pad, net, pin))

    wk = wokwi_pins(cfg)
    if wk is not None:
        board = {pin_for(p, cfg) for p, n in pins.items() if pin_for(p, cfg) and connected_elsewhere(n)}
        board.discard(None)
        for pin in sorted(board - wk):
            warns.append("wokwi: board wires %s pin %s (%s) but diagram.json does not" % (ref, pin, pins.get(pad_for(pin, cfg))))
        for pin in sorted(wk - board):
            warns.append("wokwi: diagram.json wires pin %s but the board does not wire it on %s" % (pin, ref))
    report.append("  %s: firmware uses %d pins%s" % (ref, len(used), "" if wk is None else "; wokwi wires %d" % len(wk)))
    return len(used), len(want)


def main():
    fw = getattr(NL, "FIRMWARE", None)
    if not fw:
        print("check_pinmap: %s declares no FIRMWARE in netlist.py - nothing to check" % PID)
        return 0
    wl, problems = _waivers.load(PID, "pinmap")
    errors = ["%s: %s" % p for p in problems]

    def waive(rule, refs, nets):
        return any(_waivers.matches(w, rule, refs, nets) for _, w in wl)

    warns, report = [], []
    total_pins = total_signals = 0
    for cfg in [fw] + list(fw.get("also", [])):
        r = check_mcu(cfg, None, waive, errors, warns, report)
        if r:
            total_pins += r[0]
            total_signals += r[1]
    print("\n".join(report))
    for w in warns:
        print("WARN", w)
    print("pinmap %s: %d firmware pins, %d signals name-checked, %d warnings, %d errors"
          % (PID, total_pins, total_signals, len(warns), len(errors)))
    if errors:
        sys.exit("FAILED: " + "; ".join(errors))
    return 0


if __name__ == "__main__":
    sys.exit(main())
