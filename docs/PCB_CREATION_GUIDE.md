# Creating a PCB board — the tested procedure

**Who this is for:** an agent (or person) who has never built a board in this workspace and must produce
a fabricable one without asking anybody. It assumes only what is in `README.md` § "Running the scripts".

**How this file was written:** by actually building boards and recording what went wrong. Every failure
in the "Failure catalogue" below is one this workspace really produced, with the message KiCad really
printed and the fix that really worked. Nothing here is hypothetical. When you hit something new, add
it — the catalogue is the point of the document.

Read alongside:
- `docs/NEW_BOARD_PLAYBOOK.md` — what to ask the user, and the design decisions, *before* scripting.
- `docs/LESSONS_LEARNED.md` — the workspace-wide trap list (KiCad API, Freerouting, Wokwi, Three.js).

---

## 1. The shape of a project

The generic stages live in **one shared place** and are used by every board. A project contains only
the two files that are genuinely board-specific:

```
tools/boardgen/          SHARED - one copy for the whole workspace, do not duplicate
  project.py             finds which project a run belongs to
  kicad_paths.py         where KiCad is (honours $KICAD_HOME)
  sexp.py                s-expression helper
  make_sch.py            netlist -> .kicad_sch
  check_sch.py           schematic vs netlist + ERC
  make_outputs.py        gerbers / BOM / CPL / STEP / PDF / renders
  make_fab_report.py     MANUFACTURING.md - size, layers, holes vs drill file, parts, order-form answers
  make_connections.py    CONNECTIONS.md - every pin and where its copper goes, schematic vs board checked
  make_spice.py          whole-board LTspice transient (boards with a SPICE block, i.e. no MCU)

projects/<id>/
  DESIGN_BRIEF.md        what the board must do + the decisions the user signed off
  gen/
    netlist.py           THE SOURCE OF TRUTH: parts, pins, nets, groups   <- you write this
    make_pcb.py          place | route | finish | check | render          <- copy, then edit ~8 constants
  lib/                   ONLY if the board needs a non-stock symbol/footprint
  out/fab, out/docs      generated - never hand-edit
```

To start a board, copy **only `make_pcb.py`** from the closest existing project:
- **a shield** that plugs onto an Arduino → `projects/uno-toggle/gen/make_pcb.py`
- **a standalone board** → `projects/blinky-555/gen/make_pcb.py`

Then write `netlist.py` and edit the constants block at the top of `make_pcb.py`.

> **Never copy `make_sch.py`, `check_sch.py`, `make_outputs.py` or `sexp.py` into a project.** They
> used to be copied, and they diverged: three different versions of `make_sch.py` existed at once, two
> of them still carrying bugs that had been fixed only in the third. If one of them needs a change for
> your board, make it configurable in the shared copy — do not fork it.

---

## 2. Procedure

### Step 1 — get the real pin numbers
`netlist.py` keys every part's pins by **symbol pin number**. A wrong number produces a board that
passes every check and is silently miswired, so never take these from a datasheet or from memory:

```bash
python tools/sym_pins.py Timer:NE555P
```

This follows `extends` aliases. It has to: `NE555P` is `(extends "NE555D")` and declares **no pins of
its own**, so grepping the symbol you actually chose finds zero pins and looks like a broken library.

### Step 2 — measure every footprint before you place it
**The placement coordinate is the footprint origin, and the origin is usually not the centre of the
part.** Every through-hole footprint checked so far puts its origin on **pad 1**:

```bash
python tools/fp_bbox.py Resistor_THT:R_Axial_DIN0207_L6.3mm_D2.5mm_P10.16mm_Horizontal
#   size     12.26 x 3.00 mm
#   extent   x -1.05 .. +11.21   y -1.50 .. +1.50
#   centred  NO  <-- origin is off-centre by (+5.08, +0.00)
```

So a resistor "at x=48" occupies x=46.95..59.21 — about 5 mm further right than a centred part would.
Write the resulting span next to each entry in `placements()` as a comment, and check the spans against
each other and against the mounting holes *on paper* before running anything. Skipping this put a
mounting hole through a resistor pad on the first blinky-555 build.

