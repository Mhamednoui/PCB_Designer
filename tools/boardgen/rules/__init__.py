"""Rule engine package (P2-T1). One rule per file in this directory (`lint_short.py`, ...); see engine.py.

    python tools/boardgen/rules --list | --explain <RULE-ID> | --check      (or: python pipeline.py --explain <RULE-ID>)
"""
from boardgen.rules.engine import (REGISTRY, Registry, Rule, RuleError, apply_waivers, check_fixtures, explain,  # noqa: F401
                                   rule, run, selftest, write_findings)
from boardgen.rules.finding import SEVERITIES, Finding, FindingError  # noqa: F401
