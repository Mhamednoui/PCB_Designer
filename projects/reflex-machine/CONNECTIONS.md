# reflex-machine - every connection, in plain words

_Generated 2026-09-18 15:55 by `tools/boardgen/make_connections.py` from the real board copper (`reflex-machine.kicad_pcb`), with pin names from the schematic. Regenerate: `python pipeline.py reflex-machine --only connections`._

## How to use this file

You don't need to read the PCB. Each part below lists its pins and where each pin's copper goes.

1. Start with **Check these first** - parts where a wrong pin order would really matter.
2. For each, open the datasheet picture (or look at your real part) and confirm the pin names match: e.g. a MOSFET's pin 1 really is G (gate).
3. When the board arrives, use a multimeter in beep mode: two pins listed as connected must beep.
   Two pins that are NOT listed together must not beep.

## Automatic cross-check

Every pin on the board copper goes to the same net as in the schematic: **433 pins checked, 0 differences.**

## Check these first - parts not from KiCad's standard library

### A1 - Arduino Mega 2560 R3

plug-in board · footprint `arduino-library:Arduino_Mega2560_R3_Shield` · Shield for Arduino Mega 2560 R3

> **Not from KiCad's standard library** (project library `arduino-library` - drawn here or downloaded). Nobody at KiCad has checked it: compare every pin below with a photo or the pinout of YOUR real part.