### Step 3 — write `netlist.py` and sanity-check it
```bash
python projects/<id>/gen/netlist.py
```
Prints parts, nets and the pads on each net, and **flags any single-pin net** — which is an ERC error
and always means either a typo in a net name or a rail you wired but nothing uses.

### Step 4 — edit the constants at the top of `make_pcb.py`
These eight are the entire per-project surface:

| Constant | What it is |
|---|---|
| `BW, BH` | board size in mm |
| `placements()` | `{ref: (x, y, rotation)}` — origin-based, see step 2 |
| `MOUNTING_HOLES` | `[(x, y)]`, M3 by default |
| `SHOW_REF_PREFIX` | which refs get their designator printed on silk |
| `SKIP_VALUE_SILK` | refs whose text must NOT be auto-placed at the pad centroid (big connectors) |
| `BOARD_OUTLINE` | edge segments, y stored negative; a rectangle is 4 lines |
| `TEXTS`, `SECTIONS` | silkscreen strings, `(text, x, y, size)` |

### Step 5 — run it
```bash
python pipeline.py <id> --list      # confirm the stage list first
python pipeline.py <id>
```
Build incrementally while iterating — `--only sch,sch-check` until ERC is clean, then add `place`, and
so on. `--force` is required to re-run design stages once `out/fab` exists.

### Step 6 — "done" means all four of these
```
netlist compare: N nets expected, N exported, 0 mismatches
ERC summary: {}
violations: 0 errors      (warnings are judged, see §4)
unconnected_items: 0
schematic_parity: 0
```
Anything else is not done. Do not report a board as finished on a green `--- ok` line alone: the
stage scripts exit 0 while still printing violations.

---

## 3. Failure catalogue

Every entry below actually happened. Format: the message → what it means → the fix.

### `courtyards_overlap` + `pth_inside_courtyard` between a part and a mounting hole
```
[violations] courtyards_overlap: Footprint R3 @(47.0,7.0); Footprint H2 @(56.5,3.5)
[violations] pth_inside_courtyard: PTH pad 2 [/LED_A] of R3 @(57.2,7.0); Footprint H2 @(56.5,3.5)
```
**Cause:** the placement assumed a centred footprint origin. R3's pad 2 is at origin+10.16, so the
part reached 5 mm further right than intended, into the corner hole.
**Fix:** `python tools/fp_bbox.py` on every footprint, redo `placements()` from the measured extents,
and record the span in a comment next to each entry. A mounting hole is `±3.45 mm` for M3.
**Tell-tale:** the coordinate DRC reports for the pad is not the coordinate you placed the part at.

### `text_height` on every small string
```
[violations] text_height: PCB text '9-12V' on F.Silkscreen @(8.0,13.5)
[violations] text_height: Value field of R2 (47k) @(36.1,4.8)
```
**Cause:** KiCad's default DRC minimum text height is **0.8 mm**; 0.7 mm violates it.
**Fix:** nothing below 0.8 mm anywhere — in `TEXTS`/`SECTIONS` *and* in the value/reference sizes the
generator sets. Note the second line: the generator's own auto-placed value text was also 0.7 mm, so
fixing only your `TEXTS` leaves a violation per part.

### Dozens of `silk_overlap` warnings concentrated on one part
```
violations: 60  {'warning/silk_overlap': 60}
   56  Segment of C1 on F.Silkscreen      <- one part is almost all of them
```
**Cause:** the generator prints each part's value and reference at a fixed offset from the pad
centroid. A fixed offset that clears a flat axial resistor lands *inside* a tall part — here a 6.8 mm
electrolytic with a polarity stripe and circle on the silkscreen.
**Fix:** derive the offset from the footprint's own courtyard instead of a constant:
```python
cyd = fp.GetCourtyard(pcbnew.F_CrtYd).BBox()
half = max(cyd.GetHeight() // 2, mm(1.2))
val_dy, ref_dy = half + mm(0.9), half + mm(1.3)
```
This took blinky-555 from **60 warnings to 3**, and is in `projects/blinky-555/gen/make_pcb.py`.
**General rule:** when warnings cluster on one reference, it is one geometric cause, not N problems.

