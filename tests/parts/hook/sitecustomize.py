"""Test-only hook: redirects the parts registry to another records dir without touching tools/.

run_mutations.py puts this directory on PYTHONPATH and sets PARTS_RECORDS_DIR for entries that use the
`records` op. Python imports `sitecustomize` at start-up; this registers an import hook that, right after
`boardgen.parts` (or `parts`) finishes loading, points its RECORDS_DIR at $PARTS_RECORDS_DIR.
Both lint (prepare_registry) and parts.registry() read that variable at call time, so the swap is enough.
"""
import importlib.abc
import os
import sys
from pathlib import Path

_TARGETS = ("boardgen.parts", "parts")


class _Patch(importlib.abc.MetaPathFinder):
    def find_spec(self, name, path, target=None):
        d = os.environ.get("PARTS_RECORDS_DIR")
        if name not in _TARGETS or not d:
            return None
        sys.meta_path.remove(self)
        try:
            import importlib.util
            spec = importlib.util.find_spec(name)
        finally:
            sys.meta_path.insert(0, self)
        if spec is None or spec.loader is None:
            return None
        inner = spec.loader.exec_module

        def exec_module(module, _inner=inner, _d=d):
            _inner(module)
            module.RECORDS_DIR = Path(_d)
        spec.loader.exec_module = exec_module
        return spec


if os.environ.get("PARTS_RECORDS_DIR"):
    sys.meta_path.insert(0, _Patch())
