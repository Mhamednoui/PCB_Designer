"""Versions of every external tool the pipeline depends on, detected once and cached.

Two consumers:
  * pipeline.py's stage cache key  -> `fingerprint()`: a change to ANY tool below (a KiCad upgrade, a new
    gerbonara/shapely, a different LTspice, a different Freerouting, another Python) invalidates every cached
    stage result, because a cached "pass" produced by a different tool is not evidence about this run.
  * the run report (out/run/<ts>/report.json) -> `versions()`: so a result can be reproduced from the report.

Detection never raises: a tool that is not installed is reported as `{"installed": false}` (not every project
needs every tool - blinky has no firmware, most have no SPICE). Cheap by design:
  * per process      - computed once (module-level cache).
  * across processes - the slow probes (spawning kicad-cli / python.exe) are remembered in
                       `.toolchain_cache.json` (git-ignored), keyed by the executable's size+mtime, so an
                       unchanged install costs a few stat() calls, not a process spawn.

    python tools/boardgen/toolchain.py          # print what was detected (JSON)
"""
import hashlib
import importlib.metadata
import json
import os
import re
import subprocess
import sys

try:                                       # works both as `from boardgen import toolchain` and as a script
    from boardgen import kicad_paths
except ImportError:                        # pragma: no cover - script mode
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from boardgen import kicad_paths

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DISK_CACHE = os.path.join(ROOT, ".toolchain_cache.json")
PY_PACKAGES = ("gerbonara", "shapely")      # system-Python deps of the lvs stage (pinned in requirements.txt)

_VERSIONS = {}


def _sig(path):
    try:
        st = os.stat(path)
        return "%d|%d" % (st.st_size, st.st_mtime_ns)
    except OSError:
        return None


def _load_disk():
    try:
        with open(DISK_CACHE, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def _save_disk(data):
    tmp = DISK_CACHE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        os.replace(tmp, DISK_CACHE)
    except OSError:
        pass                                 # an unwritable cache only costs a re-probe next time


def _probe(cmd, timeout=20):
    """First non-empty output line of a command, or None."""
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return None
    for line in ((r.stdout or "") + "\n" + (r.stderr or "")).splitlines():
        if line.strip():
            return line.strip()
    return None


def _slow(disk, key, exe, probe):
    """Run probe() unless the executable is unchanged since a remembered answer."""
    sig = _sig(exe)
    if sig is None:
        return None
    rec = disk.get(key)
    if rec and rec.get("sig") == sig and rec.get("exe") == exe:
        return rec.get("value")
    value = probe()
    disk[key] = {"exe": exe, "sig": sig, "value": value}
    return value


def _win_file_version(path):
    """The FileVersion resource of a Windows exe (LTspice has no --version flag), via version.dll."""
    if os.name != "nt":
        return None
    try:
        import ctypes
        from ctypes import wintypes
        ver = ctypes.WinDLL("version", use_last_error=True)
        size = ver.GetFileVersionInfoSizeW(path, None)
        if not size:
            return None
        buf = ctypes.create_string_buffer(size)
        if not ver.GetFileVersionInfoW(path, 0, size, buf):
            return None
        ptr, length = ctypes.c_void_p(), wintypes.UINT()
        if not ver.VerQueryValueW(buf, "\\", ctypes.byref(ptr), ctypes.byref(length)) or not length.value:
            return None

        class FixedInfo(ctypes.Structure):
            _fields_ = [("sig", wintypes.DWORD), ("struc", wintypes.DWORD),
                        ("ms", wintypes.DWORD), ("ls", wintypes.DWORD)]
        info = ctypes.cast(ptr, ctypes.POINTER(FixedInfo)).contents
        return "%d.%d.%d.%d" % (info.ms >> 16, info.ms & 0xFFFF, info.ls >> 16, info.ls & 0xFFFF)
    except Exception:
        return None


def _find_ltspice():
    for c in (os.environ.get("LTSPICE_PATH", ""),
              os.path.expandvars(r"%LOCALAPPDATA%\Programs\ADI\LTspice\LTspice.exe"),
              r"C:\Program Files\ADI\LTspice\LTspice.exe"):
        if c and os.path.isfile(c):
            return c
    return None


def _find_freerouting():
    """-> (executable or None, version or None). Mirrors boardgen/pcb.py: tools/freerouting/freerouting/."""
    exe = os.path.join(ROOT, "tools", "freerouting", "freerouting", "freerouting.exe")
    if not os.path.isfile(exe):
        return None, None
    version = None
    app = os.path.join(os.path.dirname(exe), "app")
    try:                                         # the jpackage config carries the app version
        with open(os.path.join(app, "freerouting.cfg"), encoding="utf-8", errors="replace") as f:
            m = re.search(r"app-version=([\w.\-]+)", f.read())
            version = m.group(1) if m else None
    except OSError:
        pass
    if not version:                              # else the jar's name: freerouting-2.4.1-*.jar / the MSI
        for name in sorted(os.listdir(app)) if os.path.isdir(app) else []:
            m = re.search(r"(\d+\.\d+\.\d+)", name)
            if m:
                version = m.group(1)
                break
    return exe, version


def _py_package(name):
    try:
        return importlib.metadata.version(name)
    except importlib.metadata.PackageNotFoundError:
        return None


def versions():
    """Dict of tool -> {"installed": bool, "version": str|None, "path": str|None}. Computed once per process."""
    if _VERSIONS:
        return _VERSIONS
    disk = _load_disk()
    before = json.dumps(disk, sort_keys=True)
    out = {}

    out["python"] = {"installed": True, "version": sys.version.split()[0], "path": sys.executable}

    cli = kicad_paths.CLI
    v = _slow(disk, "kicad-cli", cli, lambda: _probe([cli, "--version"]))
    out["kicad"] = {"installed": v is not None, "version": v, "path": cli if v else None,
                    "install_dir": kicad_paths.HOME}

    kpy = kicad_paths.PYTHON
    v = _slow(disk, "kicad-python", kpy, lambda: _probe([kpy, "-c", "import sys;print(sys.version.split()[0])"]))
    out["kicad_python"] = {"installed": v is not None, "version": v, "path": kpy if v else None}

    fr, frv = _find_freerouting()
    out["freerouting"] = {"installed": fr is not None, "version": frv, "path": fr}

    lt = _find_ltspice()
    v = _win_file_version(lt) if lt else None
    out["ltspice"] = {"installed": lt is not None, "version": v or ("unknown" if lt else None), "path": lt}

    for pkg in PY_PACKAGES:
        v = _py_package(pkg)
        out[pkg] = {"installed": v is not None, "version": v, "path": None}

    if json.dumps(disk, sort_keys=True) != before:
        _save_disk(disk)
    _VERSIONS.update(out)
    return _VERSIONS


def fingerprint():
    """Stable string for the stage cache key: versions only (paths and mtimes would make it machine-specific
    and needlessly volatile). Includes `installed: false` so installing a missing tool also invalidates."""
    v = versions()
    return "|".join("%s=%s" % (k, (v[k]["version"] if v[k]["installed"] else "-")) for k in sorted(v))


def short_fingerprint():
    return hashlib.sha256(fingerprint().encode("utf-8")).hexdigest()[:12]


if __name__ == "__main__":
    print(json.dumps(versions(), indent=2))
