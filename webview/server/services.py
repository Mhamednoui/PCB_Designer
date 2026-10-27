"""Service registry + proxy - how the platform grows without the core growing.

The core backend deliberately stays small: static files, the project registry, declared actions, and the
Wokwi live-simulation bridge. Everything added LATER (a SPICE service, a DRC service, a BOM/pricing
service, an AI review service, ...) should be its own process with its own HTTP API, registered here.
The core then just proxies to it. Adding a capability must never mean editing the core.

Register a service by dropping a `service.json` in `webview/services/<name>/`:

    {
      "name": "spice",
      "port": 8801,
      "health": "/health",
      "description": "Runs SPICE testbenches and returns structured results",
      "start": ["python", "service.py"]       // optional - documentation/convenience only
    }

It is then reachable through the core at:

    /api/services                     -> list every registered service and whether it's up
    /api/services/<name>/<anything>   -> proxied to http://127.0.0.1:<port>/<anything>

Contract each service must honour:
  - listen on 127.0.0.1 only (this is a local toolchain, never a network service)
  - expose its health path, returning 2xx when ready
  - speak JSON
  - own its domain completely: the core knows nothing about what it does, only where it lives

Services are started and stopped independently of the core (that's the point - one can crash, be
restarted, or be rewritten in another language without touching anything else).
"""
import json
import os
import urllib.error
import urllib.request

SERVICES_DIRNAME = "services"


def services_dir(webview_dir):
    return os.path.join(webview_dir, SERVICES_DIRNAME)


def load_services(webview_dir):
    """Every registered service, whether or not it's currently running."""
    root = services_dir(webview_dir)
    found = {}
    if not os.path.isdir(root):
        return found
    for entry in sorted(os.listdir(root)):
        config_path = os.path.join(root, entry, "service.json")
        if not os.path.isfile(config_path):
            continue
        try:
            with open(config_path, encoding="utf-8") as f:
                config = json.load(f)
        except (OSError, json.JSONDecodeError) as e:
            found[entry] = {"name": entry, "error": f"bad service.json: {e}"}
            continue
        config.setdefault("name", entry)
        config.setdefault("health", "/health")
        found[config["name"]] = config
    return found


def probe(config, timeout=0.5):
    """Is it up? Kept short - this runs on a page load, a dead service must not hang the UI."""
    port = config.get("port")
    if not port:
        return {"up": False, "detail": "no port in service.json"}
    url = f"http://127.0.0.1:{port}{config.get('health', '/health')}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            return {"up": 200 <= response.status < 300, "detail": f"HTTP {response.status}"}
    except urllib.error.HTTPError as e:
        return {"up": False, "detail": f"HTTP {e.code}"}
    except (urllib.error.URLError, OSError, ValueError) as e:
        return {"up": False, "detail": f"not reachable ({e.__class__.__name__})"}


def describe_all(webview_dir):
    out = []
    for name, config in load_services(webview_dir).items():
        entry = {
            "name": name,
            "description": config.get("description", ""),
            "port": config.get("port"),
            "start": config.get("start"),
        }
        entry.update(probe(config) if "error" not in config else {"up": False, "detail": config["error"]})
        out.append(entry)
    return out


def proxy(webview_dir, name, path, method, body, headers, timeout=30):
    """Forward a request to a registered service. Returns (status, content_type, body_bytes)."""
    config = load_services(webview_dir).get(name)
    if not config or not config.get("port"):
        return 404, "application/json", json.dumps({"error": f"no such service: {name}"}).encode()

    url = f"http://127.0.0.1:{config['port']}/{path.lstrip('/')}"
    request = urllib.request.Request(url, data=body, method=method)
    for key in ("Content-Type", "Accept"):
        if headers.get(key):
            request.add_header(key, headers[key])
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return (response.status,
                    response.headers.get("Content-Type", "application/json"),
                    response.read())
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", "application/json"), e.read()
    except (urllib.error.URLError, OSError) as e:
        return 502, "application/json", json.dumps({
            "error": f"service '{name}' is registered but not reachable on port {config['port']}",
            "detail": str(e),
            "hint": config.get("start") and f"start it with: {' '.join(config['start'])}",
        }).encode()
