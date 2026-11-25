/**
 * Live keymap renderer.
 *
 * Draws the ZMK keymap served at /keymap.json and highlights the active layer and
 * the keys being pressed, from the keyboard's own reports (layer mask + key
 * positions). Key tables, keymap analysis and Charybdis geometry are ported from
 * zmk-charybdis/tools/visualizer/index.html.
 */
"use strict";

// ---------------------------------------------------------------- key tables
const MOD_ALIAS = {LSHFT:"LSHIFT",LSHIFT:"LSHIFT",LSFT:"LSHIFT",LEFT_SHIFT:"LSHIFT",RSHFT:"RSHIFT",RSHIFT:"RSHIFT",RSFT:"RSHIFT",
  RIGHT_SHIFT:"RSHIFT",LCTRL:"LCTRL",LCTL:"LCTRL",LEFT_CONTROL:"LCTRL",RCTRL:"RCTRL",RCTL:"RCTRL",RIGHT_CONTROL:"RCTRL",
  LALT:"LALT",LEFT_ALT:"LALT",RALT:"RALT",RIGHT_ALT:"RALT",LGUI:"LGUI",LWIN:"LGUI",LCMD:"LGUI",LMETA:"LGUI",LEFT_GUI:"LGUI",
  RGUI:"RGUI",RWIN:"RGUI",RCMD:"RGUI",RMETA:"RGUI",RIGHT_GUI:"RGUI"};
const MOD_FN = {LS:"LSHIFT",RS:"RSHIFT",LC:"LCTRL",RC:"RCTRL",LA:"LALT",RA:"RALT",LG:"LGUI",RG:"RGUI"};
const KEY_ALIAS = {RET:"ENTER",RETURN:"ENTER",ENTER:"ENTER",BACKSPACE:"BSPC",ESCAPE:"ESC",DELETE:"DEL",SPC:"SPACE",
  APOS:"SQT",APOSTROPHE:"SQT",SINGLE_QUOTE:"SQT",SEMICOLON:"SEMI",SLASH:"FSLH",BACKSLASH:"BSLH",LEFT_BRACKET:"LBKT",
  RIGHT_BRACKET:"RBKT",PERIOD:"DOT",PAGE_UP:"PG_UP",PAGE_DOWN:"PG_DN",LEFT_ARROW:"LEFT",RIGHT_ARROW:"RIGHT",
  UP_ARROW:"UP",DOWN_ARROW:"DOWN",INSERT:"INS",CAPSLOCK:"CAPS",CLCK:"CAPS",EQL:"EQUAL",
  C_VOLUME_UP:"C_VOL_UP",C_VOLUME_DOWN:"C_VOL_DN",C_PLAY_PAUSE:"C_PP"};
const SHIFTED = {EXCL:"N1",EXCLAMATION:"N1",AT:"N2",AT_SIGN:"N2",HASH:"N3",POUND:"N3",DOLLAR:"N4",DLLR:"N4",
  PRCNT:"N5",PERCENT:"N5",CARET:"N6",AMPS:"N7",AMPERSAND:"N7",STAR:"N8",ASTRK:"N8",ASTERISK:"N8",LPAR:"N9",
  LEFT_PARENTHESIS:"N9",RPAR:"N0",RIGHT_PARENTHESIS:"N0",PLUS:"EQUAL",DQT:"SQT",DOUBLE_QUOTES:"SQT",COLON:"SEMI",
  QMARK:"FSLH",QUESTION:"FSLH",PIPE:"BSLH",UNDER:"MINUS",UNDERSCORE:"MINUS",TILDE:"GRAVE",LBRC:"LBKT",
  LEFT_BRACE:"LBKT",RBRC:"RBKT",RIGHT_BRACE:"RBKT",LT:"COMMA",LESS_THAN:"COMMA",GT:"DOT",GREATER_THAN:"DOT"};
