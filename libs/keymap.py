"""Parse a ZMK .keymap into the JSON model the web page renders.

Ported unchanged from zmk-charybdis/tools/visualizer/server.py.
"""
import os
import re


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def _bindings(body):
    """'&kp A  &hml LALT R' -> [['kp','A'], ['hml','LALT','R']]"""
    return [part.split() for part in body.split("&")[1:] if part.strip()]


def _block(src, start):
    """Return the text inside the braces that open at or after index `start`."""
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        if src[j] == "{":
            depth += 1
        elif src[j] == "}":
            depth -= 1
            if depth == 0:
                return src[i + 1 : j]
    raise ValueError("unbalanced braces")


def parse_auto_mouse(config_dir):
    """Read the trackball's auto-mouse settings (zmk,input-processor-temp-layer) from the shield overlay."""
    am = {"layer": None, "timeout": 700, "idle": 0, "excluded": []}
    for root, _, files in os.walk(config_dir):
        for f in files:
            if not f.endswith((".overlay", ".dtsi")):
                continue
            src = _strip_comments(open(os.path.join(root, f), encoding="utf-8").read())
            for m in re.finditer(r"(\w+)\s*:\s*[\w-]+\s*\{", src):
                body = _block(src, m.end() - 1)
                if '"zmk,input-processor-temp-layer"' not in body:
                    continue
                idle = re.search(r"require-prior-idle-ms\s*=\s*<(\d+)>", body)
                ex = re.search(r"excluded-positions\s*=\s*<([^>]*)>", body)
                use = re.search(r"&" + m.group(1) + r"\s+(\d+)\s+(\d+)\s*>", src)
                am["idle"] = int(idle.group(1)) if idle else 0
                am["excluded"] = [int(x) for x in ex.group(1).split()] if ex else []
                if use:
                    am["layer"], am["timeout"] = int(use.group(1)), int(use.group(2))
                return am
    return am


def parse_keymap(path):
    src = _strip_comments(open(path, encoding="utf-8").read())
    defines = {k: int(v) for k, v in re.findall(r"^\s*#define\s+(\w+)\s+(\d+)\s*$", src, flags=re.M)}

    # hold-tap behaviours: name -> {hold: behaviour, tap: behaviour}
    hold_taps = {"mt": {"hold": "kp", "tap": "kp"}, "lt": {"hold": "mo", "tap": "kp"}}
    for m in re.finditer(r"(\w+)\s*:\s*[\w-]+\s*\{", src):
        body = _block(src, m.end() - 1)
        if '"zmk,behavior-hold-tap"' in body:
            b = re.search(r"bindings\s*=\s*<&(\w+)>\s*,\s*<&(\w+)>", body)
            if b:
                hold_taps[m.group(1)] = {"hold": b.group(1), "tap": b.group(2)}
    macros = [m.group(1) for m in re.finditer(r"(\w+)\s*:\s*[\w-]+\s*\{", src)
              if '"zmk,behavior-macro' in _block(src, m.end() - 1)]

    km_at = src.index('"zmk,keymap"')
    km = src[km_at:]
    layers = []
    for m in re.finditer(r"(\w+)\s*\{\s*(?:display-name\s*=\s*\"([^\"]*)\"\s*;)?\s*bindings\s*=\s*<(.*?)>\s*;", km, re.S):
        layers.append({"id": m.group(1), "name": m.group(2) or m.group(1), "bindings": _bindings(m.group(3))})

    combos = []
    cm = re.search(r"combos\s*\{", src)
    if cm:
        for m in re.finditer(r"(\w+)\s*\{([^{}]*)\}", _block(src, cm.end() - 1)):
            body = m.group(2)
            kp = re.search(r"key-positions\s*=\s*<([^>]*)>", body)
            b = re.search(r"bindings\s*=\s*<([^>]*)>", body)
            ly = re.search(r"layers\s*=\s*<([^>]*)>", body)
            if kp and b:
                lay = [defines.get(t, t) for t in ly.group(1).split()] if ly else []
                combos.append({
                    "id": m.group(1),
                    "positions": [int(x) for x in kp.group(1).split()],
                    "binding": _bindings(b.group(1))[0],
                    "layers": [int(x) for x in lay if str(x).isdigit()],
                })

    return {
        "autoMouse": parse_auto_mouse(os.path.dirname(path)),
        "file": os.path.relpath(path),
        "mtime": os.path.getmtime(path),
        "defines": defines,
        "holdTaps": hold_taps,
        "macros": macros,
        "layers": layers,
        "combos": combos,
    }


# --------------------------------------------------------------------------- git ref

CACHE_DIR = os.path.join(os.path.expanduser("~"), ".cache", "keyboard-companion", "keymaps")


def _git(repo, *args):
    import subprocess

    return subprocess.run(["git", "-C", repo, *args], check=True, capture_output=True).stdout


def keymap_at_ref(path, ref):
    """Return (local path, label) for the keymap as committed on a git ref.

    The keymap's folder (overlays included, for the auto-mouse settings) is
    extracted once per commit into ~/.cache, so the page shows what's on a branch
    (e.g. the one that's flashed) whatever is checked out in the working tree.
    """
    import io
    import tarfile

    folder = os.path.dirname(os.path.abspath(path))
    repo = _git(folder, "rev-parse", "--show-toplevel").decode().strip()
    rel = os.path.relpath(os.path.abspath(path), repo)
    sha = _git(repo, "rev-parse", "--verify", ref + "^{commit}").decode().strip()
    dest = os.path.join(CACHE_DIR, sha)
    if not os.path.isdir(dest):
        data = _git(repo, "archive", "--format=tar", sha, "--", os.path.dirname(rel))
        tmp = dest + ".tmp"
        with tarfile.open(fileobj=io.BytesIO(data)) as tar:
            tar.extractall(tmp, filter="data")
        os.replace(tmp, dest)
    return os.path.join(dest, rel), f"{ref} ({sha[:7]}):{rel}"