| Pin | Name | Goes to |
|---|---|---|
| 3V3 | 3.3V | **+3V3** → J16 pin 3 (Pin 3) |
| 5V1 | 5V | **+5V** - 5 V supply, shared with 16 other pins |
| 5V2 | SPI 5V | *not connected (free pin)* |
| 5V3 | 5V | **+5V** - 5 V supply, shared with 16 other pins |
| 5V4 | 5V | **+5V** - 5 V supply, shared with 16 other pins |
| A0 |  | **SEG_DATA** → U3 pin 14 (SER) |
| A1 |  | **SEG_LATCH** → U3 pin 12 (RCLK) |
| A10 |  | *not connected (free pin)* |
| A11 |  | *not connected (free pin)* |
| A12 |  | *not connected (free pin)* |
| A13 |  | *not connected (free pin)* |
| A14 |  | *not connected (free pin)* |
| A15 |  | *not connected (free pin)* |
| A2 |  | **SEG_CLOCK** → U3 pin 11 (SRCLK) |
| A3 |  | **LED1** → R51 pin 1 |
| A4 |  | **LED2** → R52 pin 1 |
| A5 |  | **LED3** → R53 pin 1 |
| A6 |  | **LED4** → R54 pin 1 |
| A7 |  | **SPARE_A7** → J16 pin 15 (Pin 15) |
| A8 |  | **SPARE_A8** → J16 pin 16 (Pin 16) |
| A9 |  | *not connected (free pin)* |
| AREF |  | *not connected (free pin)* |
| D0 | D0/RX0 | *not connected (free pin)* |
| D1 | D1/TX0 | *not connected (free pin)* |
| D10 |  | **MAG7_PWM** → R17 pin 1 |
| D11 |  | **MAG8_PWM** → R18 pin 1 |
| D12 |  | **MAG9_PWM** → R19 pin 1 |
| D13 |  | **SPARE_D13** → J16 pin 10 (Pin 10) |
| D14 | D14/TX3 | **SPARE_TX3** → J16 pin 7 (Pin 7) |
| D15 | D15/RX3 | **SPARE_RX3** → J16 pin 8 (Pin 8) |
| D16 | D16/TX2 | *not connected (free pin)* |
| D17 | D17/RX2 | *not connected (free pin)* |
| D18 | D18/TX1 | **MEGA_TX1** → R62 pin 1 |
| D19 | D19/RX1 | **ESP_TX2** → A2 pin 24 (TX2/IO17) |
| D2 | D2 INT0 | **COIN_IN** → C8 pin 1, R42 pin 2, U2 pin 4 |
| D20 | D20/SDA | **I2C_SDA** → J16 pin 5 (Pin 5) |
| D21 | D21/SCL | **I2C_SCL** → J16 pin 6 (Pin 6) |
| D22 |  | **BTN_S1** → C9 pin 1, R43 pin 2, R47 pin 2 |
| D23 |  | *not connected (free pin)* |
| D24 |  | **BTN_S2** → C10 pin 1, R44 pin 2, R48 pin 2 |
| D25 |  | *not connected (free pin)* |
| D26 |  | **BTN_S3** → C11 pin 1, R45 pin 2, R49 pin 2 |
| D27 |  | *not connected (free pin)* |
| D28 |  | **BTN_RST** → C12 pin 1, R46 pin 2, R50 pin 2 |
| D29 |  | *not connected (free pin)* |
| D3 | D3 INT1 | **MAG1_PWM** → R11 pin 1 |
| D30 |  | **SPARE_D30** → J16 pin 11 (Pin 11) |
| D31 |  | **SPARE_D31** → J16 pin 12 (Pin 12) |
| D32 |  | **SPARE_D32** → J16 pin 13 (Pin 13) |
| D33 |  | **SPARE_D33** → J16 pin 14 (Pin 14) |
| D34 |  | *not connected (free pin)* |
| D35 |  | *not connected (free pin)* |
| D36 |  | *not connected (free pin)* |
| D37 |  | *not connected (free pin)* |
| D38 |  | *not connected (free pin)* |
| D39 |  | *not connected (free pin)* |
| D4 |  | **SPARE_D4** → J16 pin 9 (Pin 9) |
| D40 |  | *not connected (free pin)* |
| D41 |  | *not connected (free pin)* |
| D42 |  | *not connected (free pin)* |
| D43 |  | *not connected (free pin)* |
| D44 |  | **MAG10_PWM** → R20 pin 1 |
| D45 |  | *not connected (free pin)* |
| D46 |  | *not connected (free pin)* |
| D47 |  | *not connected (free pin)* |
| D48 |  | *not connected (free pin)* |
| D49 |  | *not connected (free pin)* |
| D5 |  | **MAG2_PWM** → R12 pin 1 |
| D50 | D50 MISO | **SPARE_MISO** → J16 pin 18 (Pin 18) |
| D51 | D51 MOSI | **SPARE_MOSI** → J16 pin 19 (Pin 19) |
| D52 | D52 SCK | **SPARE_SCK** → J16 pin 17 (Pin 17) |
| D53 | D53 CS | **SPARE_CS** → J16 pin 20 (Pin 20) |
| D6 |  | **MAG3_PWM** → R13 pin 1 |
| D7 |  | **MAG4_PWM** → R14 pin 1 |
| D8 |  | **MAG5_PWM** → R15 pin 1 |
| D9 |  | **MAG6_PWM** → R16 pin 1 |
| GND1 | GND | **GND** - ground, shared with 59 other pins |
| GND2 | GND | **GND** - ground, shared with 59 other pins |
| GND3 | GND | **GND** - ground, shared with 59 other pins |
| GND4 | SPI GND | *not connected (free pin)* |
| GND5 | GND | **GND** - ground, shared with 59 other pins |
| GND6 | GND | **GND** - ground, shared with 59 other pins |
| IORF | IOREF | *not connected (free pin)* |
| MISO | SPI MISO | *not connected (free pin)* |
| MOSI | SPI MOSI | *not connected (free pin)* |
| RST1 | RESET | *not connected (free pin)* |
| RST2 | SPI RESET | *not connected (free pin)* |
| SCK | SPI SCK | *not connected (free pin)* |
| SCL |  | *not connected (free pin)* |
| SDA |  | *not connected (free pin)* |
| VIN |  | *not connected (free pin)* |

### A2 - ESP32 DevKit V1 (30 pin)

plug-in board · footprint `reflex:ESP32_DevKit_V1_30pin_Socket` · DOIT ESP32 DevKit V1 (WROOM-32), 30 pins, plugs into 2x 1x15 female headers 25.4mm apart

> **Not from KiCad's standard library** (project library `reflex` - drawn here or downloaded). Nobody at KiCad has checked it: compare every pin below with a photo or the pinout of YOUR real part.

