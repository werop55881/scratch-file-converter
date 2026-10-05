/**
 * Scratch runtime for converted projects (browser canvas).
 *
 * This file is copied next to the generated main.js as runtime.js.
 * Classic script: exposes its functions/classes as globals for main.js.
 *
 * Generated scripts are generator functions fn(ctx, rt); the scheduler steps
 * them once per frame. A bare `yield` waits one frame, `yield* rt.wait_secs(...)`
 * waits longer. This mirrors the Python (pygame) backend one-to-one.
 */

"use strict";

const STAGE_W = 480;
const STAGE_H = 360;
const DEFAULT_FPS = 30;
const MAX_CLONES = 300;
const MAX_STEPS_PER_FRAME = 20000;

// ---------------------------------------------------------------------------
// Scratch-flavoured helper functions (used by generated code)
// ---------------------------------------------------------------------------

function s_num(value) {
  if (typeof value === "boolean") return value ? 1 : 0;
  if (typeof value === "number") return value;
  if (value === null || value === undefined) return 0;
  if (typeof value === "string") {
    const text = value.trim();
    if (text === "") return 0;
    if (text === "NaN") return NaN;
    if (text === "Infinity") return Infinity;
    if (text === "-Infinity") return -Infinity;
    const n = Number(text);
    return Number.isNaN(n) ? 0 : n;
  }
  return 0;
}

function s_str(value) {
  if (value === null || value === undefined) return "";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (Number.isNaN(value)) return "NaN";
    if (value === Infinity) return "Infinity";
    if (value === -Infinity) return "-Infinity";
    if (Number.isInteger(value)) return String(value);
    return String(value);
  }
  if (Array.isArray(value)) return value.map(s_str).join(", ");
  return String(value);
}

function _looks_numeric(value) {
  if (typeof value === "boolean") return false;
  if (typeof value === "number") return true;
  if (typeof value === "string") {
    const text = value.trim();
    if (text === "") return false;
    if (text === "NaN") return true;
    return !Number.isNaN(Number(text));
  }
  return false;
}

function _both_numeric(a, b) {
  return _looks_numeric(a) && _looks_numeric(b);
}

function _truthy(value) {
  if (typeof value === "boolean") return value;
  if (typeof value === "number") return value !== 0 && !Number.isNaN(value);
  if (typeof value === "string") return value !== "";
  if (Array.isArray(value)) return value.length > 0;
  return Boolean(value);
}

function s_add(a, b) {
  return s_num(a) + s_num(b);
}

function s_sub(a, b) {
  return s_num(a) - s_num(b);
}

function s_mul(a, b) {
  return s_num(a) * s_num(b);
}

function s_div(a, b) {
  const bn = s_num(b);
  const an = s_num(a);
  if (bn === 0) {
    if (Number.isNaN(an)) return "NaN";
    return an < 0 ? "-Infinity" : "Infinity";
  }
  return an / bn;
}

function _is_whole(value) {
  if (typeof value === "boolean") return false;
  if (typeof value === "number") return Number.isInteger(value);
  if (typeof value === "string") {
    const text = value.trim();
    if (text === "") return false;
    const n = Number(text);
    return !Number.isNaN(n) && Number.isInteger(n);
  }
  return false;
}

function s_random(a, b) {
  let lo = s_num(a);
  let hi = s_num(b);
  if (hi < lo) [lo, hi] = [hi, lo];
  if (_is_whole(a) && _is_whole(b)) {
    return Math.floor(Math.random() * (Math.floor(hi) - Math.ceil(lo) + 1)) + Math.ceil(lo);
  }
  return Math.random() * (hi - lo) + lo;
}

function s_gt(a, b) {
  if (_both_numeric(a, b)) return s_num(a) > s_num(b);
  return s_str(a) > s_str(b);
}

function s_lt(a, b) {
  if (_both_numeric(a, b)) return s_num(a) < s_num(b);
  return s_str(a) < s_str(b);
}

function s_eq(a, b) {
  if (_both_numeric(a, b)) {
    const x = s_num(a);
    const y = s_num(b);
    if (Number.isNaN(x) || Number.isNaN(y)) return false;
    return x === y;
  }
  return s_str(a).toLowerCase() === s_str(b).toLowerCase();
}

function s_not(value) {
  return !_truthy(value);
}

function s_and(a, b) {
  return _truthy(a) && _truthy(b);
}

function s_or(a, b) {
  return _truthy(a) || _truthy(b);
}

function s_join(a, b) {
  return s_str(a) + s_str(b);
}

function s_letter(index, text) {
  const string = s_str(text);
  const i = Math.trunc(s_num(index));
  if (!Number.isFinite(i) || i < 1 || i > string.length) return "";
  return string[i - 1];
}

function s_length(value) {
  return s_str(value).length;
}

function s_contains(haystack, needle) {
  return s_str(haystack).toLowerCase().includes(s_str(needle).toLowerCase());
}

function s_mod(a, b) {
  const an = s_num(a);
  const bn = s_num(b);
  if (bn === 0) return NaN;
  return an - bn * Math.floor(an / bn);
}

function s_round(value) {
  return Math.floor(s_num(value) + 0.5);
}

function s_mathop(op, value) {
  const n = s_num(value);
  const rad = (n * Math.PI) / 180;
  const deg = (r) => (r * 180) / Math.PI;
  switch (op) {
    case "abs":
      return Math.abs(n);
    case "ceiling":
      return Math.ceil(n);
    case "floor":
      return Math.floor(n);
    case "sqrt":
      return n >= 0 ? Math.sqrt(n) : NaN;
    case "sin":
      return Math.sin(rad);
    case "cos":
      return Math.cos(rad);
    case "tan":
      return Math.tan(rad);
    case "asin":
      return n >= -1 && n <= 1 ? deg(Math.asin(n)) : NaN;
    case "acos":
      return n >= -1 && n <= 1 ? deg(Math.acos(n)) : NaN;
    case "atan":
      return deg(Math.atan(n));
    case "ln":
      return n > 0 ? Math.log(n) : NaN;
    case "log":
      return n > 0 ? Math.log10(n) : NaN;
    case "e ^":
    case "e^":
      return Math.exp(n);
    case "10 ^":
    case "10^":
      return Math.pow(10, n);
    default:
      return 0;
  }
}

function repeat_count(value) {
  return Math.max(0, Math.trunc(s_round(value)));
}

// --- list helpers -----------------------------------------------------------

function _list_index(lst, index) {
  if (!Array.isArray(lst)) return null;
  const size = lst.length;
  if (s_str(index) === "last") return size ? size - 1 : null;
  const k = Math.trunc(s_num(index));
  if (!Number.isFinite(k) || k === 0) return null;
  const pos = k > 0 ? k - 1 : size + k;
  return pos >= 0 && pos < size ? pos : null;
}

