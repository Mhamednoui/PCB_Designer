# Reflex Machine Board - Wiring & Build Guide

Board: `reflex-machine.kicad_pcb` (160 × 125 mm, 2 layers, **all through-hole parts**). It plugs **on top of an Arduino Mega 2560** like a shield.
The **ESP32 DevKit V1 (30-pin)** plugs into the two long black sockets on top.

---

## 0. Reading the board
Every part has its **value printed next to it** (10k, 1N5822, 220uF...), so you can populate the board
without this document. Section headings are printed too: MAGNET DRIVERS, POWER, 7-SEG DRIVER, COIN OPTO,
MEGA SPARE PINS, ESP32 SPARE. Each magnet terminal shows the Arduino pin that drives it (for example
"- M1 + D3"), and each bottom terminal screw shows its Arduino pin underneath.

## 1. Before you wire anything

1. **Check the ESP32.**
   - Measure the distance between its two pin rows. It must be **25.4 mm** (1 inch); this is the DOIT 30-pin board.
   - Plug it in so the **antenna end points to the board's left edge**, where the silkscreen says "ANTENNA THIS END".
2. **Check the Mega.** Its USB and DC jack sit under the left side of the board. Put a piece of electrical tape on top of the Mega's USB connector so it cannot touch the board above.
3. **Do the first power-up without the Mega and without the ESP32:**
   - Connect 12V to J1. The green **12V** LED and the green **5V** LED must turn on.
   - Measure J16 pin 1 (5V) to pin 2 (GND). It must read 4.9-5.1 V.
   - Unplug the power, then insert the Mega and the ESP32.

---

## 2. Terminals

### J1 - 12V power input (right edge, big terminal)
| Terminal | Wire |
|---|---|
| **+** (lower screw, "12V IN +") | 12V supply **+** |
| **GND** (upper screw) | 12V supply **-** |

- The board has a **mini blade fuse (10A)** in holder F1. Use a car mini blade fuse.
- If the magnets pull more current, a 15A fuse is fine; your supply is 16A.

### M1 - M10 - Electromagnets (top edge, 10 terminals)
Each terminal has **- (left screw)** and **+ (right screw)**, as printed under it: `-  M1  +`.
A plain electromagnet coil works either way round.

| Terminal | Magnet | Arduino pin | Red LED lights when |
|---|---|---|---|
| M1 | stick 1 | D3 | magnet 1 is ON |
| M2 | stick 2 | D5 | magnet 2 is ON |
| M3 | stick 3 | D6 | magnet 3 is ON |
| M4 | stick 4 | D7 | magnet 4 is ON |
| M5 | stick 5 | D8 | magnet 5 is ON |
| M6 | stick 6 | D9 | magnet 6 is ON |
| M7 | stick 7 | D10 | magnet 7 is ON |
| M8 | stick 8 | D11 | magnet 8 is ON |
| M9 | stick 9 | D12 | magnet 9 is ON |
| M10 | stick 10 | D44 | magnet 10 is ON |

Each magnet has its own IRLZ44N MOSFET, flyback diode and indicator LED on the board, so do **not** add diodes on the magnets.

### COIN - Coin acceptor (bottom left, 3 screws)
| Screw | Coin acceptor wire |
|---|---|
| **12V** | DC +12V (usually red) |
| **GND** | GND (usually black) |
| **SIG** | COIN signal (usually white) |

- Set the coin acceptor's switch to **NO**.
- The board already has the resistor and an **optocoupler**, so connect the wires directly.

### BUTTONS (bottom, 8 screws)
Each button has 2 wires: one to its signal screw and one to the **G** screw next to it.

| Screws | Button | Arduino pin |
|---|---|---|
| S1 + G | SPEED 1 | D22 |
| S2 + G | SPEED 2 | D24 |
| S3 + G | SPEED 3 | D26 |
| RST + G | RESET | D28 |

Use normally-open push buttons. Filters and pull-up resistors are already on the board.

### STATUS LEDS (bottom, 8 screws)
The resistors are on the board, so connect each LED directly.
- Long leg (anode) goes to **+**.
- Short leg (cathode) goes to **-**.

| Screws | LED | Arduino pin | Lights when |
|---|---|---|---|
| 1+ / 1- | LED1 | A3 | RESET state |
| 2+ / 2- | LED2 | A4 | releasing, fast speed (SPEED3) |
| 3+ / 3- | LED3 | A5 | releasing, medium speed (SPEED2) |
| 4+ / 4- | LED4 | A6 | releasing, slow speed (SPEED1) |

### 7-SEGMENT (bottom right, 8 screws)
For a **common-cathode** 5V digit. The 74HC595 and the 470 Ω segment resistors are on the board.

| Screw | a | b | c | d | e | f | g | GND |
|---|---|---|---|---|---|---|---|---|
| Display pin | seg a | seg b | seg c | seg d | seg e | seg f | seg g | common (COM) |

The segment wiring matches your code exactly (QD→a, QG→b, QF→c, QH→d, QE→e, QC→f, QB→g), so no code changes are needed.