| Pin | Name | Goes to |
|---|---|---|
| 1 | EN | *not connected (free pin)* |
| 2 | VP/IO36 | *not connected (free pin)* |
| 3 | VN/IO39 | *not connected (free pin)* |
| 4 | IO34 | *not connected (free pin)* |
| 5 | IO35 | *not connected (free pin)* |
| 6 | IO32 | **ESP_IO32** → J17 pin 6 (Pin 6) |
| 7 | IO33 | **ESP_IO33** → J17 pin 7 (Pin 7) |
| 8 | IO25 | **ESP_IO25** → J17 pin 3 (Pin 3) |
| 9 | IO26 | **ESP_IO26** → J17 pin 4 (Pin 4) |
| 10 | IO27 | **ESP_IO27** → J17 pin 5 (Pin 5) |
| 11 | IO14 | **ESP_IO14** → J17 pin 8 (Pin 8) |
| 12 | IO12 | *not connected (free pin)* |
| 13 | IO13 | *not connected (free pin)* |
| 14 | GND | **GND** - ground, shared with 59 other pins |
| 15 | VIN(5V) | **+5V** - 5 V supply, shared with 16 other pins |
| 16 | IO23 | *not connected (free pin)* |
| 17 | IO22 | *not connected (free pin)* |
| 18 | TX0/IO1 | *not connected (free pin)* |
| 19 | RX0/IO3 | *not connected (free pin)* |
| 20 | IO21 | *not connected (free pin)* |
| 21 | IO19 | *not connected (free pin)* |
| 22 | IO18 | *not connected (free pin)* |
| 23 | IO5 | *not connected (free pin)* |
| 24 | TX2/IO17 | **ESP_TX2** → A1 pin D19 (D19/RX1) |
| 25 | RX2/IO16 | **ESP_RX2** → R62 pin 2, R63 pin 1 |
| 26 | IO4 | *not connected (free pin)* |
| 27 | IO2 | *not connected (free pin)* |
| 28 | IO15 | *not connected (free pin)* |
| 29 | GND | **GND** - ground, shared with 59 other pins |
| 30 | 3V3 | **+3V3_ESP** → J17 pin 1 (Pin 1) |

## Check these next - transistors, ICs, modules

### Q1 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG1_G** → R11 pin 2, R21 pin 1 |
| 2 | D | **MAG1_OUT** → D11 pin 2 (A), J2 pin 2 (Pin 2), R31 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q2 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG2_G** → R12 pin 2, R22 pin 1 |
| 2 | D | **MAG2_OUT** → D12 pin 2 (A), J3 pin 2 (Pin 2), R32 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q3 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG3_G** → R13 pin 2, R23 pin 1 |
| 2 | D | **MAG3_OUT** → D13 pin 2 (A), J4 pin 2 (Pin 2), R33 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q4 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG4_G** → R14 pin 2, R24 pin 1 |
| 2 | D | **MAG4_OUT** → D14 pin 2 (A), J5 pin 2 (Pin 2), R34 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q5 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG5_G** → R15 pin 2, R25 pin 1 |
| 2 | D | **MAG5_OUT** → D15 pin 2 (A), J6 pin 2 (Pin 2), R35 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q6 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG6_G** → R16 pin 2, R26 pin 1 |
| 2 | D | **MAG6_OUT** → D16 pin 2 (A), J7 pin 2 (Pin 2), R36 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q7 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG7_G** → R17 pin 2, R27 pin 1 |
| 2 | D | **MAG7_OUT** → D17 pin 2 (A), J8 pin 2 (Pin 2), R37 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q8 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG8_G** → R18 pin 2, R28 pin 1 |
| 2 | D | **MAG8_OUT** → D18 pin 2 (A), J9 pin 2 (Pin 2), R38 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q9 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG9_G** → R19 pin 2, R29 pin 1 |
| 2 | D | **MAG9_OUT** → D19 pin 2 (A), J10 pin 2 (Pin 2), R39 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### Q10 - IRLZ44N

transistor · footprint `Package_TO_SOT_THT:TO-220-3_Vertical` · 47A Id, 55V Vds, 22mOhm Rds Single N-Channel HEXFET Power MOSFET, TO-220AB

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | G | **MAG10_G** → R20 pin 2, R30 pin 1 |
| 2 | D | **MAG10_OUT** → D20 pin 2 (A), J11 pin 2 (Pin 2), R40 pin 2 |
| 3 | S | **GND** - ground, shared with 59 other pins |

### U1 - 5V 2A module (K7805-2000R3)

IC / module · footprint `Converter_DCDC:Converter_DCDC_RECOM_R-78B-2.0_THT` · 1A Step-Down DC/DC-Regulator, 6.5-18V input, 5V fixed Output Voltage, LM78xx replacement, -40°C to +85°C, SIP3

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | IN | **+12V_REG** → C2 pin 1, C3 pin 1, D2 pin 1 (K) |
| 2 | GND | **GND** - ground, shared with 59 other pins |
| 3 | OUT | **+5V** - 5 V supply, shared with 16 other pins |