### `footprint_symbol_field_mismatch` on every single part
```
schematic_parity: 9  {'warning/footprint_symbol_field_mismatch': 9}
-> "Missing symbol field 'ki_fp_filters' in footprint"
-> "Missing symbol field 'ki_locked' in footprint"
```
**Cause:** `make_sch.py` copied *every* library property onto each placed symbol, including
`ki_fp_filters` and `ki_locked`. Those are library-only hints (which footprints the chooser offers,
whether the library entry is locked) and have no footprint counterpart, so parity flags each one.
**Fix:** skip them when building the schematic — in `make_sch.py`'s property loop:
```python
if key in ("ki_fp_filters", "ki_locked"):
    continue
```
Took parity from 9 warnings to **0**. Harmless for fabrication, but a per-part warning on every board
hides the parity errors that do matter.

### `pipeline.py` reports success having done nothing
```
$ python pipeline.py blinky-555 --only finish,check
pipeline for 'blinky-555': (nothing)
pipeline complete.
```
**Cause:** `--only` was `action="append"`, so `finish,check` parsed as one stage literally named
`"finish,check"`, matched nothing, and the run "succeeded".
**Fixed in `pipeline.py`**: comma lists are split, and an unknown stage name is now a hard error listing
the valid stages. **General rule: a filter that matches nothing must never look like success.**

### A wrong pin number — ERC does NOT catch this
Break: `U1` wired on pin **9** of a DIP-8 (which has 8 pins).
```
ERC summary: {}                                            <- clean!
netlist compare: 7 nets expected, 7 exported, 1 mismatches  <- only this caught it
NET MISMATCH VCC
```
**This is the most dangerous failure mode in the whole pipeline.** A pin number that the symbol does
not have simply vanishes: the schematic is internally consistent, so ERC passes, and you get a board
where U1's real VCC pin is unconnected. Nothing downstream complains.
**What catches it:** `check_sch.py`'s netlist comparison — it exports the netlist KiCad actually
produced and diffs it against `netlist.py`. **Never skip the `sch-check` stage**, and never treat
"ERC clean" as proof the board is wired correctly.
**Prevention:** get pin numbers from `python tools/sym_pins.py <lib>:<Symbol>` (§2 step 1).

### A net-name typo — a *warning*, not an error
Break: `R3` wired to `LED_ANODE` while `D1` is wired to `LED_A`.
```
python projects/blinky-555/gen/netlist.py
  LED_A     [('D1', '2')]      <-- SINGLE PIN (ERC error)
  LED_ANODE [('R3', '2')]      <-- SINGLE PIN (ERC error)

ERC summary: {'warning/isolated_pin_label': 2}   <- WARNING, so a careless read passes
```
The two halves of a net silently become two dead-end nets. ERC only warns, so the real defence is
running `netlist.py` on its own first — it flags every single-pin net before anything is generated.
**A single-pin net is almost always a typo, and occasionally a rail you wired that nothing uses**
(`docs/LESSONS_LEARNED.md` lesson 27). Either way, fix it; never silence it.

### A footprint or symbol name typo — fails loudly (the easy case)
```
RuntimeError: footprint not found: Package_DIP:DIP-8_W7.62
KeyError: 'NE555PP not in C:\Program Files\KiCad\10.0\share\kicad\symbols\Timer.kicad_sym'
```
Both stop the run with the exact bad string. Check spelling against the library filename — the
footprint name is the `.kicad_mod` filename without the extension.

Note the pipeline prints the failing stage's full traceback. If you only see
`--- place FAILED after 2.8s (exit 1)`, you have truncated the output yourself — scroll up.

### A 4-layer board shipped with no inner copper — silent, and it costs a board run
`make_outputs.py` originally passed a **hardcoded** layer list to `kicad-cli`:
```
--layers F.Cu,B.Cu,F.Paste,B.Paste,F.Silkscreen,B.Silkscreen,F.Mask,B.Mask,Edge.Cuts
```
On a 4-layer board that exports a fab package containing **no In1.Cu and no In2.Cu**. Nothing errors.
The zip looks normal, uploads fine, and the board house builds the wrong board.
**Fixed** — the list now comes from the board itself:
```python
b = pcbnew.LoadBoard(PCB)
n = b.GetCopperLayerCount()
layers = ["F.Cu"] + ["In%d.Cu" % i for i in range(1, n - 1)] + ["B.Cu"]
```
It prints `copper layers: ...` when it runs — **read that line and confirm it matches the board you
designed.** General rule: anything that enumerates layers, nets or parts must derive them from the
design, never restate them.