function list_item(lst, index) {
  const pos = _list_index(lst, index);
  return pos === null ? "" : lst[pos];
}

function list_delete(lst, index) {
  if (!Array.isArray(lst)) return;
  if (s_str(index) === "all") {
    lst.length = 0;
    return;
  }
  const pos = _list_index(lst, index);
  if (pos !== null) lst.splice(pos, 1);
}

function list_clear(lst) {
  if (Array.isArray(lst)) lst.length = 0;
}

function list_add(lst, item) {
  if (Array.isArray(lst)) lst.push(item);
}

function list_insert(lst, index, item) {
  if (!Array.isArray(lst)) return;
  const size = lst.length;
  if (s_str(index) === "last") {
    lst.push(item);
    return;
  }
  const k = Math.trunc(s_num(index));
  if (!Number.isFinite(k) || k < 1 || k > size + 1) return;
  lst.splice(k - 1, 0, item);
}

function list_replace(lst, index, item) {
  const pos = _list_index(lst, index);
  if (pos !== null) lst[pos] = item;
}

function list_index_of(lst, item) {
  if (!Array.isArray(lst)) return "";
  for (let i = 0; i < lst.length; i++) {
    if (s_eq(lst[i], item)) return i + 1;
  }
  return "";
}

function list_length(value) {
  if (Array.isArray(value)) return value.length;
  if (typeof value === "string") return value.length;
  return 0;
}

function list_contains(lst, item) {
  if (!Array.isArray(lst)) return false;
  return lst.some((existing) => s_eq(existing, item));
}

// ---------------------------------------------------------------------------
// Key mapping
// ---------------------------------------------------------------------------

function key_to_scratch(key) {
  if (key === " " || key === "Spacebar") return "space";
  if (key === "ArrowLeft") return "left arrow";
  if (key === "ArrowRight") return "right arrow";
  if (key === "ArrowUp") return "up arrow";
  if (key === "ArrowDown") return "down arrow";
  if (key === "Enter") return "enter";
  if (key.length === 1) {
    const lower = key.toLowerCase();
    if (lower >= "a" && lower <= "z") return lower;
    if (lower >= "0" && lower <= "9") return lower;
  }
  return null;
}

// ---------------------------------------------------------------------------
// Assets
// ---------------------------------------------------------------------------

function assetUrl(assetsDir, file) {
  const map = (typeof window !== "undefined" && window.__SB3_ASSETS) || null;
  if (map && map[file]) return map[file];
  return assetsDir + "/" + file;
}

class Costume {
  constructor(data, assetsDir) {
    this.name = String(data.name || "costume");
    this.costumeId = String(data.id || this.name);
    this.resolution = Number(data.resolution || 1) || 1;
    this.cx = Number(data.cx || 0) / this.resolution;
    this.cy = Number(data.cy || 0) / this.resolution;
    this.missing = false;
    this.image = new Image();
    this.fallback = null;
    const file = String(data.file || "");
    if (!file) {
      this.missing = true;
      this._make_fallback();
    } else {
      this.image.src = assetUrl(assetsDir, file);
      this.image.addEventListener("error", () => {
        this.missing = true;
        this._make_fallback();
      });
    }
  }

  _make_fallback() {
    const canvas = document.createElement("canvas");
    canvas.width = 32;
    canvas.height = 32;
    const g = canvas.getContext("2d");
    g.fillStyle = "rgb(120,120,160)";
    g.fillRect(0, 0, 32, 32);
    this.fallback = canvas;
  }

  get source() {
    if (!this.missing && this.image.complete && this.image.naturalWidth > 0) return this.image;
    return this.fallback;
  }

  get width() {
    if (this.image.complete && this.image.naturalWidth > 0) {
      return this.image.naturalWidth / this.resolution;
    }
    return this.fallback ? this.fallback.width : 32;
  }

  get height() {
    if (this.image.complete && this.image.naturalHeight > 0) {
      return this.image.naturalHeight / this.resolution;
    }
    return this.fallback ? this.fallback.height : 32;
  }

  _ensure_alpha() {
    // lazy: images load in the background; callers fall back to full-canvas
    // bounding boxes until the pixels are available
    if (this._mask) return this._mask;
    const src = this.source;
    if (!src) return null;
    const isImage = typeof HTMLImageElement !== "undefined" && src instanceof HTMLImageElement;
    if (isImage && (!src.complete || src.naturalWidth === 0)) return null;
    const w = isImage ? src.naturalWidth : src.width;
    const h = isImage ? src.naturalHeight : src.height;
    if (!w || !h) return null;
    const canvas = document.createElement("canvas");
    canvas.width = w;
    canvas.height = h;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.drawImage(src, 0, 0);
    const data = g.getImageData(0, 0, w, h).data;
    const bits = new Uint8Array(w * h);
    let l = w, t = h, r = -1, b = -1;
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        if (data[(y * w + x) * 4 + 3]) {
          bits[y * w + x] = 1;
          if (x < l) l = x;
          if (x > r) r = x;
          if (y < t) t = y;
          if (y > b) b = y;
        }
      }
    }
    if (r < l) { l = 0; t = 0; r = w - 1; b = h - 1; }
    this._mask = { w, h, bits, l, t, r: r + 1, b: b + 1 };
    return this._mask;
  }
}

class SoundAsset {
  constructor(data, assetsDir) {
    this.name = String(data.name || "sound");
    this.audio = new Audio(assetUrl(assetsDir, String(data.file || "")));
    this.audio.preload = "auto";
  }

  play(volume, pitch) {
    const node = this.audio.cloneNode(true);
    node.volume = Math.max(0, Math.min(1, volume));
    node.playbackRate = Math.max(0.05, (100 + pitch) / 100);
    const promise = node.play();
    if (promise && typeof promise.catch === "function") {
      promise.catch(() => {});
    }
    return node;
  }
}

// ---------------------------------------------------------------------------
// Actors
// ---------------------------------------------------------------------------

class Actor {
  constructor(runtime, target, isClone = false) {
    this.rt = runtime;
    this.target = target;
    this.is_clone = isClone;
    this.x = target.x;
    this.y = target.y;
    this.direction = target.direction;
    this.size = target.size;
    this.visible = target.visible;
    this.rotation_style = target.rotation_style;
    this.volume = target.volume;
    this.current_costume = target.current_costume;
    this.effects = {
      ghost: 0, color: 0, fisheye: 0, whirl: 0, pixelate: 0, mosaic: 0, brightness: 0,
    };
    this.sound_effects = { PITCH: 0, PAN: 0 };
    this.say = null;
    this.think = null;
    this.dead = false;
    if (isClone) {
      this.vars = Object.assign({}, target.variables);
      this.lists = {};
      for (const key of Object.keys(target.lists)) this.lists[key] = target.lists[key].slice();
    } else {
      this.vars = target.variables;
      this.lists = target.lists;
    }
  }