### U2 - PC817

IC / module · footprint `Package_DIP:DIP-4_W7.62mm` · DC Optocoupler, Vce 35V, CTR 50-300%, DIP-4

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **COIN_OPTO_A** → R41 pin 2 |
| 2 |  | **COIN_SIG** → J12 pin 3 (Pin 3) |
| 3 |  | **GND** - ground, shared with 59 other pins |
| 4 |  | **COIN_IN** → A1 pin D2 (D2 INT0), C8 pin 1, R42 pin 2 |

### U3 - 74HC595N

IC / module · footprint `Package_DIP:DIP-16_W7.62mm` · 8-bit serial in/out Shift Register 3-State Outputs

> Compare the pin order with the part's datasheet picture.

| Pin | Name | Goes to |
|---|---|---|
| 1 | QB | **SEG_QB** → R61 pin 1 |
| 2 | QC | **SEG_QC** → R60 pin 1 |
| 3 | QD | **SEG_QD** → R55 pin 1 |
| 4 | QE | **SEG_QE** → R59 pin 1 |
| 5 | QF | **SEG_QF** → R57 pin 1 |
| 6 | QG | **SEG_QG** → R56 pin 1 |
| 7 | QH | **SEG_QH** → R58 pin 1 |
| 8 | GND | **GND** - ground, shared with 59 other pins |
| 9 | QH' | *not connected (free pin)* |
| 10 | SRCLR (active-low) | **+5V** - 5 V supply, shared with 16 other pins |
| 11 | SRCLK | **SEG_CLOCK** → A1 pin A2 |
| 12 | RCLK | **SEG_LATCH** → A1 pin A1 |
| 13 | OE (active-low) | **GND** - ground, shared with 59 other pins |
| 14 | SER | **SEG_DATA** → A1 pin A0 |
| 15 | QA | *not connected (free pin)* |
| 16 | VCC | **+5V** - 5 V supply, shared with 16 other pins |

## Everything else

### C1 - 1000uF 25V

capacitor · footprint `Capacitor_THT:CP_Radial_D10.0mm_P5.00mm` · Polarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+12V** - 12 V supply, shared with 37 other pins |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C2 - 220uF 25V

capacitor · footprint `Capacitor_THT:CP_Radial_D6.3mm_P2.50mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+12V_REG** → C3 pin 1, D2 pin 1 (K), U1 pin 1 (IN) |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C3 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+12V_REG** → C2 pin 1, D2 pin 1 (K), U1 pin 1 (IN) |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C6 - 220uF 25V

capacitor · footprint `Capacitor_THT:CP_Radial_D6.3mm_P2.50mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C7 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C8 - 1nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **COIN_IN** → A1 pin D2 (D2 INT0), R42 pin 2, U2 pin 4 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C9 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_S1** → A1 pin D22, R43 pin 2, R47 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C10 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_S2** → A1 pin D24, R44 pin 2, R48 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C11 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_S3** → A1 pin D26, R45 pin 2, R49 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C12 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_RST** → A1 pin D28, R46 pin 2, R50 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### C13 - 100nF

capacitor · footprint `Capacitor_THT:C_Disc_D5.0mm_W2.5mm_P5.00mm` · Unpolarized capacitor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **GND** - ground, shared with 59 other pins |

### D1 - P6KE15A

diode / LED · footprint `Diode_THT:D_DO-15_P10.16mm_Horizontal` · Zener diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **GND** - ground, shared with 59 other pins |

### D2 - 1N4007

diode / LED · footprint `Diode_THT:D_DO-41_SOD81_P7.62mm_Horizontal` · Diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V_REG** → C2 pin 1, C3 pin 1, U1 pin 1 (IN) |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D3 - GREEN

diode / LED · footprint `LED_THT:LED_D5.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **GND** - ground, shared with 59 other pins |
| 2 | A | **PWR12_LED** → R1 pin 2 |

### D4 - GREEN

diode / LED · footprint `LED_THT:LED_D5.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **GND** - ground, shared with 59 other pins |
| 2 | A | **PWR5_LED** → R2 pin 2 |

### D11 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG1_OUT** → J2 pin 2 (Pin 2), Q1 pin 2 (D), R31 pin 2 |

### D12 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG2_OUT** → J3 pin 2 (Pin 2), Q2 pin 2 (D), R32 pin 2 |

### D13 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG3_OUT** → J4 pin 2 (Pin 2), Q3 pin 2 (D), R33 pin 2 |

