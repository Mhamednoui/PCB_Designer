"""Minimal VCD (Value Change Dump) reader - stdlib only.

Why this exists: reading a PWM-driven pin by sampling it is a coin flip. The Reflex Machine holds its
magnets at `analogWrite(..., 100)` = ~39% duty, so a single read returns LOW ~61% of the time and the
dashboard "flickers" even though nothing changed (see webview/ROADMAP.md Phase 2c).

A VCD capture contains every edge with its timestamp, so we can report what's actually true:
"Magnet 3: 39.2% duty, 490 Hz" instead of a dot that lies.
"""
import re

_TIMESCALE_UNITS = {"s": 1.0, "ms": 1e-3, "us": 1e-6, "ns": 1e-9, "ps": 1e-12, "fs": 1e-15}


def parse(text):
    """Returns {signal_name: [(time_seconds, value_int), ...]} plus the capture duration."""
    timescale = 1e-9
    m = re.search(r"\$timescale\s+(\d+)\s*([munpf]?s)\s*\$end", text)
    if m:
        timescale = int(m.group(1)) * _TIMESCALE_UNITS.get(m.group(2), 1e-9)

    # $var wire 1 ! D3 $end   ->  id "!" is the short code used in the value section
    ids = {}
    for var in re.finditer(r"\$var\s+\w+\s+\d+\s+(\S+)\s+([^\s$]+)[^$]*\$end", text):
        ids[var.group(1)] = var.group(2)

    changes = {name: [] for name in ids.values()}
    now = 0.0
    body = text.split("$enddefinitions $end", 1)[-1]
    for line in body.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("#"):
            try:
                now = int(line[1:]) * timescale
            except ValueError:
                pass
        elif line[0] in "01xzXZ" and len(line) >= 2:
            value, code = line[0], line[1:].strip()
            name = ids.get(code)
            if name:
                changes[name].append((now, 1 if value == "1" else 0))
    return changes, now


def summarise(changes, duration):
    """Per signal: duty cycle, edge count, and an estimated frequency - what you actually want to know
    about an output that's being driven rather than simply switched."""
    out = {}
    for name, edges in changes.items():
        if not edges:
            out[name] = {"duty_pct": None, "edges": 0, "freq_hz": None, "state": None}
            continue
        high_time = 0.0
        for i, (t, v) in enumerate(edges):
            end = edges[i + 1][0] if i + 1 < len(edges) else duration
            if v == 1:
                high_time += max(0.0, end - t)
        rising = sum(1 for i, (_, v) in enumerate(edges) if v == 1 and (i == 0 or edges[i - 1][1] == 0))
        out[name] = {
            "duty_pct": round(100.0 * high_time / duration, 1) if duration > 0 else None,
            "edges": len(edges),
            "freq_hz": round(rising / duration, 1) if duration > 0 and rising else None,
            "state": edges[-1][1],
        }
    return out


def analyse_file(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        changes, duration = parse(f.read())
    return {"duration_s": round(duration, 6), "signals": summarise(changes, duration)}