  get costume() {
    const costumes = this.target.costumes;
    if (!costumes.length) return null;
    return costumes[Math.trunc(this.current_costume) % costumes.length];
  }

  set_costume(ref) {
    const costumes = this.target.costumes;
    if (!costumes.length) return;
    const text = s_str(ref);
    for (let i = 0; i < costumes.length; i++) {
      if (text === costumes[i].name || text === costumes[i].costumeId) {
        this.current_costume = i;
        return;
      }
    }
    if (_looks_numeric(text)) {
      const index = Math.trunc(s_num(text)) - 1;
      this.current_costume = Math.max(0, Math.min(index, costumes.length - 1));
      return;
    }
    this.rt.warn_once(`unknown costume '${text}' for sprite '${this.target.name}'`);
  }

  next_costume() {
    const costumes = this.target.costumes;
    if (costumes.length) {
      this.current_costume = (Math.trunc(this.current_costume) + 1) % costumes.length;
    }
  }

  remove_clone() {
    this.rt.remove_clone(this);
  }

  half_size() {
    const costume = this.costume;
    if (!costume) return [0, 0];
    const scale = this.size / 100;
    return [(costume.width * scale) / 2, (costume.height * scale) / 2];
  }

  rect() {
    const costume = this.costume;
    const mask = costume ? costume._ensure_alpha() : null;
    if (mask) {
      // tight opaque bounds, like Scratch's pixel-based collision
      const scale = this.size / 100;
      const res = costume.resolution || 1;
      const left = Math.trunc(this.x + (mask.l / res - costume.cx) * scale);
      const top = Math.trunc(this.y + (costume.cy - mask.b / res) * scale);
      const width = Math.max(1, Math.trunc(((mask.r - mask.l) / res) * scale));
      const height = Math.max(1, Math.trunc(((mask.b - mask.t) / res) * scale));
      return { left, top, width, height, right: left + width, bottom: top + height };
    }
    const [hw, hh] = this.half_size();
    const left = Math.trunc(this.x - hw);
    const top = Math.trunc(this.y - hh);
    const width = Math.max(1, Math.trunc(hw * 2));
    const height = Math.max(1, Math.trunc(hh * 2));
    return { left, top, width, height, right: left + width, bottom: top + height };
  }

  opaqueAt(sx, sy) {
    const costume = this.costume;
    if (!costume) return false;
    const mask = costume._ensure_alpha();
    if (!mask) {
      const r = this.rect();
      return sx >= r.left && sx < r.right && sy >= r.top && sy < r.bottom;
    }
    const scale = this.size / 100;
    if (scale <= 0) return false;
    const res = costume.resolution || 1;
    const px = Math.floor(((sx - this.x) / scale + costume.cx) * res);
    const py = Math.floor((costume.cy - (sy - this.y) / scale) * res);
    if (px < 0 || py < 0 || px >= mask.w || py >= mask.h) return false;
    return !!mask.bits[py * mask.w + px];
  }

  overlaps(other) {
    const ra = this.rect();
    const rb = other.rect();
    if (ra.left >= rb.right || ra.right <= rb.left || ra.top >= rb.bottom || ra.bottom <= rb.top) {
      return false;
    }
    const ca = this.costume;
    const cb = other.costume;
    const ma = ca ? ca._ensure_alpha() : null;
    const mb = cb ? cb._ensure_alpha() : null;
    if (!ma || !mb) return true;
    const sa = this.size / 100;
    const sb = other.size / 100;
    if (sa <= 0 || sb <= 0) return false;
    const resa = ca.resolution || 1;
    const ax = this.x - ca.cx * sa;
    const ay = this.y + ca.cy * sa;
    const bx = other.x - cb.cx * sb;
    const by = other.y + cb.cy * sb;
    const pitch = sa / resa;
    if (pitch <= 0) return false;
    const dx = Math.round((bx - ax) / pitch);
    const dy = Math.round((ay - by) / pitch);
    const x0 = Math.max(ma.l, dx + mb.l);
    const x1 = Math.min(ma.r, dx + mb.r);
    const y0 = Math.max(ma.t, dy + mb.t);
    const y1 = Math.min(ma.b, dy + mb.b);
    for (let y = y0; y < y1; y++) {
      const rowa = y * ma.w;
      const rowb = (y - dy) * mb.w;
      for (let x = x0; x < x1; x++) {
        if (ma.bits[rowa + x] && mb.bits[rowb + x - dx]) return true;
      }
    }
    return false;
  }
}

// ---------------------------------------------------------------------------
// Scripts and threads
// ---------------------------------------------------------------------------

class ScriptReg {
  constructor(sprite, hat, fields, fn) {
    this.sprite = sprite;
    this.hat = hat;
    this.fields = fields;
    this.fn = fn;
  }
}

class Thread {
  constructor(generator, actor, reg) {
    this.generator = generator;
    this.actor = actor;
    this.reg = reg;
    this.done = false;
    this.stepped_frame = -1;
  }
}

// ---------------------------------------------------------------------------
// Runtime
// ---------------------------------------------------------------------------

class Runtime {
  constructor(manifest, scripts, options = {}) {
    this.manifest = manifest;
    this.assetsDir = String(manifest.assetDir || "assets");
    this.scale = Math.max(1, Number(options.scale || manifest.scale || 2));
    this.fps = Math.max(1, Number(options.fps || manifest.fps || DEFAULT_FPS));
    this.smoke = Number(options.smoke || 0);

    this.warned = new Set();

    this.stage_def = this._load_target(manifest.stage || {}, true);
    this.sprite_defs = {};
    this.target_defs = [this.stage_def];
    for (const data of manifest.sprites || []) {
      const def = this._load_target(data, false);
      this.sprite_defs[def.name] = def;
      this.target_defs.push(def);
    }

    this.stage_actor = new Actor(this, this.stage_def);
    this.actors = [this.stage_actor];
    for (const def of this.target_defs) {
      if (!def.is_stage) this.actors.push(new Actor(this, def));
    }
    this.layers = this.actors.filter((a) => !a.target.is_stage);
    this.layers.sort((a, b) => a.target.layer_order - b.target.layer_order);

    this.vars = this.stage_def.variables;
    this.lists = this.stage_def.lists;
    this.timer = 0;
    this.answer = "";
    this.loudness = 100;
    this.username = "";
    this.mouse_x = 0;
    this.mouse_y = 0;
    this.mouse_down = false;
    this.down_keys = new Set();
    this.frame = 0;
    this.frame_time = 1 / this.fps;
    this.quitting = false;

    this.monitors = {};
    for (const m of manifest.monitors || []) this.monitors[m.id] = m;
    this.monitor_visible = {};
    this.list_visible = {};
    for (const m of manifest.monitors || []) {
      this.monitor_visible[m.id] = m.visible !== false;
      if (m.isList) this.list_visible[m.id] = m.visible !== false;
    }

    this.asking = false;
    this.ask_question = "";
    this.ask_buffer = "";

    this.routes = this._build_routes(scripts);
    this.threads = [];
    this.current_thread = null;

    this.canvas = null;
    this.g = null;
    this.font = "14px sans-serif";
    this.big_font = "bold 48px sans-serif";
    this._active_audio = [];
    this._backdrop_cache = null;
  }

