"""ZSA Voyager support: the Oryx layout as a keymap model, and the matrix -> key map.

The layout is read from Oryx's public GraphQL API (the same query zmk-charybdis uses
to port it) and turned into the JSON model web/keymap.js renders for ZMK keymaps:
layers of ZMK-style bindings (["kp", "A"], ["mt", "LALT", "A"], ["lt", "1", "BSPC"]),
plus "geometry": "voyager" so the page draws the Voyager.

Oryx lists a layer's 52 keys left half first (4 rows of 6, then the 2 thumb keys),
then the right half the same way. The keyboard reports key presses by matrix
(row, col); MATRIX_TO_INDEX turns those into that order.
"""
import json
import logging
import time
import urllib.request

ORYX_API = "https://oryx.zsa.io/graphql"
REFRESH_EVERY = 60.0  # seconds: Oryx edits show up within a minute, without hammering the API

QUERY = """query getLayout($hashId: String!, $revisionId: String!, $geometry: String) {
  layout(hashId: $hashId, geometry: $geometry, revisionId: $revisionId) {
    title
    revision { hashId createdAt layers { title position keys } combos { keyIndices layerIdx trigger name } }
  }
}"""


def _voyager_matrix():
    """(row, col) -> Oryx key index, from the LAYOUT order in zsa/qmk_firmware keyboards/zsa/voyager/keyboard.json."""
    layout = [
        (0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6), (6, 0), (6, 1), (6, 2), (6, 3), (6, 4), (6, 5),
        (1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (7, 0), (7, 1), (7, 2), (7, 3), (7, 4), (7, 5),
        (2, 1), (2, 2), (2, 3), (2, 4), (2, 5), (2, 6), (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5),
        (3, 1), (3, 2), (3, 3), (3, 4), (3, 5), (4, 4), (10, 2), (9, 1), (9, 2), (9, 3), (9, 4), (9, 5),
        (5, 0), (5, 1), (11, 5), (11, 6),
    ]
    out = {}
    for i, rc in enumerate(layout):
        if i < 48:
            r, c = divmod(i, 12)
            out[rc] = r * 6 + c if c < 6 else 26 + r * 6 + (c - 6)
        else:
            out[rc] = {48: 24, 49: 25, 50: 50, 51: 51}[i]
    return out


MATRIX_TO_INDEX = _voyager_matrix()

# ------------------------------------------------------------------ Oryx keycode -> ZMK token
KC = {
    "ESCAPE": "ESC", "ENTER": "RET", "SPACE": "SPACE", "TAB": "TAB", "BSPC": "BSPC", "DELETE": "DEL",
    "MINUS": "MINUS", "EQUAL": "EQUAL", "QUOTE": "SQT", "DQUO": "DQT", "COMMA": "COMMA", "DOT": "DOT",
    "SLASH": "FSLH", "QUES": "QMARK", "SCLN": "SEMI", "COLN": "COLON", "BSLS": "BSLH", "GRAVE": "GRAVE",
    "TILD": "TILDE", "EXLM": "EXCL", "AT": "AT", "HASH": "HASH", "DLR": "DOLLAR", "PERC": "PRCNT",
    "CIRC": "CARET", "AMPR": "AMPS", "ASTR": "STAR", "LPRN": "LPAR", "RPRN": "RPAR", "LBRC": "LBKT",
    "RBRC": "RBKT", "LCBR": "LBRC", "RCBR": "RBRC", "PLUS": "PLUS", "PIPE": "PIPE", "UNDS": "UNDER",
    "LABK": "LT", "RABK": "GT", "UP": "UP", "DOWN": "DOWN", "LEFT": "LEFT", "RIGHT": "RIGHT",
    "PAGE_UP": "PG_UP", "PGUP": "PG_UP", "PGDN": "PG_DN", "PAGE_DOWN": "PG_DN", "HOME": "HOME", "END": "END",
    "INSERT": "INS", "CAPS": "CAPS", "CAPS_LOCK": "CAPS", "PSCR": "PSCRN", "PRINT_SCREEN": "PSCRN",
    "LEFT_ALT": "LALT", "LEFT_GUI": "LGUI", "LEFT_SHIFT": "LSHFT", "LEFT_CTRL": "LCTRL",
    "RIGHT_ALT": "RALT", "RIGHT_GUI": "RGUI", "RIGHT_SHIFT": "RSHFT", "RIGHT_CTRL": "RCTRL",
    "AUDIO_VOL_UP": "C_VOL_UP", "AUDIO_VOL_DOWN": "C_VOL_DN", "AUDIO_MUTE": "C_MUTE",
    "MEDIA_PLAY_PAUSE": "C_PP", "MEDIA_NEXT_TRACK": "C_NEXT", "MEDIA_PREV_TRACK": "C_PREV",
    "MEDIA_STOP": "C_STOP",
}
for _c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
    KC[_c] = _c
for _d in "0123456789":
    KC[_d] = "N" + _d
for _f in range(1, 25):
    KC[f"F{_f}"] = f"F{_f}"

MODS = {"LEFT_ALT", "LEFT_GUI", "LEFT_SHIFT", "LEFT_CTRL", "RIGHT_ALT", "RIGHT_GUI", "RIGHT_SHIFT", "RIGHT_CTRL"}
MODFN = {"leftCtrl": "LC", "leftShift": "LS", "leftAlt": "LA", "leftGui": "LG",
         "rightCtrl": "RC", "rightShift": "RS", "rightAlt": "RA", "rightGui": "RG"}
# Codes that aren't plain keys: shown as a label
LABEL = {
    "QK_LLCK": "Lock", "QK_BOOT": "Boot", "DRAG_SCROLL": "Scroll", "TOGGLE_SCROLL": "Scroll ⇄",
    "NAVIGATOR_AIM": "Aim", "NAVIGATOR_TURBO": "Turbo", "NAVIGATOR_INC_CPI": "CPI+", "NAVIGATOR_DEC_CPI": "CPI−",
    "RGB_TOG": "RGB", "RGB_MODE_FORWARD": "Effect", "RGB_SLD": "Solid", "TOGGLE_LAYER_COLOR": "Layer clr",
    "RGB_HUI": "Hue+", "RGB_HUD": "Hue−", "RGB_SAI": "Sat+", "RGB_SAD": "Sat−", "RGB_SPI": "Speed+", "RGB_SPD": "Speed−",
}
SPECIAL = {
    "CW_TOGG": ["caps_word"], "RGB_VAI": ["rgb_ug", "RGB_BRI"], "RGB_VAD": ["rgb_ug", "RGB_BRD"],
    "MS_BTN1": ["mkp", "LCLK"], "MS_BTN2": ["mkp", "RCLK"], "MS_BTN3": ["mkp", "MCLK"],
    "MS_BTN4": ["mkp", "MB4"], "MS_BTN5": ["mkp", "MB5"],
}
LAYER_CODES = {"MO": "mo", "TO": "to", "TG": "tog", "OSL": "sl", "TT": "mo", "DF": "to"}


def _code(action):
    c = (action or {}).get("code")
    return c[3:] if c and c.startswith("KC_") else c


def _key(action):
    """A plain key with its modifiers as a ZMK token (LC(X)), or None if it isn't one."""
    c = _code(action)
    if c not in KC:
        return None
    tok = KC[c]
    for m, on in ((action.get("modifiers") or {}).items()):
        if on and m in MODFN:
            tok = f"{MODFN[m]}({tok})"
    return tok


def _tap(action):
    """One action (an Oryx key's tap) as a ZMK binding."""
    c = _code(action)
    if c is None:
        return ["none"]
    if c == "TRANSPARENT":
        return ["trans"]
    if c == "NO":
        return ["none"]
    if c in LAYER_CODES:
        return [LAYER_CODES[c], str(action.get("layer") or 0)]
    if c in SPECIAL:
        return list(SPECIAL[c])
    if c in LABEL:
        return ["lbl", LABEL[c]]
    k = _key(action)
    if k:
        return ["kp", k]
    return ["lbl", c.replace("_", " ").title()]


def _binding(key):
    if key.get("customLabel"):
        return ["lbl", key["customLabel"]]
    tap, hold = key.get("tap"), key.get("hold")
    hc = _code(hold)
    if not hc:
        return _tap(tap)
    tk = _key(tap)
    if hc in LAYER_CODES:
        layer = str(hold.get("layer") or 0)
        if not _code(tap):
            return [LAYER_CODES[hc], layer]
        if tk:
            return ["lt", layer, tk] if LAYER_CODES[hc] == "mo" else ["htto", layer, tk]
        return _tap(tap)
    if hc in MODS and tk:
        return ["mt", KC[hc], tk]
    hk = _key(hold)
    if hk and tk:
        return ["ht", hk, tk]
    if hk and not _code(tap):
        return ["kp", hk]  # hold-only key, e.g. a modifier
    return _tap(tap)


def to_model(layout):
    rev = layout["revision"]
    layers = sorted(rev["layers"], key=lambda l: l["position"])
    combos = []
    for c in rev.get("combos") or []:
        trigger = c.get("trigger") or {}
        combos.append({
            "id": c.get("name") or "combo",
            "positions": list(c["keyIndices"]),
            "binding": ["lbl", c["name"]] if c.get("name") else _binding(trigger),
            "layers": [c.get("layerIdx", 0)],
        })
    return {
        "geometry": "voyager",
        "file": f"Oryx: {layout.get('title') or ''} ({rev['hashId']})",
        "mtime": rev["hashId"],
        "defines": {},
        "holdTaps": {
            "mt": {"hold": "kp", "tap": "kp"}, "lt": {"hold": "mo", "tap": "kp"},
            "ht": {"hold": "kp", "tap": "kp"}, "htto": {"hold": "to", "tap": "kp"},
        },
        "macros": [],
        "tapDances": {},
        "layers": [{"id": f"L{l['position']}", "name": l["title"] or f"Layer {l['position']}",
                    "bindings": [_binding(k) for k in l["keys"]]} for l in layers],
        "combos": combos,
        "autoMouse": None,
    }


class OryxLayout:
    """Fetches the layout from Oryx, at most once a minute; keeps the last good copy if Oryx is unreachable."""

    def __init__(self, hash_id, revision="latest", geometry="voyager"):
        self.variables = {"hashId": hash_id, "revisionId": revision, "geometry": geometry}
        self.model = None
        self.fetched = 0.0

    def get(self):
        if self.model is None or time.monotonic() - self.fetched >= REFRESH_EVERY:
            self.fetched = time.monotonic()
            try:
                self.model = to_model(self._fetch())
            except Exception as e:
                logging.warning(f"Could not fetch the Oryx layout: {e}")
                if self.model is None:
                    raise
        return self.model

    def _fetch(self):
        body = json.dumps({"query": QUERY, "variables": self.variables}).encode()
        req = urllib.request.Request(ORYX_API, data=body, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if data.get("errors"):
            raise RuntimeError(data["errors"][0].get("message", "Oryx API error"))
        layout = (data.get("data") or {}).get("layout")
        if not layout:
            raise RuntimeError(f"Oryx layout {self.variables['hashId']} not found")
        return layout
