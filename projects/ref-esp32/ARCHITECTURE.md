# ref-esp32 - architecture

Companion to `DESIGN_BRIEF.md`. Planning only: nothing here is a netlist; every pin and value is a proposal
for P1 (registry), P2 (rules) and P3 (blocks) to turn into data and then check.
Date of all stock/price figures: **2026-10-27**. Short names for sources:
- **WROOM-1 DS** = ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8 (read as text), https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf
- **HW checklist** = Espressif ESP32-S3 Hardware Design Guidelines, Schematic Checklist, https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html (sections are headings, the page numbers its sections only by name)
- **HW layout** = same guide, PCB Layout Design, https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html
- **LDL1117 DS** = ST LDL1117, DocID030319 Rev 3 (LCSC copy), https://datasheet.lcsc.com/datasheet/pdf/29f4e8f2c569cb1b438995f2c8fccc58.pdf?productCode=C435835
- **SHT3x DS** = Sensirion SHT3x-DIS v7 (Dec 2022), https://sensirion.com/media/documents/213E6A3B/63A5A569/Datasheet_SHT3x_DIS.pdf
- **USBLC6 DS** = ST USBLC6-2 (LCSC copy), https://datasheet.lcsc.com/datasheet/pdf/0d3a2ab954b34651a0695e7ccf534db0.pdf?productCode=C7519
- **PTC DS** = Ruilon SMD1206 series SP-PTC-006 A6, https://datasheet.lcsc.com/datasheet/pdf/147b01ecd3cb8b8f5a5deee7c25b85b7.pdf?productCode=C20801
- **AMS1117 DS** = AMS1117 (SLKOR copy), https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8122/AMS11173.3SOT223.pdf

"Verified" below means I read the cited document in this task. Items marked *(from knowledge)* were not re-read.

---

## 1. Block diagram

```
                                       +--------------------------------------------------+
  USB host                             |  ref-esp32  (3V3 domain unless marked 5 V)       |
  (5 V, 500 mA default)                |                                                  |
        |                              |                                                  |
   +----+-----+  VBUS (5 V)            |                                                  |
   | J1 USB-C |---------+--------------+--> U4 pin5 (ESD rail clamp)                       |
   | 16-pin   |         |              |                                                  |
   |          |   +-----v-----+  VBUS_F (5 V)                                              |
   |          |   | F1 PTC    |-----+---------+------------------+------> J3.1 "5V" (OUT)   |
   |          |   | 1.1 A     |     |         |                  |                         |
   |          |   +-----------+  [D1 TVS]  [C1 4.7u]       +-----v------+                  |
   |          |                    SMAJ5.0A  [C2 100n]      | U2 LDO     |  3V3            |
   | CC1 -----|--[R1 5.1k]--GND                             | LDL1117S33R|---+--[C3 22u]   |
   | CC2 -----|--[R2 5.1k]--GND                             +------------+   |             |
   |          |                                                              |             |
   | D+ A6/B6-|--+                                                           |             |
   | D- A7/B7-|--|--+                                                        |             |
   |          |  v  v                                                        |             |
   | SHIELD --|-GND U4 USBLC6-2SC6 (flow-through)                           |             |
   +----------+  |  |                                                        |             |
                 v  v                                                        |             |
            [R9 22][R10 22]                                                  |             |
                 |  |                                                        |             |
        IO20/D+  |  | IO19/D-            3V3 -----------------------------+---+----+--- J2.1, J3.14
                 v  v                                                    |   |    |
              +--------------------------+  EN  <--[R3 10k to 3V3]---+---+   |    |
              | U1 ESP32-S3-WROOM-1-N8   |           [C5 1u to GND]  |       |    |
              | pin2 3V3 [C4 100n]       |<----------[SW2 RESET]-----+       |    |
              | pin27 IO0 <--[R4 10k]    |<----------[SW1 BOOT] to GND       |    |
              |                          |                                    |    |
              | IO8  SDA  ----+---[R5 2.2k]--3V3                              |    |
              | IO9  SCL  ----|---[R6 2.2k]--3V3                              |    |
              |               +--> U3 SHT30 (0x44, ADDR=GND) [C6 100n]        |    |
              |               +--> J5 Qwiic (GND,3V3,SDA,SCL)                 |    |
              | IO21 --[R8 470]--> LED2 (yellow) --GND                        |    |
              | TXD0 --[R11 470]-> J4.1   RXD0 -> J4.2   GND -> J4.3          |    |
              | IO1,2,4-7,10-18,35-42,47,48 --> J2 / J3 (25 GPIO)             |    |
              | IO3, IO45, IO46: not connected (strapping)                    |    |
              +--------------------------+                                    |    |
   3V3 --[R7 1k]--> LED1 (red) --GND  (power indicator) ----------------------+    |
```

Top view of the intended floor plan (sketch, mm, board 30 x 55; P4 decides exact coordinates):

```
   y=0  +--------------------------------+   antenna end flush with the edge
        |  X X X X X X X X X X X X X X X |   X = antenna keep-out, ALL copper layers
        |  X X X  (about 18 x 6-7.5 mm) X|
   y=8  |   +------------------------+   |
 J2     o   |   U1  ESP32-S3-WROOM-1  |   o   J3     (first header pin must be below the keep-out)
 1x16   o   |   18 x 25.5             |   o   1x16     25.4 mm apart
        o   |   EPAD + GND vias       |   o
        o   +------------------------+   o
        o     C4 R3 C5 SW1 SW2 (EN/BOOT) o
        o   U3 SHT30 .......  R5 R6      o   (sensor >= 12 mm from U2, >= 10 mm from U1)
        o                 U4  D1  F1 U2  o   (U2 tab pour >= 2 cm2)
   y=55 |  J4       J5      [J1 USB-C]     |   mounting holes at the two bottom corners
        +--------------------------------+
```

## 2. Power tree and budget

### 2.1 Tree

| Node | Source | Range | Notes |
|---|---|---|---|
| VBUS | J1 | 4.75-5.25 V at the source (USB 2.0); down to ~4.40 V at the device end under load *(from knowledge: USB 2.0 §7.2.1.5; design uses 4.40 V as the low corner)* | 500 mA default-power sink: CC pulled down 5.1 kΩ, no negotiation |
| VBUS_F | F1 (PTC) | VBUS − I·R, R <= 0.25 Ω (R1max, PTC DS p.3) | 0.116 V drop at 465 mA worst case |
| 3V3 | U2 | 3.3 V ±2 % (25 °C) / ±3 % (−40-125 °C), LDL1117 DS Table 4 | module needs 3.0-3.6 V and >= 0.5 A (WROOM-1 DS Table 6-2) |

### 2.2 3V3 budget (peak = design point)

