# ref-esp32 - design brief

The platform's **reference board** (PLATFORM_PLAN §5 P6, assumption A3): a general-purpose ESP32-S3 dev/IoT
board, assembled by JLCPCB, with USB-C power + native USB data, a 3V3 LDO, ESD, an I2C sensor, buttons, LEDs
and 2.54 mm breakout headers. It exists to drive P1-P5: every class of risk in the register that a *complex
SMD board* can hit (R1 library pinout, R4 CPL rotation, R5 levels, R7 critical layout, R8 strapping, R10
connector protection, R11 thermal, R12 mechanical, R14 stock) has a concrete instance on this board.

Status 2026-10-27: **planning only** - no netlist, no registry records, nothing signed. Design reasoning,
numbers and the BOM are in `ARCHITECTURE.md`; open questions with defaults are in its §10.

Sources are cited inline. Datasheet short names used below:
- **WROOM-1 DS** = ESP32-S3-WROOM-1 & WROOM-1U Datasheet v1.8, https://documentation.espressif.com/esp32-s3-wroom-1_wroom-1u_datasheet_en.pdf
- **HW checklist** = ESP32-S3 Hardware Design Guidelines, Schematic Checklist, https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/schematic-checklist.html
- **HW layout** = same guide, PCB Layout Design, https://docs.espressif.com/projects/esp-hardware-design-guidelines/en/latest/esp32s3/pcb-layout-design.html

## 1. Purpose

A board a person can plug into a USB port, flash over native USB with no bridge chip, read a temperature and
humidity value from, and wire other things to. For the platform it is the proof that a brief like this can be
taken from text to a JLCPCB-ready PCBA package by agents, with every check green and every waiver written down.

## 2. Answers to the playbook questions (NEW_BOARD_PLAYBOOK §1; the owner said "defaults")

| Question | Answer / default |
|---|---|
| What does it do? | Wi-Fi/BLE dev board: ESP32-S3 module, USB-C, SHT30 temp/humidity, Qwiic I2C port, 25 free GPIO on headers, BOOT/RESET, power LED, status LED. |
| Firmware? | None exists. Boot/flash over native USB (USB Serial/JTAG, WROOM-1 DS §5.2.1.8). A bring-up sketch (blink + I2C read + CDC) is a P6 deliverable, not part of this brief. |
| Supply | USB-C 5 V only, default-power sink (500 mA, USB 2.0). No battery, no external supply. |
| Sensors / actuators | SHT30-DIS (I2C 0x44), 1 status LED. External: anything on the headers/Qwiic (3.3 V logic). |
| Can the owner solder SMD? | Not needed: JLCPCB assembles every SMD part. Only the three 2.54 mm pin headers are through-hole and are left to the owner (default; Q5). |
| Dev boards? | None. The ESP32-S3 is a pre-certified **module** (A3), not a bare chip. |
| Size / holes / who assembles / where made | ~30 x 55 mm (max 100 x 100), 2 mounting holes, JLCPCB PCBA, JLCPCB fab. See §6, §7. |

## 3. Design decisions (each justified in ARCHITECTURE.md)

| Topic | Decision | Why in one line |
|---|---|---|
| Module | **ESP32-S3-WROOM-1-N8** (LCSC C2913198, extended) | 8 MB quad flash, no PSRAM, so GPIO35-37 stay free (WROOM-1 DS Table 3-1 note b) and the strap/boot picture is the simplest. |
| Regulator | **LDL1117S33R** (C435835, extended), SOT-223 | 0.35 V typ / 0.6 V max dropout at 1.2 A (ST DS Table 4) keeps 3.3 V up on a 4.4 V USB rail; AMS1117 (basic) needs 1.3-1.4 V and fails that corner. |
| Layers | **2** (1.6 mm FR-4, 1 oz), bottom = ground plane | USB is full-speed only; the pair is ~30 mm = 0.18 ns, 4.5 % of the 4 ns minimum rise time. 4-layer is the pre-agreed escalation (§9, ARCH §5.3). |
| USB | Native USB, no bridge. USBLC6-2SC6 ESD, 22 Ω series, 2 x 5.1 kΩ Rd | WROOM-1 DS §5.2.1.7/8; HW checklist "USB". |
| Protection | 1.1 A polyfuse + SMAJ5.0A TVS on VBUS. **No reverse-polarity element** | The only 5 V entry is a keyed USB-C source; the "5V" header is an output only (R10 waiver W-4). |
| I2C | SDA = IO8, SCL = IO9, 2.2 kΩ pull-ups to 3V3, SHT30 + JST-SH Qwiic port | Rise time 186 ns at 100 pF < 300 ns (Fast-mode). |
| Assembly | `ASSEMBLY = "pcba"`, single-side SMT (top), headers hand | Bottom side is a ground plane; nothing to place there. |