### An export "succeeds" but writes no file
Seen with Wokwi's VCD export. **Suspect a missing probe/input declaration before suspecting the tool** —
see `docs/LESSONS_LEARNED.md` § 9. The same shape of bug appears whenever a tool's output depends on
something you have to declare.

### `ModuleNotFoundError: No module named 'pcbnew'`
Running a `gen/` script with system Python. Use
`"C:\Program Files\KiCad\10.0\bin\python.exe"`, or just use `pipeline.py`, which picks the right
interpreter per stage.

---

## 4. Which warnings are acceptable

- **0 errors, 0 unconnected, 0 parity** — never negotiable.
- `silk_overlap` — acceptable *only* when it is the deliberate consequence of a choice the user made.
  The Reflex Machine has ~213 because the user asked for part values printed over the pads. If you
  have not made such a choice, treat them as a bug: blinky-555 gets to 3 without trying hard.
- `text_height` — never acceptable; it is always a real setting you can change.

---

## 5. Scenarios built and verified

| # | Scenario | Exercises | Result |
|---|---|---|---|
| A | `blinky-555` — standalone NE555 flasher, 2-layer THT | no MCU, self-chosen rectangular outline, own mounting holes, real VCC rail, DIP-8 pin numbers, electrolytic polarity | **0 errors, 0 unconnected, 0 parity, 3 silk warnings.** Found 5 failures above. |
| B | 4-layer conversion of the same board | `SetCopperLayerCount(4)`, inner GND + VCC planes, gerber export | **Works.** DRC 0 errors / 0 unconnected; gerbers emit `.g1`/`.g2`. Found the hardcoded-layer-list bug. |
| C | Deliberate breakage: bad footprint name, bad symbol name, bad pin number, split net name | how each class of mistake surfaces | All four caught, but **by four different mechanisms** — see §6. |

### Scenario B — how to make a 4-layer board

Verified working. The stackup change itself is three lines; the traps are downstream.
```python
board.SetCopperLayerCount(4)          # In1_Cu and In2_Cu become enabled automatically
```
Then pour the inner layers the same way `finish` pours F.Cu/B.Cu — typically In1 = GND, In2 = VCC,
which also lets you drop the GND pours from the outer layers and route more freely.

Two things to know:
- **Net names**: `board.GetNetsByName()` returns local nets with a leading `/` (`"/VCC"`) but global
  power nets without (`"GND"`) — the same rule as `pcb_net_name()` in `make_pcb.py`. Look up both.
- **`make_outputs.py` must not hardcode the layer list** (see the failure above). It no longer does.

Freerouting routes 4 layers from the same DSN export; the layer count comes through the DSN.

---

## 6. The four mechanisms that catch mistakes — and what each one misses

Scenario C broke the same board four ways. Each was caught by a *different* check, which is why the
pipeline runs all of them and why skipping a stage is how bad boards get made.

| Mistake | Caught by | Would the others catch it? |
|---|---|---|
| Footprint name typo | `place` — `RuntimeError` | n/a, it stops the run |
| Symbol name typo | `sch` — `KeyError` | n/a, it stops the run |
| **Pin number that doesn't exist** | **`sch-check` netlist compare only** | **ERC says clean. DRC says clean.** |
| Net name split in two | `netlist.py` pre-check (error); ERC (warning only) | DRC says clean — both halves are legal nets |

The two in bold are the ones that reach fabrication. Neither ERC nor DRC can see them, because both
check *internal consistency*, and a board can be perfectly consistent and still not be the board you
meant. Only the netlist comparison — diffing what KiCad produced against your declared intent —
catches a wrong pin number. **Run `netlist.py` before generating, and never skip `sch-check`.**