const CHAR = {MINUS:"-",EQUAL:"=",LBKT:"[",RBKT:"]",BSLH:"\\",SEMI:";",SQT:"'",GRAVE:"`",COMMA:",",DOT:".",FSLH:"/",
  BSPC:"⌫",DEL:"⌦",ENTER:"⏎",TAB:"⇥",SPACE:"␣",ESC:"Esc",LEFT:"←",RIGHT:"→",UP:"↑",DOWN:"↓",PG_UP:"PgUp",PG_DN:"PgDn",
  HOME:"Home",END:"End",INS:"Ins",CAPS:"Caps",LSHIFT:"⇧",RSHIFT:"⇧",LCTRL:"Ctrl",RCTRL:"Ctrl",LALT:"Alt",RALT:"Alt",
  LGUI:"Win",RGUI:"Win",C_MUTE:"Mute",C_VOL_UP:"Vol+",C_VOL_DN:"Vol−",C_NEXT:"⏭",C_PREV:"⏮",C_PP:"⏯"};
for (let d = 0; d <= 9; d++) CHAR["N" + d] = String(d);
const SHIFT_CHAR = {N1:"!",N2:"@",N3:"#",N4:"$",N5:"%",N6:"^",N7:"&",N8:"*",N9:"(",N0:")",EQUAL:"+",SQT:"\"",SEMI:":",
  FSLH:"?",BSLH:"|",MINUS:"_",GRAVE:"~",LBKT:"{",RBKT:"}",COMMA:"<",DOT:">"};
const MOD_NAME = {LSHIFT:"Shift",RSHIFT:"Shift",LCTRL:"Ctrl",RCTRL:"Ctrl",LALT:"Alt",RALT:"Alt",LGUI:"Win",RGUI:"Win"};
const MOD_SYM = {CTRL:"⌃",ALT:"⌥",SHIFT:"⇧",GUI:"⊞"};
const MOD_ORDER = ["CTRL","ALT","SHIFT","GUI"];
const side = m => m.slice(1); // LSHIFT -> SHIFT
const isModKey = k => k in MOD_NAME;

function parseKey(tok) {
  const m = /^(\w+)\((.*)\)$/.exec(tok);
  if (m && MOD_FN[m[1]]) { const inner = parseKey(m[2]); inner.mods.add(MOD_FN[m[1]]); return inner; }
  if (MOD_ALIAS[tok]) return {mods: new Set(), key: MOD_ALIAS[tok]};
  if (SHIFTED[tok]) return {mods: new Set(["LSHIFT"]), key: SHIFTED[tok]};
  const num = /^NUMBER_(\d)$/.exec(tok);
  if (num) return {mods: new Set(), key: "N" + num[1]};
  return {mods: new Set(), key: KEY_ALIAS[tok] || tok};
}
function outLabel(out) {
  const mods = new Set([...out.mods].map(side));
  if (mods.size === 1 && mods.has("SHIFT") && SHIFT_CHAR[out.key]) return SHIFT_CHAR[out.key];
  const base = CHAR[out.key] ?? out.key;
  return MOD_ORDER.filter(m => mods.has(m)).map(m => MOD_SYM[m]).join("") + base;
}

const BT = {BT_CLR:"BT clear",BT_NXT:"BT →",BT_PRV:"BT ←",BT_CLR_ALL:"BT clr all"};
const OUT = {OUT_USB:"USB",OUT_BLE:"BLE",OUT_TOG:"USB/BLE"};
const RGB = {RGB_TOG:"RGB",RGB_EFF:"Effect",RGB_EFR:"Effect ←",RGB_BRI:"Bright+",RGB_BRD:"Bright−",RGB_HUI:"Hue+",
  RGB_HUD:"Hue−",RGB_SAI:"Sat+",RGB_SAD:"Sat−",RGB_SPI:"Speed+",RGB_SPD:"Speed−",RGB_ON:"RGB on",RGB_OFF:"RGB off"};
const MOUSE_LABEL = {LCLK:"L click",RCLK:"R click",MCLK:"M click",MB4:"Back",MB5:"Fwd"};
const HOLD_AFTER_MS = 220; // a hold-tap key down this long is shown as held