### D14 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG4_OUT** → J5 pin 2 (Pin 2), Q4 pin 2 (D), R34 pin 2 |

### D15 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG5_OUT** → J6 pin 2 (Pin 2), Q5 pin 2 (D), R35 pin 2 |

### D16 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG6_OUT** → J7 pin 2 (Pin 2), Q6 pin 2 (D), R36 pin 2 |

### D17 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG7_OUT** → J8 pin 2 (Pin 2), Q7 pin 2 (D), R37 pin 2 |

### D18 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG8_OUT** → J9 pin 2 (Pin 2), Q8 pin 2 (D), R38 pin 2 |

### D19 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG9_OUT** → J10 pin 2 (Pin 2), Q9 pin 2 (D), R39 pin 2 |

### D20 - 1N5822

diode / LED · footprint `Diode_THT:D_DO-201AD_P5.08mm_Vertical_CathodeUp` · Schottky diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | A | **MAG10_OUT** → J11 pin 2 (Pin 2), Q10 pin 2 (D), R40 pin 2 |

### D21 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG1_LED** → R31 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D22 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG2_LED** → R32 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D23 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG3_LED** → R33 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D24 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG4_LED** → R34 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D25 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG5_LED** → R35 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D26 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG6_LED** → R36 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D27 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG7_LED** → R37 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D28 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG8_LED** → R38 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D29 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG9_LED** → R39 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### D30 - RED

diode / LED · footprint `LED_THT:LED_D3.0mm` · Light emitting diode

| Pin | Name | Goes to |
|---|---|---|
| 1 | K | **MAG10_LED** → R40 pin 1 |
| 2 | A | **+12V** - 12 V supply, shared with 37 other pins |

### F1 - 10A mini blade

fuse · footprint `Fuse:Fuseholder_Blade_Mini_Keystone_3568` · Fuse

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+12V_IN** → J1 pin 1 (Pin 1) |
| 2 |  | **+12V** - 12 V supply, shared with 36 other pins |

### J1 - 12V_IN

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-3-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V_IN** → F1 pin 1, F1 pin 1 |
| 2 | Pin 2 | **GND** - ground, shared with 59 other pins |

### J2 - MAG1

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG1_OUT** → D11 pin 2 (A), Q1 pin 2 (D), R31 pin 2 |

### J3 - MAG2

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG2_OUT** → D12 pin 2 (A), Q2 pin 2 (D), R32 pin 2 |

### J4 - MAG3

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG3_OUT** → D13 pin 2 (A), Q3 pin 2 (D), R33 pin 2 |

### J5 - MAG4

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG4_OUT** → D14 pin 2 (A), Q4 pin 2 (D), R34 pin 2 |

### J6 - MAG5

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG5_OUT** → D15 pin 2 (A), Q5 pin 2 (D), R35 pin 2 |

### J7 - MAG6

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG6_OUT** → D16 pin 2 (A), Q6 pin 2 (D), R36 pin 2 |

### J8 - MAG7

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG7_OUT** → D17 pin 2 (A), Q7 pin 2 (D), R37 pin 2 |

### J9 - MAG8

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG8_OUT** → D18 pin 2 (A), Q8 pin 2 (D), R38 pin 2 |

### J10 - MAG9

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG9_OUT** → D19 pin 2 (A), Q9 pin 2 (D), R39 pin 2 |

### J11 - MAG10

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_MKDS-1,5-2-5.08_1x02_P5.08mm_Horizontal` · Generic screw terminal, single row, 01x02, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **MAG10_OUT** → D20 pin 2 (A), Q10 pin 2 (D), R40 pin 2 |

### J12 - COIN

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-3-3.5-H_1x03_P3.50mm_Horizontal` · Generic screw terminal, single row, 01x03, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+12V** - 12 V supply, shared with 37 other pins |
| 2 | Pin 2 | **GND** - ground, shared with 59 other pins |
| 3 | Pin 3 | **COIN_SIG** → U2 pin 2 |

