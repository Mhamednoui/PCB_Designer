"""Write lib/reflex.pretty/ESP32_DevKit_V1_30pin_Socket.kicad_mod.

Local coords: pin 1 (EN) at (0,0); column A (pins 1-15, EN..VIN) at x=0 going +y;
column B (pins 16-30, IO23..3V3) at x=25.4. Antenna end is towards -y.
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), "lib", "reflex.pretty")
os.makedirs(OUT, exist_ok=True)

A = ["EN", "VP", "VN", "D34", "D35", "D32", "D33", "D25", "D26", "D27", "D14", "D12", "D13", "GND", "VIN"]
B = ["D23", "D22", "TX0", "RX0", "D21", "D19", "D18", "D5", "TX2", "RX2", "D4", "D2", "D15", "GND", "3V3"]
ROW = 25.4
P = 2.54

lines = [
    '(footprint "ESP32_DevKit_V1_30pin_Socket"',
    '\t(version 20241229)',
    '\t(generator "reflex_gen")',
    '\t(layer "F.Cu")',
    '\t(descr "DOIT ESP32 DevKit V1 30-pin on 2x 1x15 female headers, rows 25.4mm apart. Antenna end towards -Y.")',
    '\t(tags "ESP32 DevKit socket")',
    '\t(property "Reference" "REF**" (at 12.7 -3.2 0) (layer "F.SilkS") (effects (font (size 1 1) (thickness 0.15))))',
    '\t(property "Value" "ESP32_DevKit_V1_30pin_Socket" (at 12.7 44 0) (layer "F.Fab") (effects (font (size 1 1) (thickness 0.15))))',
    '\t(attr through_hole)',
]


def rect(x1, y1, x2, y2, layer, w=0.12):
    return '\t(fp_rect (start %.3f %.3f) (end %.3f %.3f) (stroke (width %.2f) (type solid)) (fill no) (layer "%s"))' % (x1, y1, x2, y2, w, layer)


def text(s, x, y, layer, size=0.8, rot=0):
    return '\t(fp_text user "%s" (at %.3f %.3f %d) (layer "%s") (effects (font (size %.2f %.2f) (thickness %.3f))))' % (
        s, x, y, rot, layer, size, size, size * 0.15)


# DevKit board outline (fab) + antenna area
lines.append(rect(-1.45, -9.5, ROW + 1.45, 42.0, "F.Fab", 0.1))
lines.append(rect(-1.45, -9.5, ROW + 1.45, -3.5, "F.Fab", 0.1))
lines.append(text("ANTENNA", ROW / 2, -6.5, "F.Fab", 1.0))
lines.append(text("USB", ROW / 2, 40.0, "F.Fab", 1.0))
# silkscreen: socket outlines + pin names + orientation
lines.append(rect(-1.33, -1.33, 1.33, 14 * P + 1.33, "F.SilkS"))
lines.append(rect(ROW - 1.33, -1.33, ROW + 1.33, 14 * P + 1.33, "F.SilkS"))
for i, n in enumerate(A):
    lines.append(text(n, 3.1, i * P, "F.SilkS", 0.8))
for i, n in enumerate(B):
    lines.append(text(n, ROW - 3.1, i * P, "F.SilkS", 0.8))
lines.append(text("ESP32 DEVKIT V1", ROW / 2, 16.0, "F.SilkS", 1.2, 90))
lines.append(text("ANTENNA THIS END", ROW / 2, -1.6, "F.SilkS", 0.8))
# courtyard around the two socket rows (area between rows kept free of parts)
lines.append('\t(fp_rect (start -1.8 -1.8) (end %.3f %.3f) (stroke (width 0.05) (type solid)) (fill no) (layer "F.CrtYd"))' % (ROW + 1.8, 14 * P + 1.8))

for i in range(15):
    shape = "rect" if i == 0 else "oval"
    lines.append('\t(pad "%d" thru_hole %s (at 0 %.3f) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask"))' % (i + 1, shape, i * P))
for i in range(15):
    lines.append('\t(pad "%d" thru_hole oval (at %.3f %.3f) (size 1.7 1.7) (drill 1.0) (layers "*.Cu" "*.Mask"))' % (i + 16, ROW, i * P))

for dx in (0.0, ROW):
    lines.append('\t(model "${KICAD10_3DMODEL_DIR}/Connector_PinSocket_2.54mm.3dshapes/PinSocket_1x15_P2.54mm_Vertical.step" (offset (xyz %.3f 0 0)) (scale (xyz 1 1 1)) (rotate (xyz 0 0 0)))' % dx)
lines.append(")")

path = os.path.join(OUT, "ESP32_DevKit_V1_30pin_Socket.kicad_mod")
with open(path, "w", encoding="utf-8") as f:
    f.write("\n".join(lines) + "\n")
print("wrote", path)