// ---------------------------------------------------------------- geometry (Charybdis 4x6)
const U = 58, GAP = 0.08;
const COL_OFF = [0.45, 0.45, 0.15, 0, 0.15, 0.3];
const POS = [];
for (let r = 0; r < 4; r++) {
  for (let c = 0; c < 6; c++) POS[r * 12 + c] = {x: c + 0.5, y: r + 0.5 + COL_OFF[c], rot: 0};
  for (let c = 0; c < 6; c++) POS[r * 12 + 6 + c] = {x: 7.9 + c + 0.5, y: r + 0.5 + COL_OFF[5 - c], rot: 0};
}
const MIRROR = 13.4 + 0.5 + 0.5;
const thumbsL = {48: [3.85, 4.95, 8], 49: [4.9, 5.15, 16], 50: [5.9, 5.5, 26], 53: [4.7, 6.2, 16], 54: [5.65, 6.55, 26]};
for (const [p, [x, y, r]] of Object.entries(thumbsL)) POS[p] = {x, y, rot: r};
POS[51] = {x: MIRROR - 5.9, y: 5.5, rot: -26};
POS[52] = {x: MIRROR - 4.9, y: 5.15, rot: -16};
POS[55] = {x: MIRROR - 5.65, y: 6.55, rot: -26};
const BALL = {x: MIRROR - 3.3, y: 6.0, r: 0.95};
const VIEW = {w: 14.4 * U, h: 7.35 * U};

const NS = "http://www.w3.org/2000/svg";
const svgEl = (tag, attrs = {}, parent) => { const e = document.createElementNS(NS, tag);
  for (const [k, v] of Object.entries(attrs)) e.setAttribute(k, v); if (parent) parent.appendChild(e); return e; };
const layerColor = i => `oklch(0.62 0.16 ${(i * 53 + 265) % 360})`;

class KeymapView {
  constructor(svg) {
    this.svg = svg;
    this.km = null;
    this.mtime = null;
    this.mask = 1;          // active layer mask, from the keyboard
    this.defaultMask = 1;   // default layer mask (GAME mode moves it)
    this.down = new Map();  // position -> {layer at press, time}
    this.timer = null;
  }

  // ------------------------------------------------------------ model
  layerOf(t) { return this.km.defines[t] ?? parseInt(t, 10); }

  analyze(b) {
    const [beh, ...p] = b;
    // Tap-dance: draw its first real binding (td_bspc -> &u_lt NUM BSPC on one tap).
    // Miryoku's u_to_U_* do nothing on one tap, so they show the double tap as "2× →Nav".
    const td = this.km.tapDances?.[beh];
    if (td?.length) {
      const i = td.findIndex(x => !["none", "trans", beh].includes(x[0]));
      if (i >= 0) {
        const a = this.analyze(td[i]);
        if (i > 0 && a.tap) a.tap = {...a.tap, taps: i + 1};
        return a;
      }
    }
    const ht = this.km.holdTaps[beh];
    if (ht) {
      const part = (kind, arg) => kind === "kp" ? {out: parseKey(arg)}
        : ["mo","to","tog","sl"].includes(kind) ? {layer: this.layerOf(arg), kind} : {label: kind + " " + arg};
      return {hold: part(ht.hold, p[0]), tap: part(ht.tap, p[1])};
    }
    switch (beh) {
      case "kp": return {tap: {out: parseKey(p[0])}};
      case "trans": return {trans: true};
      case "none": return {none: true};
      case "mo": return {hold: {layer: this.layerOf(p[0]), kind: "mo"}};
      case "to": case "tog": case "sl": return {tap: {layer: this.layerOf(p[0]), kind: beh}};
      case "mkp": return {tap: {label: MOUSE_LABEL[p[0]] || p[0]}};
      case "bt": return {tap: {label: p[0] === "BT_SEL" ? "BT " + p[1] : (BT[p[0]] || p[0])}};
      case "out": return {tap: {label: OUT[p[0]] || p[0]}};
      case "rgb_ug": return {tap: {label: RGB[p[0]] || p[0]}};
      case "bootloader": return {tap: {label: "Boot"}};
      case "sys_reset": return {tap: {label: "Reset"}};
      case "caps_word": return {tap: {label: "Caps W"}};
      case "key_repeat": return {tap: {label: "Repeat"}};
      default:
        if (this.km.macros.includes(beh)) return {tap: {label: beh.replace(/_/g, " ")}};
        return {tap: {label: beh + (p.length ? " " + p.join(" ") : "")}};
    }
  }

