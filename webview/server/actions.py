"""Executes exactly what a project's manifest.json declares - a subprocess for "script" actions, a
plain file read for "file" actions. Nothing else. The action definitions are trusted local config
(written by whoever onboards a project), never anything from the browser - the frontend only ever sends
an action id, never a command.
"""
import os
import subprocess


def run_action(workspace_root, action):
    kind = action.get("kind")
    if kind == "file":
        path = os.path.join(workspace_root, action["path"])
        try:
            with open(path, encoding="utf-8") as f:
                return {"ok": True, "output": f.read(), "exit_code": 0}
        except OSError as e:
            return {"ok": False, "output": str(e), "exit_code": -1}

    if kind == "script":
        cwd = os.path.join(workspace_root, action.get("cwd", "."))
        try:
            result = subprocess.run(
                action["cmd"], cwd=cwd, capture_output=True, text=True, timeout=60,
            )
            output = result.stdout + (("\n" + result.stderr) if result.stderr else "")
            return {"ok": result.returncode == 0, "output": output, "exit_code": result.returncode}
        except subprocess.TimeoutExpired:
            return {"ok": False, "output": "action timed out after 60s", "exit_code": -1}
        except OSError as e:
            return {"ok": False, "output": str(e), "exit_code": -1}

    return {"ok": False, "output": f"unknown action kind: {kind!r}", "exit_code": -1}
