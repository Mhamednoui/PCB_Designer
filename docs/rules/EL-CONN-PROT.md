# EL-CONN-PROT

**What.** Every net that leaves the board through a connector (declared in `EXTERNAL` in `netlist.py`) must carry the
protection its class needs. A missing protection is an ERROR (waivable only with a written reason).

| Class of external net | How it is recognised | Required (else ERROR) |
|---|---|---|
| **supply** input | a passive connector pin declared `dir: "supply"` | a surge clamp (TVS/zener to GND) on the rail; **reverse-polarity protection** (series diode or P-FET, or a TVS/diode across the rail with its cathode on the rail *behind a fuse*, a crowbar that blows the fuse); a **fuse/PTC** if the declaration gives a source current `i` |
| **signal** | any other passive connector pin | a clamp on the net or behind its first resistors: TVS/zener to GND, a diode to a rail (flyback), or an ESD IC. Reported class: `protected` / `isolated` (only optocoupler pins behind it) / `series-R-only` / `bare`. The last two are ERRORs |
| **module** | the connector pin's *record* class is not `passive` (an Arduino/ESP32 socket) | nothing: the other side is an active board with its own protection |
| **supply-output** | a rail the board hands out (`dir: "out"`) | nothing (the spec only constrains inputs); it is reported |

Not judged (fail closed, never silently passed): a connector with no `EXTERNAL` entry at all, or a connected non-ground
pin left out of an otherwise declared connector. `EXTERNAL = {"J3": "none"}` declares that nothing leaves the board.

**Why.** The connector is where the outside world, a user's finger, a long cable, a wrong-way adapter, meets the silicon.
Protection that was meant to be there (a fuse in the brief, a TVS in the schematic) is the first thing lost in a rewrite,
and nothing else in the pipeline notices.

**Basis.** Graph analysis of the IR: `parts`, `nets`, `external`. No voltages are used, so this rule does not need the
electrical model. Severity ERROR; a waiver (`projects/<id>/waivers.json`, `"check": "electrical"`, `"rule": "EL-CONN-PROT"`,
`why` of 20+ characters) may demote it to WAIVED. Findings are grouped: one per missing item on a supply input, one
per connector for its unprotected signals (every net is listed with its class).

**Run it.**
- `python pipeline.py <id> --only ir` then `python tools/boardgen/elec/conn_prot.py <id> [--table]` prints the per-net
  class table and the findings and exits 1 on an unwaived ERROR.
- Inside the engine: `boardgen.rules.run(ir, only=["EL-CONN-PROT"])`. The `electrical` stage runs it together with the
  other electrical rules (the supervisor wires that stage in; this rule needs nothing but the IR).

**Example fix.** A 12 V input `J1` with no protection: put a fuse after the connector, a TVS across the rail behind it
and the rail is protected on all three counts.

```python
rp("J1", J_PWR_ID, "12V_IN", {1: "+12V_IN", 2: "GND"}, G)
rp("F1", FUSE_ID, "10A mini blade", {1: "+12V_IN", 2: "+12V"}, G)      # fuse/PTC
rp("D1", DO15_ID, "P6KE15A", {"K": "+12V", "A": "GND"}, G)           # surge clamp; also the reverse crowbar behind F1
EXTERNAL = X.pins("J1", [1], dir="supply", v=(10.8, 13.2), i=10.0, why="12 V adapter")
```

For an off-board signal wire, add a TVS/ESD diode from the connector net to GND (next to the connector), then the
series resistor.

**Known limits.**
- *Presence, not adequacy*: a clamp is found by element type, its standoff and clamping voltage are not checked
  against the working voltage or the part's absolute maximum (that belongs to EL-ABSMAX).
- A series diode / P-FET counts as reverse protection only if it is the *only* way off the supply node (a 1N4007 in
  front of a regulator while other loads hang on the rail protects only that branch and is not credited).
- Dir-less and `v`-less declarations are accepted for classification (only `supply` changes the requirement).
- An on-board switch or fuse holder is declared `"none"`: it is a series element, not a cable. The finger-ESD exposure of
  an on-board button is judged on the Arduino pin net it drives (a `module` net, so not required to have a clamp). That is
  a deliberate, documented acceptance: the AVR pin has its own ESD structures and the 100 nF at the switch is the
  usual hobby-shield practice. A button on a cable (reflex-machine J13) is a different case and is an ERROR.
