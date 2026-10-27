# Reflex Machine PCB - Design Spec

**Status:** DONE 2026-09-11. Schematic (ERC clean, netlist verified) + PCB (0 DRC errors, 0 unconnected, 0 parity issues)
+ JLCPCB fab files, STEP model and renders in `out/`. Wiring instructions: `WIRING_GUIDE.md`. Session write-up: `../../PROJECT_LOG.md`.
Source firmware: `CODES/arduino_main_code.cpp` and `CODES/ESP32_main_code.cpp`. **No code changes**: every pin stays the same.

---

## 1. Board concept
- **One PCB that plugs on top of a standard Arduino Mega 2560 R3, like a shield.**
  - The Mega sits underneath, so there are no loose wires between the two.
  - The Mega's USB port stays reachable for programming.
- **ESP32 DevKit V1 (30-pin, WROOM-32)** plugs into female headers on top of the PCB.
  - Its WiFi antenna sticks out past the board edge, with no copper under it.
  - Both controller boards stay removable, so they can be swapped later.
- **All outside wires go to labelled screw terminals** printed with names like MAG1+, MAG1-, COIN SIG and BTN S1.
- **Zones on the board:**
  - power input in one corner
  - the 10 magnet terminals in one row along one long edge (about 102 mm, the same length as the Mega)
  - coin, buttons, LEDs and 7-segment along the opposite edge
- **Size:** as compact as possible while keeping comfortable spacing. Target is about 120 × 95 mm; the final size is set after placement.
- **Layers:** 2-layer, 1 oz copper. The 12V and magnet paths use wide copper areas.
- **Mounting:** 4× M3 holes at the corners, and the stack uses the Mega's own mounting holes with standoffs.

## 2. Connectors (what you wire to)

### J1 - 12V power input (5.08 mm terminal, high current)
| Pin | Label |
|---|---|
| 1 | +12V |
| 2 | GND |

**User confirmed:** ONE external 12V supply (16A) feeds the whole board through J1, including the magnets.
After the main fuse, the 12V splits into the magnet rail (heavy copper) and the 5V regulator. The magnet ground returns straight to J1.

### J2-J11 - Electromagnets (10× 2-pin 5.08 mm terminals)
Each magnet has two wires: **+** (always 12V) and **-** (switched to GND by the MOSFET).
Polarity does not matter for a plain electromagnet coil.

| Terminal | Magnet | Mega pin | Code index |
|---|---|---|---|
| J2 | MAG1 | 3 | PWM_PINS[0] |
| J3 | MAG2 | 5 | PWM_PINS[1] |
| J4 | MAG3 | 6 | PWM_PINS[2] |
| J5 | MAG4 | 7 | PWM_PINS[3] |
| J6 | MAG5 | 8 | PWM_PINS[4] |
| J7 | MAG6 | 9 | PWM_PINS[5] |
| J8 | MAG7 | 10 | PWM_PINS[6] |
| J9 | MAG8 | 11 | PWM_PINS[7] |
| J10 | MAG9 | 12 | PWM_PINS[8] |
| J11 | MAG10 | 44 | PWM_PINS[9] |

### J12 - Coin acceptor (3-pin 5.08 mm terminal)
| Pin | Label | Goes to on the coin acceptor |
|---|---|---|
| 1 | +12V | DC+ (red) |
| 2 | GND | GND (black) |
| 3 | SIG | COIN signal (white) |

Set the acceptor's switch to **NO**.

### J13 - Buttons (8-pin 3.5 mm terminal, one signal and one GND per button)
| Pins | Button | Mega pin |
|---|---|---|
| 1-2 | S1 (SPEED1) + GND | 22 |
| 3-4 | S2 (SPEED2) + GND | 24 |
| 5-6 | S3 (SPEED3) + GND | 26 |
| 7-8 | RST (RESET) + GND | 28 |

### J14 - Status LEDs (8-pin 3.5 mm terminal; resistors are on the PCB, so wire the LED directly)
| Pins | LED | Mega pin | Meaning |
|---|---|---|---|
| 1-2 | LED1 + / - | A3 | RESET state |
| 3-4 | LED2 + / - | A4 | releasing, fast (SPEED3) |
| 5-6 | LED3 + / - | A5 | releasing, medium (SPEED2) |
| 7-8 | LED4 + / - | A6 | releasing, slow (SPEED1) |

