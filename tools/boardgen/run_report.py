"""Run report for one `pipeline.py` run: parsing stage output, git identity, and the JSON + HTML writers.

Layout written next to the project's other outputs (git-ignored, last RUNS_KEPT kept):

    projects/<id>/out/run/<UTC timestamp>/
        report.json     machine-readable, schema "pcb-run-report/1" (see `new_report`)
        report.html     the same, self-contained (no external assets), for a human
        <stage>.log     the FULL stdout+stderr of each stage that actually ran

The report is meant to make any failure reproducible from the report alone: the git commit (+ dirty flag),
every tool version, and for each stage its exact command, working directory, extra environment, and the
sha256 of every declared input file.

`findings` per stage is deliberately an empty list today: the error taxonomy (rule id / severity / location /
measured vs limit / fix) is PA-7. The slot exists so PA-7 fills it without a schema change.
"""
import datetime
import html
import json
import os
import re
import shutil
import subprocess

SCHEMA = "pcb-run-report/1"
RUNS_KEPT = 10
TAIL_LINES = 60

# ---------------------------------------------------------------------------------------- output parsing
# Each rule: (regex, builder(match) -> dict merged into the stage's `counts`). Order does not matter; add a
# line here when a stage prints a summary worth keeping as numbers. Everything is optional - a stage that
# prints none of these just has empty counts.
_COUNT_RULES = [
    (re.compile(r"^DRC gate: (\d+) errors, (\d+) unconnected, (\d+) parity, (\d+) warnings -> (PASS|FAIL)", re.M),
     lambda m: {"drc_errors": int(m[1]), "drc_unconnected": int(m[2]), "drc_parity": int(m[3]),
                "drc_warnings": int(m[4]), "drc_gate": m[5]}),
    (re.compile(r"^decap distance: examined (\d+) IC supply pins, skipped (\d+), (\d+) violations", re.M),
     lambda m: {"decap_examined": int(m[1]), "decap_skipped": int(m[2]), "decap_violations": int(m[3])}),
    (re.compile(r"^catch rate (\d+)/(\d+)", re.M),
     lambda m: {"catch_caught": int(m[1]), "catch_total": int(m[2])}),
    (re.compile(r"^FAILED: (\d+) (?:lint |parts |unwaived gating review )?(errors?|findings?)", re.M),
     lambda m: {"failed_count": int(m[1])}),
    (re.compile(r"^FAILED: (\d+) opens, (\d+) shorts", re.M),
     lambda m: {"lvs_opens": int(m[1]), "lvs_shorts": int(m[2])}),
    (re.compile(r"\bERC[^\n]*?(\d+) errors?", re.M),
     lambda m: {"erc_errors": int(m[1])}),
]
_FAILED_LINE = re.compile(r"^(?:\s*)(FAILED:.*|route FAILED:.*|CMD FAILED.*)$", re.M)
_ERROR_LINE = re.compile(r"^\s*(?:ERROR|error:|Traceback)")
_SUMMARY_HINTS = re.compile(r"^(ERROR|DRC gate:|decap distance:|catch rate|FAILED:|PASS|OK\b|netlist compare|ERC)", re.M)


def parse_output(text):
    """-> (counts dict, failed_line or None, summary lines list) from a stage's full output."""
    counts = {}
    for rx, build in _COUNT_RULES:
        m = rx.search(text)
        if m:
            counts.update(build(m))
    m = _FAILED_LINE.search(text)
    failed = m.group(1).strip() if m else None
    summary = []
    for line in text.splitlines():
        if _SUMMARY_HINTS.match(line.strip()) and line.strip() not in summary:
            summary.append(line.strip())
    first_error = next((l.strip() for l in text.splitlines() if _ERROR_LINE.match(l)), None)
    if failed and first_error and first_error not in failed:
        failed = "%s [first error: %s]" % (failed, first_error)
    return counts, failed, summary[:12]


def tail_lines(text, n=TAIL_LINES):
    lines = text.splitlines()
    return lines[-n:]


# ------------------------------------------------------------------------------------------------- git
def _git(root, *args):
    try:
        r = subprocess.run(["git", "-C", root] + list(args), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.SubprocessError):
        return None