## 4. Interfaces

| Interface | Connector / part | Signals | Level | Protection |
|---|---|---|---|---|
| USB-C (power + data) | J1 HRO TYPE-C-31-M-12 | VBUS, D+/D−, CC1/CC2, GND, shield | 5 V power, 3.3 V FS data | F1 polyfuse, D1 TVS, U4 USBLC6 |
| Breakout headers | J2, J3 (1x16, 2.54 mm) | 25 GPIO, 3V3 x2, 5V (out), GND x4 | 3.3 V logic | none (waiver W-1) |
| Qwiic / STEMMA-QT | J5 JST-SH 4-pin | GND, 3V3, SDA, SCL | 3.3 V | none (waiver W-2) |
| UART0 debug | J4 (1x3) | TXD0 (GPIO43, 470 Ω series), RXD0 (GPIO44), GND | 3.3 V | none (waiver W-3) |
| Buttons | SW1 BOOT (GPIO0), SW2 RESET (EN) | | 3.3 V | none (touch only) |
| LEDs | LED1 power (3V3), LED2 status (GPIO21) | | | series R |
| Sensor | U3 SHT30-DIS | I2C 0x44 | 3.3 V | none |

## 5. Electrical requirements

Rails: **VBUS** 4.75-5.25 V from the host -> polyfuse -> **VBUS_F** -> LDO -> **3V3** (3.0-3.6 V allowed,
WROOM-1 DS Table 6-2). Everything on the module side is 3.3 V; 5 V never touches a module, sensor or
header GPIO pin (rule PR-V in P2).

Power budget (derivation and sources in ARCHITECTURE §2):

| Item | Peak | Average (planning) | Source |
|---|---|---|---|
| U1 module, Wi-Fi TX 802.11b 1 Mbps @ 20.5 dBm, 100 % duty | **355 mA** | ~120 mA (assumption) | WROOM-1 DS Table 6-4 (p.28) |
| U3 SHT30 measuring | 0.6 mA | 2 µA | Sensirion SHT3x-DIS DS v7, Table 3 |
| I2C pull-ups (one line low) | 1.5 mA | ~0 | 3.3 V / 2.2 kΩ |
| LED1 + LED2 | 4.4 mA | 4.4 mA | 3.3 V, Vf ~1.9 V, 1 kΩ / 470 Ω |
| External allowance on 3V3 (headers + Qwiic) | 100 mA | 0 | design choice |
| **3V3 total** | **~465 mA** (462 sum + 0.7 mA button pull-ups, rounded up) | ~125 mA | module supply must deliver >= 0.5 A (Table 6-2) |
| External allowance on 5V header | 35 mA | 0 | closes the USB budget at exactly 500 mA |
| **VBUS total** | **~500 mA** | ~125 mA | USB 2.0 default-power sink limit |

LDO U2 dissipation (ARCH §2.3): **0.74 W at 465 mA / 5.0 V**, **0.85 W at 5.25 V**, **0.91 W at the 500 mA cap**;
average 0.21-0.24 W at 125 mA. Worst case needs θJA <= 100 °C/W at 40 °C ambient; ST's baseline is 120 °C/W,
so the layout must give the tab (VOUT) a copper pour, rule in §9.

## 6. Mechanical