| Load | Peak mA | Basis |
|---|---|---|
| U1 module, Wi-Fi 802.11b 1 Mbps TX @20.5 dBm, 100 % duty | **355** | WROOM-1 DS Table 6-4 (p.28). BLE TX @20 dBm is 344 mA (Table 6-5); both cannot be the absolute worst at once, 355 is used. |
| U3 SHT30 measuring | 0.6 | SHT3x DS Table 3 (idle 0.2 µA, average 1.7 µA at 1 Hz low-rep) |
| I2C pull-ups, one line low | 1.5 | 3.3 V / 2.2 kΩ; both low never happens on the same bus phase, use one (worst-case both = 3.0) |
| LED1 | 1.4 | (3.3 − 1.9) / 1 kΩ, Vf 1.8-2.4 V (KT-0805Y desc.; NCD0805R1 Vf unverified) |
| LED2 | 3.0 | (3.3 − 1.9) / 470 Ω; GPIO source current is well inside the GPIO limit (WROOM-1 DS Table 6-3 IOH 40 mA) |
| BOOT/RESET pull-ups when pressed | 0.7 | 2 x 3.3 V / 10 kΩ, momentary |
| External allowance, J2/J3/J5 | 100 | design choice |
| **Total** | **~463 -> 465 mA** | <= 500 mA requirement (Table 6-2); LDO rated 1.2 A (LDL1117 DS Table 4 dropout rated at 1.2 A) |

Average planning figure: **125 mA** (module ~120 mA connected/active, RX 95-97 mA Table 6-4, modem-sleep 240 MHz dual core 92-108 mA Table 6-6; plus ~5 mA). An *assumption*, not a datasheet number.

### 2.3 LDO dissipation (U2) and thermal check

P = (VBUS_F − 3.3 V) · I, with VBUS_F = VBUS − I · 0.25 Ω (worst-case PTC).

| Case | VBUS | I | VBUS_F | **P_diss** | Tj at 40 °C, θJA = 120 °C/W | θJA needed for Tj <= 125 °C at 40 °C / 25 °C |
|---|---|---|---|---|---|---|
| Peak, nominal | 5.00 V | 465 mA | 4.884 V | **0.74 W** | 128 °C | 115 / 136 °C/W |
| Peak, high USB | 5.25 V | 465 mA | 5.134 V | **0.85 W** | 142 °C | 100 / 117 °C/W |
| At the 500 mA cap, high USB | 5.25 V | 500 mA | 5.125 V | **0.91 W** | 150 °C | 93 / 110 °C/W |
| Module TX only (no allowance) | 5.00 V | 355 mA | 4.911 V | 0.57 W | 109 °C | 149 / 175 °C/W |
| **Average** | 5.00 V | 125 mA | 4.969 V | **0.21 W** | 65 °C | - |
| Average, high USB | 5.25 V | 125 mA | 5.219 V | **0.24 W** | 69 °C | - |

Facts: θJA = 120 °C/W and θJC = 15 °C/W (LDL1117 DS Table 3), TJ-OP −40-125 °C (Table 2), thermal
shutdown ~175 °C typ, restart ~150 °C (§6.1). The 120 °C/W figure is ST's test board; copper area changes it
and **I could not find a copper-area-vs-θJA table in the ST datasheet**, so the achieved θJA must be
estimated in P4 (not asserted).

Verdict:
1. Average operation is fine (65-69 °C at 40 °C ambient with no extra copper).
2. *Continuous* 100 %-duty TX at high USB voltage and 40 °C exceeds 125 °C with ST's board. Real firmware
   never transmits 100 % of the time (the 355 mA figure is "rated at 100 % duty cycle", WROOM-1 DS §6.4.1),
   and SOT-223 thermal time constants are tens of seconds, so the average, not the peak, sets Tj for any
   realistic workload. Even a 30 % TX duty (≈195 mA average, 0.32-0.37 W) is 79-85 °C at 40 °C with ST's board.
3. Layout requirement to widen the margin: the tab is VOUT (LDL1117 DS Table 1, "The tab is connected to
   VOUT") and is the heat path; give it >= 2 cm² of connected copper (top pour + bottom pour stitched by
   >= 6 vias). Do **not** put a GND pour under the tab - it is not GND.
4. If a future brief needs sustained Wi-Fi TX at high ambient: replace U2 by a small synchronous buck
   (P3 "buck module" block, loss ~0.05 W) at the cost of an inductor next to an RF module; not default.
5. A series Schottky/resistor to share the dissipation was rejected: it eats the dropout margin that is
   the reason for this LDO.

Why LDL1117S33R and not AMS1117-3.3 (C6186, basic, about $0.30 cheaper and no extended fee):
- Dropout: AMS1117 is **1.30 V typ / 1.40 V max at 1 A** (AMS1117 DS, Electrical Characteristics); the
  LCSC listing for C6186 quotes 1.1 V at 800 mA. At 4.40 V − 0.116 V = 4.28 V into the LDO, 3.3 V + ~1.1 V = 4.4 V is
  *not* available at 465 mA, so the rail would sag below 3.3 V on a weak/long cable. LDL1117: 0.35 V typ,
  **0.6 V max** at 1.2 A (Table 4), ≈0.15-0.25 V at 0.46 A by scaling (my estimate, no curve read) -> needs only ~3.6 V in.
- Stability: AMS1117 needs an output capacitor with ESR <= 0.5 Ω (tantalum / electrolytic recommended,
  "ESR must not exceed 0.5 Ω" and ceramics are borderline) vs LDL1117 designed for a ceramic Cout
  (§6.2: 1 µF in, 4.7 µF out suggested, "X5R and X7R are suggested"). A 22 µF X5R Cout is outside the
  4.7 µF the datasheet characterises; check Figure 20 (stability plan) at P1 crosscheck (open item).
- Cost: +1 extended-part fee (JLCPCB page last updated 2026-10-22: ~$1.53 standard PCBA, per the P1 spike §5) and $0.30 more.
  AMS1117 stays the documented fallback (Q2); pin order identical (1 GND, 2 VOUT, 3 VIN, tab VOUT).

### 2.4 5 V side and USB budget

| Item | mA |
|---|---|
| 3V3 peak | 465 |
| U2 quiescent (LCSC listing shows 500 µA) | 0.5 |
| 5V header allowance (J3.1, OUT only) | 35 |
| **VBUS total** | **~500** = USB 2.0 default-power limit (Rd 5.1 kΩ without Rp negotiation: default USB power, 56 kΩ Rp case, *from knowledge, USB Type-C spec; search summaries agree*) |

The 35 mA allowance exists only to make the budget close; if the owner wants more on 5 V the Rd must be
replaced by a CC controller (out of scope).

PTC: Ruilon SMD1206P110TF, Ihold 1.10 A, Itrip 2.20 A, Vmax 6 V, Imax 35 A, R1max 0.25 Ω (PTC DS p.3). The
rated Vmax of 6 V is above VBUS max 5.25 V. Hold current falls with temperature (derating chart, PTC DS
p.4, not extracted precisely): assume ≥ 0.8 A at 60 °C, still well above 500 mA.

TVS: SMAJ5.0A (MDD, C113952): standoff 5.0 V, Vbr min 6.4 V, Vclamp 9.2 V at 43.5 A (LCSC listing). Clamp
9.2 V is below the LDO's 20 V absolute maximum (LDL1117 DS Table 2) and the 6 V PTC Vmax is never seen because
the TVS is downstream of F1 (the PTC takes the sustained overvoltage, TVS the transients).

## 3. Net-level interface and level map