def git_info(root):
    commit = _git(root, "rev-parse", "HEAD")
    if not commit:
        return {"available": False, "commit": None, "branch": None, "dirty": None, "dirty_files": []}
    porcelain = _git(root, "status", "--porcelain") or ""
    files = [l[3:] for l in porcelain.splitlines() if l.strip()]
    return {"available": True, "commit": commit, "branch": _git(root, "rev-parse", "--abbrev-ref", "HEAD"),
            "dirty": bool(files), "dirty_files": files[:30], "dirty_file_count": len(files)}


# ------------------------------------------------------------------------------------------- run dirs
def utc_stamp(now=None):
    return (now or datetime.datetime.now(datetime.timezone.utc)).strftime("%Y%m%dT%H%M%SZ")


def make_run_dir(project_dir):
    """Create out/run/<UTC timestamp>/ (a numeric suffix if two runs start in the same second)."""
    base = os.path.join(project_dir, "out", "run")
    os.makedirs(base, exist_ok=True)
    stamp, n = utc_stamp(), 0
    while True:
        path = os.path.join(base, stamp if n == 0 else "%s-%d" % (stamp, n))
        try:
            os.mkdir(path)
            return path
        except FileExistsError:
            n += 1


def prune(project_dir, keep=RUNS_KEPT):
    """Delete the oldest run directories beyond `keep` (names sort chronologically)."""
    base = os.path.join(project_dir, "out", "run")
    try:
        runs = sorted(d for d in os.listdir(base) if os.path.isdir(os.path.join(base, d)))
    except OSError:
        return []
    gone = runs[:-keep] if len(runs) > keep else []
    for d in gone:
        shutil.rmtree(os.path.join(base, d), ignore_errors=True)
    return gone


# ----------------------------------------------------------------------------------------- the report
def new_report(project, pipeline_argv, toolchain_versions, git, design_snapshot):
    return {
        "schema": SCHEMA,
        "project": project,
        "started_utc": datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "finished_utc": None,
        "duration_s": None,
        "result": "running",               # ok | FAILED | interrupted
        "failed_stage": None,
        "failure_reason": None,
        "pipeline_argv": pipeline_argv,
        "reproduce": None,
        "git": git,
        "toolchain": toolchain_versions,
        "design_snapshot": design_snapshot,  # sha256 of the files that define the design (for design stages)
        "not_applicable": [],
        "deselected": [],
        "stages": [],
    }


def stage_record(entry, command, cwd, env_extra, inputs, cache_key):
    return {
        "name": entry["name"],
        "description": entry["description"],
        "status": "pending",               # ok | FAILED | cached | skipped | interrupted
        "design_stage": entry["design_stage"],
        "argv": command,
        "cwd": cwd,
        "env_extra": env_extra,
        "inputs": inputs,                  # [{"path", "sha256"}] - the registry's declared inputs, by content
        "cache_key": cache_key,
        "cache_note": None,
        "exit_code": None,
        "duration_s": None,
        "counts": {},
        "summary": [],
        "failure": None,                   # the FAILED: line, else "exit code N: <last output line>"
        "log": None,                       # file name inside the run dir (full output)
        "tail": [],                        # last TAIL_LINES lines of the output
        "findings": [],                    # reserved for PA-7 (rule id / severity / location / measured / fix)
    }


