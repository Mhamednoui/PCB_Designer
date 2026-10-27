"""Generic .kicad_pcb reader - stdlib only, no KiCad/pcbnew import needed.

This is what makes the webview platform work for ANY KiCad project, not just ones built with this
workspace's scripted `gen/netlist.py` convention. Every KiCad project has a .kicad_pcb, and it already
contains everything the manifest needs: each footprint's reference, value, footprint id, and every pad's
net name.

Produces the same shape `build_manifest.py` expects from `gen/netlist.py`:
    components: [{ref, value, symbol(None), footprint, pins{pad: net}, group(None)}, ...]
    nets:       {net_name: ["REF.PAD", ...]}
"""
import os
import re


def tokenize(text):
    """S-expression tokenizer. Handles quoted strings (with backslash escapes) and comments."""
    token_re = re.compile(r'"(?:[^"\\]|\\.)*"|\(|\)|[^\s()]+')
    for match in token_re.finditer(text):
        yield match.group(0)


def parse_sexpr(text):
    """Returns a nested list. Quoted strings keep their value (unquoted, unescaped)."""
    stack = [[]]
    for token in tokenize(text):
        if token == "(":
            node = []
            stack[-1].append(node)
            stack.append(node)
        elif token == ")":
            if len(stack) > 1:
                stack.pop()
        elif token.startswith('"'):
            stack[-1].append(token[1:-1].replace('\\"', '"').replace("\\\\", "\\"))
        else:
            stack[-1].append(token)
    return stack[0]


def _children(node, name):
    return [c for c in node if isinstance(c, list) and c and c[0] == name]


def _property(footprint, key):
    for prop in _children(footprint, "property"):
        if len(prop) >= 3 and prop[1] == key:
            return prop[2]
    return None


def _pad_net(pad):
    """`(net "NAME")` or `(net 5 "NAME")` depending on KiCad version - accept both.

    Normalises the name so it matches what a schematic/netlist-based flow would call the same net, which
    is what `io_map.json`/`wokwi_map.json` are written against:
      - strips KiCad's leading hierarchical `/` (`/SEG_DATA` -> `SEG_DATA`)
      - drops KiCad's auto-generated `unconnected-(REF-PadN)` placeholder nets, which aren't real nets
        and would otherwise flood the manifest (62 of them on this board alone).
    """
    for net in _children(pad, "net"):
        for item in net[1:]:
            if isinstance(item, str) and not item.isdigit():
                if item.startswith("unconnected-("):
                    return None
                return item[1:] if item.startswith("/") else item
    return None


def parse_pcb(pcb_path):
    with open(pcb_path, encoding="utf-8") as f:
        tree = parse_sexpr(f.read())

    root = tree[0] if tree and isinstance(tree[0], list) else tree

    components = []
    nets = {}
    for footprint in _children(root, "footprint"):
        ref = _property(footprint, "Reference")
        if not ref or ref.startswith("#"):  # skip power symbols / unannotated
            continue
        footprint_id = footprint[1] if len(footprint) > 1 and isinstance(footprint[1], str) else None

        pins = {}
        for pad in _children(footprint, "pad"):
            pad_number = pad[1] if len(pad) > 1 and isinstance(pad[1], str) else ""
            net_name = _pad_net(pad)
            if not pad_number or not net_name:
                continue  # unnumbered mechanical pads (mounting holes) have neither
            pins[pad_number] = net_name
            nets.setdefault(net_name, set()).add(f"{ref}.{pad_number}")

        components.append({
            "ref": ref,
            "value": _property(footprint, "Value"),
            "symbol": None,  # the PCB doesn't know schematic symbols; icons fall back to ref-prefix
            "footprint": footprint_id,
            "pins": pins,
            "group": None,
        })

    components.sort(key=lambda c: c["ref"])
    return {
        "name": os.path.splitext(os.path.basename(pcb_path))[0],
        "components": components,
        "nets": {net: sorted(refs) for net, refs in nets.items()},
    }


def find_pcb(project_dir):
    """The project's main .kicad_pcb, ignoring backups/derived copies."""
    candidates = [
        f for f in os.listdir(project_dir)
        if f.endswith(".kicad_pcb") and "-backup" not in f and "-routed" not in f
    ]
    if not candidates:
        return None
    # Prefer one named after the folder, else the first alphabetically for determinism.
    preferred = os.path.basename(project_dir.rstrip("/\\")) + ".kicad_pcb"
    if preferred in candidates:
        return os.path.join(project_dir, preferred)
    return os.path.join(project_dir, sorted(candidates)[0])


if __name__ == "__main__":
    import sys
    import json
    data = parse_pcb(sys.argv[1])
    print(f"{len(data['components'])} components, {len(data['nets'])} nets")
    print(json.dumps(data["components"][:3], indent=2))