  // ------------------------------------------------------------------
  // construction helpers
  // ------------------------------------------------------------------
  _load_target(data, isStage) {
    const costumeList = (data.costumes || []).map((c) => new Costume(c, this.assetsDir));
    const sounds = {};
    for (const soundData of data.sounds || []) {
      const sound = new SoundAsset(soundData, this.assetsDir);
      sounds[sound.name] = sound;
    }
    const variables = Object.assign({}, data.variables || {});
    const lists = {};
    for (const key of Object.keys(data.lists || {})) lists[key] = (data.lists[key] || []).slice();
    return {
      name: String(data.name || (isStage ? "Stage" : "Sprite")),
      is_stage: isStage,
      x: Number(data.x || 0),
      y: Number(data.y || 0),
      direction: Number(data.direction === undefined ? 90 : data.direction),
      size: Number(data.size === undefined ? 100 : data.size),
      visible: data.visible === undefined ? true : Boolean(data.visible),
      rotation_style: String(data.rotationStyle || "all around"),
      layer_order: Number(data.layerOrder || 0),
      volume: Number(data.volume === undefined ? 100 : data.volume),
      current_costume: Number(data.currentCostume || 0),
      costumes: costumeList,
      sounds,
      variables,
      lists,
    };
  }

  _build_routes(scripts) {
    const routes = {
      flag: [],
      key: {},
      click: {},
      broadcast: {},
      backdrop: {},
      clone: {},
      greater: [],
    };
    const push = (map, key, reg) => {
      if (!map[key]) map[key] = [];
      map[key].push(reg);
    };
    for (const reg of scripts) {
      if (reg.hat === "event_whenflagclicked") routes.flag.push(reg);
      else if (reg.hat === "event_whenkeypressed") push(routes.key, reg.fields.KEY_OPTION || "space", reg);
      else if (reg.hat === "event_whenthisspriteclicked") push(routes.click, reg.sprite, reg);
      else if (reg.hat === "event_whenbroadcastreceived") push(routes.broadcast, reg.fields.BROADCAST_OPTION || "", reg);
      else if (reg.hat === "event_whenbackdroptoggles") push(routes.backdrop, reg.fields.BACKDROP || "", reg);
      else if (reg.hat === "control_start_as_clone") push(routes.clone, reg.sprite, reg);
      else if (reg.hat === "event_whengreaterthan") {
        routes.greater.push({
          op: String(reg.fields.WHENGREATERTHANOPERATOR || "loudness"),
          threshold: s_num(reg.fields.WHENGREATERTHANVALUE === undefined ? 100 : reg.fields.WHENGREATERTHANVALUE),
          reg,
          latched: false,
        });
      } else {
        this.warn_once(`script hat '${reg.hat}' (${reg.sprite}) is not routed and will never run`);
      }
    }
    return routes;
  }

  // ------------------------------------------------------------------
  // warnings
  // ------------------------------------------------------------------
  warn_once(message) {
    if (!this.warned.has(message)) {
      this.warned.add(message);
      console.warn("warning: " + message);
    }
  }

  unsupported(opcode) {
    this.warn_once(`block '${opcode}' is not supported by this conversion`);
    return "";
  }

  // ------------------------------------------------------------------
  // threading
  // ------------------------------------------------------------------
  spawn(reg, actor) {
    if (actor.dead) return null;
    let generator;
    try {
      generator = reg.fn(actor, this);
    } catch (exc) {
      console.error(`error: script ${reg.fn.name || "?"} crashed on start:`, exc);
      return null;
    }
    const thread = new Thread(generator, actor, reg);
    this.threads.push(thread);
    return thread;
  }

  spawn_regs(regs) {
    // snapshot: a script creating clones while running must not receive the
    // event it is itself causing, and the actor list must not mutate under us
    const started = [];
    for (const reg of regs) {
      for (const actor of Array.from(this.actors)) {
        if (actor.dead || actor.target.name !== reg.sprite) continue;
        const thread = this.spawn(reg, actor);
        if (thread) started.push(thread);
      }
    }
    return started;
  }

  green_flag() {
    this.spawn_regs(this.routes.flag);
  }

  broadcast(name) {
    this.spawn_regs(this.routes.broadcast[name] || []);
  }

  *broadcast_wait(name) {
    const started = this.spawn_regs(this.routes.broadcast[name] || []);
    if (!started.length) return;
    while (started.some((t) => !t.done)) yield;
  }

  stop_all() {
    for (const thread of this.threads) thread.done = true;
    this.stop_all_sounds();
  }

  stop_others(actor) {
    for (const thread of this.threads) {
      if (thread === this.current_thread) continue;
      if (thread.actor === actor && !thread.done) thread.done = true;
    }
  }

  stop_script(actor) {
    for (const thread of this.threads) {
      if (thread.actor === actor) thread.done = true;
    }
  }

  step() {
    this.frame += 1;
    this.timer += this.frame_time;
    this._check_greater_than();
    let steps = 0;
    let index = 0;
    while (index < this.threads.length) {
      const thread = this.threads[index];
      index += 1;
      if (thread.done || thread.stepped_frame === this.frame) continue;
      thread.stepped_frame = this.frame;
      steps += 1;
      if (steps > MAX_STEPS_PER_FRAME) {
        this.warn_once("frame step limit reached (possible broadcast loop)");
        break;
      }
      this.current_thread = thread;
      try {
        thread.generator.next();
      } catch (exc) {
        const name = (thread.reg.fn && thread.reg.fn.name) || "?";
        console.error(`error: script ${name} crashed:`, exc);
        thread.done = true;
      } finally {
        this.current_thread = null;
      }
    }
    if (this.threads.some((t) => t.done)) {
      this.threads = this.threads.filter((t) => !t.done);
    }
  }

  _check_greater_than() {
    for (const route of this.routes.greater) {
      const value = route.op === "timer" ? this.timer : this.loudness;
      if (value > route.threshold) {
        if (!route.latched) {
          route.latched = true;
          this.spawn(route.reg, this._actor_for(route.reg.sprite));
        }
      } else {
        route.latched = false;
      }
    }
  }

  _actor_for(spriteName) {
    for (const actor of this.actors) {
      if (!actor.dead && actor.target.name === spriteName) return actor;
    }
    return this.stage_actor;
  }

  // ------------------------------------------------------------------
  // waits
  // ------------------------------------------------------------------
  *wait_secs(seconds) {
    const frames = Math.max(1, Math.round(s_num(seconds) * this.fps));
    for (let i = 0; i < frames; i++) yield;
  }

