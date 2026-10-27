"""Minimal KiCad S-expression parser/serializer + symbol library helpers."""
import copy
import re

_TOKEN = re.compile(r'\s*(?:(\()|(\))|("(?:[^"\\]|\\.)*")|([^\s()"]+))')


class Sym(str):
    """Bare (unquoted) atom."""


def parse(text):
    stack = [[]]
    pos = 0
    n = len(text)
    while pos < n:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip() == "":
                break
            raise ValueError("parse error at %d: %r" % (pos, text[pos:pos + 40]))
        pos = m.end()
        if m.group(1):
            stack.append([])
        elif m.group(2):
            done = stack.pop()
            stack[-1].append(done)
        elif m.group(3) is not None:
            s = m.group(3)[1:-1]
            s = s.replace('\\"', '"').replace("\\\\", "\\").replace("\\n", "\n")
            stack[-1].append(s)
        else:
            stack[-1].append(Sym(m.group(4)))
    return stack[0][0]


def _q(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n") + '"'


def dumps(node, indent=0):
    if isinstance(node, list):
        simple = all(not isinstance(x, list) for x in node)
        if simple:
            return "(" + " ".join(dumps(x) for x in node) + ")"
        pad = "\t" * (indent + 1)
        parts = []
        head = []
        for x in node:
            if not isinstance(x, list) and not parts:
                head.append(dumps(x))
            else:
                parts.append(pad + dumps(x, indent + 1))
        return "(" + " ".join(head) + "\n" + "\n".join(parts) + "\n" + "\t" * indent + ")"
    if isinstance(node, Sym):
        return str(node)
    if isinstance(node, bool):
        return "yes" if node else "no"
    if isinstance(node, (int, float)):
        return fmt(node)
    return _q(node)


def fmt(v):
    if isinstance(v, int):
        return str(v)
    s = "%.4f" % v
    s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def find(node, key):
    for x in node:
        if isinstance(x, list) and x and x[0] == key:
            return x
    return None


def find_all(node, key):
    return [x for x in node if isinstance(x, list) and x and x[0] == key]


_lib_cache = {}


def load_lib(path):
    if path not in _lib_cache:
        with open(path, encoding="utf-8") as f:
            _lib_cache[path] = parse(f.read())
    return _lib_cache[path]


def get_symbol(path, name):
    """Return a flattened copy of symbol `name` (resolves `extends`)."""
    lib = load_lib(path)
    syms = {x[1]: x for x in find_all(lib, "symbol")}
    if name not in syms:
        raise KeyError("%s not in %s" % (name, path))
    s = syms[name]
    ext = find(s, "extends")
    if not ext:
        return copy.deepcopy(s)
    parent_name = ext[1]
    parent = get_symbol(path, parent_name)
    child_props = {p[1]: p for p in find_all(s, "property")}
    new = [Sym("symbol"), name]
    for item in parent[2:]:
        if isinstance(item, list) and item and item[0] == "property" and item[1] in child_props:
            new.append(copy.deepcopy(child_props.pop(item[1])))
        elif isinstance(item, list) and item and item[0] == "symbol":
            it = copy.deepcopy(item)
            it[1] = name + it[1][len(parent_name):]
            new.append(it)
        else:
            new.append(copy.deepcopy(item))
    for p in child_props.values():
        new.append(copy.deepcopy(p))
    return new


def symbol_pins(sym, unit=1, body_style=1):
    """List of dicts for pins in unit (plus common unit 0)."""
    name = sym[1]
    pins = []
    for sub in find_all(sym, "symbol"):
        suffix = sub[1][len(name) + 1:]
        try:
            u, b = [int(x) for x in suffix.split("_")]
        except ValueError:
            continue
        if u not in (0, unit) or b not in (0, body_style):
            continue
        for p in find_all(sub, "pin"):
            at = find(p, "at")
            pins.append({
                "type": str(p[1]),
                "x": float(at[1]), "y": float(at[2]),
                "rot": float(at[3]) if len(at) > 3 else 0.0,
                "length": float(find(p, "length")[1]),
                "name": find(p, "name")[1],
                "number": find(p, "number")[1],
                "hidden": any(isinstance(t, Sym) and t == "hide" for t in p)
                          or (find(p, "hide") is not None and str(find(p, "hide")[1]) != "no"),
            })
    return pins


def symbol_units(sym):
    name = sym[1]
    units = set()
    for sub in find_all(sym, "symbol"):
        suffix = sub[1][len(name) + 1:]
        try:
            u, _ = [int(x) for x in suffix.split("_")]
            if u > 0:
                units.add(u)
        except ValueError:
            pass
    return sorted(units) or [1]


def prop(sym, key):
    for p in find_all(sym, "property"):
        if p[1] == key:
            return p[2]
    return None