Convention: nets are upper-case; GPIO nets keep the Espressif name `IOn`. Level = logic/rail voltage; the
column "abs-max" is the limit that rule PR-V (P2) checks.

### 3.1 Power and USB nets

| Net | Driver -> loads | Level | abs-max / limit |
|---|---|---|---|
| VBUS | J1 A4,A9,B4,B9 -> U4.5, F1.1 | 5 V | U4 pin5 5.25 V rated V_RM; no module pin |
| VBUS_F | F1.2 -> D1, C1, C2, U2.3 (VIN), J3.1 | 5 V | LDL1117 VIN 20 V abs-max (Table 2) |
| 3V3 | U2.2 + tab (VOUT) -> U1.2, C3, C4, C6, R3, R4, R5, R6, R7, U3.5, J2.1, J3.14, J5.2 | 3.3 V | module 3.0-3.6 V, abs-max −0.3-3.6 V (WROOM-1 DS Table 6-1, 6-2) |
| GND | all | 0 V | |
| CC1 / CC2 | J1 A5 / B5 -> R1 / R2 -> GND | Rd | 5.1 kΩ 1 % |
| USB_DP | J1 A6+B6 -> U4.1 (ESD) | 3.3 V FS | |
| USB_DM | J1 A7+B7 -> U4.3 (ESD) | 3.3 V FS | |
| ESP_DP | U4.6 -> R9 -> U1.14 (IO20, USB_D+) | 3.3 V | VDD + 0.3 V |
| ESP_DM | U4.4 -> R10 -> U1.13 (IO19, USB_D−) | 3.3 V | VDD + 0.3 V |
| (SBU1/SBU2 A8/B8) | not connected | - | explicit NC |
| (SHIELD) | J1 SH tabs -> GND | - | direct (Q9) |

### 3.2 Control and peripheral nets

| Net | From -> to | Module pin / GPIO | Level | Notes |
|---|---|---|---|---|
| EN | R3 (to 3V3), C5 (to GND), SW2 (to GND) -> U1.3 | pin 3, EN | 3.3 V | datasheet-recommended RC, §3.4 |
| BOOT | R4 (to 3V3), SW1 (to GND) -> U1.27 | pin 27, IO0 | 3.3 V | strap, §4 |
| I2C_SDA | R5 (to 3V3), U3.1, J5.3, U1.12 | pin 12, IO8 | 3.3 V | open-drain |
| I2C_SCL | R6 (to 3V3), U3.4, J5.4, U1.17 | pin 17, IO9 | 3.3 V | open-drain |
| LED_STATUS | U1.23 -> R8 -> LED2 anode; cathode GND | pin 23, IO21 | 3.3 V | active high |
| LED_PWR | 3V3 -> R7 -> LED1 -> GND | - | - | always on |
| UART0_TX | U1.37 (TXD0, GPIO43) -> R11 470 Ω -> J4.1 | pin 37 | 3.3 V | series R per HW checklist "UART download": "Add a 499 Ω series resistor on U0TXD" (470 Ω used: same E-series class, saves a BOM line) |
| UART0_RX | U1.36 (RXD0, GPIO44) <- J4.2 | pin 36 | 3.3 V | input only; do not connect 5 V |
| SHT_ALERT / SHT_RESET | U3.3 / U3.6 | - | - | explicit NC (SHT3x DS Table 7: ALERT "must be left floating if unused"; nRESET "recommended to be left floating", internal pull-up to VDD §3.6) |
| SHT ADDR | U3.2 -> GND | - | 0 | I2C address 0x44 (SHT3x DS Table 8); "do not leave floating" |
| SHT R | U3.7 -> GND | - | 0 | "to be connected to VSS" (Table 7) |

### 3.3 Header allocation (25 GPIO + power)

All GPIO nets are 3.3 V logic, abs-max VDD + 0.3 V. Order follows the module's pin order so no crossings are needed.

| J2 (left edge), top -> bottom | J3 (right edge), top -> bottom |
|---|---|
| 1 `3V3` | 1 `VBUS_F` ("5V", output only) |
| 2 `IO4` (pin 4) | 2 `IO1` (39) |
| 3 `IO5` (5) | 3 `IO2` (38) |
| 4 `IO6` (6) | 4 `IO42` (35, MTMS) |
| 5 `IO7` (7) | 5 `IO41` (34, MTDI) |
| 6 `IO15` (8) | 6 `IO40` (33, MTDO) |
| 7 `IO16` (9) | 7 `IO39` (32, MTCK) |
| 8 `IO17` (10) | 8 `IO38` (31) |
| 9 `IO18` (11) | 9 `IO37` (30) |
| 10 `IO10` (18) | 10 `IO36` (29) |
| 11 `IO11` (19) | 11 `IO35` (28) |
| 12 `IO12` (20) | 12 `IO47` (24) |
| 13 `IO13` (21) | 13 `IO48` (25) |
| 14 `IO14` (22) | 14 `3V3` |
| 15 `GND` | 15 `GND` |
| 16 `GND` | 16 `GND` |

J3 pins 4-7 are the four JTAG pins (MTMS/MTDI/MTDO/MTCK) in order; the built-in USB Serial/JTAG makes an
external JTAG unnecessary. IO35-IO37 are free **only** because the module is N8 (WROOM-1 DS Table 3-1 note b); IO47/IO48 are free
for all but the R16V variants (note c).

### 3.4 Module pin -> net (all 41 pins; what P1 must put in the registry as pins-by-function)

| Pin | Name | Net | | Pin | Name | Net |
|---|---|---|---|---|---|---|
| 1 | GND | GND | | 22 | IO14 | IO14 |
| 2 | 3V3 | 3V3 | | 23 | IO21 | LED_STATUS |
| 3 | EN | EN | | 24 | IO47 | IO47 |
| 4 | IO4 | IO4 | | 25 | IO48 | IO48 |
| 5 | IO5 | IO5 | | 26 | IO45 | **NC (strap)** |
| 6 | IO6 | IO6 | | 27 | IO0 | BOOT |
| 7 | IO7 | IO7 | | 28 | IO35 | IO35 |
| 8 | IO15 | IO15 | | 29 | IO36 | IO36 |
| 9 | IO16 | IO16 | | 30 | IO37 | IO37 |
| 10 | IO17 | IO17 | | 31 | IO38 | IO38 |
| 11 | IO18 | IO18 | | 32 | IO39 | IO39 |
| 12 | IO8 | I2C_SDA | | 33 | IO40 | IO40 |
| 13 | IO19 / USB_D− | ESP_DM | | 34 | IO41 | IO41 |
| 14 | IO20 / USB_D+ | ESP_DP | | 35 | IO42 | IO42 |
| 15 | IO3 | **NC (strap)** | | 36 | RXD0 | UART0_RX |
| 16 | IO46 | **NC (strap)** | | 37 | TXD0 | UART0_TX |
| 17 | IO9 | I2C_SCL | | 38 | IO2 | IO2 |
| 18 | IO10 | IO10 | | 39 | IO1 | IO1 |
| 19 | IO11 | IO11 | | 40 | GND | GND |
| 20 | IO12 | IO12 | | 41 | EPAD | GND (thermal vias) |
| 21 | IO13 | IO13 | | | | |