### J16 - MEGA SPARE pins (2x10 header, under the ESP32)
Every pin here is free for future add-ons. The pin names are printed on the board next to the header.

| Row | Pins |
|---|---|
| top row (odd pins) | 5V, 3.3V, SDA (D20), TX3 (D14), D4, D30, D32, A7, SCK (D52), MOSI (D51) |
| bottom row (even pins) | GND, GND, SCL (D21), RX3 (D15), D13, D31, D33, A8, MISO (D50), CS (D53) |

That gives you: I2C (SDA/SCL), a spare serial port (Serial3), full SPI, 6 spare digital pins, 2 spare analog
inputs, and both supplies. Enough for a display, an RFID reader, a real-time clock, extra sensors or relays.

### J17 - ESP32 SPARE pins (2x4 header, next to J16)
| Row | Pins |
|---|---|
| top row | 3.3V (from the ESP32), GPIO25, GPIO27, GPIO33 |
| bottom row | GND, GPIO26, GPIO32, GPIO14 |

Use these for anything the ESP32 should handle directly (extra WiFi-controlled outputs, sensors, a buzzer).

**Warning:** ESP32 pins are 3.3V only. Do not connect 5V signals to them directly.

---

## 3. Mega ↔ ESP32 link (already on the board, nothing to wire)
- **Mega TX1 (D18)** → 1k / 2k resistor divider (5V down to 3.3V) → **ESP32 GPIO16 (RX2)**
- **ESP32 GPIO17 (TX2)** → **Mega RX1 (D19)**
- The ESP32 is powered from the board's 5V through its **VIN** pin, and both boards share GND.

You can still plug USB into the Mega or the ESP32 to upload code, even while 12V is connected.

---

## 4. Parts you solder yourself - ALL through-hole (leaded), normal size

The board has **no surface-mount parts**. Everything is standard leaded components you can solder by hand.

| Qty | Part | Where | Notes |
|---|---|---|---|
| 10 | IRLZ44N MOSFET (TO-220) | Q1-Q10 | metal tab facing the magnet terminals |
| 10 | 1N5822 Schottky diode (DO-201AD) | D11-D20 | **stands upright**, stripe (cathode) to the marked hole |
| 10 | 3 mm red LED | D21-D30 | magnet ON indicators; long leg = + |
| 2 | 5 mm green LED | D3 (12V), D4 (5V) | power indicators; long leg = + |
| 1 | 1N4007 diode (DO-41) | D2 | stripe towards the 5V module |
| 1 | P6KE15A surge diode (DO-15) | D1 | stripe towards +12V |
| 1 | **5V DC-DC module, 3-pin** (K7805-2000R3, R-78B5.0-2.0 or equivalent, 2 A) | U1 | drop-in replacement for a 7805, pins 2.54 mm apart: IN / GND / OUT |
| 1 | 74HC595 in DIP-16 | U3 | notch towards the top; a DIP socket is fine |
| 1 | PC817 optocoupler in DIP-4 | U2 | dot = pin 1 |
| 10 | 100 Ohm resistor (1/4 W) | R11-R20 | gate resistors |
| 15 | 10k resistor | R21-R30, R42, R47-R50 | |
| 11 | 2.2k resistor | R31-R40, R41 | |
| 7 | 470 Ohm resistor | R55-R61 | 7-segment |
| 4 | 330 Ohm resistor | R51-R54 | status LEDs |
| 6 | 1k resistor | R2, R43-R46, R62 | |
| 1 | 2k resistor | R63 | serial divider |
| 1 | 4.7k resistor | R1 | |
| 6 | 100 nF ceramic capacitor (5 mm) | C3, C7, C9-C13 | |
| 1 | 1 nF ceramic capacitor | C8 | |
| 2 | 220 uF 25V electrolytic | C2, C6 | **watch polarity**, long leg = + |
| 1 | 1000 uF 25V electrolytic (10 mm) | C1 | **watch polarity** |
| 1 | Mini blade fuse holder + 10 A fuse | F1 | car-type mini fuse |
| 1 | 2-pin screw terminal, 5.08 mm, 16 A+ | J1 | 12V input |
| 10 | 2-pin screw terminal, 5.08 mm | M1-M10 | magnets |
| 1 | 3-pin screw terminal, 3.5 mm | COIN | |
| 3 | 8-pin screw terminal, 3.5 mm | BUTTONS, STATUS LEDS, 7-SEGMENT | |
| 2 | 1x15 female header, 2.54 mm | ESP32 sockets | |
| 1 | 2x5 male header, 2.54 mm | J16 | |
| 1 set | **Arduino Mega stacking / long male headers**: 1x10, 3x 1x8, 2x 1x8, 2x18 | Mega pin holes | solder these LAST |

**Solder the Mega headers LAST**, from the bottom side, with the board sitting on the Mega. That keeps every pin straight.

### Soldering order that works well
1. Resistors and diodes (lie flat / stand up as the silkscreen shows)
2. Ceramic capacitors, then the DIP sockets or ICs
3. Electrolytic capacitors and LEDs (check polarity)
4. MOSFETs, fuse holder, 5V module
5. Screw terminals and the ESP32 sockets
6. Mega headers last