  partLabel(part, isHold) {
    if (!part) return "";
    if (part.taps) return part.taps + "× " + this.partLabel({...part, taps: 0}, isHold);
    if (part.out) return isHold && isModKey(part.out.key) && !part.out.mods.size ? MOD_NAME[part.out.key] : outLabel(part.out);
    if (part.layer !== undefined) {
      const n = this.short[part.layer] || ("L" + part.layer);
      return part.kind === "to" ? "→" + n : part.kind === "tog" ? "⇄" + n : part.kind === "sl" ? "1×" + n : n;
    }
    return part.label || "";
  }

  load(data) {
    this.km = data;
    const byNum = {};
    for (const [k, v] of Object.entries(data.defines))
      if (v < data.layers.length && /^[A-Z][A-Z0-9_]*$/.test(k) && !(v in byNum)) byNum[v] = k;
    this.short = data.layers.map((l, i) => byNum[i] || l.name.toUpperCase());
    this.info = data.layers.map(l => l.bindings.map(b => this.analyze(b)));
    this.combos = data.combos.map(c => ({c, layers: c.layers.length ? c.layers : [0],
      label: this.partLabel(this.analyze(c.binding).tap)}));
    this.mouseLayer = (data.autoMouse && data.autoMouse.layer) ?? data.defines.MOUSE ?? -1;
    this.draw();
    this.render();
  }

  // ------------------------------------------------------------ state from the keyboard
  topLayer(mask) {
    const n = this.km ? this.km.layers.length : 32;
    for (let l = n - 1; l > 0; l--) if (mask & (1 << l)) return l;
    return 0;
  }
  get baseLayer() { return this.topLayer(this.defaultMask); }
  get layer() { return this.topLayer(this.mask | this.defaultMask); }

  setLayer(mask, defaultMask) {
    this.mask = mask;
    if (defaultMask) this.defaultMask = defaultMask;
    this.render();
  }
  setDown(positions) {
    this.down.clear();
    const t = performance.now();
    positions.forEach(p => this.down.set(p, {layer: this.layer, t}));
    this.render();
  }
  setKey(pos, isDown) {
    if (isDown) this.down.set(pos, {layer: this.layer, t: performance.now()});
    else this.down.delete(pos);
    this.render();
    // re-render once hold-taps pass the hold threshold
    clearTimeout(this.timer);
    if (this.down.size) this.timer = setTimeout(() => this.render(), HOLD_AFTER_MS + 10);
  }

  // Resolve &trans down through the active layers to the default layer
  effective(layer, pos) {
    const active = this.mask | this.defaultMask;
    const order = [layer, ...[...Array(layer).keys()].reverse().filter(l => active & (1 << l)), this.baseLayer, 0];
    for (const l of order) {
      const a = this.info[l] && this.info[l][pos];
      if (a && !a.trans) return a;
    }
    return {none: true};
  }