The only unconnected GPIO pins are 15, 16 and 26 (the strapping pins). Pin names/numbers verified against WROOM-1 DS Table 3-1 (pp.11-12) and against the installed KiCad symbol
`RF_Module:ESP32-S3-WROOM-1` via `tools/sym_pins.py`: all 41 numbers and names agree
(the KiCad symbol renames pins 13/14 to `USB_D-`/`USB_D+`).

## 4. Strapping and boot pins (chosen module: ESP32-S3-WROOM-1-N8)

Sources: WROOM-1 DS §4 (Table 4-1 default configuration p.13, Table 4-3 boot mode p.14, Table 4-4 VDD_SPI p.15,
§4.4 JTAG source p.15, §4.5 power-up/reset p.16, Table 4-6) and HW checklist "Strapping Pins", "Chip Power-up and Reset Timing".

| GPIO / module pin | Strap function | Default (Table 4-1) | Required at reset on this board | Board handling | Rule it feeds |
|---|---|---|---|---|---|
| **GPIO0**, pin 27 | boot mode (with GPIO46) | weak pull-up = 1 | 1 for SPI boot; 0 (with GPIO46 = 0) for Joint Download Boot (UART or USB download) | R4 10 kΩ pull-up to 3V3 + SW1 BOOT to GND. **No capacitor** ("Do not add high-value capacitors at GPIO0, or the chip may enter download mode", HW checklist). Not on a header. | M-strap: pull-up present, no C, no other driver |
| **GPIO46**, pin 16 | boot mode (with GPIO0) and ROM message print | weak pull-down = 0 | 0 for download mode; "any value" in SPI boot (Table 4-3) | **Not connected**; internal pull-down gives the correct 0. Not broken out (an external high level with GPIO0 = 0 is not a defined mode in Table 4-3). | NC allowed, strap-pin must not be driven |
| **GPIO45**, pin 26 | VDD_SPI voltage | weak pull-down = 0 | 0 -> VDD_SPI = 3.3 V (Table 4-4, EFUSE_VDD_SPI_FORCE = 0). A 1 selects 1.8 V and would under-supply this module's 3.3 V flash. | **Not connected**, not broken out. Never externally pulled up. | strap-pin must not be driven |
| **GPIO3**, pin 15 | JTAG signal source | floating (no internal pull) | ignored with all JTAG eFuses at default 0 (Table 4-5 row 1, "Ignored"); "strapping value must be controlled by the external circuit that cannot be in a high impedance state" only when eFuse STRAP_JTAG_SEL is set | **Not connected** (eFuses stay default). Documented limitation: if the owner burns EFUSE_STRAP_JTAG_SEL, GPIO3 needs an external definite level. | NC with reason |
| **EN**, pin 3 | chip enable / reset | - (never float) | high after 3V3 stable (tSTBL >= 50 µs, tRST >= 50 µs, Table 4-6) | R3 10 kΩ to 3V3, C5 1 µF to GND, SW2 to GND. Espressif: "R = 10 kΩ and C = 1 µF" (WROOM-1 DS §9 p.41; HW checklist). | M-strap: EN has R and C |
| Timing | tSU >= 0 ms, tH >= 3 ms (Table 4-2) | | BOOT must be stable for 3 ms after EN rises | EN delay below | |

EN timing check: τ = 10 kΩ · 1 µF = 10 ms. EN crosses VIL_nRST = 0.25·3.3 V = 0.825 V after 0.288·τ = **2.9 ms**
(if 3V3 steps instantly; the LDO with 22 µF reaches 3.3 V in well under 1 ms), and VIH_nRST = 0.75·3.3 V = 2.48 V
after 1.386·τ = **13.9 ms**, both >> tSTBL 50 µs. Reset pulse: pressing SW2 discharges C5 through the switch
(sub-µs), far past tRST 50 µs. Pull-up current when pressed: 0.33 mA.

Download entry on this board: hold BOOT, tap RESET, release BOOT; or use the USB Serial/JTAG auto-reset from the host (no DTR/RTS circuit, no bridge chip).

Other pins with boot-time behaviour: **GPIO19/20** (USB) show "two high-level glitches of about 60 µs during
power-up" and "USB_D+ will fluctuate between high and low states" (HW checklist, "USB"); see §5.4 for the pull-up question.
**GPIO43/44** (UART0) print ROM messages by default; the 470 Ω series resistor limits harmonics.
GPIO26-32 (flash) and GPIO33/34 are not on the module's pins at all.

## 5. USB-C design

### 5.1 Connector wiring (HRO TYPE-C-31-M-12, LCSC C165948; KiCad `Connector:USB_C_Receptacle_USB2.0_16P`, footprint `Connector_USB:USB_C_Receptacle_HRO_TYPE-C-31-M-12`)

| Connector pin(s) | Net | Notes |
|---|---|---|
| A4, A9, B4, B9 (VBUS) | VBUS | all four tied at the connector |
| A1, A12, B1, B12 (GND) | GND | all four |
| A5 (CC1) | CC1 | R1 5.1 kΩ to GND |
| B5 (CC2) | CC2 | R2 5.1 kΩ to GND; **separate resistor per CC pin**, never one shared |
| A6 + B6 (D+) | USB_DP | joined at the connector, stub < 2 mm |
| A7 + B7 (D−) | USB_DM | joined at the connector |
| A8, B8 (SBU1/2) | NC | unused, explicit NC marks |
| SH (4 THT tabs) | GND | direct (Q9). The KiCad footprint has 4 `thru_hole` shield pads and 2 NPTH locating holes - an SMT part with THT tabs; verified in the installed `.kicad_mod`. |

Rd: a UFP/sink presents 5.1 kΩ on each CC to GND; with a plain USB-A-to-C or default source this yields default USB
power (500 mA, USB 2.0) *(from knowledge; search summaries: Rd 5.1 kΩ ±20 % in the USB spec, ±10 % in TI/NXP
controller datasheets; 1 % resistors satisfy both)*. VCONN not needed (no e-marker). Both KiCad's pad names
(`A6`, `B6`, ...) and EasyEDA's footprint (`USB-C_SMD-TYPE-C-31-M-12_1`) differ in numbering, so PR-GEO must align by pad position.

### 5.2 ESD: USBLC6-2SC6 (ST, C7519; alternates C2687116/C2827654 cheaper clones)

Pins: 1 and 6 = I/O1 (same line, flow-through), 3 and 4 = I/O2, 2 = GND, 5 = VBUS (KiCad symbol and USBLC6 DS figure 1 agree).
Wire: connector side `USB_DP` -> pin 1, pin 6 -> R9 (flow-through means the signal passes the pads, not a stub); `USB_DM` -> pin 3, pin 4 -> R10.
Pin 5 to VBUS (raw, before F1), pin 2 to GND by a short wide connection. Place within 5 mm of J1; ST: "the track from data
lines to I/O pins, from VCC to VBUS pin and from GND plane to GND pin must be as short as possible" (USBLC6 DS §2.3).
Data specs: VBR >= 6 V, Ci/o-GND 2.5 typ / 3.5 pF max (negligible at 12 Mbps), IEC 61000-4-2 ±15 kV contact and air
(USBLC6 DS, Absolute ratings/Electrical characteristics). Residual risk accepted (waiver W-5): the clamp is 17 V at 1 A
(VCL), above the S3 pin's 3.6 V ratings for sub-ns transients, as on every USB devkit; the series 22 Ω helps.