| Item | Requirement |
|---|---|
| Outline | ~30 x 55 mm rectangle, 1 mm corner radius, 1.6 mm FR-4. Hard max 100 x 100 mm (cheapest JLCPCB tier). |
| Connector edges | USB-C J1 centred on the **bottom** short edge, mouth flush with the edge (overhang <= 0.5 mm). Headers J2/J3 along the two long edges, 25.4 mm apart (DevKit-style); Qwiic J5 beside J1; UART J4 on the bottom-left. |
| Module | U1 at the **top** short edge, antenna end flush with the board edge (HW layout, "General Principles of PCB Layout for Modules": antenna outside/at the board edge, feed point near the edge). |
| Antenna keepout | Rule area on **all copper layers** over the module's antenna area (WROOM-1 DS Fig. 11-1 "Antenna Area", about 18 mm wide and 6-7.5 mm deep from the module's end - exact numbers must be taken from Espressif's land-pattern source file, the DS text gives only the figure) and to the board edge: no copper, pour, via, track, component, or silkscreen-on-copper. Headers' first pin must lie below it. >= 15 mm of free space in all directions around the antenna inside any future enclosure (HW layout). |
| Mounting | 2 x M2.5 NPTH (2.7 mm) at the **bottom** corners only. Nothing metallic (screws, standoffs) near the antenna. |
| Heights | Module 3.1 mm, USB-C 3.3 mm, headers ~11.5 mm total. No enclosure in scope. |
| Thermal placement | U2 (LDO) near J1, sensor U3 as far from both heat sources as the outline allows: >= 12 mm from U2 and >= 10 mm from the module body (self-heating error; a routed slot beside U3 is an optional extra, Q11). |

## 7. Assembly and fabrication

| Item | Choice |
|---|---|
| Assembly mode | `ASSEMBLY = "pcba"`: JLCPCB places all SMT parts on the **top** side, standard (not economic) PCBA so the extended-part fee is the lower tier (P1 spike §5: $1.53 vs $3.07, re-verify at P5). |
| Parts | 32 parts = 29 SMT placed by JLCPCB + 3 pin headers (J2, J3, J4). The 29 use 13 distinct **basic** values (6 R, 4 C, 2 LED, 1 switch) and 8 distinct **extended** parts (module, LDO, sensor, ESD, USB-C, polyfuse, TVS, JST-SH). The headers (2 distinct, both extended, hand-soldered by the owner) are listed in the project BOM but excluded from the JLCPCB BOM/CPL. Detail: ARCH §8. |
| Cost | Sum of first-tier JLCPCB unit prices = about $9.50 per board, parts only (2026-10-27), excluding PCB, assembly and fees. |
| PCB | 2 layers, 1.6 mm, 1 oz, **ENIG** (0.5 mm-pitch DFN and USB-C pads; lead-free HASL is the acceptable fallback, Q8), green mask, white silk. Min track/space 0.15/0.15 mm, via 0.3/0.6 mm. |
| Fab | JLCPCB first (A1). Gerbers, drill, BOM, CPL, STEP via the shared `outputs` stage. |
| Mixed parts to watch | USB-C has THT shield tabs and two locating holes inside an SMT part (it reflows as SMT); module has an exposed GND pad needing a reduced paste aperture. Both are CPL/paste checks at P5. |

## 8. Out of scope (explicit)