### J13 - BUTTONS

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal` · Generic screw terminal, single row, 01x08, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **BTN_S1_EXT** → R43 pin 1 |
| 2 | Pin 2 | **GND** - ground, shared with 59 other pins |
| 3 | Pin 3 | **BTN_S2_EXT** → R44 pin 1 |
| 4 | Pin 4 | **GND** - ground, shared with 59 other pins |
| 5 | Pin 5 | **BTN_S3_EXT** → R45 pin 1 |
| 6 | Pin 6 | **GND** - ground, shared with 59 other pins |
| 7 | Pin 7 | **BTN_RST_EXT** → R46 pin 1 |
| 8 | Pin 8 | **GND** - ground, shared with 59 other pins |

### J14 - STATUS_LEDS

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal` · Generic screw terminal, single row, 01x08, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **LED1_OUT** → R51 pin 2 |
| 2 | Pin 2 | **GND** - ground, shared with 59 other pins |
| 3 | Pin 3 | **LED2_OUT** → R52 pin 2 |
| 4 | Pin 4 | **GND** - ground, shared with 59 other pins |
| 5 | Pin 5 | **LED3_OUT** → R53 pin 2 |
| 6 | Pin 6 | **GND** - ground, shared with 59 other pins |
| 7 | Pin 7 | **LED4_OUT** → R54 pin 2 |
| 8 | Pin 8 | **GND** - ground, shared with 59 other pins |

### J15 - 7SEG

connector / terminal · footprint `TerminalBlock_Phoenix:TerminalBlock_Phoenix_PT-1,5-8-3.5-H_1x08_P3.50mm_Horizontal` · Generic screw terminal, single row, 01x08, script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **SEG_A** → R55 pin 2 |
| 2 | Pin 2 | **SEG_B** → R56 pin 2 |
| 3 | Pin 3 | **SEG_C** → R57 pin 2 |
| 4 | Pin 4 | **SEG_D** → R58 pin 2 |
| 5 | Pin 5 | **SEG_E** → R59 pin 2 |
| 6 | Pin 6 | **SEG_F** → R60 pin 2 |
| 7 | Pin 7 | **SEG_G** → R61 pin 2 |
| 8 | Pin 8 | **GND** - ground, shared with 59 other pins |

### J16 - MEGA SPARE

connector / terminal · footprint `Connector_PinHeader_2.54mm:PinHeader_2x10_P2.54mm_Vertical` · Generic connector, double row, 02x10, odd/even pin numbering scheme (row 1 odd numbers, row 2 even numbers), script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+5V** - 5 V supply, shared with 16 other pins |
| 2 | Pin 2 | **GND** - ground, shared with 59 other pins |
| 3 | Pin 3 | **+3V3** → A1 pin 3V3 (3.3V) |
| 4 | Pin 4 | **GND** - ground, shared with 59 other pins |
| 5 | Pin 5 | **I2C_SDA** → A1 pin D20 (D20/SDA) |
| 6 | Pin 6 | **I2C_SCL** → A1 pin D21 (D21/SCL) |
| 7 | Pin 7 | **SPARE_TX3** → A1 pin D14 (D14/TX3) |
| 8 | Pin 8 | **SPARE_RX3** → A1 pin D15 (D15/RX3) |
| 9 | Pin 9 | **SPARE_D4** → A1 pin D4 |
| 10 | Pin 10 | **SPARE_D13** → A1 pin D13 |
| 11 | Pin 11 | **SPARE_D30** → A1 pin D30 |
| 12 | Pin 12 | **SPARE_D31** → A1 pin D31 |
| 13 | Pin 13 | **SPARE_D32** → A1 pin D32 |
| 14 | Pin 14 | **SPARE_D33** → A1 pin D33 |
| 15 | Pin 15 | **SPARE_A7** → A1 pin A7 |
| 16 | Pin 16 | **SPARE_A8** → A1 pin A8 |
| 17 | Pin 17 | **SPARE_SCK** → A1 pin D52 (D52 SCK) |
| 18 | Pin 18 | **SPARE_MISO** → A1 pin D50 (D50 MISO) |
| 19 | Pin 19 | **SPARE_MOSI** → A1 pin D51 (D51 MOSI) |
| 20 | Pin 20 | **SPARE_CS** → A1 pin D53 (D53 CS) |

### J17 - ESP32 SPARE

connector / terminal · footprint `Connector_PinHeader_2.54mm:PinHeader_2x04_P2.54mm_Vertical` · Generic connector, double row, 02x04, odd/even pin numbering scheme (row 1 odd numbers, row 2 even numbers), script generated (kicad-library-utils/schlib/autogen/connector/)