Series R9/R10 22 Ω: "reserve series resistors (initial value can be 22/33 Ω) and capacitors to ground on the traces",
close to the chip (HW checklist, "USB"). Fitted as 22 Ω, no ground capacitors (they would slow a 4 ns edge; not fitted, no footprint needed).

### 5.3 Differential routing: 2-layer vs 4-layer

Requirement sources: Espressif "Maintain a differential pair impedance of 90 Ω with ±10 % tolerance", parallel equal
length, minimise vias, continuous reference plane, ground copper around (HW layout, "USB Layout"). USB 2.0 requires 90 Ω ±15 %
for the cable/differential line (Cadence summary of the spec; I did not read the USB-IF spec).

Stackup assumption: JLCPCB 2-layer 1.6 mm board, dielectric between layers ≈ 1.5 mm *(assumed; fab-specific, the
number to confirm is in JLCPCB's stackup page)*, εr ≈ 4.5, 35 µm copper. IPC-2141 microstrip / edge-coupled
approximation (own calculation, valid for w/h 0.1-2, accurate to ~±10 %):

| Pair (w / gap) over a 1.5 mm dielectric | Zdiff |
|---|---|
| 0.25 / 0.20 mm | ~151 Ω |
| 0.30 / 0.20 mm | ~144 Ω |
| 0.40 / 0.20 mm | ~134 Ω |
| 0.50 / 0.20 mm | ~125 Ω |
| 1.00 / 0.30 mm | ~103 Ω |
| **1.40 / 0.30 mm** | **~89 Ω** (90 Ω target) |
| 4-layer, 0.2 mm prepreg: 0.25 / 0.20 mm | ~95 Ω |
| Single-ended 50 Ω over 1.5 mm | w ≈ 2.8 mm |

So a true 90 Ω pair on 2 layers needs ~1.4 mm traces 0.3 mm apart (3.1 mm wide pair): impossible at the 0.5-mm
pitch USB-C pads and the 1.27-mm pitch module pads, only possible mid-route. The practical 2-layer pair
(0.3-0.4 / 0.2 mm) is ~135-145 Ω, i.e. ~50 % above target (reflection coefficient ≈ 0.2). JLCPCB offers controlled
impedance only on multilayer orders *(from knowledge; not re-verified)*.

Why USB **full speed** tolerates this on this board:
1. FS signalling is 12 Mbps with 4-20 ns edge rates (Cadence summary of the USB 2.0 table; skew budget 1-5 ns).
2. Propagation on FR-4 microstrip ≈ 6.1 ps/mm (εeff ≈ 3.3). The longest the pair can be on this floor plan is
   ≈ 35 mm = 0.21 ns one way, 0.43 ns round trip, ≈ 5 % of the 4 ns minimum edge. The usual "electrically long"
   threshold (t_rise / 6 -> ≈ 110 mm) is 3x longer than the pair, so the mismatch cannot produce meaningful ringing.
3. Both S3 USB controllers are FS-only (WROOM-1 DS §5.2.1.7 "USB 2.0 OTG Full-Speed", §5.2.1.8 "USB Serial/JTAG ... full-speed").
4. Native FS devices without any controlled impedance are common practice; Espressif's 90 Ω is a general
   recommendation covering HS-capable parts.

Decision: **2 layers**, with these hard constraints (checked at P4): pair ≤ 40 mm total, ≤ 1 mm length
difference, no vias, no stubs > 2 mm, ground plane unbroken beneath it, ground copper at ≥ 0.5 mm either side
stitched with vias, 22 Ω resistors at the module end. **Escalation to 4 layers (JLC04161-class, inner GND +
power)** if any of: (a) the router cannot give 0 unconnected with the bottom plane unbroken under the pair and
under the module; (b) a P4 check shows more than 3 stitched cuts in the bottom plane; (c) the owner requires
true 90 Ω. The routability pressure is the 25-GPIO breakout from a 1.27 mm-pitch module, not USB. Espressif's own
guide prefers 4 layers for chips and says "there are no official two-layer modules" in the chip-down stackup
discussion (HW layout, "Ground and Stackup"); this board uses a module, which Espressif's DevKit-class
designs are, and the 2-layer alternative it lists (Layer 2 = complete ground plane) is what is adopted.

### 5.4 Remaining USB decisions

- Series 22 Ω (Espressif range 22/33 Ω) fitted; **no** ground capacitors.
- No external D+ pull-up by default: the S3 integrates the FS device pull-up; the Espressif note about an external
  pull-up is "if you need a stable initial state" (HW checklist, "USB"). It would signal a device attach before
  firmware runs. Flagged as Q4; ship without.
- Bus-powered device: no VBUS-sense divider on a GPIO (ESP-IDF needs it only for self-powered devices *(from knowledge)*).
- USB inrush: VBUS-side C1 4.7 µF + C2 0.1 µF = 4.8 µF; 22 µF behind the LDO is charged through the LDO. USB 2.0
  limits bulk capacitance seen at attach *(from knowledge: §7.2.4.1, 10 µF without limiting, charge 50 µC)*;
  C3 22 µF · 3.3 V = 73 µC is above 50 µC, accepted risk R-6 (below) like every devkit.

## 6. Decoupling plan

Espressif for the module: "ESD protection diode and at least 10 µF capacitor at the main power entrance"; Figure 9-1
shows C1 22 µF and C3 0.1 µF at the module's 3V3 supply and R1/C2 on EN (WROOM-1 DS §9 p.41; HW checklist,
"Power Supply", "Chip Power-up and Reset Timing"). The VDD3P3/VDD_SPI/VDDA pins (digital 0.1 µF, RF LC filter, 1 µF
VDD_SPI) are *inside* the module; the board decouples the module's single 3V3 pin.

| Ref | Value / part | Net | Placement rule | Source |
|---|---|---|---|---|
| C1 | 4.7 µF X5R 0603 16 V (C19666) | VBUS_F -> GND | <= 3 mm from U2 pin 3 | LDL1117 DS §6.2: 1 µF input capacitor minimum, "as close as possible to the input pin"; 4.7 µF keeps VBUS-side capacitance low (§5.4) |
| C2 | 100 nF X7R 0603 (C14663) | VBUS_F -> GND | next to C1 | HF bypass |
| C3 | 22 µF X5R 0805 25 V (C45783) | 3V3 -> GND | <= 5 mm from U2 pin 2; also serves as the >=10 µF "main power entrance" capacitor | LDL1117 DS §6.2 (ceramic Cout, 4.7 µF suggested; verify the 22 µF point in Figure 20) + HW checklist (>= 10 µF) |
| C4 | 100 nF X7R 0603 (C14663) | 3V3 -> GND at U1 pin 2 | <= 3 mm from pin 2, ground via at its pad | WROOM-1 DS Figure 9-1 (C3 0.1 µF) |
| C5 | 1 µF X5R 0603 (C15849) | EN -> GND | <= 10 mm from pin 3 | WROOM-1 DS §9 (10 kΩ / 1 µF) |
| C6 | 100 nF X7R 0603 (C14663) | 3V3 -> GND at U3 pin 5 | <= 2 mm from U3 | SHT3x DS §3.1: "decoupled with a 100 nF capacitor ... as close as possible" |
| (module) | 3V3 trace, 0.5 mm min | | main 3.3 V trace >= 25 mil in Espressif's chip guide; 0.5 mm carries 0.5 A at ≈ 10 K rise (1 oz) - verified by the P2/P4 current rule | HW layout, "Power Supply Layout" |

