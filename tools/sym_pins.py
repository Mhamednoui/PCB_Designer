"""Print a KiCad symbol's pin numbers + names. Resolves `extends` (inherited pins).

Why this exists: `netlist.py` keys every part's pins by **symbol pin number**, and getting one wrong
produces a board that passes DRC and is silently miswired. You cannot read the numbers off the
datasheet - they must come from the symbol KiCad will actually instantiate.

The trap this tool removes: many stock symbols are thin aliases, e.g. `NE555P` is
`(extends "NE555D")` and defines NO pins of its own. Grepping the symbol you chose finds zero pins,
which looks like a broken library rather than a redirect.

Usage:
    python tools/sym_pins.py Timer:NE555P
    python tools/sym_pins.py Device:R Switch:SW_Push        # several at once
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from boardgen.kicad_paths import SYMBOLS as KICAD_SYMBOLS  # noqa: E402


def _block(text, name):
    """Return the s-expression text of symbol `name`, or None.

    Slices between this symbol's header and the next one at the same indent level. Good enough for
    reading pins, and avoids dragging in a full s-expression parser.
    """
    m = re.search(r'\n(\t*)\(symbol "%s"\n' % re.escape(name), text)
    if not m:
        return None
    indent = m.group(1)
    start = m.end()
    nxt = re.search(r'\n%s\(symbol "' % re.escape(indent), text[start:])
    return text[start:start + nxt.start()] if nxt else text[start:]


def pins(lib, name, _seen=None):
    """[(number, name, type)] for lib:name, following `extends` to the parent symbol."""
    _seen = _seen or set()
    if name in _seen:                      # malformed library; don't spin
        return []
    _seen.add(name)

    path = os.path.join(KICAD_SYMBOLS, lib + ".kicad_sym")
    if not os.path.isfile(path):
        raise SystemExit("no such symbol library: %s" % path)
    text = open(path, encoding="utf-8").read()

    blk = _block(text, name)
    if blk is None:
        raise SystemExit('no symbol "%s" in %s.kicad_sym' % (name, lib))

    ext = re.search(r'\(extends "([^"]+)"\)', blk)
    if ext:
        return pins(lib, ext.group(1), _seen)

    # Pins live in sub-units ("NE555D_1_1"); each is (pin <type> <shape> ... (name ..) (number ..))
    found = []
    for pin in re.finditer(
            r'\(pin (\w+) \w+\s*\(at [^)]*\)\s*\(length [^)]*\)'
            r'(?:\s*\([^()]*\))*?\s*\(name "([^"]*)"',
            blk):
        tail = blk[pin.end():pin.end() + 400]
        num = re.search(r'\(number "([^"]*)"', tail)
        if num:
            found.append((num.group(1), pin.group(2), pin.group(1)))
    return found


def main(argv):
    if not argv:
        raise SystemExit(__doc__)
    for spec in argv:
        if ":" not in spec:
            raise SystemExit("use lib:Symbol, e.g. Timer:NE555P (got %r)" % spec)
        lib, name = spec.split(":", 1)
        got = pins(lib, name)
        print("%s  (%d pins)" % (spec, len(got)))
        for num, nm, typ in sorted(got, key=lambda t: (len(t[0]), t[0])):
            print("  %-4s %-12s %s" % (num, nm, typ))
        print()


if __name__ == "__main__":
    main(sys.argv[1:])