| Pin | Name | Goes to |
|---|---|---|
| 1 | Pin 1 | **+3V3_ESP** → A2 pin 30 (3V3) |
| 2 | Pin 2 | **GND** - ground, shared with 59 other pins |
| 3 | Pin 3 | **ESP_IO25** → A2 pin 8 (IO25) |
| 4 | Pin 4 | **ESP_IO26** → A2 pin 9 (IO26) |
| 5 | Pin 5 | **ESP_IO27** → A2 pin 10 (IO27) |
| 6 | Pin 6 | **ESP_IO32** → A2 pin 6 (IO32) |
| 7 | Pin 7 | **ESP_IO33** → A2 pin 7 (IO33) |
| 8 | Pin 8 | **ESP_IO14** → A2 pin 11 (IO14) |

### R1 - 4.7k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+12V** - 12 V supply, shared with 37 other pins |
| 2 |  | **PWR12_LED** → D3 pin 2 (A) |

### R2 - 1k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **PWR5_LED** → D4 pin 2 (A) |

### R11 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG1_PWM** → A1 pin D3 (D3 INT1) |
| 2 |  | **MAG1_G** → Q1 pin 1 (G), R21 pin 1 |

### R12 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG2_PWM** → A1 pin D5 |
| 2 |  | **MAG2_G** → Q2 pin 1 (G), R22 pin 1 |

### R13 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG3_PWM** → A1 pin D6 |
| 2 |  | **MAG3_G** → Q3 pin 1 (G), R23 pin 1 |

### R14 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG4_PWM** → A1 pin D7 |
| 2 |  | **MAG4_G** → Q4 pin 1 (G), R24 pin 1 |

### R15 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG5_PWM** → A1 pin D8 |
| 2 |  | **MAG5_G** → Q5 pin 1 (G), R25 pin 1 |

### R16 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG6_PWM** → A1 pin D9 |
| 2 |  | **MAG6_G** → Q6 pin 1 (G), R26 pin 1 |

### R17 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG7_PWM** → A1 pin D10 |
| 2 |  | **MAG7_G** → Q7 pin 1 (G), R27 pin 1 |

### R18 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG8_PWM** → A1 pin D11 |
| 2 |  | **MAG8_G** → Q8 pin 1 (G), R28 pin 1 |

### R19 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG9_PWM** → A1 pin D12 |
| 2 |  | **MAG9_G** → Q9 pin 1 (G), R29 pin 1 |

### R20 - 100R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG10_PWM** → A1 pin D44 |
| 2 |  | **MAG10_G** → Q10 pin 1 (G), R30 pin 1 |

### R21 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG1_G** → Q1 pin 1 (G), R11 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R22 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG2_G** → Q2 pin 1 (G), R12 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R23 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG3_G** → Q3 pin 1 (G), R13 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R24 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG4_G** → Q4 pin 1 (G), R14 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R25 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG5_G** → Q5 pin 1 (G), R15 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R26 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG6_G** → Q6 pin 1 (G), R16 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R27 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG7_G** → Q7 pin 1 (G), R17 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R28 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG8_G** → Q8 pin 1 (G), R18 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R29 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG9_G** → Q9 pin 1 (G), R19 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R30 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG10_G** → Q10 pin 1 (G), R20 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |

### R31 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG1_LED** → D21 pin 1 (K) |
| 2 |  | **MAG1_OUT** → D11 pin 2 (A), J2 pin 2 (Pin 2), Q1 pin 2 (D) |

### R32 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG2_LED** → D22 pin 1 (K) |
| 2 |  | **MAG2_OUT** → D12 pin 2 (A), J3 pin 2 (Pin 2), Q2 pin 2 (D) |

### R33 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG3_LED** → D23 pin 1 (K) |
| 2 |  | **MAG3_OUT** → D13 pin 2 (A), J4 pin 2 (Pin 2), Q3 pin 2 (D) |

### R34 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG4_LED** → D24 pin 1 (K) |
| 2 |  | **MAG4_OUT** → D14 pin 2 (A), J5 pin 2 (Pin 2), Q4 pin 2 (D) |

### R35 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG5_LED** → D25 pin 1 (K) |
| 2 |  | **MAG5_OUT** → D15 pin 2 (A), J6 pin 2 (Pin 2), Q5 pin 2 (D) |

### R36 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG6_LED** → D26 pin 1 (K) |
| 2 |  | **MAG6_OUT** → D16 pin 2 (A), J7 pin 2 (Pin 2), Q6 pin 2 (D) |