- Battery, charger, power path, deep-sleep current optimisation (the LDO's quiescent current is not tuned).
- USB-C PD negotiation, 3 A sinks, VCONN, alternate modes; the board is a 5 V default-power sink.
- RF design beyond the pre-certified module: no matching network, no external antenna (WROOM-1U), no certification work.
- Controlled-impedance 90 Ω USB routing (out of scope per PLATFORM_PLAN §1 beyond USB 2.0; here USB FS only and the 2-layer deviation is documented, ARCH §5.3).
- Octal-PSRAM or 16 MB modules, ESP32-S3 bare chip, 1.8 V I/O.
- Enclosure, antenna in a housing, FCC/CE testing, firmware, cloud.
- Reverse-polarity protection (no unkeyed 5 V entry), input surge beyond TVS/polyfuse, galvanic isolation.
- Mains, high-current, high-speed (>100 MHz) interfaces, BGA, flex.

## 9. Acceptance criteria per platform stage

"Done" for `ref-esp32` = every row green, every waiver in `waivers.json` with a reason, and the sign-off lists
non-`verified` parts as open human-check items (P1 §9).

| Stage | Pass criterion (measurable) |
|---|---|
| Brief / architecture (this task) | Both docs present, every BOM id verified by exact-id lookup against the returned MPN (done 2026-10-27), open questions carry defaults. |
| `parts` (P1) | 24 registry ids (23 orderable + 1 mechanical, ARCH §8) exist; each at least `crosschecked` (>= 2 independent sources agree on every pin, 0 `assist` diffs); `unverified_dims` printed; PR-MPN/PKG/GEO/STOCK green; stock >= boards x qty x 1.2 from the JLCPCB stock figure; PR-STOCK reports class per part; snapshot <= 7 days old at release. |
| `lint` / P2 rules | PR-SYM/PAD/HOLE multiset-correct for `SOT-223-3_TabPin2` (two pads "2") and the USB-C footprint; ratings: no net above 3.6 V on any module/sensor pin; strap rules: GPIO0 has a pull-up and no capacitor, GPIO45/46/3 not driven, EN has R and C; open-drain I2C has pull-ups; SHT30 ADDR not floating; unused pins explicitly marked NC (ALERT, nRESET); connector protection: USB has fuse + TVS + ESD, headers waived W-1..W-4; thermal: LDO Tj computed for 0.24 W average <= 125 °C, peak case reported as WARN with duty note. |
| `sch` / `sch-check` | ERC 0 errors, netlist compare 0 mismatches. |
| `spice` | Optional: EN RC (τ = 10 ms, EN passes VIL 0.825 V at 2.9 ms), LED currents 1-3 mA, I2C rise time < 300 ns. No Wokwi model exists for this board; `live_sim: false`. |
| `place` / `route` / `finish` | 2 layers, 0 unconnected, 0 DRC errors, 0 parity. Antenna keepout violations = 0 (new P4 check). D+/D− pair: no vias, length difference <= 1 mm, total <= 40 mm, bottom ground plane unbroken under the pair and under the module. 100 nF at U1 pin 2 within 3 mm; USBLC6 within 5 mm of J1; 22 Ω series within 5 mm of U1; R3/C5 EN network within 10 mm; U2 tab copper >= 2 cm² total (top + stitched bottom); U3 >= 12 mm from U2 and >= 10 mm from U1. 3V3 and VBUS_F tracks >= 0.5 mm or pour. |
| `check` (DRC + JLCPCB + current) | 0 errors against the JLCPCB 2-layer profile; current rules pass for 0.5 A on VBUS_F and 3V3; no silk-over-pad errors. |
| `lvs` | Gerber-derived connectivity equals the netlist (0 differences). |
| `outputs` / `fabreport` / `connections` | JLCPCB BOM has 21 distinct lines covering 29 parts (headers excluded), CPL has 29 rows with rotation from the P5 DB for U1, J1, U2, U3, U4, SW1, SW2 (R4); drill file matches `MANUFACTURING.md`; `CONNECTIONS.md` 0 differences; size and layer count in the quick-answers box. |
| `pinmap` | Not applicable until firmware exists; stage must report "no firmware" rather than pass silently (principle 4). |
| `webview` | Onboards with 3D model; click on U1/U2/J1 highlights; no live simulation. |
| `release` (P5) | Hash chain intact, stock re-check <= 24 h, rev + git hash on silk, SIGNOFF lists: antenna-keepout visual check (human), parts not `verified`, USB-C footprint/shield-tab check, ESP32 module land pattern. JLCPCB upload preview with no warnings (owner, one-time). |

## 10. Open questions

See ARCHITECTURE.md §10 (Q1-Q13, each with a recommended default). The brief assumes every default.
