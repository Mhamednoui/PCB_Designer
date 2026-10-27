# Uno Toggle — design brief

A deliberately simple board, built end-to-end (design → fab files → all test stages → live simulation)
to exercise the whole pipeline and the webview platform on something other than the Reflex Machine.

## What the user asked for
> "two leds two buttons thats all, arduino uno r3, each button when pressed run a led if pressed again
> off, through-hole, buttons and led on board"

## Spec

| | Decision |
|---|---|
| Function | Press button 1 → LED 1 toggles on; press again → off. Same for button 2 / LED 2. |
| Controller | Arduino Uno R3, board sits on top as a **shield** |
| Inputs | 2 tactile push buttons, **on the board** |
| Outputs | 2 LEDs, **on the board** |
| Assembly | **All through-hole** (user cannot solder SMD — standing constraint from the Reflex Machine) |
| Power | From the Uno's own 5V/GND through the shield headers. No external supply. |

## Decisions I made (defaults, not asked — flag if any is wrong)

**Pin map** — chosen to avoid pins that would confuse testing:
| Signal | Uno pin | Why |
|---|---|---|
| `BTN1` | D2 | free, interrupt-capable if ever needed |
| `BTN2` | D3 | same |
| `LED1` | D8 | plain digital, well clear of D0/D1 |
| `LED2` | D9 | same |

Avoided: **D0/D1** (serial — would fight uploads/monitor) and **D13** (has an LED soldered on the Uno
itself, which would make "is that my LED or the board's?" ambiguous during bring-up).

**Buttons**: wired to **GND**, using the AVR's internal pull-ups (`INPUT_PULLUP`), so pressed = LOW.
No external pull-up resistors needed. Each button gets a **100nF cap across it** for hardware debounce —
two cheap through-hole parts that make the board behave properly even before firmware debouncing. This
is the lesson from the Reflex Machine, where unfiltered button inputs caused false triggers.

**LEDs**: each with a **330R** series resistor to GND — ~10mA at 5V, comfortably inside the Uno's
20mA/pin limit, and bright enough to read across a room.

**Form factor**: Uno R3 shield outline, so it needs no enclosure or wiring to be testable — plug it on,
upload, press.

## Parts (8 components + the shield connector)
| Ref | Part | Value |
|---|---|---|
| A1 | Arduino Uno R3 shield headers | — |
| SW1, SW2 | Tactile push button, 6mm THT | — |
| D1, D2 | LED 5mm THT | red, green |
| R1, R2 | Resistor, axial THT | 330R |
| C1, C2 | Capacitor, disc THT | 100nF |

## Firmware
`firmware/uno_toggle.ino` — reads both buttons with debounce + edge detection, toggles the matching LED.
Kept intentionally small so the Wokwi simulation stage is easy to verify by eye.

## What "done" means for this board
Per `docs/NEW_BOARD_PLAYBOOK.md` §4: ERC clean, netlist compare 0 mismatches, DRC 0 errors /
0 unconnected / 0 parity issues, renders reviewed, fab files written — **and** it appears in the webview
platform with working live simulation (press a button in the browser, watch the right LED light up).
