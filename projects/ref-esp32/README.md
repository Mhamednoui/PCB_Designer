# ref-esp32 - platform reference board (planning stage)
General-purpose ESP32-S3-WROOM-1-N8 dev/IoT board for JLCPCB PCBA: USB-C power + native USB, LDL1117 3V3 LDO, USBLC6 ESD, SHT30 + Qwiic, BOOT/RESET, 2 LEDs, 2x16 GPIO headers.
Read `DESIGN_BRIEF.md` first: purpose, decisions, power budget, mechanical, fab choices, out-of-scope, acceptance criteria per pipeline stage.
Then `ARCHITECTURE.md`: block diagram, power tree and LDO thermal numbers, net/level map, strapping table, USB-C and 2-layer justification, decoupling, BOM with LCSC ids and stock.
Open questions Q1-Q13 with defaults and the ranked risk list are in `ARCHITECTURE.md` section 10.
Status 2026-10-27: documents only - no netlist, no registry records, nothing signed or built yet (tasks P1-P6 in `docs/PLATFORM_PLAN.md`).