  *glide_to(actor, seconds, x, y) {
    const frames = Math.max(1, Math.round(s_num(seconds) * this.fps));
    const x0 = actor.x;
    const y0 = actor.y;
    const tx = s_num(x);
    const ty = s_num(y);
    for (let i = 0; i < frames; i++) {
      const t = (i + 1) / frames;
      actor.x = x0 + (tx - x0) * t;
      actor.y = y0 + (ty - y0) * t;
      yield;
    }
  }

  *ask(question) {
    this.ask_question = question;
    this.ask_buffer = "";
    this.asking = true;
    while (this.asking) yield;
  }

  // ------------------------------------------------------------------
  // motion
  // ------------------------------------------------------------------
  norm_dir(direction) {
    return (((s_num(direction) + 180) % 360) + 360) % 360 - 180;
  }

  move(actor, steps) {
    const amount = s_num(steps);
    const rad = (actor.direction * Math.PI) / 180;
    actor.x += amount * Math.sin(rad);
    actor.y += amount * Math.cos(rad);
  }

  point_towards(actor, ref) {
    const tx = this.tx(ref);
    const ty = this.ty(ref);
    actor.direction = this.norm_dir((Math.atan2(tx - actor.x, ty - actor.y) * 180) / Math.PI);
  }

  tx(ref) {
    if (ref === "_mouse_") return this.mouse_x;
    const target = this._find_sprite(ref);
    return target ? target.x : 0;
  }

  ty(ref) {
    if (ref === "_mouse_") return this.mouse_y;
    const target = this._find_sprite(ref);
    return target ? target.y : 0;
  }

  _find_sprite(name) {
    for (const actor of this.layers) {
      if (actor.target.name === name && !actor.dead) return actor;
    }
    return null;
  }

  goto(actor, ref) {
    if (ref === "_mouse_") {
      actor.x = this.mouse_x;
      actor.y = this.mouse_y;
    } else if (ref === "_random_") {
      actor.x = Math.random() * STAGE_W - STAGE_W / 2;
      actor.y = Math.random() * STAGE_H - STAGE_H / 2;
    } else {
      const target = this._find_sprite(ref);
      if (!target) {
        this.warn_once(`goto target '${ref}' not found`);
        return;
      }
      actor.x = target.x;
      actor.y = target.y;
    }
  }

  bounce(actor) {
    const [hw, hh] = actor.half_size();
    if (hw * 2 >= STAGE_W || hh * 2 >= STAGE_H) return;
    const left = -STAGE_W / 2 + hw;
    const right = STAGE_W / 2 - hw;
    const bottom = -STAGE_H / 2 + hh;
    const top = STAGE_H / 2 - hh;
    const hit_x = actor.x < left || actor.x > right;
    const hit_y = actor.y < bottom || actor.y > top;
    if (!hit_x && !hit_y) return;
    actor.x = Math.max(left, Math.min(right, actor.x));
    actor.y = Math.max(bottom, Math.min(top, actor.y));
    let direction = actor.direction;
    if (hit_x) direction = -direction;
    if (hit_y) direction = 180 - direction;
    actor.direction = this.norm_dir(direction);
  }

  // ------------------------------------------------------------------
  // looks
  // ------------------------------------------------------------------
  clamp_size(value) {
    return Math.max(15, Math.min(150, s_num(value)));
  }

  clamp_volume(value) {
    return Math.max(0, Math.min(100, s_num(value)));
  }

  set_effect(actor, effect, value) {
    actor.effects[effect] = s_num(value);
    if (effect !== "ghost") {
      this.warn_once(`visual effect '${effect}' is stored but not rendered by the browser runtime`);
    }
  }

  change_effect(actor, effect, delta) {
    this.set_effect(actor, effect, (actor.effects[effect] || 0) + s_num(delta));
  }

  clear_effects(actor) {
    for (const key of Object.keys(actor.effects)) actor.effects[key] = 0;
  }

  go_to_front(actor) {
    const i = this.layers.indexOf(actor);
    if (i !== -1) {
      this.layers.splice(i, 1);
      this.layers.push(actor);
    }
  }

  go_to_back(actor) {
    const i = this.layers.indexOf(actor);
    if (i !== -1) {
      this.layers.splice(i, 1);
      this.layers.unshift(actor);
    }
  }

  go_layer(actor, delta) {
    const index = this.layers.indexOf(actor);
    if (index === -1) return;
    const newIndex = Math.max(0, Math.min(this.layers.length - 1, index + Math.trunc(delta)));
    if (newIndex !== index) {
      this.layers.splice(index, 1);
      this.layers.splice(newIndex, 0, actor);
    }
  }

  // ------------------------------------------------------------------
  // stage
  // ------------------------------------------------------------------
  set_backdrop(ref) {
    const costumes = this.stage_def.costumes;
    if (!costumes.length) return;
    const previous = this.stage_def.current_costume;
    let found = false;
    for (let i = 0; i < costumes.length; i++) {
      if (ref === costumes[i].name || ref === costumes[i].costumeId) {
        this.stage_def.current_costume = i;
        found = true;
        break;
      }
    }
    if (!found) {
      if (_looks_numeric(ref)) {
        const index = Math.trunc(s_num(ref)) - 1;
        this.stage_def.current_costume = Math.max(0, Math.min(index, costumes.length - 1));
      } else {
        this.warn_once(`unknown backdrop '${ref}'`);
        return;
      }
    }
    if (this.stage_def.current_costume !== previous) this._fire_backdrop_hats();
  }

  next_backdrop() {
    const costumes = this.stage_def.costumes;
    if (!costumes.length) return;
    this.stage_def.current_costume = (this.stage_def.current_costume + 1) % costumes.length;
    this._fire_backdrop_hats();
  }

  _fire_backdrop_hats() {
    const costumes = this.stage_def.costumes;
    const name = costumes[this.stage_def.current_costume].name;
    const regs = (this.routes.backdrop && this.routes.backdrop[name]) || [];
    if (regs.length) this.spawn_regs(regs);
  }

  // ------------------------------------------------------------------
  // sound
  // ------------------------------------------------------------------
  play_sound(actor, name) {
    const sound = actor.target.sounds[name];
    if (!sound) {
      this.warn_once(`sound '${name}' not found for '${actor.target.name}'`);
      return null;
    }
    const volume = Math.max(0, Math.min(1, actor.volume / 100));
    const pitch = actor.sound_effects.PITCH || 0;
    const node = sound.play(volume, pitch);
    this._active_audio.push(node);
    return node;
  }

  *play_until_done(actor, name) {
    const node = this.play_sound(actor, name);
    if (!node) return;
    while (!node.ended && !node.paused) yield;
  }

  stop_all_sounds() {
    for (const node of this._active_audio) {
      try {
        node.pause();
        node.currentTime = 0;
      } catch (exc) {
        // ignore: the node may not be seekable yet
      }
    }
    this._active_audio = [];
  }

