"""Mega shield footprint fixes: the Mega sits UNDER this board.

- drop its courtyard (otherwise every part above it is a false 'inside courtyard' error)
- move back silkscreen to back fab (not printed, and it runs off the cut board edge)
- drop the stray '.' marker texts and the two mounting holes that fall outside the board
Idempotent: safe to run again.
"""
import os
import re

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "lib", "arduino-library.pretty", "Arduino_Mega2560_R3_Shield.kicad_mod")
text = open(PATH, encoding="utf-8").read()


def elements(src, kinds):
    """Yield (start, end) of each top-level element of the given kinds."""
    for m in re.finditer(r"\n\t\((?:%s)\b" % "|".join(kinds), src):
        depth, j = 0, m.start() + 2
        while True:
            if src[j] == "(":
                depth += 1
            elif src[j] == ")":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        yield m.start(), j + 1


def drop(src, kinds, predicate):
    out, pos, n = [], 0, 0
    for start, end in elements(src, kinds):
        if start < pos:
            continue
        elem = src[start:end]
        out.append(src[pos:start])
        if predicate(elem):
            n += 1
        else:
            out.append(elem)
        pos = end
    out.append(src[pos:])
    return "".join(out), n


text, n_crtyd = drop(text, ["fp_line", "fp_rect", "fp_poly", "fp_arc", "fp_circle"],
                     lambda e: '"B.CrtYd"' in e or '"F.CrtYd"' in e)
text, n_dots = drop(text, ["fp_text"], lambda e: 'user "."' in e)
text, n_holes = drop(text, ["pad"], lambda e: "(at 13.97 -2.54)" in e or "(at 15.24 -50.8)" in e)
text = text.replace('"B.SilkS"', '"B.Fab"')
open(PATH, "w", encoding="utf-8").write(text)
print("removed: %d courtyard shapes, %d dot texts, %d off-board holes" % (n_crtyd, n_dots, n_holes))
