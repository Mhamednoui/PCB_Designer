"""CLI: python tools/boardgen/rules --list | --explain <RULE-ID or legacy name> | --check   (system Python, stdlib)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))   # tools/
from boardgen.rules import engine                                                                  # noqa: E402


def main(argv):
    try:
        if argv[:1] == ["--explain"] and len(argv) == 2:
            print(engine.explain(argv[1]))
        elif argv == ["--list"]:
            engine.REGISTRY.load_builtin()
            for r in sorted(engine.REGISTRY.rules.values(), key=lambda x: x.id):
                print("%-18s %-6s %s" % (r.id, r.severity, r.doc))
        elif argv == ["--check"]:
            problems = engine.selftest()
            for p in problems:
                print("  " + p)
            print("rule registry: %d rule(s), %s" % (len(engine.REGISTRY.rules),
                                                     "%d problem(s)" % len(problems) if problems else "OK"))
            return 1 if problems else 0
        else:
            print(__doc__)
            return 2
    except engine.RuleError as e:
        print("ERROR: %s" % e)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
