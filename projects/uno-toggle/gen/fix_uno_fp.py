"""Uno shield footprint fixes: the Uno sits UNDER this board.

Same class of fix as the Reflex Machine's fix_mega_fp.py (see docs/LESSONS_LEARNED.md lesson 13):
- drop the courtyard, otherwise every part placed above the Uno is a false 'inside courtyard' error
- move back silkscreen to back fab (it isn't printed and runs off the cut board edge)
- drop the stray '.' marker texts

Unlike the Mega, the footprint's two unnumbered mounting-hole pads fall INSIDE this board's outline,
so they are kept and serve as the board's mounting holes.

Idempotent: safe to run again.
"""
import os
import re

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                    "lib", "arduino-library.pretty", "Arduino_Uno_R3_Shield.kicad_mod")
text = open(PATH, encoding="utf-8").read()


def elements(src, kinds):
    """Yield (start, end) of each top-level element of the given kinds.

    NOTE: matches ANY leading indentation. The Mega footprint this was adapted from is tab-indented
    modern KiCad format; this Uno footprint is the older (version 20211014) 2-space + CRLF format, and
    a tab-only pattern silently matched nothing - removing 0 courtyards while reporting success.
    """
    for m in re.finditer(r"\n[ \t]*\((?:%s)\b" % "|".join(kinds), src):
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
text = text.replace('"B.SilkS"', '"B.Fab"')
open(PATH, "w", encoding="utf-8").write(text)
print("removed: %d courtyard shapes, %d dot texts (mounting holes kept - they are inside this board)"
      % (n_crtyd, n_dots))