Ceramic bias derating: X5R 4.7 µF 16 V at 5 V keeps ~2.5-3 µF (>= 1 µF required); 22 µF 25 V at 3.3 V keeps ~15 µF (>= 10 µF).
*Estimates from typical MLCC DC-bias curves, not from the Samsung data for these exact parts; P1 should record them as unverified.*

Module EPAD (GND, pin 41): "not a must, however, it can optimize thermal performance. If you choose to solder it,
please apply the correct amount of soldering paste" (WROOM-1 DS §9). Use a window-paned paste aperture (~50 %) and a
via array to the bottom plane (HW layout: EPAD vias; the guide asks for >= 9 for the chip). P5 must verify the stencil aperture.

## 7. Layout constraints P3/P4 must carry (summary)

1. **Antenna**: module at the top edge, keep-out rule area on all layers (brief §6); no ground pour inside it;
   the bottom GND plane stops at the keep-out boundary. Header pad 1 below the boundary. KiCad's own footprint draws
   the keep-out on `F.CrtYd`/`Cmts.User` - a *courtyard*, not a DRC rule area, so the platform needs its own check (R7/R12/G gap).
2. **Module placement**: >= 15 mm free space around the antenna in any enclosure (documented, not checked).
3. **USB**: §5.3 constraints; ESD at the connector; series R at the module.
4. **LDO**: tab pour >= 2 cm²; input/output caps per §6; the 3V3 output pour reaches the module on the top layer.
5. **EN/BOOT**: R3/C5 near U1; no routing of fast signals under SW1/SW2.
6. **I2C**: Qwiic and sensor on the same two nets; pull-ups near the module; keep SDA/SCL off the USB pair.
7. **GND**: bottom layer is a plane; stitching vias every ~5 mm along the board edge outside the keep-out; thermal vias under U1 EPAD and U2 tab are separate nets (EPAD GND, tab VOUT).
8. **Fiducials/tooling**: not needed for JLCPCB standard PCBA (rails added by the fab) - confirm at P5.

## 8. Candidate BOM

Stock method (**2026-10-27**): jlcsearch (`jlcsearch.tscircuit.com`) has *no* stock for resistors/capacitors/LEDs
(tables return `stock: null`) and does not list the ESP32-S3 modules at all (they appear only through its EasyEDA endpoint). Stock and class
were therefore read from two undocumented JSON endpoints, by **exact LCSC id**, checking the returned MPN against intent:
JLCPCB parts search `POST https://jlcpcb.com/api/overseas-pcb-order/v1/shoppingCart/smtGood/selectSmtComponentList`
(`componentLibraryType` `base` = basic, `expand` = extended; `stockCount` = JLCPCB assembly stock) and the LCSC product endpoint
`GET https://wmsc.lcsc.com/ftps/wm/product/detail?productCode=Cxxxxx` (retail stock `stockNumber`, `pdfUrl`). Neither is documented; both
worked unauthenticated at 0.6 s spacing. Manufacturer strings and basic/extended flags were cross-read from the EasyEDA JSON
(`/api/easyeda_components/Cxxxxx`). Price = first-tier JLCPCB unit price. For passives the LCSC figure is often 0 while JLCPCB stock is millions: **JLCPCB stock is the one
that matters for PCBA.** Registry id column is a *proposed* P1 slug.

### 8.1 Orderable parts (23 registry ids + 1 mechanical)

| Refs | Function | Registry id (proposed) | MPN | LCSC | Class | Pkg | JLC stock | LCSC stock | $ (tier 1) | P3 block |
|---|---|---|---|---|---|---|---|---|---|---|
| U1 | MCU module | `esp32-s3-wroom-1-n8` | ESP32-S3-WROOM-1-N8 (Espressif) | **C2913198** | extended | SMD 25.5x18 mm | 2,708 | 1,765 | 4.93 | `esp32s3_module` |
| U2 | 3V3 LDO | `ldl1117s33r-sot223` | LDL1117S33R (ST) | **C435835** | extended | SOT-223-4 | 70,549 | 68,870 | 0.50 | `ldo_3v3` |
| U3 | Temp/humidity | `sht30-dis-b-dfn8` | SHT30-DIS-B2.5KS (Sensirion) | **C77361** | extended | DFN-8-EP 2.5x2.5 | 19,679 | (n/a on LCSC endpoint) | 2.81 | `i2c_sensor` |
| U4 | USB ESD | `usblc6-2sc6` | USBLC6-2SC6 (ST) | **C7519** | extended | SOT-23-6L | 43,868 | 39,515 | 0.18 | `usb_c_data` |
| J1 | USB-C 16P | `hro-type-c-31-m-12` | TYPE-C-31-M-12 (HRO) | **C165948** | extended | SMD + 4 THT tabs | 302,781 | 284,095 | 0.19 | `usb_c_data` / `power_input` |
| F1 | PTC 1.1 A | `ruilon-smd1206p110tf` | SMD1206P110TF (Ruilon) | **C20801** | extended | 1206 | 5,533 | 5,530 | 0.08 | `power_input` |
| D1 | VBUS TVS | `mdd-smaj5-0a` | SMAJ5.0A (MDD) | **C113952** | extended | SMA (DO-214AC) | 499,861 | 488,180 | 0.04 | `power_input` |
| J5 | Qwiic JST-SH 4P | `jst-sm04b-srss-tb` | SM04B-SRSS-TB(LF)(SN) (JST) | **C160404** | extended | SMD 1.0 mm RA | 71,934 | 60,770 | 0.21 | `i2c_header` |
| J2, J3 | 1x16 header | `pz254v-11-16p` | PZ254V-11-16P (XFCN) | **C22465876** | extended (THT) | 2.54 mm | 6,018 | 5,955 | 0.10 | `gpio_header` |
| J4 | 1x3 header | `pz254v-11-03p` | PZ254V-11-03P | **C2937625** | extended (THT) | 2.54 mm | 780,481 | 635,750 | 0.02 | `uart_header` |
| SW1, SW2 | tact switch | `ts-1187a-b-a-b` | TS-1187A-B-A-B | **C318884** | **basic** | SMD 5.1x5.1 | 1,165,510 | 891,660 | 0.02 | `button` (BOOT, RESET) |
| LED1 | power LED red | `ncd0805r1` | NCD0805R1 | **C84256** | **basic** | 0805 | 2,881,083 | 1,587,350 | 0.01 | `led_indicator` |
| LED2 | status LED yellow | `kt-0805y` | KT-0805Y (Vf 1.8-2.4 V) | **C2296** | **basic** | 0805 | 672,773 | 417,000 | 0.01 | `led_indicator` |
| R1, R2 | CC Rd 5.1 kΩ 1 % | `res-0603` (generic, value 5k1) | 0603WAF5101T5E | **C23186** | **basic** | 0603 | 21,825,937 | 16,734,700 | 0.0015 | `usb_c_data` |
| R3, R4 | 10 kΩ | `res-0603` (10k) | 0603WAF1002T5E | **C25804** | **basic** | 0603 | 38,788,340 | 0 | 0.0018 | `esp32s3_module` |
| R5, R6 | 2.2 kΩ | `res-0603` (2k2) | 0603WAF2201T5E | **C4190** | **basic** | 0603 | 5,834,076 | 3,161,600 | 0.0018 | `i2c_header` |
| R7 | 1 kΩ | `res-0603` (1k) | 0603WAF1001T5E | **C21190** | **basic** | 0603 | 33,616,714 | 7,518,700 | 0.0017 | `led_indicator` |
| R8, R11 | 470 Ω | `res-0603` (470R) | 0603WAF4700T5E | **C23179** | **basic** | 0603 | 4,895,903 | 2,224,500 | 0.0023 | `led_indicator`, `uart_header` |
| R9, R10 | 22 Ω | `res-0603` (22R) | 0603WAF220JT5E | **C23345** | **basic** | 0603 | 6,975,252 | 3,304,000 | 0.0017 | `usb_c_data` |
| C2, C4, C6 | 100 nF | `cap-0603` (100n) | CC0603KRX7R9BB104 | **C14663** | **basic** | 0603 | 41,550,549 | 0 | 0.0087 | various |
| C5 | 1 µF | `cap-0603` (1u) | CL10A105KB8NNNC | **C15849** | **basic** | 0603 | 13,107,434 | 600,100 | 0.0146 | `esp32s3_module` |
| C1 | 4.7 µF | `cap-0603` (4u7) | CL10A475KO8NNNC | **C19666** | **basic** | 0603 | 3,371,633 | 607,090 | 0.0169 | `ldo_3v3` |
| C3 | 22 µF | `cap-0805` (22u) | CL21A226MAQNNNE | **C45783** | **basic** | 0805 | 4,051,017 | 341,160 | 0.1917 | `ldo_3v3` |
| H1, H2 | M2.5 NPTH | `mounting-hole-m2_5` (mechanical, `bom:false`) | - | - | - | 2.7 mm drill | - | - | - | (mechanical) |