### R37 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG7_LED** → D27 pin 1 (K) |
| 2 |  | **MAG7_OUT** → D17 pin 2 (A), J8 pin 2 (Pin 2), Q7 pin 2 (D) |

### R38 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG8_LED** → D28 pin 1 (K) |
| 2 |  | **MAG8_OUT** → D18 pin 2 (A), J9 pin 2 (Pin 2), Q8 pin 2 (D) |

### R39 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG9_LED** → D29 pin 1 (K) |
| 2 |  | **MAG9_OUT** → D19 pin 2 (A), J10 pin 2 (Pin 2), Q9 pin 2 (D) |

### R40 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MAG10_LED** → D30 pin 1 (K) |
| 2 |  | **MAG10_OUT** → D20 pin 2 (A), J11 pin 2 (Pin 2), Q10 pin 2 (D) |

### R41 - 2.2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+12V** - 12 V supply, shared with 37 other pins |
| 2 |  | **COIN_OPTO_A** → U2 pin 1 |

### R42 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **COIN_IN** → A1 pin D2 (D2 INT0), C8 pin 1, U2 pin 4 |

### R43 - 1k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_S1_EXT** → J13 pin 1 (Pin 1) |
| 2 |  | **BTN_S1** → A1 pin D22, C9 pin 1, R47 pin 2 |

### R44 - 1k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_S2_EXT** → J13 pin 3 (Pin 3) |
| 2 |  | **BTN_S2** → A1 pin D24, C10 pin 1, R48 pin 2 |

### R45 - 1k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_S3_EXT** → J13 pin 5 (Pin 5) |
| 2 |  | **BTN_S3** → A1 pin D26, C11 pin 1, R49 pin 2 |

### R46 - 1k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **BTN_RST_EXT** → J13 pin 7 (Pin 7) |
| 2 |  | **BTN_RST** → A1 pin D28, C12 pin 1, R50 pin 2 |

### R47 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **BTN_S1** → A1 pin D22, C9 pin 1, R43 pin 2 |

### R48 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **BTN_S2** → A1 pin D24, C10 pin 1, R44 pin 2 |

### R49 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **BTN_S3** → A1 pin D26, C11 pin 1, R45 pin 2 |

### R50 - 10k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **+5V** - 5 V supply, shared with 16 other pins |
| 2 |  | **BTN_RST** → A1 pin D28, C12 pin 1, R46 pin 2 |

### R51 - 330R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **LED1** → A1 pin A3 |
| 2 |  | **LED1_OUT** → J14 pin 1 (Pin 1) |

### R52 - 330R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **LED2** → A1 pin A4 |
| 2 |  | **LED2_OUT** → J14 pin 3 (Pin 3) |

### R53 - 330R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **LED3** → A1 pin A5 |
| 2 |  | **LED3_OUT** → J14 pin 5 (Pin 5) |

### R54 - 330R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **LED4** → A1 pin A6 |
| 2 |  | **LED4_OUT** → J14 pin 7 (Pin 7) |

### R55 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QD** → U3 pin 3 (QD) |
| 2 |  | **SEG_A** → J15 pin 1 (Pin 1) |

### R56 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QG** → U3 pin 6 (QG) |
| 2 |  | **SEG_B** → J15 pin 2 (Pin 2) |

### R57 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QF** → U3 pin 5 (QF) |
| 2 |  | **SEG_C** → J15 pin 3 (Pin 3) |

### R58 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QH** → U3 pin 7 (QH) |
| 2 |  | **SEG_D** → J15 pin 4 (Pin 4) |

### R59 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QE** → U3 pin 4 (QE) |
| 2 |  | **SEG_E** → J15 pin 5 (Pin 5) |

### R60 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QC** → U3 pin 2 (QC) |
| 2 |  | **SEG_F** → J15 pin 6 (Pin 6) |

### R61 - 470R

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **SEG_QB** → U3 pin 1 (QB) |
| 2 |  | **SEG_G** → J15 pin 7 (Pin 7) |

### R62 - 1k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **MEGA_TX1** → A1 pin D18 (D18/TX1) |
| 2 |  | **ESP_RX2** → A2 pin 25 (RX2/IO16), R63 pin 1 |

### R63 - 2k

resistor · footprint `Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal` · Resistor

| Pin | Name | Goes to |
|---|---|---|
| 1 |  | **ESP_RX2** → A2 pin 25 (RX2/IO16), R62 pin 2 |
| 2 |  | **GND** - ground, shared with 59 other pins |
