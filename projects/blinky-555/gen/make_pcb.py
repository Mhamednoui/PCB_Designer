"""Board data for blinky-555: placements, outline, silkscreen. The place/route/finish/check/render
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

BW, BH = 70.0, 45.0         # board size - chosen freely: this board plugs into nothing


def placements():
    """Three rows: resistors along the top, the active parts across the middle, caps along the bottom.

    Signal flow runs left to right - power in at J1, the timer in the middle, the LED at the right edge -
    so the autorouter never has to cross the board to finish a net.

    THE COORDINATE IS THE FOOTPRINT ORIGIN, WHICH IS USUALLY NOT THE CENTRE OF THE PART. Every THT
    footprint used here puts its origin on pad 1, so a part placed at x=47 extends to the RIGHT of 47,
    not around it. Measure before placing - `python tools/fp_bbox.py <lib>:<footprint>` prints the real
    courtyard extent relative to the origin. The numbers below are from that tool:

        R_Axial_..._P10.16mm_Horizontal   x -1.05 .. +11.21   y -1.50 .. +1.50
        DIP-8_W7.62mm                     x -1.06 .. +8.67    y -1.52 .. +9.14
        TerminalBlock_MaiXu_MX126-5.0-02P x -3.50 .. +8.00    y -4.50 .. +4.31
        CP_Radial_D6.3mm_P2.50mm          x -2.15 .. +4.65    y -3.40 .. +3.40
        C_Disc_D5.0mm_W2.5mm_P5.00mm      x -1.05 .. +6.05    y -1.50 .. +1.50
        LED_D5.0mm                        x -1.94 .. +4.49    y -3.21 .. +3.21
        MountingHole_3.2mm_M3             x -3.45 .. +3.45    y -3.45 .. +3.45

    Guessing these (assuming centred origins) is what put mounting hole H2 through R3's pad 2 on the
    first build - DRC caught it as courtyards_overlap + pth_inside_courtyard.
    """
    return {
        # top row, y=12 -> occupies y 10.5..13.5, clear of the corner holes (which end at y=7.45)
        "R1": (8.0, 12.0, 0),      # 10k  VCC -> DISCH    x  6.95..19.21
        "R2": (28.0, 12.0, 0),     # 47k  DISCH -> TRIG   x 26.95..39.21
        "R3": (48.0, 12.0, 0),     # 470R OUT -> LED      x 46.95..59.21
        # middle row - power in at the left, timer, LED at the right
        "J1": (10.0, 24.0, 0),     # terminal block   x  6.50..18.00  y 19.50..28.31
        "U1": (30.0, 22.0, 0),     # NE555P, DIP-8    x 28.94..38.67  y 20.48..31.14
        "D1": (52.0, 24.0, 0),     # 5 mm LED         x 50.06..56.49  y 20.79..27.21
        # bottom row - the capacitors
        "C1": (10.0, 36.0, 0),     # 10uF timing      x  7.85..14.65  y 32.60..39.40
        "C3": (36.0, 17.5, 0),     # 100nF decoupling, above-right of U1, pad 1 (VCC) 4.8 mm from pin 8  x 34.95..42.05  y 16.00..19.00
        "C2": (40.0, 36.0, 0),     # 10nF on CONT     x 38.95..46.05  y 34.50..37.50
    }


# No shield footprint to inherit holes from, so this board needs its own: 4x M3 inset from the corners.
# Each spans +-3.45 mm, i.e. x 0.05..6.95 / 63.05..69.95 and y 0.55..7.45 / 37.55..44.45. Checked
# against every part extent listed above - the nearest approach is C1's left edge at x=7.85.
MOUNTING_HOLES = [(3.5, 4.0), (66.5, 4.0), (3.5, 41.0), (66.5, 41.0)]

# Silk text goes in the margins above/below the three part rows. Keep it out of the rows themselves:
# the generator also prints each part's value at its centroid, and overlapping those is what produced
# the ~213 silk warnings on the Reflex Machine. Nothing may be smaller than 0.8 mm (DRC minimum).
TEXTS = [  # (text, x, y, size)
    ("BLINKY 555", 35.0, 4.0, 1.4),
    # J1 has no polarity marking of its own, and reversing 9 V into a 555 destroys it. Label the pads:
    # pad 1 (x=10) is VCC, pad 2 (x=15) is GND.
    ("+", 10.0, 18.0, 1.4), ("-", 15.0, 18.0, 1.4), ("9-12V", 12.0, 30.5, 1.0),
    ("C1+", 18.0, 36.0, 0.9),          # electrolytic polarity: pad 1, the left one, is positive
    ("~1.4Hz", 53.0, 31.0, 1.0),
    ("v1.0", 58.0, 42.0, 1.0),
]
SECTIONS = [  # (text, x, y, size)
    ("NE555 ASTABLE LED FLASHER", 33.0, 42.0, 1.0),
]

if __name__ == "__main__":
    # Plain BW x BH rectangle (default outline) and no hooks: this board has 4 signal nets, each a short
    # two-pad run, and a GND pour that reaches every ground pad without help.
    pcb.main(NL, placements, OX=100.0, OY=50.0, BW=BW, BH=BH, MOUNTING_HOLES=MOUNTING_HOLES,
             SHOW_REF_PREFIX=("U", "J", "D", "R", "C"), TEXTS=TEXTS, SECTIONS=SECTIONS)