def finish_report(report, started_monotonic, now_monotonic, result):
    report["finished_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report["duration_s"] = round(now_monotonic - started_monotonic, 2)
    report["result"] = result
    bad = next((s for s in report["stages"] if s["status"] == "FAILED"), None)
    if bad:
        report["failed_stage"] = bad["name"]
        report["failure_reason"] = bad["failure"]
    g = report["git"]
    pa = " ".join(report["pipeline_argv"])
    report["reproduce"] = (
        ("git checkout %s%s && " % (g["commit"], " (+ the uncommitted changes listed in git.dirty_files)" if g.get("dirty") else ""))
        if g.get("commit") else "") + "python pipeline.py %s" % pa
    return report


def write_report(run_dir, report):
    with open(os.path.join(run_dir, "report.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(report, f, indent=1)
        f.write("\n")
    with open(os.path.join(run_dir, "report.html"), "w", encoding="utf-8", newline="\n") as f:
        f.write(render_html(report))


# ------------------------------------------------------------------------------------------------ HTML
_CSS = """
:root{--bg:#fafafa;--fg:#1c1f23;--mut:#5b6670;--card:#fff;--line:#d9dee3;--ok:#1a7f37;--bad:#cf222e;--warn:#9a6700;
--cache:#0969da;--skip:#6e7781;--code:#f3f5f7}
@media (prefers-color-scheme:dark){:root{--bg:#0f1317;--fg:#e6e9ec;--mut:#9aa5b1;--card:#171c21;--line:#2b333b;
--ok:#3fb950;--bad:#ff7b72;--warn:#d29922;--cache:#58a6ff;--skip:#8b949e;--code:#0c1014}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--fg);font:14px/1.45 system-ui,Segoe UI,sans-serif;
padding:16px;max-width:1100px;margin-inline:auto}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px}
.mut{color:var(--mut)}.big{font-size:15px;font-weight:600}
.banner{border:1px solid var(--line);border-left-width:6px;background:var(--card);border-radius:6px;padding:10px 14px;margin:12px 0}
.banner.ok{border-left-color:var(--ok)}.banner.bad{border-left-color:var(--bad)}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:6px}
th,td{text-align:left;padding:6px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;color:var(--mut);font-weight:600}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.chip{display:inline-block;padding:1px 8px;border-radius:10px;font-size:12px;font-weight:600;border:1px solid currentColor}
.ok{color:var(--ok)}.FAILED,.bad{color:var(--bad)}.cached{color:var(--cache)}.skipped,.pending{color:var(--skip)}
.interrupted{color:var(--warn)}
details{background:var(--card);border:1px solid var(--line);border-radius:6px;margin:8px 0;padding:6px 12px}
details>summary{cursor:pointer;font-weight:600}
pre{background:var(--code);border:1px solid var(--line);border-radius:4px;padding:8px;overflow:auto;font:12px/1.4 Consolas,monospace;
white-space:pre-wrap;word-break:break-word;margin:6px 0}
code{font:12px Consolas,monospace;background:var(--code);padding:1px 4px;border-radius:3px}
.kv{display:grid;grid-template-columns:max-content 1fr;gap:2px 14px}.kv div:nth-child(odd){color:var(--mut)}
.hash{font:11px Consolas,monospace;color:var(--mut)}
@media (max-width:640px){body{padding:10px}th,td{padding:5px 6px}.kv{grid-template-columns:1fr}}
"""


def _e(x):
    return html.escape("" if x is None else str(x))


def _chip(status):
    return '<span class="chip %s">%s</span>' % (_e(status), _e(status))


def _secs(v):
    return "" if v is None else "%.1f" % v


def render_html(r):
    g, ok = r["git"], r["result"] == "ok"
    out = ['<!doctype html><html lang="en"><head><meta charset="utf-8">',
           '<meta name="viewport" content="width=device-width,initial-scale=1">',
           "<title>Run report - %s</title><style>%s</style></head><body>" % (_e(r["project"]), _CSS),
           "<h1>Run report - %s</h1>" % _e(r["project"]),
           '<div class="mut">%s &middot; %s s &middot; <code>python %s</code></div>' % (
               _e(r["started_utc"]), _e(r["duration_s"]), _e(" ".join(r["pipeline_argv"]))),
           '<div class="banner %s"><span class="big">%s</span>' % ("ok" if ok else "bad",
                                                                 "All stages passed" if ok else _e(r["result"]))]
    if r["failed_stage"]:
        out.append('<div>Stage <b>%s</b> failed: <code>%s</code> &mdash; full output in <code>%s.log</code></div>'
                   % (_e(r["failed_stage"]), _e(r["failure_reason"]), _e(r["failed_stage"])))
    out.append("</div>")

    out.append("<h2>Stages</h2><table><tr><th>Stage</th><th>Result</th><th>Exit</th><th class='n'>Seconds</th>"
               "<th>Counts</th></tr>")
    for s in r["stages"]:
        counts = ", ".join("%s=%s" % (k, v) for k, v in s["counts"].items())
        out.append("<tr><td><a href='#st-%s'>%s</a></td><td>%s</td><td>%s</td><td class='n'>%s</td><td>%s</td></tr>"
                   % (_e(s["name"]), _e(s["name"]), _chip(s["status"]), _e(s["exit_code"]),
                      _e(_secs(s["duration_s"])), _e(counts)))
    out.append("</table>")
    if r["not_applicable"] or r["deselected"]:
        out.append('<p class="mut">Not applicable to this project: %s. Deselected by --only/--skip: %s.</p>'
                   % (_e(", ".join(r["not_applicable"]) or "none"), _e(", ".join(r["deselected"]) or "none")))

    out.append("<h2>Stage details</h2>")
    for s in r["stages"]:
        opened = " open" if s["status"] == "FAILED" else ""
        out.append("<details id='st-%s'%s><summary>%s %s</summary><div class='kv'>" % (
            _e(s["name"]), opened, _e(s["name"]), _chip(s["status"])))
        rows = [("What", s["description"]),
                ("Command", " ".join(s["argv"]) if s["argv"] else ""),
                ("Working dir", s["cwd"]),
                ("Extra environment", ", ".join("%s=%s" % kv for kv in (s["env_extra"] or {}).items()) or "none"),
                ("Exit code", s["exit_code"]), ("Duration", (_secs(s["duration_s"]) + " s") if s["duration_s"] is not None else ""),
                ("Cache key", s["cache_key"] or "(not cacheable)"), ("Cache note", s["cache_note"]),
                ("Log", s["log"] or "(no output captured)")]
        for k, v in rows:
            out.append("<div>%s</div><div>%s</div>" % (_e(k), "<code>%s</code>" % _e(v) if k in ("Command", "Log", "Cache key") and v else _e(v)))
        out.append("</div>")
        if s["failure"]:
            out.append('<p class="bad"><b>Failure:</b> <code>%s</code></p>' % _e(s["failure"]))
        if s["summary"]:
            out.append("<div><b>Summary lines</b></div><pre>%s</pre>" % _e("\n".join(s["summary"])))
        if s["tail"]:
            out.append("<div><b>Last %d lines of output</b></div><pre>%s</pre>" % (len(s["tail"]), _e("\n".join(s["tail"]))))
        if s["inputs"]:
            out.append("<details><summary>%d input files (sha256)</summary><pre>%s</pre></details>" % (
                len(s["inputs"]), _e("\n".join("%s  %s" % (i["sha256"], i["path"]) for i in s["inputs"]))))
        if s["findings"]:
            out.append("<div><b>Findings</b></div><pre>%s</pre>" % _e(json.dumps(s["findings"], indent=1)))
        out.append("</details>")

    out.append("<h2>Reproduce</h2><pre>%s</pre>" % _e(r["reproduce"]))
    out.append("<h2>Git</h2><div class='kv'><div>Commit</div><div><code>%s</code></div><div>Branch</div><div>%s</div>"
               "<div>Working tree</div><div>%s</div></div>" % (
                   _e(g.get("commit") or "(not a git checkout)"), _e(g.get("branch")),
                   "unknown" if g.get("dirty") is None else
                   ("<b class='bad'>DIRTY</b> - %d changed file(s)" % g.get("dirty_file_count", 0) if g["dirty"] else "clean")))
    if g.get("dirty_files"):
        out.append("<details><summary>changed files</summary><pre>%s</pre></details>" % _e("\n".join(g["dirty_files"])))

    out.append("<h2>Toolchain</h2><table><tr><th>Tool</th><th>Version</th><th>Path</th></tr>")
    for name in sorted(r["toolchain"]):
        t = r["toolchain"][name]
        out.append("<tr><td>%s</td><td>%s</td><td class='hash'>%s</td></tr>" % (
            _e(name), _e(t["version"]) if t["installed"] else "<span class='mut'>not installed</span>", _e(t.get("path"))))
    out.append("</table>")

    out.append("<details><summary>Design snapshot (%d files, sha256)</summary><pre>%s</pre></details>" % (
        len(r["design_snapshot"]), _e("\n".join("%s  %s" % (i["sha256"], i["path"]) for i in r["design_snapshot"]))))
    out.append("</body></html>\n")
    return "".join(out)