Counts: **29 SMT parts** assembled by JLCPCB (U1-U4, J1, J5, F1, D1, SW1-2, LED1-2, R1-R11, C1-C6); **3 headers**
by hand (J2, J3, J4); 8 distinct extended SMT parts (+2 extended headers), 13 distinct basic. Parts-only cost ≈ **$9.50**
(sum of the tier-1 prices, which for U2 is the 1-9 quantity price: the jlcsearch tiered price was $0.21, JLCPCB's first tier is $0.50).

Verified/other: the ESP32-S3-WROOM-1-N8 MPN is confirmed on LCSC (`productModel`) and JLCPCB (`componentModelEn`) and the EasyEDA record
(`Manufacturer Part`), all "ESP32-S3-WROOM-1-N8", class Extended. All other ids were fetched by exact id and the returned MPN
is the intended one. C25804 and C14663 show LCSC stock 0 but JLCPCB stock in the tens of millions (a basic-library stocking artefact).

### 8.2 Alternates considered (not in the BOM)

| Role | Part | LCSC | Class | JLC stock | Why not |
|---|---|---|---|---|---|
| LDO | AMS1117-3.3 | C6186 | basic | 1,898,639 | dropout 1.3-1.4 V at 1 A, low-VBUS corner fails; ESR constraint (§2.3). Fallback (Q2). |
| LDO | AP2112K-3.3 | C51118 | extended | n/a | 600 mA max, SOT-23-5 θJA far too high for 0.85 W |
| LDO | ME6211C33M5G-N | C82942 | extended | n/a | 500 mA, SOT-23-5 thermal |
| Module | ESP32-S3-WROOM-1-N16R8 | C2913202 | extended | 21,887 (more stock) | octal PSRAM occupies GPIO35-37 (Table 3-1 note b); $5.35 |
| Module | ESP32-S3-WROOM-1-N4 | C2913197 | extended | 2,376 | 4 MB flash only; LCSC retail stock 0 |
| Sensor | AHT20 | C2757850 | extended | 39,238 | $0.80, but vendor variants (AHT20, AHT20-F...) with different pinout data; SHT30 has a clean Sensirion datasheet and an ADDR/ALERT/nRESET set that exercises R9 rules (Q6) |
| USB ESD | USBLC6-2SC6 clones | C2687116, C2827654 | extended | 126,813; 111,438 | $0.045 vs $0.18; genuine ST part kept for the datasheet-traceable pinout |
| LED green | KT-0603G | C12624 | extended | 435,859 | extended; Vf ~3.1 V leaves no headroom at 3.3 V |

## 9. Planned P3 block map

Plan P3 first block set vs. this board (PLATFORM_PLAN §5):

| P3 block (plan list) | Used here | Parts | New block needed? |
|---|---|---|---|
| power input (connector + fuse + reverse protection + TVS) | **yes**, without the reverse-protection element (not applicable to a keyed USB-C source) | J1 power pins, F1, D1, C1, C2 | - |
| USB-C 2.0 data (CC resistors, ESD, 90 Ω pair) | **yes**, 2-layer variant (§5.3) | J1 data pins, R1, R2, U4, R9, R10 | - |
| LDO 3V3 | **yes** | U2, C3 | - |
| ESP32-S3 module minimal system (EN RC, boot strap, antenna keepout) | **yes** | U1, R3, R4, C4, C5, SW1, SW2 | - |
| button + debounce | yes (BOOT and RESET; the RESET debounce is C5) | SW1, SW2 | - |
| LED indicator | yes (x2) | LED1+R7, LED2+R8 | - |
| I2C header + pull-ups | yes | R5, R6, J5, U3, C6 | sensor-specific part `i2c_sensor` (SHT30: ADDR, ALERT, nRESET, R handling) |
| buck module, AVR, MOSFET+flyback, crystal | not used | - | - |
| - | **new**: `gpio_header` (2.54 mm breakout with power/ground placement rule) | J2, J3 | yes |
| - | **new**: `uart_header` (TX series R, RX, GND) | J4, R11 | yes |

28 of 32 parts (87.5 %) come from blocks already on the plan's list (P3 exit target: >= 80 %). The other four
(J2, J3, J4, R11) need the two small new blocks above, which would bring it to 100 %. The mounting holes H1/H2 are
board-level mechanical records, not parts.

## 10. Risks and open questions

### 10.1 Risks (ranked)

| # | Risk | Plan ref | Where it bites | Mitigation / gate |
|---|---|---|---|---|
| R-1 | **Antenna keep-out not machine-checked.** Espressif's text gives no numbers, only a figure; KiCad's footprint draws it as a courtyard | R7, R12, §3 gap G | A copper pour or track near the antenna detunes it: board "works" on the bench with poor range | P4 rule-area check; numbers taken from Espressif's land-pattern source file; human check line in SIGNOFF |
| R-2 | **LDO thermal at sustained TX** (0.85 W at 5.25 V in a 120 °C/W part) | R11 | Brown-out/reset under heavy Wi-Fi at warm ambient | §2.3: >= 2 cm² tab copper; P2 thermal rule with duty note; buck as documented alternative |
| R-3 | **Library vs real part**: HRO USB-C has 16 signal pads, 4 THT tabs, 2 NPTH holes; LDL1117 tab is VOUT, KiCad `SOT-223-3_TabPin2` has *two* pads named "2"; module land pattern | R1, R3 | A GND pour under the LDO tab shorts VOUT | P1 crosscheck with multiset pads; PR-GEO vs EasyEDA by pad position; human sign line |
| R-4 | **Strapping** (GPIO45/46/3 left NC; GPIO0 pull-up) | R8 | Wrong VDD_SPI level or accidental download mode | §4; P3 module block rules; mutation M-strap |
| R-5 | **Routability of 25 GPIO on 2 layers** with an unbroken bottom plane | R15 | Router fails or cuts the ground plane under the USB pair | P4 escalation to 4 layers (§5.3); fallback is dropping unused header pins (e.g. keep 16) |
| R-6 | **USB budget closes at exactly 500 mA and attach inrush** (73 µC on 3V3, 24 µC on VBUS vs ~50 µC guideline) | R10 | Host current-limit trips on attach with a strict port | Accept (all devkits do); PTC R helps; documented; reduce C3 to 10 µF if a host misbehaves |
| R-7 | **Stock single-sourcing** of the module: 2,708 at JLCPCB, 1,765 at LCSC; N16R8 has 8x more stock | R14 | Order of 100 boards uses ~4 % of stock; a surge could stock out | PR-STOCK at release (24 h); N16R8 is a documented alternate that costs GPIO35-37 |
| R-8 | **CPL rotation/origin** for the module (pin 1 at a corner, EPAD), USB-C (THT tabs), SOT-223 tab, SOT-23-6, DFN-8 | R4 | Parts placed rotated or shifted | P5 rotation DB + rendered CPL overlay for these 7 parts |
| R-9 | **Sensor self-heating** by LDO/module | - | Temperature reads high by several K | Placement >= 12 mm from U2, optional slot (Q11); not a safety issue |
| R-10 | **Residual ESD**: USBLC6 clamp (17 V at 1 A) > S3 pin rating (3.6 V) for the first nanoseconds | R10 | Rare latent damage under severe ESD | Waiver W-5; 22 Ω series; same as Espressif devkits |
| R-11 | **Stock-lookup tooling is undocumented**: the two JSON endpoints used here can change; jlcsearch has no passive stock and omits ESP32 modules | R14 | Parts stage silently loses stock data | Record both endpoints in AGENT_NOTES §E; parts stage must WARN "not judged" when absent |
| R-12 | **Dimensions not extracted**: antenna-area mm, 22 µF stability (LDL1117 Fig. 20), PTC derating at temperature, JLCPCB stackup thickness, NCD0805R1 Vf; WROOM-1 DS Table 4-4 (VDD_SPI) came out of the PDF text partly garbled, the GPIO45 = 0 -> 3.3 V mapping is read from it and from memory of the chip datasheet | R3 | A number in this plan is an estimate, flagged where used | Listed in P1 `unverified_dims` |

### 10.2 Expected waivers (`waivers.json`, rule R10)

| Id | Scope | Reason |
|---|---|---|
| W-1 | J2/J3 GPIO | Dev-header GPIOs are unprotected by design; owner's external circuits are the owner's responsibility |
| W-2 | J5 Qwiic SDA/SCL | board-to-board inside an enclosure; no ESD part, no series R |
| W-3 | J4 UART | same; TX has a series R only for EMI |
| W-4 | No reverse-polarity element on VBUS | the only entry is a keyed USB-C source; J3.1 "5V" is an output only |
| W-5 | USB D± clamp above pin abs-max for transients | see R-10 |
| W-6 | LDO peak dissipation above the 120 °C/W limit at 40 °C | Only for 100 % TX duty at 5.25 V; average case passes (§2.3) |

### 10.3 Open questions (each with the default this plan already assumes)

| # | Question | Default | Consequence of the other answer |
|---|---|---|---|
| Q1 | Module: N8 or something else? | **N8** (C2913198) | N16R8 (C2913202): +$0.42, 16 MB flash + 8 MB PSRAM, loses IO35-37 (25 -> 22 GPIO) |
| Q2 | LDO: LDL1117S33R (extended) or AMS1117 (basic)? | **LDL1117S33R** | AMS1117: -1 extended fee but fails the 4.4 V corner; needs a tantalum or low-ESR-verified output cap |
| Q3 | 2 or 4 layers? | **2 layers**, escalate on R-5 criteria | 4 layers: +cost/lead time, real 90 Ω, easier routing; P3/P4 variant needed |
| Q4 | External D+ pull-up and series R values? | **No pull-up, 22 Ω series, no ground caps** | Adding a pull-up changes attach behaviour at power-up |
| Q5 | Headers hand-soldered (default) or JLCPCB THT assembly? | **Hand**, excluded from JLC BOM/CPL | JLC THT: more extended fees, orientation risk; P5 BOM generator needs a per-part `hand` flag either way |
| Q6 | SHT30 or AHT20? | **SHT30-DIS-B** ($2.81) | AHT20 ($0.80) is cheaper; datasheet traceability weaker |
| Q7 | Fuse: polyfuse, or an e-fuse IC? | **Polyfuse + TVS** | e-fuse adds a part and a stock risk; better current limiting |
| Q8 | Surface finish | **ENIG** | HASL lead-free: cheaper, slightly worse pad flatness for DFN/USB-C |
| Q9 | USB shield to GND | **Direct** | RC (1 MΩ \|\| 4.7 nF) is quieter for EMC at +2 parts |
| Q10 | Antenna end: flush with the edge (default) or overhanging beyond it? | **Flush + keep-out** | Overhang follows Espressif's "outside the base board if possible" but the antenna end is fragile and the pick-and-place/fab may refuse |
| Q11 | Slot to isolate the sensor? | **No** | A 1 mm routed slot around U3 improves accuracy |
| Q12 | I2C pull-up: 2.2 kΩ or 4.7 kΩ? | **2.2 kΩ** (rise time 0.8473·2.2 kΩ·100 pF = 186 ns < 300 ns Fast-mode limit *(NXP UM10204 Table 10, from knowledge)*; min R = (3.3−0.4)/3 mA = 967 Ω) | 4.7 kΩ: 398 ns, only fine for 100 kHz |
| Q13 | Bring-up firmware scope | **P6 deliverable**: blink + SHT30 read + USB CDC, built with PlatformIO/ESP-IDF; `pinmap` reports "no firmware" until then | No Wokwi live simulation either way (no custom-board model) |