  change_sound_effect(actor, effect, delta) {
    const key = effect.toUpperCase();
    actor.sound_effects[key] = (actor.sound_effects[key] || 0) + s_num(delta);
    if (key !== "PITCH") {
      this.warn_once(`sound effect '${key}' has no audible effect in this runtime`);
    }
  }

  set_sound_effect(actor, effect, value) {
    actor.sound_effects[effect.toUpperCase()] = s_num(value);
  }

  clear_sound_effects(actor) {
    for (const key of Object.keys(actor.sound_effects)) actor.sound_effects[key] = 0;
  }

  // ------------------------------------------------------------------
  // sensing
  // ------------------------------------------------------------------
  key_down(key) {
    const name = s_str(key);
    if (name === "any") return this.down_keys.size > 0;
    return this.down_keys.has(name);
  }

  touching(actor, ref) {
    const rect = actor.rect();
    if (ref === "_edge_") {
      return (
        rect.left <= -STAGE_W / 2 ||
        rect.right >= STAGE_W / 2 ||
        rect.top >= STAGE_H / 2 ||
        rect.bottom <= -STAGE_H / 2
      );
    }
    if (ref === "_mouse_") {
      return actor.opaqueAt(this.mouse_x, this.mouse_y);
    }
    const other = this._visible_actor(ref, actor);
    if (!other) return false;
    return actor.overlaps(other);
  }

  _visible_actor(name, exclude) {
    for (let i = this.layers.length - 1; i >= 0; i--) {
      const actor = this.layers[i];
      if (actor === exclude || actor.dead || !actor.visible) continue;
      if (actor.target.name === name) return actor;
    }
    return null;
  }

  distance_to(actor, ref) {
    return Math.hypot(this.tx(ref) - actor.x, this.ty(ref) - actor.y);
  }

  touching_colour(actor, colour) {
    const target = _parse_colour(colour);
    if (!target) return false;
    return this._probe(actor, (rgb) => rgb === target, target);
  }

  colour_touching_colour(actor, first, second) {
    const c1 = _parse_colour(first);
    const c2 = _parse_colour(second);
    if (!c1 || !c2) return false;
    return this._probe(actor, (rgb) => rgb === c1, c2);
  }

  _render_to(actor) {
    // draw the actor alone onto an offscreen canvas in stage pixel space
    const costume = actor.costume;
    if (!costume || !costume.source) return null;
    const canvas = document.createElement("canvas");
    canvas.width = STAGE_W;
    canvas.height = STAGE_H;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    this._draw_actor(g, actor, 1);
    return g.getImageData(0, 0, STAGE_W, STAGE_H);
  }

  _probe(actor, matchActorPixel, targetRgb) {
    const image = this._render_to(actor);
    if (!image) return false;
    const data = image.data;
    const step = 4;
    const backdropImage = this._backdrop_image_data();
    for (let py = 0; py < STAGE_H; py += step) {
      for (let px = 0; px < STAGE_W; px += step) {
        const offset = (py * STAGE_W + px) * 4;
        if (data[offset + 3] < 128) continue;
        if (!matchActorPixel(`${data[offset]},${data[offset + 1]},${data[offset + 2]}`)) continue;
        if (this._colour_at(px, py, backdropImage) === targetRgb) return true;
      }
    }
    return false;
  }

  _colour_at(px, py, backdropImage) {
    if (backdropImage) {
      const offset = (py * STAGE_W + px) * 4;
      if (backdropImage.data[offset + 3] >= 128) {
        return `${backdropImage.data[offset]},${backdropImage.data[offset + 1]},${backdropImage.data[offset + 2]}`;
      }
    }
    for (let i = this.layers.length - 1; i >= 0; i--) {
      const other = this.layers[i];
      if (other.dead || !other.visible) continue;
      const image = this._render_to(other);
      if (!image) continue;
      const offset = (py * STAGE_W + px) * 4;
      if (image.data[offset + 3] >= 128) {
        return `${image.data[offset]},${image.data[offset + 1]},${image.data[offset + 2]}`;
      }
    }
    return null;
  }

  _backdrop_image_data() {
    if (!this.stage_def.costumes.length) return null;
    const costume = this.stage_def.costumes[this.stage_def.current_costume];
    if (!costume.source) return null;
    if (this._backdrop_cache && this._backdrop_cache.index === this.stage_def.current_costume) {
      return this._backdrop_cache.image;
    }
    const canvas = document.createElement("canvas");
    canvas.width = STAGE_W;
    canvas.height = STAGE_H;
    const g = canvas.getContext("2d", { willReadFrequently: true });
    g.drawImage(costume.source, 0, 0, STAGE_W, STAGE_H);
    const image = g.getImageData(0, 0, STAGE_W, STAGE_H);
    this._backdrop_cache = { index: this.stage_def.current_costume, image };
    return image;
  }

  of(attribute, obj) {
    if (obj === "_mouse_") {
      if (attribute === "x position") return this.mouse_x;
      if (attribute === "y position") return this.mouse_y;
      return 0;
    }
    if (attribute === "backdrop") {
      const costumes = this.stage_def.costumes;
      return costumes.length ? costumes[this.stage_def.current_costume].name : "";
    }
    const actor = this._visible_actor(obj);
    if (!actor) return "";
    if (attribute === "x position") return actor.x;
    if (attribute === "y position") return actor.y;
    if (attribute === "direction") return actor.direction;
    if (attribute === "size") return actor.size;
    if (attribute === "volume") return actor.volume;
    if (attribute === "costume #") return actor.current_costume + 1;
    if (attribute === "costume name") return actor.costume ? actor.costume.name : "";
    if (attribute === "loudness") return this.loudness;
    return "";
  }

  reset_timer() {
    this.timer = 0;
  }

  // ------------------------------------------------------------------
  // variables and lists
  // ------------------------------------------------------------------
  set_monitor_visible(monitorId, visible) {
    if (monitorId in this.monitor_visible) this.monitor_visible[monitorId] = visible;
    else this.warn_once(`no monitor for id '${monitorId}'`);
  }

  set_list_visible(monitorId, visible) {
    if (monitorId in this.list_visible) this.list_visible[monitorId] = visible;
    else {
      for (const known of Object.values(this.monitors)) {
        if (known.isList && known.label) {
          if (!(known.id in this.list_visible)) this.list_visible[known.id] = true;
        }
      }
    }
  }

