"""Board data for reflex-machine: placements, silkscreen labels, pre-routes and the +12V pour. The
place/route/finish/check/render machinery is shared - see tools/boardgen/pcb.py.

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

BW, BH = 160.0, 125.0      # board size


# ── placement ──────────────────────────────────────────────
def placements():
    """Through-hole layout. Channel pitch 14 mm; leaded parts need the room."""
    P = {}
    for i in range(10):
        n, xc = i + 1, 8.0 + 14.0 * i
        P["J%d" % (1 + n)] = (xc + 2.54, 7.0, 180)    # wire openings face the top edge
        P["Q%d" % n] = (xc - 2.54, 18.0, 0)           # TO-220, tab towards the terminal
        P["R%d" % (10 + n)] = (xc - 5.08, 25.5, 0)    # gate resistor  (axial, horizontal)
        P["R%d" % (20 + n)] = (xc - 5.08, 30.5, 0)    # gate pull-down
        P["R%d" % (30 + n)] = (xc - 5.08, 35.5, 0)    # LED resistor
        P["D%d" % (10 + n)] = (xc - 3.035, 41.5, 0)   # 1N5822 flyback, stood upright
        P["D%d" % (20 + n)] = (xc - 1.265, 47.5, 0)   # 3 mm indicator LED
    P.update({
        "A1": (-16.0, 104.34, 0), "A2": (4.0, 83.4, 90),
        # power strip, right of the Mega
        "J1": (150.0, 90.0, 90), "F1": (142.0, 74.0, 90), "D1": (116.0, 52.0, 0),
        "C1": (132.0, 55.0, 0), "D2": (116.0, 60.0, 0), "U1": (116.0, 70.0, 0),
        "C2": (116.0, 82.0, 0), "C3": (116.0, 100.0, 0), "C6": (133.0, 82.0, 0), "C7": (128.0, 76.0, 0),
        "R1": (116.0, 90.0, 0), "D3": (132.0, 90.0, 0), "R2": (116.0, 95.0, 0), "D4": (132.0, 98.0, 0),
        "J16": (6.0, 92.0, 90), "J17": (34.0, 92.0, 90),
        # ICs beside the Mega; coin terminal sits right under its optocoupler
        "U3": (86.0, 52.0, 0), "U2": (86.0, 76.0, 0),
        "J13": (4.0, 113.0, 0), "J14": (39.0, 113.0, 0), "J15": (74.0, 113.0, 0), "J12": (110.0, 113.0, 0),
    })
    # column A: over the Mega, between the ICSP pads and the double-row header
    for k, ref in enumerate(["R43", "R44", "R45", "R46", "R47", "R48", "R49", "R50",
                             "R51", "R52", "R53", "R54", "R62"]):
        P[ref] = (53.5, 56.0 + 3.6 * k, 0)
    # column C: beside the Mega, left of the power strip
    for k, ref in enumerate(["R55", "R56", "R57", "R58", "R59", "R60", "R61", "R41", "R42", "R63",
                             "C9", "C10", "C11"]):
        P[ref] = (99.0, 53.0 + 3.6 * k, 0)
    # column B: short column beside the Mega, below the ICs
    for k, ref in enumerate(["C12", "C8"]):
        P[ref] = (86.0, 84.0 + 4.5 * k, 0)
    # U3 decoupling: right beside pin 16 (VCC) in the 3 mm gap before column C; rotated so pad 1 (+5V) is at the pin
    P["C13"] = (96.3, 51.5, 270)     # 100nF  pads (96.3,51.5) / (96.3,56.5)
    return P


MOUNTING_HOLES = [(155.0, 72.0), (145.0, 117.0)]

TEXTS = [  # (text, x, y, size)
    ("12V IN +", 146.0, 96.5, 0.9), ("GND", 146.0, 99.5, 0.9),
    ("REFLEX MACHINE v1.0", 135.0, 107.0, 1.3),
    ("ARDUINO MEGA 2560 PLUGS UNDER THIS BOARD", 30.0, 103.5, 0.9),
    ("BUTTONS", 16.0, 121.5, 1.0), ("STATUS LEDS", 51.0, 121.5, 1.0),
    ("7-SEGMENT", 86.0, 121.5, 1.0), ("COIN", 113.5, 121.5, 1.0),
    ("FUSE 10A", 144.0, 58.0, 0.8), ("12V", 140.5, 86.5, 0.8), ("5V", 140.5, 94.5, 0.8),
    ("5V MODULE", 118.0, 65.0, 0.8),
]
SECTIONS = [  # (text, x, y, size)
    ("MAGNET DRIVERS  M1-M10", 80.0, 22.4, 1.0),
    ("POWER  12V IN -> 5V", 130.0, 46.5, 1.0),
    ("7-SEG DRIVER 74HC595", 92.0, 48.8, 0.8),
    ("COIN OPTO", 92.0, 72.8, 0.8),
    ("MEGA SPARE PINS", 14.0, 97.5, 0.8),
    ("ESP32 SPARE", 38.0, 97.5, 0.8),
]
HEADER_LABELS = [  # (x of pin 1, y of pin 1, odd-row names, even-row names)
    (6.0, 92.0, ["5V", "3V3", "20", "14", "4", "30", "32", "A7", "52", "51"],
                ["GND", "GND", "21", "15", "13", "31", "33", "A8", "50", "53"]),
    (34.0, 92.0, ["3V3", "25", "27", "33"], ["GND", "26", "32", "14"]),
]
PIN_SUBLABELS = [  # Arduino pin under each bottom terminal screw
    (4.0, 3.5, ["D22", "", "D24", "", "D26", "", "D28", ""]),
    (39.0, 3.5, ["A3", "", "A4", "", "A5", "", "A6", ""]),
    (74.0, 3.5, ["", "", "", "", "", "", "", ""]),
    (110.0, 3.5, ["", "", "D2"]),
]
PIN_LABELS = [  # (terminal origin x, pitch, labels)
    (4.0, 3.5, ["S1", "G", "S2", "G", "S3", "G", "RST", "G"]),
    (39.0, 3.5, ["1+", "1-", "2+", "2-", "3+", "3-", "4+", "4-"]),
    (74.0, 3.5, ["a", "b", "c", "d", "e", "f", "g", "GND"]),
    (110.0, 3.5, ["12V", "GND", "SIG"]),
]


# ── hooks (see tools/boardgen/pcb.py) ──────────────────────
def extra_silk(board):
    """Per-magnet pin labels, spare-header pin names, and the Arduino pin under each terminal screw."""
    for i in range(10):
        pcb.add_text(board, "- M%d +  %s" % (i + 1, NL.MAG_PINS[i]), 8.0 + 14.0 * i, 13.4, 0.9)
    for x0, y0, odd, even in HEADER_LABELS:
        for k, name in enumerate(odd):
            pcb.add_text(board, name, x0 + 2.54 * k, y0 + 1.7, 0.7)
        for k, name in enumerate(even):
            pcb.add_text(board, name, x0 + 2.54 * k, y0 - 4.2, 0.7)
    for x0, pitch, labels in PIN_SUBLABELS:
        for k, s2 in enumerate(labels):
            if s2:
                pcb.add_text(board, s2, x0 + k * pitch, 105.6, 0.7)
    for x0, pitch, labels in PIN_LABELS:
        for k, s in enumerate(labels):
            pcb.add_text(board, s, x0 + k * pitch, 107.6, 0.8)


def extra_routes(board, P, net):
    """Pre-routes for spots the router and the pours cannot handle (docs/LESSONS_LEARNED.md 22-23)."""
    B = pcb.pcbnew.B_Cu
    # J16 pin 9 (SPARE_D4) to the Mega D4 pad: the header block is too congested for the
    # router, so take it around the ESP32 socket on the back layer.
    pcb.add_track(board, [(16.2, 92.0), (16.2, 96.8), (43.0, 96.8), (43.0, 55.5),
                          (37.3, 55.5), (37.3, 53.5)], 0.4, net("/SPARE_D4"), B)

    # GND bus in the gap between the ESP32 socket and the two spare headers, with stubs to
    # the ESP32 GND pin and the headers' GND pins (the headers otherwise split the pour).
    pcb.add_track(board, [(4.0, 86.5), (40.0, 86.5)], 0.6, net("GND"), B)
    for x in (6.0, 8.54, 34.0):          # J16 pin 2, J16 pin 4, J17 pin 2
        pcb.add_track(board, [(x, 86.5), (x, 89.46)], 0.5, net("GND"), B)
    pcb.add_track(board, [(37.02, 86.5), (37.02, 83.4)], 0.5, net("GND"), B)   # ESP32 GND

    # U3 pin 13 (~OE) to pin 8 (GND): both are GND, and the pour cannot reach pin 13 between
    # the DIP pad rows. Pre-wiring it on B.Cu keeps the router and the pours out of trouble.
    u3x, u3y, _ = P["U3"]
    pcb.add_track(board, [(u3x + 7.62, u3y + 7.62), (u3x + 3.81, u3y + 7.62),
                          (u3x + 3.81, u3y + 17.78), (u3x, u3y + 17.78)], 0.4, net("GND"), B)

    # heavy power path J1 -> fuse (both holder pads): only a 2.5 mm skeleton here, so the autorouter keeps
    # its channels. The 10 A copper (IPC-2221: 7.2 mm at 1 oz / 10 C) is the +12V_IN pour added after
    # routing in extra_pours; a 7.5 mm track present during routing made Freerouting fail ~3 in 8 builds.
    pcb.add_track(board, [(150.0, 90.0), (146.4, 90.0), (146.4, 74.0), (145.4, 74.0)], 2.5, net("+12V_IN"))


def extra_pours(board, nets, inset):
    """+12V pour on F.Cu over the power-strip region, above the GND pour (priority 1)."""
    pcb.add_zone(board, nets["+12V"], pcb.pcbnew.F_Cu,
                 [(inset, inset), (BW - inset, inset), (BW - inset, 66.0), (112.0, 66.0), (112.0, 13.2), (inset, 13.2)],
                 priority=1, clearance=0.4)
    # +12V_IN pour over the 2.5 mm skeleton from extra_routes (J1 pad 1 -> fuse pad pair), so the pad
    # connections and any router stubs are copper of the same width; GND pad J1.2 stays 1.5 mm outside.
    pcb.add_zone(board, board.FindNet("/+12V_IN") or board.FindNet("+12V_IN"), pcb.pcbnew.F_Cu,
                 [(140.25, 72.5), (147.75, 72.5), (147.75, 87.75), (152.5, 87.75), (152.5, 95.25), (140.25, 95.25)],
                 priority=1, clearance=0.4)


if __name__ == "__main__":
    pcb.main(NL, placements, OX=100.0, OY=50.0, BW=BW, BH=BH, MOUNTING_HOLES=MOUNTING_HOLES,
             SHOW_REF_PREFIX=("U", "F", "J", "Q", "D3", "D4"), SKIP_VALUE_SILK=("A1", "A2"),
             TEXTS=TEXTS, SECTIONS=SECTIONS,
             extra_silk=extra_silk, extra_routes=extra_routes, extra_pours=extra_pours)
