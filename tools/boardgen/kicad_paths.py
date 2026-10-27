"""Where KiCad is, resolved once for the whole workspace.

Before this existed, 18 files each hardcoded `C:\\Program Files\\KiCad\\10.0`, so upgrading KiCad
meant editing all of them and any one that was missed would fail in a different way (a missing
`kicad-cli`, or worse, a symbol library silently read from the old version).

Resolution order:
  1. the `KICAD_HOME` environment variable, if set
  2. the highest-numbered `C:\\Program Files\\KiCad\\<version>` that is actually installed
  3. the path this workspace was built against, as a last resort

Import what you need rather than rebuilding paths by hand:
    from boardgen.kicad_paths import CLI, PYTHON, SYMBOLS, FOOTPRINTS
"""
import os
import re

_FALLBACK = r"C:\Program Files\KiCad\10.0"


def _discover():
    env = os.environ.get("KICAD_HOME")
    if env and os.path.isdir(env):
        return env

    base = r"C:\Program Files\KiCad"
    if os.path.isdir(base):
        versions = []
        for name in os.listdir(base):
            m = re.fullmatch(r"(\d+)\.(\d+)", name)
            if m and os.path.isfile(os.path.join(base, name, "bin", "kicad-cli.exe")):
                versions.append(((int(m.group(1)), int(m.group(2))), name))
        if versions:
            return os.path.join(base, max(versions)[1])

    return _FALLBACK


HOME = _discover()
BIN = os.path.join(HOME, "bin")
CLI = os.path.join(BIN, "kicad-cli.exe")
PYTHON = os.path.join(BIN, "python.exe")
SHARE = os.path.join(HOME, "share", "kicad")
SYMBOLS = os.path.join(SHARE, "symbols")
FOOTPRINTS = os.path.join(SHARE, "footprints")
VERSION = os.path.basename(HOME)


def check():
    """Raise a clear error now rather than a confusing one later."""
    missing = [p for p in (CLI, SYMBOLS, FOOTPRINTS) if not os.path.exists(p)]
    if missing:
        raise SystemExit(
            "KiCad looks wrong at %s - missing:\n  %s\n"
            "Set KICAD_HOME to your KiCad install directory." % (HOME, "\n  ".join(missing)))
    return True


if __name__ == "__main__":
    print("KICAD_HOME env : %s" % (os.environ.get("KICAD_HOME") or "(not set)"))
    for k in ("HOME", "VERSION", "CLI", "PYTHON", "SYMBOLS", "FOOTPRINTS"):
        v = globals()[k]
        print("%-11s %s%s" % (k, v, "" if os.path.exists(v) or k == "VERSION" else "   <-- MISSING"))