  // ------------------------------------------------------------------
  // clones
  // ------------------------------------------------------------------
  create_clone(actor, targetName) {
    let sourceActor = null;
    let definition;
    if (targetName === "_myself_") {
      sourceActor = actor;
      definition = actor.target;
    } else {
      definition = this.sprite_defs[targetName];
      if (!definition) {
        this.warn_once(`cannot clone unknown sprite '${targetName}'`);
        return;
      }
      for (const existing of this.actors) {
        if (!existing.dead && existing.target.name === targetName && !existing.is_clone) {
          sourceActor = existing;
          break;
        }
      }
    }
    const cloneCount = this.actors.filter((a) => a.is_clone && !a.dead).length;
    if (cloneCount >= MAX_CLONES) {
      this.warn_once("clone limit (300) reached");
      return;
    }
    const clone = new Actor(this, definition, true);
    if (sourceActor) {
      clone.x = sourceActor.x;
      clone.y = sourceActor.y;
      clone.direction = sourceActor.direction;
      clone.size = sourceActor.size;
      clone.current_costume = sourceActor.current_costume;
      // Scratch clones inherit the creator's current local variable values
      clone.vars = Object.assign({}, sourceActor.vars);
      clone.lists = {};
      for (const key of Object.keys(sourceActor.lists)) {
        clone.lists[key] = sourceActor.lists[key].slice();
      }
    }
    this.actors.push(clone);
    const sourceIndex = sourceActor ? this.layers.indexOf(sourceActor) : -1;
    if (sourceIndex !== -1) this.layers.splice(sourceIndex + 1, 0, clone);
    else this.layers.push(clone);
    for (const reg of (this.routes.clone[definition.name] || [])) this.spawn(reg, clone);
  }

  remove_clone(actor) {
    actor.dead = true;
    const i = this.layers.indexOf(actor);
    if (i !== -1) this.layers.splice(i, 1);
    for (const thread of this.threads) {
      if (thread.actor === actor) thread.done = true;
    }
  }

  // ------------------------------------------------------------------
  // rendering
  // ------------------------------------------------------------------
  _stage_to_canvas(x, y, pixelScale = this.scale) {
    return [(x + STAGE_W / 2) * pixelScale, (STAGE_H / 2 - y) * pixelScale];
  }

  _draw_actor(g, actor, pixelScale) {
    const costume = actor.costume;
    if (!costume) return;
    const source = costume.source;
    if (!source) return;
    const scale = (actor.size / 100) * pixelScale;
    const [cx, cy] = this._stage_to_canvas(actor.x, actor.y, pixelScale);

    g.save();
    g.translate(cx, cy);
    if (actor.rotation_style === "all around") {
      g.rotate(((actor.direction - 90) * Math.PI) / 180);
    } else if (actor.rotation_style === "left-right" && actor.direction < 0) {
      g.scale(-1, 1);
    }
    const ghost = actor.effects.ghost || 0;
    const alpha = Math.max(0, Math.min(1, 1 - ghost / 100));
    if (alpha !== 1) g.globalAlpha = alpha;
    const w = costume.width * scale;
    const h = costume.height * scale;
    g.drawImage(source, -costume.cx * scale, -costume.cy * scale, w, h);
    g.restore();
  }

  draw() {
    const g = this.g;
    if (!g) return;
    g.save();
    g.setTransform(1, 0, 0, 1, 0, 0);
    g.fillStyle = "rgb(15,15,30)";
    g.fillRect(0, 0, this.canvas.width, this.canvas.height);

    const backdrop = this.stage_def.costumes.length
      ? this.stage_def.costumes[this.stage_def.current_costume]
      : null;
    if (backdrop && backdrop.source) {
      g.drawImage(backdrop.source, 0, 0, this.canvas.width, this.canvas.height);
    }

    for (const actor of this.layers) {
      if (actor.dead || !actor.visible) continue;
      this._draw_actor(g, actor, this.scale);
    }

    g.restore();

    for (const actor of [...this.layers, this.stage_actor]) {
      if (actor.dead) continue;
      if (actor.say === null && actor.think === null) continue;
      this._draw_bubble(g, actor);
    }
    this._draw_monitors(g);
    if (this.asking) this._draw_ask(g);
  }

  _draw_bubble(g, actor) {
    const text = s_str(actor.say !== null ? actor.say : actor.think);
    if (!text) return;
    const lines = _wrap_text(text, 24);
    const lineH = 16 * this.scale;
    g.font = this.font;
    let width = 0;
    for (const line of lines) width = Math.max(width, g.measureText(line).width);
    width += 14 * this.scale;
    const height = lineH * lines.length + 8 * this.scale;
    const [bxRaw, byRaw] = this._stage_to_canvas(actor.x, actor.y + actor.half_size()[1]);
    const bx = Math.max(4, Math.min(this.canvas.width - width - 4, bxRaw - width / 2));
    const by = Math.max(4, byRaw - height - 12 * this.scale);
    g.fillStyle = "#ffffff";
    _round_rect(g, bx, by, width, height, 6 * this.scale);
    g.fill();
    g.strokeStyle = "#b4b4b4";
    g.lineWidth = 1;
    g.stroke();
    g.fillStyle = "#141414";
    for (let i = 0; i < lines.length; i++) {
      g.fillText(lines[i], bx + 7 * this.scale, by + 4 * this.scale + (i + 0.8) * lineH);
    }
    g.fillStyle = "#ffffff";
    g.beginPath();
    g.moveTo(bx + width / 2 - 6 * this.scale, by + height);
    g.lineTo(bx + width / 2 + 6 * this.scale, by + height);
    g.lineTo(bx + width / 2, by + height + 8 * this.scale);
    g.closePath();
    g.fill();
  }

  _draw_monitors(g) {
    for (const monitor of Object.values(this.monitors)) {
      if (monitor.isList) {
        if (!this.list_visible[monitor.id]) continue;
      } else if (!this.monitor_visible[monitor.id]) continue;
      const value = this._monitor_value(monitor);
      const [mx, my] = this._stage_to_canvas(Number(monitor.x || 0), Number(monitor.y || 0));
      if (monitor.mode === "large") {
        g.font = this.big_font;
        g.lineWidth = 4;
        g.strokeStyle = "#ffffff";
        g.strokeText(s_str(value), mx, my + 40 * this.scale);
        g.fillStyle = "#6ee6ff";
        g.fillText(s_str(value), mx, my + 40 * this.scale);
        continue;
      }
      g.font = this.font;
      const label = String(monitor.label || "");
      const text = s_str(value);
      const labelW = g.measureText(label).width;
      const valueW = g.measureText(text).width;
      const boxW = labelW + valueW + 22 * this.scale;
      const boxH = Math.max(20 * this.scale, 14 * this.scale + 6 * this.scale);
      g.fillStyle = "#f5f5f5";
      _round_rect(g, mx, my, boxW, boxH, 4 * this.scale);
      g.fill();
      g.strokeStyle = "#b0b0b0";
      g.lineWidth = 1;
      g.stroke();
      g.fillStyle = "#3c3c3c";
      g.fillText(label, mx + 6 * this.scale, my + boxH - 6 * this.scale);
      g.fillStyle = "#141414";
      g.fillText(text, mx + boxW - valueW - 6 * this.scale, my + boxH - 6 * this.scale);
    }
  }