  // ------------------------------------------------------------ drawing
  draw() {
    const svg = this.svg;
    svg.innerHTML = "";
    svg.setAttribute("viewBox", `0 0 ${VIEW.w} ${VIEW.h}`);
    const s = (1 - GAP) * U;
    this.keys = POS.map((p, i) => {
      const g = svgEl("g", {class: "k", transform: `translate(${p.x * U} ${p.y * U}) rotate(${p.rot})`}, svg);
      svgEl("rect", {class: "cap", x: -s / 2, y: -s / 2, width: s, height: s, rx: 9}, g);
      svgEl("rect", {class: "band", x: -s / 2 + 7, y: s / 2 - 6, width: s - 14, height: 3, rx: 1.5}, g);
      const tap = svgEl("text", {class: "tap", x: 0, y: -4}, g);
      const hold = svgEl("text", {class: "hold", x: 0, y: s / 2 - 14}, g);
      return {g, tap, hold, pos: i};
    });
    const bg = svgEl("g", {class: "ball"}, svg);
    svgEl("circle", {class: "b", cx: BALL.x * U, cy: BALL.y * U, r: BALL.r * U}, bg);
    const bt = svgEl("text", {x: BALL.x * U, y: BALL.y * U}, bg);
    bt.textContent = "trackball";
    this.ball = bg;
    this.comboEls = this.combos.map(({c, label, layers}) => {
      const [a, b] = c.positions.map(p => POS[p]);
      const cx = (a.x + b.x) / 2 * U, cy = ((a.y + b.y) / 2 + 0.3) * U;
      const g = svgEl("g", {class: "combo"}, svg);
      const w = Math.max(26, 7 * [...label].length + 12);
      svgEl("rect", {x: cx - w / 2, y: cy - 8, width: w, height: 16, rx: 8}, g);
      const t = svgEl("text", {x: cx, y: cy}, g);
      t.textContent = label;
      return {g, c, layers};
    });
  }

  fit(t, label) {
    t.textContent = label;
    const n = [...label].length;
    t.style.fontSize = (n <= 1 ? 20 : n <= 2 ? 17 : n <= 4 ? 13.5 : n <= 6 ? 11.5 : 9.5) + "px";
  }

  render() {
    if (!this.km) return;
    const L = this.layer, now = performance.now();
    const color = layerColor(L);
    this.svg.style.setProperty("--layer-c", color);
    this.onLayer && this.onLayer(this.km.layers[L].name, color);

    // classify pressed keys: layer key holding the current layer, held modifier, or plain press
    const on = new Set(), held = new Set(), lkey = new Set();
    const active = this.mask | this.defaultMask;
    for (const [pos, d] of this.down) {
      const a = this.effective(d.layer, pos);
      const holdLayer = a.hold && a.hold.layer !== undefined ? a.hold.layer
                      : a.tap && a.tap.kind === "mo" ? a.tap.layer : null;
      if (holdLayer !== null && active & (1 << holdLayer)) lkey.add(pos);
      else if (a.hold && a.hold.out && now - d.t >= HOLD_AFTER_MS) held.add(pos);
      else on.add(pos);
    }

    for (const k of this.keys) {
      const own = this.info[L][k.pos];
      // a held layer key is usually &none/&trans on its own layer: show what it does underneath
      const a = lkey.has(k.pos) && (own.none || own.trans)
        ? this.effective(this.baseLayer, k.pos) : this.effective(L, k.pos);
      this.fit(k.tap, a.none ? "" : this.partLabel(a.tap, false));
      k.hold.textContent = a.none ? "" : this.partLabel(a.hold, true);
      const holdLayer = a.hold && a.hold.layer !== undefined ? a.hold.layer
                      : (a.tap && a.tap.layer !== undefined ? a.tap.layer : null);
      k.g.style.setProperty("--key-c", lkey.has(k.pos) ? color : holdLayer !== null ? layerColor(holdLayer) : "transparent");
      k.g.classList.toggle("fade", !!own.trans);
      k.g.classList.toggle("none", !!a.none);
      k.g.classList.toggle("layerhold", holdLayer !== null);
      k.g.classList.toggle("on", on.has(k.pos));
      k.g.classList.toggle("held", held.has(k.pos));
      k.g.classList.toggle("lkey", lkey.has(k.pos));
    }
    for (const {g, c, layers} of this.comboEls) {
      g.style.display = layers.includes(L) ? "" : "none";
      g.classList.toggle("on", c.positions.every(p => this.down.has(p)));
    }
    // auto-mouse: the firmware switches to the mouse layer while the ball moves
    const mouseish = this.mouseLayer >= 0 && L >= this.mouseLayer;
    this.ball.classList.toggle("move", mouseish);
    this.ball.querySelector("text").textContent = mouseish ? this.km.layers[L].name : "trackball";
  }
}

window.KeymapView = KeymapView;
