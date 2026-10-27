"""Board data for uno-toggle: placements, outline, silkscreen. The place/route/finish/check/render
machinery is shared - see tools/boardgen/pcb.py.

Usage (KiCad python):  python make_pcb.py place | route | finish | check | render
Board-local coordinates in mm, origin = top-left corner of the board, +Y down.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import netlist as NL  # noqa: E402
# The generic stages are shared, not copied (see tools/boardgen/project.py). HERE is already on
# sys.path above, so boardgen's own `import netlist` resolves to THIS project's netlist.
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(HERE))), "tools"))
from boardgen import pcb  # noqa: E402

BW, BH = 68.58, 53.34       # board size (Arduino Uno R3 outline)


def placements():
    """Two identical channels in the free band between the shield's two header rows.

    With A1 at (0, BH) the header pads land at y=2.54 (one row) and y=50.8 (the other), leaving roughly
    y=6..48 clear across x=14..66. Parts are spaced ~8 mm apart vertically, comfortably clear of the
    real leaded courtyards (axial R 12.35x3.08, disc cap 7.18x3.08, 5 mm LED ~6x6, 6 mm button ~7x7 -
    see docs/LESSONS_LEARNED.md lesson 17).
    """
    P = {"A1": (0.0, BH, 0)}
    for n, xc in ((1, 28.0), (2, 52.0)):
        P["SW%d" % n] = (xc, 16.0, 0)          # button
        P["C%d" % n] = (xc, 24.0, 0)           # 100nF debounce, right by its switch
        P["R%d" % n] = (xc, 33.0, 0)           # 330R, axial horizontal (needs ~12.4 mm width)
        P["D%d" % n] = (xc, 42.0, 0)           # 5 mm LED
    return P


# The shield footprint carries its own two mounting holes, and they fall inside this outline.
MOUNTING_HOLES = []

# Real Arduino Uno board outline from the shield footprint's B.Fab geometry, y-flipped at draw time.
# Only the board-edge segments: the same layer also carries the USB and barrel-jack outlines
# (x from -6.34 to 11.81), which are the connectors on the Uno underneath, not the board edge.
BOARD_OUTLINE = [
    (0.0, 0.0, 66.04, 0.0),
    (66.04, 0.0, 66.04, -1.27),
    (66.04, -1.27, 68.58, -3.81),
    (68.58, -3.81, 68.58, -38.1),
    (68.58, -38.1, 66.04, -40.64),
    (66.04, -40.64, 66.04, -51.816),
    (66.04, -51.816, 64.516, -53.34),
    (64.516, -53.34, 0.0, -53.34),
    (0.0, -53.34, 0.0, 0.0),
]

# Title/notes live in the free strip at x<14 (over the Uno's USB + barrel jack, where no part of ours
# sits). Keeping them out of the two part columns avoids silk-over-silk collisions - the earlier layout
# put the title straight through R1's value field.
TEXTS = [  # (text, x, y, size)
    ("UNO", 4.5, 24.0, 1.3), ("TOGGLE", 4.5, 29.0, 1.3), ("v1.0", 4.5, 33.5, 0.9),
    ("UNO R3", 4.5, 40.0, 0.8), ("SHIELD", 4.5, 44.0, 0.8),
    ("BTN1 -> D2", 22.0, 11.0, 0.8), ("BTN2 -> D3", 46.0, 11.0, 0.8),
    ("LED1 -> D8", 22.0, 47.0, 0.8), ("LED2 -> D9", 46.0, 47.0, 0.8),
]
SECTIONS = [  # (text, x, y, size)
    ("PRESS A BUTTON TO TOGGLE ITS LED", 16.0, 8.0, 0.9),
]

if __name__ == "__main__":
    # A1 is the shield header: its pads span the whole board, so no value text at its centroid.
    pcb.main(NL, placements, OX=100.0, OY=50.0, BW=BW, BH=BH, MOUNTING_HOLES=MOUNTING_HOLES,
             SHOW_REF_PREFIX=("SW", "D", "R", "C"), SKIP_VALUE_SILK=("A1",),
             BOARD_OUTLINE=BOARD_OUTLINE, TEXTS=TEXTS, SECTIONS=SECTIONS)