LED **+** is the long leg (anode) and **-** is the short leg (cathode).

### J15 - 7-segment display (8-pin 3.5 mm terminal; common cathode, 5V; the 74HC595 and resistors are on the PCB)
| Pin | 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 |
|---|---|---|---|---|---|---|---|---|
| Segment | a | b | c | d | e | f | g | COM (GND) |

The PCB keeps the exact 595 bit mapping from the code:
- QB → g, QC → f, QD → a, QE → e, QF → c, QG → b, QH → d
- QA is not connected

### J16 - Spare / expansion header (2×5 pin header, for the future)
- 5V, 3V3, GND ×2
- SDA (20), SCL (21), D4, D13, A7, A8

## 3. Circuits

| Block | Design |
|---|---|
| **12V input** | Replaceable blade fuse (10A default; swap to suit the magnets), reverse-polarity protection (P-MOSFET, low heat), TVS surge diode, 1000 µF bulk capacitor, green "12V" LED |
| **5V supply** | On-board 12V to 5V switching regulator (3A, stays cool). Feeds the Mega 5V pin and the ESP32 VIN pin, with a "5V" LED. You can still plug in USB to program while 12V is connected |
| **Magnet drivers ×10** | IRLZ44N (TO-220), 100 Ω gate resistor, 10k pull-down, SS34 Schottky flyback diode across each magnet terminal, small red LED per channel that lights when the magnet is ON |
| **Coin input** | PC817 optocoupler: the acceptor's signal switches the opto LED (from 12V through a resistor), and the opto output pulls Mega pin 2 LOW with a 10k pull-up to 5V. The pulses stay the same polarity, so the code does not change. This isolation removes the "false coin when a button is pressed" noise |
| **Buttons ×4** | External 10k pull-up to 5V, 1k series resistor, 100 nF capacitor to GND on each input, to filter noise from long cables |
| **Status LEDs ×4** | 330 Ω series resistor on each Mega output |
| **7-segment** | 74HC595 (SOIC-16) + 100 nF decoupling capacitor + 7× 470 Ω segment resistors (about 6 mA per segment, safe for the 595) |
| **Mega → ESP32 serial** | Mega TX1 (18) → 1k / 2k resistor divider (3.3V) → ESP32 GPIO16. ESP32 GPIO17 → Mega RX1 (19) directly. Common GND |
| **Grounding** | Magnet current returns through its own heavy GND path back to J1. Logic GND joins at one point, which keeps magnet noise away from the Mega and ESP32 |

## 4. Final decisions (user answers + defaults)
| # | Topic | Decision | Source |
|---|---|---|---|
| A1 | Arduino | Mega 2560 R3 (standard), shield-style stack | user: "the old ones" |
| A2 | ESP32 | DevKit V1 30-pin WROOM-32, female headers | user: "the old ones" |
| A3/A4 | Mounting | removable; USB ports reachable | default |
| B | Magnets | 10× 2-pin outputs (+/-), IRLZ44N + diode (same as the prototype) | user |
| B2 | Magnet current | unknown; board sized for up to 1.5A each, 10A total fuse | default |
| B3c | Divider | 1k / 2k | default |
| C | Coin acceptor | 12V, GND, SIG terminal, with an optocoupler input | user + default |
| D/F | Buttons / LEDs | normal buttons, small DIY LEDs wired off-board; resistors on the PCB | user |
| E | 7-segment | small 5V common cathode; 74HC595 on the PCB; 8-pin output | user ("mux" = the 74HC595 in the code) |
| G1 | PSU | 12V 16A | user |
| G2/G4 | Power input | screw terminal, fuse, power LEDs | default |
| H1 | Size | compact with comfortable spacing and clear labels | user |
| H2 | Assembly | JLCPCB solders the small SMD parts; you solder the terminals, headers and MOSFETs | default |
| H3 | Connectors | screw terminals: 5.08 mm for power and magnets, 3.5 mm for signals | default |
| H4 | Extras | per-magnet ON LEDs, spare expansion header | default |
| H5 | Code | unchanged | default |

## 5. Deliverables (after GO)
1. KiCad project in this folder, with schematic and ERC passing.
2. PCB layout with DRC passing.
3. 3D model (STEP) and 3D pictures of the top and bottom.
4. JLCPCB files: Gerbers, drill files, BOM and pick-and-place.
5. Design review report.
6. `WIRING_GUIDE.md` - which cable goes to which terminal.