  _monitor_value(monitor) {
    const label = String(monitor.label || "");
    const targetName = monitor.target;
    for (const definition of this.target_defs) {
      if (targetName !== undefined && targetName !== null && definition.name !== targetName) continue;
      if (monitor.isList && label in definition.lists) return definition.lists[label];
      if (!monitor.isList && label in definition.variables) return definition.variables[label];
    }
    if (monitor.isList) return [];
    return label in this.vars ? this.vars[label] : monitor.value !== undefined ? monitor.value : 0;
  }

  _draw_ask(g) {
    const height = 60 * this.scale;
    const y = this.canvas.height - height;
    g.fillStyle = "#f5f5f5";
    g.fillRect(0, y, this.canvas.width, height);
    g.strokeStyle = "#a0a0a0";
    g.strokeRect(0, y, this.canvas.width, height);
    g.font = this.font;
    g.fillStyle = "#141414";
    g.fillText(s_str(this.ask_question).slice(0, 90), 10 * this.scale, y + 20 * this.scale);
    g.fillText(this.ask_buffer + "_", 10 * this.scale, y + 44 * this.scale);
  }

  // ------------------------------------------------------------------
  // events
  // ------------------------------------------------------------------
  _update_mouse(event) {
    const rect = this.canvas.getBoundingClientRect();
    const px = (event.clientX - rect.left) * (this.canvas.width / rect.width);
    const py = (event.clientY - rect.top) * (this.canvas.height / rect.height);
    this.mouse_x = px / this.scale - STAGE_W / 2;
    this.mouse_y = STAGE_H / 2 - py / this.scale;
  }

  _fire_click() {
    for (let i = this.layers.length - 1; i >= 0; i--) {
      const actor = this.layers[i];
      if (actor.dead || !actor.visible) continue;
      if (actor.opaqueAt(this.mouse_x, this.mouse_y)) {
        for (const reg of this.routes.click[actor.target.name] || []) {
          this.spawn(reg, actor);
        }
        return;
      }
    }
  }

  _handle_key_down(event) {
    if (this.asking) {
      if (event.key === "Enter") {
        this.answer = this.ask_buffer;
        this.asking = false;
        event.preventDefault();
      } else if (event.key === "Backspace") {
        this.ask_buffer = this.ask_buffer.slice(0, -1);
        event.preventDefault();
      } else if (event.key.length === 1) {
        this.ask_buffer += event.key;
        event.preventDefault();
      }
      return;
    }
    const name = key_to_scratch(event.key);
    if (name === null) return;
    this.down_keys.add(name);
    for (const key of [name, "any"]) {
      for (const reg of this.routes.key[key] || []) {
        this.spawn(reg, this._actor_for(reg.sprite));
      }
    }
    if (["space", "left arrow", "right arrow", "up arrow", "down arrow", "enter"].includes(name)) {
      event.preventDefault();
    }
  }

  _handle_key_up(event) {
    const name = key_to_scratch(event.key);
    if (name !== null) this.down_keys.delete(name);
  }

  bind_input() {
    const canvas = this.canvas;
    canvas.addEventListener("mousemove", (event) => this._update_mouse(event));
    canvas.addEventListener("mousedown", (event) => {
      this._update_mouse(event);
      this.mouse_down = true;
      this._fire_click();
    });
    window.addEventListener("mouseup", () => {
      this.mouse_down = false;
    });
    window.addEventListener("keydown", (event) => this._handle_key_down(event));
    window.addEventListener("keyup", (event) => this._handle_key_up(event));
  }

  // ------------------------------------------------------------------
  // main loop
  // ------------------------------------------------------------------
  run() {
    const manifest = this.manifest;
    this.canvas = document.getElementById("stage");
    if (!this.canvas) {
      this.canvas = document.createElement("canvas");
      this.canvas.id = "stage";
      document.body.appendChild(this.canvas);
    }
    this.canvas.width = STAGE_W * this.scale;
    this.canvas.height = STAGE_H * this.scale;
    this.g = this.canvas.getContext("2d");
    document.title = String(manifest.name || "Scratch project");
    this.bind_input();

    this.green_flag();

    const interval = 1000 / this.fps;
    let last = performance.now();
    let acc = 0;
    const tick = (now) => {
      acc += now - last;
      last = now;
      if (acc >= interval) {
        acc = Math.min(acc % interval, interval);
        this.step();
        this.draw();
        if (this.smoke && this.frame >= this.smoke) {
          const line = `SMOKE OK frames=${this.frame} threads=${this.threads.length}`;
          console.log(line);
          document.title = line; // readable via --dump-dom in headless browsers
          return;
        }
      }
      requestAnimationFrame(tick);
    };
    requestAnimationFrame(tick);
  }
}

// ---------------------------------------------------------------------------
// colour and text helpers
// ---------------------------------------------------------------------------

function _parse_colour(text) {
  const value = s_str(text).trim();
  if (!value) return null;
  if (value.startsWith("#") && (value.length === 4 || value.length === 7)) {
    if (value.length === 4) {
      return `${parseInt(value[1] + value[1], 16)},${parseInt(value[2] + value[2], 16)},${parseInt(value[3] + value[3], 16)}`;
    }
    return `${parseInt(value.slice(1, 3), 16)},${parseInt(value.slice(3, 5), 16)},${parseInt(value.slice(5, 7), 16)}`;
  }
  return null;
}

function _round_rect(g, x, y, w, h, r) {
  g.beginPath();
  g.moveTo(x + r, y);
  g.arcTo(x + w, y, x + w, y + h, r);
  g.arcTo(x + w, y + h, x, y + h, r);
  g.arcTo(x, y + h, x, y, r);
  g.arcTo(x, y, x + w, y, r);
  g.closePath();
}

function _wrap_text(text, width) {
  const words = text.split(/\s+/).filter((w) => w.length > 0);
  if (!words.length) return [""];
  const lines = [];
  let current = words[0];
  for (let i = 1; i < words.length; i++) {
    const word = words[i];
    if (current.length + 1 + word.length <= width) current += " " + word;
    else {
      lines.push(current);
      current = word;
    }
  }
  lines.push(current);
  return lines;
}

// ---------------------------------------------------------------------------
// entry point used by generated main.js
// ---------------------------------------------------------------------------

function run(scripts, manifest, options = {}) {
  if (typeof document === "undefined") {
    console.error("runtime: no DOM available; open index.html in a browser");
    return null;
  }
  const params = new URLSearchParams(typeof location !== "undefined" ? location.search : "");
  if (params.has("smoke")) options.smoke = Number(params.get("smoke")) || 1;
  if (params.has("scale")) options.scale = Number(params.get("scale")) || undefined;
  if (params.has("fps")) options.fps = Number(params.get("fps")) || undefined;
  const runtime = new Runtime(manifest, scripts, options);
  runtime.run();
  return runtime;
}
