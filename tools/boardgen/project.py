"""Find the project a generator stage is building, and import its netlist.

The generic stages (`make_sch`, `check_sch`, `make_outputs`) live here in `tools/boardgen/` as ONE
copy, but each run belongs to one project under `projects/<id>/`. This module is how a shared script
finds out which.

It used to be implicit: every stage sat inside `projects/<id>/gen/` and did
`sys.path.insert(0, HERE); import netlist`. That worked, but it meant four scripts were duplicated
per project - and they diverged. `make_sch.py` ended up with three different versions, two of them
carrying bugs that were fixed only in the third.

Resolution order:
  1. an explicit project id argument  ->  projects/<id>/gen
  2. the current working directory, if it contains a netlist.py (how `pipeline.py` runs stages)
"""
import os
import sys

# tools/boardgen/project.py -> tools/boardgen -> tools -> the workspace root
WORKSPACE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PROJECTS = os.path.join(WORKSPACE, "projects")


def gen_dir(project_id=None):
    if project_id:
        d = os.path.join(PROJECTS, project_id, "gen")
        if not os.path.isfile(os.path.join(d, "netlist.py")):
            raise SystemExit("no netlist.py for project %r (looked in %s)" % (project_id, d))
        return d

    cwd = os.getcwd()
    if os.path.isfile(os.path.join(cwd, "netlist.py")):
        return cwd

    raise SystemExit(
        "don't know which project to build.\n"
        "Pass a project id (e.g. `python tools/boardgen/make_sch.py blinky-555`), or run from a\n"
        "project's gen/ directory. Current directory: %s" % cwd)


def load_netlist(project_id=None):
    """Import the project's netlist.py and return it as a module.

    Also puts the project's gen/ on sys.path, because its own make_pcb.py and any project-local
    helpers expect to be importable by bare name.
    """
    d = gen_dir(project_id)
    if d not in sys.path:
        sys.path.insert(0, d)
    import netlist  # noqa: E402  - resolved from the path just inserted
    return netlist


def project_id_from_argv(argv):
    """The first argument that names a real project, or None.

    It must VALIDATE rather than take the first word it sees. These modules are also imported by a
    project's own make_pcb.py, which is invoked as `make_pcb.py place` - so a naive reading of argv[1]
    resolved the project id to "place" and the build died with
    "no netlist.py for project 'place'". Anything that isn't an actual project is ignored, and the
    caller falls back to the working directory.
    """
    for a in argv[1:]:
        if a.startswith("-"):
            continue
        if os.path.isfile(os.path.join(PROJECTS, a, "gen", "netlist.py")):
            return a
    return None
