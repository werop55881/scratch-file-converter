--[[
  Scratch runtime for converted projects (LÖVE / LuaJIT).

  This file is copied next to the generated main.lua as runtime.lua.
  Loaded via require("runtime") for its side effects: it publishes the
  helper functions (s_add, list_item, ...) and ScriptReg/run as globals,
  mirroring the JavaScript backend's classic-script layout.

  Generated scripts are plain functions fn(ctx, rt) run as coroutines; the
  scheduler resumes them once per frame. A bare coroutine.yield() waits one
  frame, rt:wait_secs(...) waits longer. This mirrors the Python and
  JavaScript backends one-to-one. Truthiness goes through s_bool so Lua
  matches JavaScript (0 and "" are truthy in Lua but falsy in JS).
]]

local M = {}

local STAGE_W = 480
local STAGE_H = 360
local DEFAULT_FPS = 30
local MAX_CLONES = 300
local MAX_STEPS_PER_FRAME = 20000

-- ---------------------------------------------------------------------------
-- Scratch-flavoured helper functions (used by generated code)
-- ---------------------------------------------------------------------------

local function s_num(value)
  local t = type(value)
  if t == "boolean" then
    return value and 1 or 0
  end
  if t == "number" then
    return value
  end
  if value == nil then
    return 0
  end
  if t == "string" then
    local text = value:match("^%s*(.-)%s*$")
    if text == "" then
      return 0
    end
    if text == "NaN" then
      return 0 / 0
    end
    if text == "Infinity" then
      return math.huge
    end
    if text == "-Infinity" then
      return -math.huge
    end
    local n = tonumber(text)
    if n == nil then
      return 0
    end
    return n
  end
  return 0
end

local function _fmt_number(value)
  if value ~= value then
    return "NaN"
  end
  if value == math.huge then
    return "Infinity"
  end
  if value == -math.huge then
    return "-Infinity"
  end
  if value == math.floor(value) and math.abs(value) < 1e15 then
    return string.format("%.0f", value)
  end
  return tostring(value)
end

local function s_str(value)
  local t = type(value)
  if value == nil then
    return ""
  end
  if t == "boolean" then
    return value and "true" or "false"
  end
  if t == "number" then
    return _fmt_number(value)
  end
  if t == "table" then
    local parts = {}
    for index = 1, #value do
      parts[index] = s_str(value[index])
    end
    return table.concat(parts, ", ")
  end
  return tostring(value)
end

-- JavaScript truthiness: false/nil, 0, "" and NaN are falsy; empty lists too.
local function s_bool(value)
  local t = type(value)
  if t == "boolean" then
    return value
  end
  if value == nil then
    return false
  end
  if t == "number" then
    return value ~= 0 and value == value
  end
  if t == "string" then
    return value ~= ""
  end
  if t == "table" then
    return #value > 0
  end
  return true
end

local function _looks_numeric(value)
  local t = type(value)
  if t == "boolean" then
    return false
  end
  if t == "number" then
    return true
  end
  if t == "string" then
    local text = value:match("^%s*(.-)%s*$")
    if text == "" then
      return false
    end
    if text == "NaN" then
      return true
    end
    return tonumber(text) ~= nil
  end
  return false
end

local function _both_numeric(a, b)
  return _looks_numeric(a) and _looks_numeric(b)
end

local function s_add(a, b)
  return s_num(a) + s_num(b)
end

local function s_sub(a, b)
  return s_num(a) - s_num(b)
end

local function s_mul(a, b)
  return s_num(a) * s_num(b)
end

local function s_div(a, b)
  local bn = s_num(b)
  local an = s_num(a)
  if bn == 0 then
    if an ~= an then
      return "NaN"
    end
    return an < 0 and "-Infinity" or "Infinity"
  end
  return an / bn
end

local function _is_whole(value)
  local t = type(value)
  if t == "boolean" then
    return false
  end
  if t == "number" then
    return value == math.floor(value)
  end
  if t == "string" then
    local text = value:match("^%s*(.-)%s*$")
    if text == "" then
      return false
    end
    local n = tonumber(text)
    return n ~= nil and n == math.floor(n)
  end
  return false
end

local function s_random(a, b)
  local lo = s_num(a)
  local hi = s_num(b)
  if hi < lo then
    lo, hi = hi, lo
  end
  if _is_whole(a) and _is_whole(b) then
    return math.floor(math.random() * (math.floor(hi) - math.ceil(lo) + 1)) + math.ceil(lo)
  end
  return math.random() * (hi - lo) + lo
end

local function s_gt(a, b)
  if _both_numeric(a, b) then
    return s_num(a) > s_num(b)
  end
  return s_str(a) > s_str(b)
end

local function s_lt(a, b)
  if _both_numeric(a, b) then
    return s_num(a) < s_num(b)
  end
  return s_str(a) < s_str(b)
end

local function s_eq(a, b)
  if _both_numeric(a, b) then
    local x = s_num(a)
    local y = s_num(b)
    if x ~= x or y ~= y then
      return false
    end
    return x == y
  end
  return s_str(a):lower() == s_str(b):lower()
end

local function s_not(value)
  return not s_bool(value)
end

local function s_and(a, b)
  return s_bool(a) and s_bool(b)
end

local function s_or(a, b)
  return s_bool(a) or s_bool(b)
end

local function s_join(a, b)
  return s_str(a) .. s_str(b)
end

local function s_letter(index, text)
  local string_value = s_str(text)
  local i = math.floor(s_num(index))
  if i ~= i or i == math.huge or i == -math.huge or i < 1 or i > #string_value then
    return ""
  end
  return string_value:sub(i, i)
end

local function s_length(value)
  return #s_str(value)
end

local function s_contains(haystack, needle)
  return s_str(haystack):lower():find(s_str(needle):lower(), 1, true) ~= nil
end

local function s_mod(a, b)
  local an = s_num(a)
  local bn = s_num(b)
  if bn == 0 then
    return 0 / 0
  end
  return an - bn * math.floor(an / bn)
end

local function s_round(value)
  return math.floor(s_num(value) + 0.5)
end

local function s_mathop(op, value)
  local n = s_num(value)
  local rad = (n * math.pi) / 180
  local function deg(r)
    return (r * 180) / math.pi
  end
  if op == "abs" then
    return math.abs(n)
  elseif op == "ceiling" then
    return math.ceil(n)
  elseif op == "floor" then
    return math.floor(n)
  elseif op == "sqrt" then
    if n >= 0 then
      return math.sqrt(n)
    end
    return 0 / 0
  elseif op == "sin" then
    return math.sin(rad)
  elseif op == "cos" then
    return math.cos(rad)
  elseif op == "tan" then
    return math.tan(rad)
  elseif op == "asin" then
    if n >= -1 and n <= 1 then
      return deg(math.asin(n))
    end
    return 0 / 0
  elseif op == "acos" then
    if n >= -1 and n <= 1 then
      return deg(math.acos(n))
    end
    return 0 / 0
  elseif op == "atan" then
    return deg(math.atan(n))
  elseif op == "ln" then
    if n > 0 then
      return math.log(n)
    end
    return 0 / 0
  elseif op == "log" then
    if n > 0 then
      return math.log10 and math.log10(n) or (math.log(n) / math.log(10))
    end
    return 0 / 0
  elseif op == "e ^" or op == "e^" then
    return math.exp(n)
  elseif op == "10 ^" or op == "10^" then
    return 10 ^ n
  end
  return 0
end

local function repeat_count(value)
  return math.max(0, math.floor(s_round(value)))
end

-- --- list helpers -----------------------------------------------------------

local function _list_index(lst, index)
  if type(lst) ~= "table" then
    return nil
  end
  local size = #lst
  if s_str(index) == "last" then
    if size > 0 then
      return size
    end
    return nil
  end
  local k = math.floor(s_num(index))
  if k ~= k or k == math.huge or k == -math.huge or k == 0 then
    return nil
  end
  local pos = k > 0 and k or (size + 1 + k)
  if pos >= 1 and pos <= size then
    return pos
  end
  return nil
end

local function list_item(lst, index)
  local pos = _list_index(lst, index)
  if pos == nil then
    return ""
  end
  return lst[pos]
end

local function list_delete(lst, index)
  if type(lst) ~= "table" then
    return
  end
  if s_str(index) == "all" then
    for i = #lst, 1, -1 do
      lst[i] = nil
    end
    return
  end
  local pos = _list_index(lst, index)
  if pos ~= nil then
    table.remove(lst, pos)
  end
end

local function list_clear(lst)
  if type(lst) ~= "table" then
    return
  end
  for i = #lst, 1, -1 do
    lst[i] = nil
  end
end

local function list_add(lst, item)
  if type(lst) == "table" then
    lst[#lst + 1] = item
  end
end

local function list_insert(lst, index, item)
  if type(lst) ~= "table" then
    return
  end
  local size = #lst
  if s_str(index) == "last" then
    lst[size + 1] = item
    return
  end
  local k = math.floor(s_num(index))
  if k ~= k or k == math.huge or k == -math.huge or k < 1 or k > size + 1 then
    return
  end
  table.insert(lst, k, item)
end

local function list_replace(lst, index, item)
  local pos = _list_index(lst, index)
  if pos ~= nil then
    lst[pos] = item
  end
end

local function list_index_of(lst, item)
  if type(lst) ~= "table" then
    return ""
  end
  for i = 1, #lst do
    if s_eq(lst[i], item) then
      return i
    end
  end
  return ""
end

local function list_length(value)
  if type(value) == "table" then
    return #value
  end
  if type(value) == "string" then
    return #value
  end
  return 0
end

local function list_contains(lst, item)
  if type(lst) ~= "table" then
    return false
  end
  for i = 1, #lst do
    if s_eq(lst[i], item) then
      return true
    end
  end
  return false
end

local function s_costume_name(ctx)
  local costume = ctx:costume()
  if costume then
    return costume.name
  end
  return ""
end

-- ---------------------------------------------------------------------------
-- Key mapping (LÖVE key constants -> Scratch key names)
-- ---------------------------------------------------------------------------

local KEY_MAP = {
  space = "space",
  left = "left arrow",
  right = "right arrow",
  up = "up arrow",
  down = "down arrow",
  ["return"] = "enter",
}

local function key_to_scratch(key)
  if KEY_MAP[key] then
    return KEY_MAP[key]
  end
  if type(key) == "string" and #key == 1 then
    local lower = key:lower()
    if lower >= "a" and lower <= "z" then
      return lower
    end
    if lower >= "0" and lower <= "9" then
      return lower
    end
  end
  return nil
end

-- math.atan2 exists in LuaJIT/Lua 5.1; 5.2+ renamed it to math.atan(y, x)
local function _atan2(x, y)
  if math.atan2 then
    return math.atan2(x, y)
  end
  return math.atan(y, x)
end

-- ---------------------------------------------------------------------------
-- Costume
-- ---------------------------------------------------------------------------

local Costume = {}
Costume.__index = Costume

function Costume.new(data, assets_dir)
  local self = setmetatable({}, Costume)
  self.name = tostring(data.name or "costume")
  self.costumeId = tostring(data.id or self.name)
  self.resolution = tonumber(data.resolution) or 1
  if self.resolution == 0 then
    self.resolution = 1
  end
  self.cx = (tonumber(data.cx) or 0) / self.resolution
  self.cy = (tonumber(data.cy) or 0) / self.resolution
  self.missing = false
  self.image = nil
  self.imageData = nil
  local file = tostring(data.file or "")
  if file == "" then
    self.missing = true
  else
    local path = assets_dir .. "/" .. file
    local ok_data, data_or_err = pcall(love.image.newImageData, path)
    if ok_data then
      self.imageData = data_or_err
      local ok_image, image_or_err = pcall(love.graphics.newImage, data_or_err)
      if ok_image then
        self.image = image_or_err
      else
        self.missing = true
      end
    else
      self.missing = true
    end
  end
  self._mask = nil
  return self
end

function Costume:width()
  if self.image then
    return self.image:getWidth() / self.resolution
  end
  return 32
end

function Costume:height()
  if self.image then
    return self.image:getHeight() / self.resolution
  end
  return 32
end

function Costume:_ensure_alpha()
  if self._mask then
    return self._mask
  end
  local data = self.imageData
  if not data then
    return nil
  end
  local w = data:getWidth()
  local h = data:getHeight()
  if w == 0 or h == 0 then
    return nil
  end
  local bits = {}
  local l, t, r, b = w, h, -1, -1
  for y = 0, h - 1 do
    for x = 0, w - 1 do
      local alpha = select(4, data:getPixel(x, y))
      if alpha > 0 then
        bits[y * w + x] = true
        if x < l then l = x end
        if x > r then r = x end
        if y < t then t = y end
        if y > b then b = y end
      end
    end
  end
  if r < l then
    l, t, r, b = 0, 0, w - 1, h - 1
  end
  self._mask = { w = w, h = h, bits = bits, l = l, t = t, r = r + 1, b = b + 1 }
  return self._mask
end

-- ---------------------------------------------------------------------------
-- SoundAsset
-- ---------------------------------------------------------------------------

local SoundAsset = {}
SoundAsset.__index = SoundAsset

function SoundAsset.new(data, assets_dir)
  local self = setmetatable({}, SoundAsset)
  self.name = tostring(data.name or "sound")
  self.path = assets_dir .. "/" .. tostring(data.file or "")
  self.source = nil
  local ok, source = pcall(love.audio.newSource, self.path, "static")
  if ok then
    self.source = source
  end
  return self
end

function SoundAsset:play(volume, pitch)
  if not self.source then
    return nil
  end
  local node = self.source:clone()
  node:setVolume(math.max(0, math.min(1, volume)))
  node:setPitch(math.max(0.05, (100 + pitch) / 100))
  node:play()
  return node
end

-- ---------------------------------------------------------------------------
-- Actor
-- ---------------------------------------------------------------------------

local Actor = {}
Actor.__index = Actor

local EFFECT_NAMES = { "ghost", "color", "fisheye", "whirl", "pixelate", "mosaic", "brightness" }

function Actor.new(runtime, target, isClone)
  local self = setmetatable({}, Actor)
  self.rt = runtime
  self.target = target
  self.is_clone = isClone or false
  self.x = target.x
  self.y = target.y
  self.direction = target.direction
  self.size = target.size
  self.visible = target.visible
  self.rotation_style = target.rotation_style
  self.volume = target.volume
  self.current_costume = target.current_costume
  self.effects = {}
  for _, name in ipairs(EFFECT_NAMES) do
    self.effects[name] = 0
  end
  self.sound_effects = { PITCH = 0, PAN = 0 }
  self.say = nil
  self.think = nil
  self.dead = false
  if isClone then
    self.vars = {}
    for key, value in pairs(target.variables) do
      self.vars[key] = value
    end
    self.lists = {}
    for key, value in pairs(target.lists) do
      local copy = {}
      for index = 1, #value do
        copy[index] = value[index]
      end
      self.lists[key] = copy
    end
  else
    self.vars = target.variables
    self.lists = target.lists
  end
  return self
end

function Actor:costume()
  local costumes = self.target.costumes
  if #costumes == 0 then
    return nil
  end
  local index = math.floor(self.current_costume) % #costumes
  if index < 0 then
    index = index + #costumes
  end
  return costumes[index + 1]
end

function Actor:set_costume(ref)
  local costumes = self.target.costumes
  if #costumes == 0 then
    return
  end
  local text = s_str(ref)
  for i = 1, #costumes do
    if text == costumes[i].name or text == costumes[i].costumeId then
      self.current_costume = i - 1
      return
    end
  end
  if _looks_numeric(text) then
    local index = math.floor(s_num(text)) - 1
    self.current_costume = math.max(0, math.min(index, #costumes - 1))
    return
  end
  self.rt:warn_once(string.format("unknown costume '%s' for sprite '%s'", text, self.target.name))
end

function Actor:next_costume()
  local costumes = self.target.costumes
  if #costumes > 0 then
    self.current_costume = (math.floor(self.current_costume) + 1) % #costumes
  end
end

function Actor:remove_clone()
  self.rt:remove_clone(self)
end

function Actor:half_size()
  local costume = self:costume()
  if not costume then
    return 0, 0
  end
  local scale = self.size / 100
  return (costume:width() * scale) / 2, (costume:height() * scale) / 2
end

function Actor:rect()
  local costume = self:costume()
  local mask = costume and costume:_ensure_alpha() or nil
  if mask then
    local scale = self.size / 100
    local res = costume.resolution
    local left = math.floor(self.x + (mask.l / res - costume.cx) * scale)
    local top = math.floor(self.y + (costume.cy - mask.b / res) * scale)
    local width = math.max(1, math.floor(((mask.r - mask.l) / res) * scale))
    local height = math.max(1, math.floor(((mask.b - mask.t) / res) * scale))
    return {
      left = left, top = top, width = width, height = height,
      right = left + width, bottom = top + height,
    }
  end
  local hw, hh = self:half_size()
  local left = math.floor(self.x - hw)
  local top = math.floor(self.y - hh)
  local width = math.max(1, math.floor(hw * 2))
  local height = math.max(1, math.floor(hh * 2))
  return {
    left = left, top = top, width = width, height = height,
    right = left + width, bottom = top + height,
  }
end

function Actor:opaqueAt(sx, sy)
  local costume = self:costume()
  if not costume then
    return false
  end
  local mask = costume:_ensure_alpha()
  if not mask then
    local r = self:rect()
    return sx >= r.left and sx < r.right and sy >= r.top and sy < r.bottom
  end
  local scale = self.size / 100
  if scale <= 0 then
    return false
  end
  local res = costume.resolution
  local px = math.floor(((sx - self.x) / scale + costume.cx) * res)
  local py = math.floor((costume.cy - (sy - self.y) / scale) * res)
  if px < 0 or py < 0 or px >= mask.w or py >= mask.h then
    return false
  end
  return mask.bits[py * mask.w + px] == true
end

function Actor:overlaps(other)
  local ra = self:rect()
  local rb = other:rect()
  if ra.left >= rb.right or ra.right <= rb.left or ra.top >= rb.bottom or ra.bottom <= rb.top then
    return false
  end
  local ca = self:costume()
  local cb = other:costume()
  local ma = ca and ca:_ensure_alpha() or nil
  local mb = cb and cb:_ensure_alpha() or nil
  if not ma or not mb then
    return true
  end
  local sa = self.size / 100
  local sb = other.size / 100
  if sa <= 0 or sb <= 0 then
    return false
  end
  local resa = ca.resolution
  local ax = self.x - ca.cx * sa
  local ay = self.y + ca.cy * sa
  local bx = other.x - cb.cx * sb
  local by = other.y + cb.cy * sb
  local pitch = sa / resa
  if pitch <= 0 then
    return false
  end
  local dx = math.floor((bx - ax) / pitch + 0.5)
  local dy = math.floor((ay - by) / pitch + 0.5)
  local x0 = math.max(ma.l, dx + mb.l)
  local x1 = math.min(ma.r, dx + mb.r)
  local y0 = math.max(ma.t, dy + mb.t)
  local y1 = math.min(ma.b, dy + mb.b)
  for y = y0, y1 - 1 do
    local rowa = y * ma.w
    local rowb = (y - dy) * mb.w
    for x = x0, x1 - 1 do
      if ma.bits[rowa + x] and mb.bits[rowb + x - dx] then
        return true
      end
    end
  end
  return false
end

-- ---------------------------------------------------------------------------
-- Scripts and threads
-- ---------------------------------------------------------------------------

local function ScriptReg(sprite, hat, fields, fn)
  return { sprite = sprite, hat = hat, fields = fields, fn = fn }
end

-- ---------------------------------------------------------------------------
-- Runtime
-- ---------------------------------------------------------------------------

local Runtime = {}
Runtime.__index = Runtime

local function _copy_string_map(data)
  local out = {}
  for key, value in pairs(data or {}) do
    out[tostring(key)] = value
  end
  return out
end

local function _copy_lists(data)
  local out = {}
  for key, value in pairs(data or {}) do
    local copy = {}
    for index = 1, #(value or {}) do
      copy[index] = value[index]
    end
    out[tostring(key)] = copy
  end
  return out
end

local function _load_target(data, isStage, assets_dir)
  local costumeList = {}
  for _, costume_data in ipairs(data.costumes or {}) do
    costumeList[#costumeList + 1] = Costume.new(costume_data, assets_dir)
  end
  local sounds = {}
  for _, sound_data in ipairs(data.sounds or {}) do
    local sound = SoundAsset.new(sound_data, assets_dir)
    sounds[sound.name] = sound
  end
  local visible = data.visible
  if visible == nil then
    visible = true
  end
  local direction = data.direction
  if direction == nil then
    direction = 90
  end
  local size = data.size
  if size == nil then
    size = 100
  end
  local volume = data.volume
  if volume == nil then
    volume = 100
  end
  return {
    name = tostring(data.name or (isStage and "Stage" or "Sprite")),
    is_stage = isStage,
    x = tonumber(data.x) or 0,
    y = tonumber(data.y) or 0,
    direction = tonumber(direction) or 90,
    size = tonumber(size) or 100,
    visible = visible and true or false,
    rotation_style = tostring(data.rotationStyle or "all around"),
    layer_order = tonumber(data.layerOrder) or 0,
    volume = tonumber(volume) or 100,
    current_costume = tonumber(data.currentCostume) or 0,
    costumes = costumeList,
    sounds = sounds,
    variables = _copy_string_map(data.variables),
    lists = _copy_lists(data.lists),
  }
end

function Runtime.new(manifest, scripts, options)
  local self = setmetatable({}, Runtime)
  options = options or {}
  self.manifest = manifest
  self.assetsDir = tostring(manifest.assetDir or "assets")
  self.scale = math.max(1, tonumber(options.scale or manifest.scale) or 2)
  self.fps = math.max(1, tonumber(options.fps or manifest.fps) or DEFAULT_FPS)

  self.warned = {}

  self.stage_def = _load_target(manifest.stage or {}, true, self.assetsDir)
  self.sprite_defs = {}
  self.target_defs = { self.stage_def }
  for _, data in ipairs(manifest.sprites or {}) do
    local def = _load_target(data, false, self.assetsDir)
    self.sprite_defs[def.name] = def
    self.target_defs[#self.target_defs + 1] = def
  end

  self.stage_actor = Actor.new(self, self.stage_def, false)
  self.actors = { self.stage_actor }
  for _, def in ipairs(self.target_defs) do
    if not def.is_stage then
      self.actors[#self.actors + 1] = Actor.new(self, def, false)
    end
  end
  self.layers = {}
  for _, actor in ipairs(self.actors) do
    if not actor.target.is_stage then
      self.layers[#self.layers + 1] = actor
    end
  end
  table.sort(self.layers, function(a, b)
    return a.target.layer_order < b.target.layer_order
  end)

  self.vars = self.stage_def.variables
  self.lists = self.stage_def.lists
  self.timer = 0
  self.answer = ""
  self.loudness = 100
  self.username = ""
  self.mouse_x = 0
  self.mouse_y = 0
  self.mouse_down = false
  self.down_keys = {}
  self.frame = 0
  self.frame_time = 1 / self.fps
  self.quitting = false

  self.monitors = {}
  self.monitor_visible = {}
  self.list_visible = {}
  for _, m in ipairs(manifest.monitors or {}) do
    self.monitors[m.id] = m
    local visible = m.visible ~= false
    self.monitor_visible[m.id] = visible
    if m.isList then
      self.list_visible[m.id] = visible
    end
  end

  self.asking = false
  self.ask_question = ""
  self.ask_buffer = ""

  self.routes = self:_build_routes(scripts)
  self.threads = {}
  self.current_thread = nil

  self.font = nil
  self.big_font = nil
  self._active_audio = {}
  self._backdrop_cache = nil
  self._acc = 0
  return self
end

function Runtime:_build_routes(scripts)
  local routes = {
    flag = {},
    key = {},
    click = {},
    broadcast = {},
    backdrop = {},
    clone = {},
    greater = {},
  }
  local function push(map, key, reg)
    if not map[key] then
      map[key] = {}
    end
    map[key][#map[key] + 1] = reg
  end
  for _, reg in ipairs(scripts) do
    if reg.hat == "event_whenflagclicked" then
      routes.flag[#routes.flag + 1] = reg
    elseif reg.hat == "event_whenkeypressed" then
      push(routes.key, reg.fields.KEY_OPTION or "space", reg)
    elseif reg.hat == "event_whenthisspriteclicked" then
      push(routes.click, reg.sprite, reg)
    elseif reg.hat == "event_whenbroadcastreceived" then
      push(routes.broadcast, reg.fields.BROADCAST_OPTION or "", reg)
    elseif reg.hat == "event_whenbackdroptoggles" then
      push(routes.backdrop, reg.fields.BACKDROP or "", reg)
    elseif reg.hat == "control_start_as_clone" then
      push(routes.clone, reg.sprite, reg)
    elseif reg.hat == "event_whengreaterthan" then
      routes.greater[#routes.greater + 1] = {
        op = tostring(reg.fields.WHENGREATERTHANOPERATOR or "loudness"),
        threshold = s_num(reg.fields.WHENGREATERTHANVALUE == nil and 100
          or reg.fields.WHENGREATERTHANVALUE),
        reg = reg,
        latched = false,
      }
    else
      self:warn_once(string.format("script hat '%s' (%s) is not routed and will never run",
        reg.hat, reg.sprite))
    end
  end
  return routes
end

function Runtime:warn_once(message)
  if not self.warned[message] then
    self.warned[message] = true
    print("warning: " .. message)
  end
end

function Runtime:unsupported(opcode)
  self:warn_once(string.format("block '%s' is not supported by this conversion", opcode))
  return ""
end

-- ---------------------------------------------------------------------------
-- threading
-- ------------------------------------------------------------------

function Runtime:spawn(reg, actor)
  if actor.dead then
    return nil
  end
  local co = coroutine.create(function()
    reg.fn(actor, self)
  end)
  local thread = { co = co, actor = actor, reg = reg, done = false, stepped_frame = -1 }
  self.threads[#self.threads + 1] = thread
  return thread
end

function Runtime:spawn_regs(regs)
  -- snapshot: a script creating clones while running must not receive the
  -- event it is itself causing, and the actor list must not mutate under us
  local started = {}
  local actors_snapshot = {}
  for _, actor in ipairs(self.actors) do
    actors_snapshot[#actors_snapshot + 1] = actor
  end
  for _, reg in ipairs(regs) do
    for _, actor in ipairs(actors_snapshot) do
      if not actor.dead and actor.target.name == reg.sprite then
        local thread = self:spawn(reg, actor)
        if thread then
          started[#started + 1] = thread
        end
      end
    end
  end
  return started
end

function Runtime:green_flag()
  self:spawn_regs(self.routes.flag)
end

function Runtime:broadcast(name)
  self:spawn_regs(self.routes.broadcast[name] or {})
end

function Runtime:broadcast_wait(name)
  local started = self:spawn_regs(self.routes.broadcast[name] or {})
  if #started == 0 then
    return
  end
  while true do
    local any_alive = false
    for _, thread in ipairs(started) do
      if not thread.done then
        any_alive = true
        break
      end
    end
    if not any_alive then
      break
    end
    coroutine.yield()
  end
end

function Runtime:stop_all()
  for _, thread in ipairs(self.threads) do
    thread.done = true
  end
  self:stop_all_sounds()
end

function Runtime:stop_others(actor)
  for _, thread in ipairs(self.threads) do
    if thread ~= self.current_thread and thread.actor == actor and not thread.done then
      thread.done = true
    end
  end
end

function Runtime:stop_script(actor)
  for _, thread in ipairs(self.threads) do
    if thread.actor == actor then
      thread.done = true
    end
  end
end

function Runtime:step()
  self.frame = self.frame + 1
  self.timer = self.timer + self.frame_time
  self:_check_greater_than()
  local steps = 0
  local index = 1
  while index <= #self.threads do
    local thread = self.threads[index]
    index = index + 1
    if not thread.done and thread.stepped_frame ~= self.frame then
      thread.stepped_frame = self.frame
      steps = steps + 1
      if steps > MAX_STEPS_PER_FRAME then
        self:warn_once("frame step limit reached (possible broadcast loop)")
        break
      end
      self.current_thread = thread
      local ok, err = coroutine.resume(thread.co)
      self.current_thread = nil
      if not ok then
        print("error: script crashed: " .. tostring(err))
        thread.done = true
      elseif coroutine.status(thread.co) == "dead" then
        thread.done = true
      end
    end
  end
  local alive = {}
  for _, thread in ipairs(self.threads) do
    if not thread.done then
      alive[#alive + 1] = thread
    end
  end
  self.threads = alive
end

function Runtime:_check_greater_than()
  for _, route in ipairs(self.routes.greater) do
    local value = route.op == "timer" and self.timer or self.loudness
    if value > route.threshold then
      if not route.latched then
        route.latched = true
        self:spawn(route.reg, self:_actor_for(route.reg.sprite))
      end
    else
      route.latched = false
    end
  end
end

function Runtime:_actor_for(spriteName)
  for _, actor in ipairs(self.actors) do
    if not actor.dead and actor.target.name == spriteName then
      return actor
    end
  end
  return self.stage_actor
end

-- ---------------------------------------------------------------------------
-- waits
-- ------------------------------------------------------------------

function Runtime:wait_secs(seconds)
  local frames = math.max(1, math.floor(s_num(seconds) * self.fps + 0.5))
  for _ = 1, frames do
    coroutine.yield()
  end
end

function Runtime:glide_to(actor, seconds, x, y)
  local frames = math.max(1, math.floor(s_num(seconds) * self.fps + 0.5))
  local x0 = actor.x
  local y0 = actor.y
  local tx = s_num(x)
  local ty = s_num(y)
  for i = 1, frames do
    local t = i / frames
    actor.x = x0 + (tx - x0) * t
    actor.y = y0 + (ty - y0) * t
    coroutine.yield()
  end
end

function Runtime:ask(question)
  self.ask_question = question
  self.ask_buffer = ""
  self.asking = true
  while self.asking do
    coroutine.yield()
  end
end

-- ---------------------------------------------------------------------------
-- motion
-- ------------------------------------------------------------------

function Runtime:norm_dir(direction)
  return ((s_num(direction) + 180) % 360 + 360) % 360 - 180
end

function Runtime:move(actor, steps)
  local amount = s_num(steps)
  local rad = (actor.direction * math.pi) / 180
  actor.x = actor.x + amount * math.sin(rad)
  actor.y = actor.y + amount * math.cos(rad)
end

function Runtime:point_towards(actor, ref)
  local tx = self:tx(ref)
  local ty = self:ty(ref)
  actor.direction = self:norm_dir(math.deg(_atan2(tx - actor.x, ty - actor.y)))
end

function Runtime:tx(ref)
  if ref == "_mouse_" then
    return self.mouse_x
  end
  local target = self:_find_sprite(ref)
  return target and target.x or 0
end

function Runtime:ty(ref)
  if ref == "_mouse_" then
    return self.mouse_y
  end
  local target = self:_find_sprite(ref)
  return target and target.y or 0
end

function Runtime:_find_sprite(name)
  for _, actor in ipairs(self.layers) do
    if actor.target.name == name and not actor.dead then
      return actor
    end
  end
  return nil
end

function Runtime:goto_target(actor, ref)
  if ref == "_mouse_" then
    actor.x = self.mouse_x
    actor.y = self.mouse_y
  elseif ref == "_random_" then
    actor.x = math.random() * STAGE_W - STAGE_W / 2
    actor.y = math.random() * STAGE_H - STAGE_H / 2
  else
    local target = self:_find_sprite(ref)
    if not target then
      self:warn_once(string.format("goto target '%s' not found", ref))
      return
    end
    actor.x = target.x
    actor.y = target.y
  end
end

function Runtime:bounce(actor)
  local hw, hh = actor:half_size()
  if hw * 2 >= STAGE_W or hh * 2 >= STAGE_H then
    return
  end
  local left = -STAGE_W / 2 + hw
  local right = STAGE_W / 2 - hw
  local bottom = -STAGE_H / 2 + hh
  local top = STAGE_H / 2 - hh
  local hit_x = actor.x < left or actor.x > right
  local hit_y = actor.y < bottom or actor.y > top
  if not hit_x and not hit_y then
    return
  end
  actor.x = math.max(left, math.min(right, actor.x))
  actor.y = math.max(bottom, math.min(top, actor.y))
  local direction = actor.direction
  if hit_x then
    direction = -direction
  end
  if hit_y then
    direction = 180 - direction
  end
  actor.direction = self:norm_dir(direction)
end

-- ---------------------------------------------------------------------------
-- looks
-- ------------------------------------------------------------------

function Runtime:clamp_size(value)
  return math.max(15, math.min(150, s_num(value)))
end

function Runtime:clamp_volume(value)
  return math.max(0, math.min(100, s_num(value)))
end

function Runtime:set_effect(actor, effect, value)
  actor.effects[effect] = s_num(value)
  if effect ~= "ghost" then
    self:warn_once(string.format(
      "visual effect '%s' is stored but not rendered by the LÖVE runtime", effect))
  end
end

function Runtime:change_effect(actor, effect, delta)
  self:set_effect(actor, effect, (actor.effects[effect] or 0) + s_num(delta))
end

function Runtime:clear_effects(actor)
  for key in pairs(actor.effects) do
    actor.effects[key] = 0
  end
end

local function _table_index(list, value)
  for i = 1, #list do
    if list[i] == value then
      return i
    end
  end
  return nil
end

function Runtime:go_to_front(actor)
  local i = _table_index(self.layers, actor)
  if i then
    table.remove(self.layers, i)
    self.layers[#self.layers + 1] = actor
  end
end

function Runtime:go_to_back(actor)
  local i = _table_index(self.layers, actor)
  if i then
    table.remove(self.layers, i)
    table.insert(self.layers, 1, actor)
  end
end

function Runtime:go_layer(actor, delta)
  local index = _table_index(self.layers, actor)
  if not index then
    return
  end
  local new_index = math.max(1, math.min(#self.layers, index + math.floor(delta)))
  if new_index ~= index then
    table.remove(self.layers, index)
    table.insert(self.layers, new_index, actor)
  end
end

-- ---------------------------------------------------------------------------
-- stage
-- ------------------------------------------------------------------

function Runtime:set_backdrop(ref)
  local costumes = self.stage_def.costumes
  if #costumes == 0 then
    return
  end
  local previous = self.stage_def.current_costume
  local found = false
  for i = 1, #costumes do
    if ref == costumes[i].name or ref == costumes[i].costumeId then
      self.stage_def.current_costume = i - 1
      found = true
      break
    end
  end
  if not found then
    if _looks_numeric(ref) then
      local index = math.floor(s_num(ref)) - 1
      self.stage_def.current_costume = math.max(0, math.min(index, #costumes - 1))
    else
      self:warn_once(string.format("unknown backdrop '%s'", ref))
      return
    end
  end
  if self.stage_def.current_costume ~= previous then
    self:_fire_backdrop_hats()
  end
end

function Runtime:next_backdrop()
  local costumes = self.stage_def.costumes
  if #costumes == 0 then
    return
  end
  self.stage_def.current_costume = (self.stage_def.current_costume + 1) % #costumes
  self:_fire_backdrop_hats()
end

function Runtime:_fire_backdrop_hats()
  local costumes = self.stage_def.costumes
  local name = costumes[self.stage_def.current_costume + 1].name
  local regs = self.routes.backdrop and self.routes.backdrop[name] or {}
  if #regs > 0 then
    self:spawn_regs(regs)
  end
end

-- ---------------------------------------------------------------------------
-- sound
-- ------------------------------------------------------------------

function Runtime:play_sound(actor, name)
  local sound = actor.target.sounds[name]
  if not sound then
    self:warn_once(string.format("sound '%s' not found for '%s'", name, actor.target.name))
    return nil
  end
  local volume = math.max(0, math.min(1, actor.volume / 100))
  local pitch = actor.sound_effects.PITCH or 0
  local node = sound:play(volume, pitch)
  if node then
    self._active_audio[#self._active_audio + 1] = node
  end
  return node
end

function Runtime:play_until_done(actor, name)
  local node = self:play_sound(actor, name)
  if not node then
    return
  end
  while node:isPlaying() do
    coroutine.yield()
  end
end

function Runtime:stop_all_sounds()
  for _, node in ipairs(self._active_audio) do
    pcall(function()
      node:stop()
    end)
  end
  self._active_audio = {}
end

function Runtime:change_sound_effect(actor, effect, delta)
  local key = effect:upper()
  actor.sound_effects[key] = (actor.sound_effects[key] or 0) + s_num(delta)
  if key ~= "PITCH" then
    self:warn_once(string.format(
      "sound effect '%s' has no audible effect in this runtime", key))
  end
end

function Runtime:set_sound_effect(actor, effect, value)
  actor.sound_effects[effect:upper()] = s_num(value)
end

function Runtime:clear_sound_effects(actor)
  for key in pairs(actor.sound_effects) do
    actor.sound_effects[key] = 0
  end
end

-- ---------------------------------------------------------------------------
-- sensing
-- ------------------------------------------------------------------

function Runtime:key_down(key)
  local name = s_str(key)
  if name == "any" then
    return next(self.down_keys) ~= nil
  end
  return self.down_keys[name] == true
end

function Runtime:touching(actor, ref)
  local rect = actor:rect()
  if ref == "_edge_" then
    return rect.left <= -STAGE_W / 2
      or rect.right >= STAGE_W / 2
      or rect.top >= STAGE_H / 2
      or rect.bottom <= -STAGE_H / 2
  end
  if ref == "_mouse_" then
    return actor:opaqueAt(self.mouse_x, self.mouse_y)
  end
  local other = self:_visible_actor(ref, actor)
  if not other then
    return false
  end
  return actor:overlaps(other)
end

function Runtime:_visible_actor(name, exclude)
  for i = #self.layers, 1, -1 do
    local actor = self.layers[i]
    if actor ~= exclude and not actor.dead and actor.visible and actor.target.name == name then
      return actor
    end
  end
  return nil
end

function Runtime:distance_to(actor, ref)
  local dx = self:tx(ref) - actor.x
  local dy = self:ty(ref) - actor.y
  return math.sqrt(dx * dx + dy * dy)
end

local function _parse_colour(text)
  local value = s_str(text):match("^%s*(.-)%s*$")
  if value == "" then
    return nil
  end
  if value:sub(1, 1) == "#" and (#value == 4 or #value == 7) then
    if #value == 4 then
      local r = tonumber(value:sub(2, 2) .. value:sub(2, 2), 16)
      local g = tonumber(value:sub(3, 3) .. value:sub(3, 3), 16)
      local b = tonumber(value:sub(4, 4) .. value:sub(4, 4), 16)
      return string.format("%d,%d,%d", r, g, b)
    end
    local r = tonumber(value:sub(2, 3), 16)
    local g = tonumber(value:sub(4, 5), 16)
    local b = tonumber(value:sub(6, 7), 16)
    return string.format("%d,%d,%d", r, g, b)
  end
  return nil
end

function Runtime:touching_colour(actor, colour)
  local target = _parse_colour(colour)
  if not target then
    return false
  end
  return self:_probe(actor, function(rgb)
    return rgb == target
  end, target)
end

function Runtime:colour_touching_colour(actor, first, second)
  local c1 = _parse_colour(first)
  local c2 = _parse_colour(second)
  if not c1 or not c2 then
    return false
  end
  return self:_probe(actor, function(rgb)
    return rgb == c1
  end, c2)
end

function Runtime:_render_to(actor)
  -- draw the actor alone onto an offscreen canvas in stage pixel space
  local costume = actor:costume()
  if not costume or not costume.image then
    return nil
  end
  local canvas = love.graphics.newCanvas(STAGE_W, STAGE_H)
  love.graphics.setCanvas(canvas)
  love.graphics.clear(0, 0, 0, 0)
  self:_draw_actor(actor, 1)
  love.graphics.setCanvas()
  local ok, image_data = pcall(function()
    return love.graphics.newImageData(canvas)
  end)
  if not ok then
    return nil
  end
  return image_data
end

function Runtime:_probe(actor, matchActorPixel, target)
  local image_data = self:_render_to(actor)
  if not image_data then
    return false
  end
  local step = 4
  local backdrop_data = self:_backdrop_image_data()
  for py = 0, STAGE_H - 1, step do
    for px = 0, STAGE_W - 1, step do
      local r, g, b, a = image_data:getPixel(px, py)
      if a >= 128 then
        local rgb = string.format("%d,%d,%d", r, g, b)
        if matchActorPixel(rgb) and self:_colour_at(px, py, backdrop_data) == target then
          return true
        end
      end
    end
  end
  return false
end

function Runtime:_colour_at(px, py, backdrop_data)
  if backdrop_data then
    local r, g, b, a = backdrop_data:getPixel(px, py)
    if a >= 128 then
      return string.format("%d,%d,%d", r, g, b)
    end
  end
  for i = #self.layers, 1, -1 do
    local other = self.layers[i]
    if not other.dead and other.visible then
      local costume = other:costume()
      local data = costume and costume.imageData or nil
      if data then
        local r, g, b, a = data:getPixel(px, py)
        if a >= 128 then
          return string.format("%d,%d,%d", r, g, b)
        end
      end
    end
  end
  return nil
end

function Runtime:_backdrop_image_data()
  if #self.stage_def.costumes == 0 then
    return nil
  end
  local costume = self.stage_def.costumes[self.stage_def.current_costume + 1]
  if not costume then
    return nil
  end
  if self._backdrop_cache and self._backdrop_cache.index == self.stage_def.current_costume then
    return self._backdrop_cache.image
  end
  self._backdrop_cache = { index = self.stage_def.current_costume, image = costume.imageData }
  return costume.imageData
end

function Runtime:of(attribute, obj)
  if obj == "_mouse_" then
    if attribute == "x position" then
      return self.mouse_x
    end
    if attribute == "y position" then
      return self.mouse_y
    end
    return 0
  end
  if attribute == "backdrop" then
    local costumes = self.stage_def.costumes
    if #costumes > 0 then
      return costumes[self.stage_def.current_costume + 1].name
    end
    return ""
  end
  local actor = self:_visible_actor(obj)
  if not actor then
    return ""
  end
  if attribute == "x position" then
    return actor.x
  end
  if attribute == "y position" then
    return actor.y
  end
  if attribute == "direction" then
    return actor.direction
  end
  if attribute == "size" then
    return actor.size
  end
  if attribute == "volume" then
    return actor.volume
  end
  if attribute == "costume #" then
    return actor.current_costume + 1
  end
  if attribute == "costume name" then
    local costume = actor:costume()
    return costume and costume.name or ""
  end
  if attribute == "loudness" then
    return self.loudness
  end
  return ""
end

function Runtime:reset_timer()
  self.timer = 0
end

-- ---------------------------------------------------------------------------
-- variables and lists
-- ------------------------------------------------------------------

function Runtime:set_monitor_visible(monitorId, visible)
  if self.monitor_visible[monitorId] ~= nil then
    self.monitor_visible[monitorId] = visible
  else
    self:warn_once(string.format("no monitor for id '%s'", monitorId))
  end
end

function Runtime:set_list_visible(monitorId, visible)
  if self.list_visible[monitorId] ~= nil then
    self.list_visible[monitorId] = visible
  else
    for _, known in pairs(self.monitors) do
      if known.isList and known.label then
        if self.list_visible[known.id] == nil then
          self.list_visible[known.id] = true
        end
      end
    end
  end
end

-- ---------------------------------------------------------------------------
-- clones
-- ------------------------------------------------------------------

function Runtime:create_clone(actor, targetName)
  local sourceActor = nil
  local definition
  if targetName == "_myself_" then
    sourceActor = actor
    definition = actor.target
  else
    definition = self.sprite_defs[targetName]
    if not definition then
      self:warn_once(string.format("cannot clone unknown sprite '%s'", targetName))
      return
    end
    for _, existing in ipairs(self.actors) do
      if not existing.dead and existing.target.name == targetName and not existing.is_clone then
        sourceActor = existing
        break
      end
    end
  end
  local cloneCount = 0
  for _, a in ipairs(self.actors) do
    if a.is_clone and not a.dead then
      cloneCount = cloneCount + 1
    end
  end
  if cloneCount >= MAX_CLONES then
    self:warn_once("clone limit (300) reached")
    return
  end
  local clone = Actor.new(self, definition, true)
  if sourceActor then
    clone.x = sourceActor.x
    clone.y = sourceActor.y
    clone.direction = sourceActor.direction
    clone.size = sourceActor.size
    clone.current_costume = sourceActor.current_costume
    -- Scratch clones inherit the creator's current local variable values
    for key, value in pairs(sourceActor.vars) do
      clone.vars[key] = value
    end
    clone.lists = {}
    for key, value in pairs(sourceActor.lists) do
      local copy = {}
      for index = 1, #value do
        copy[index] = value[index]
      end
      clone.lists[key] = copy
    end
  end
  self.actors[#self.actors + 1] = clone
  local sourceIndex = sourceActor and _table_index(self.layers, sourceActor) or nil
  if sourceIndex then
    table.insert(self.layers, sourceIndex + 1, clone)
  else
    self.layers[#self.layers + 1] = clone
  end
  for _, reg in ipairs(self.routes.clone[definition.name] or {}) do
    self:spawn(reg, clone)
  end
end

function Runtime:remove_clone(actor)
  actor.dead = true
  local i = _table_index(self.layers, actor)
  if i then
    table.remove(self.layers, i)
  end
  for _, thread in ipairs(self.threads) do
    if thread.actor == actor then
      thread.done = true
    end
  end
end

-- ---------------------------------------------------------------------------
-- rendering
-- ------------------------------------------------------------------

function Runtime:_stage_to_canvas(x, y, pixelScale)
  pixelScale = pixelScale or self.scale
  return (x + STAGE_W / 2) * pixelScale, (STAGE_H / 2 - y) * pixelScale
end

function Runtime:_draw_actor(actor, pixelScale)
  local costume = actor:costume()
  if not costume then
    return
  end
  local scale = (actor.size / 100) * pixelScale
  local cx, cy = self:_stage_to_canvas(actor.x, actor.y, pixelScale)

  love.graphics.push()
  love.graphics.translate(cx, cy)
  if actor.rotation_style == "all around" then
    love.graphics.rotate((actor.direction - 90) * math.pi / 180)
  elseif actor.rotation_style == "left-right" and actor.direction < 0 then
    love.graphics.scale(-1, 1)
  end
  local ghost = actor.effects.ghost or 0
  local alpha = math.max(0, math.min(1, 1 - ghost / 100))
  if costume.image then
    love.graphics.setColor(1, 1, 1, alpha)
    local w = costume:width() * scale
    local h = costume:height() * scale
    love.graphics.draw(costume.image,
      -costume.cx * scale, -costume.cy * scale,
      0, w / costume.image:getWidth(), h / costume.image:getHeight())
  else
    love.graphics.setColor(0.47, 0.47, 0.63, alpha)
    local w = 32 * scale
    love.graphics.rectangle("fill", -w / 2, -w / 2, w, w)
  end
  love.graphics.pop()
  love.graphics.setColor(1, 1, 1, 1)
end

local function _wrap_text(text, width)
  local words = {}
  for word in s_str(text):gmatch("%S+") do
    words[#words + 1] = word
  end
  if #words == 0 then
    return { "" }
  end
  local lines = {}
  local current = words[1]
  for i = 2, #words do
    local word = words[i]
    if #current + 1 + #word <= width then
      current = current .. " " .. word
    else
      lines[#lines + 1] = current
      current = word
    end
  end
  lines[#lines + 1] = current
  return lines
end

function Runtime:_draw_bubble(actor)
  local text = s_str(actor.say ~= nil and actor.say or actor.think)
  if text == "" then
    return
  end
  local lines = _wrap_text(text, 24)
  local lineH = 16 * self.scale
  local width = 0
  for _, line in ipairs(lines) do
    width = math.max(width, self.font:getWidth(line))
  end
  width = width + 14 * self.scale
  local height = lineH * #lines + 8 * self.scale
  local _, hh = actor:half_size()
  local bxRaw, byRaw = self:_stage_to_canvas(actor.x, actor.y + hh)
  local bx = math.max(4, math.min(love.graphics.getWidth() - width - 4, bxRaw - width / 2))
  local by = math.max(4, byRaw - height - 12 * self.scale)
  love.graphics.setColor(1, 1, 1, 1)
  love.graphics.rectangle("fill", bx, by, width, height)
  love.graphics.setColor(0.7, 0.7, 0.7, 1)
  love.graphics.rectangle("line", bx, by, width, height)
  love.graphics.setColor(0.08, 0.08, 0.08, 1)
  for i, line in ipairs(lines) do
    love.graphics.print(line, bx + 7 * self.scale, by + 4 * self.scale + (i - 1) * lineH)
  end
  love.graphics.setColor(1, 1, 1, 1)
  love.graphics.polygon("fill",
    bx + width / 2 - 6 * self.scale, by + height,
    bx + width / 2 + 6 * self.scale, by + height,
    bx + width / 2, by + height + 8 * self.scale)
  love.graphics.setColor(1, 1, 1, 1)
end

function Runtime:_monitor_value(monitor)
  local label = tostring(monitor.label or "")
  local targetName = monitor.target
  for _, definition in ipairs(self.target_defs) do
    if targetName == nil or definition.name == targetName then
      if monitor.isList and definition.lists[label] ~= nil then
        return definition.lists[label]
      end
      if not monitor.isList and definition.variables[label] ~= nil then
        return definition.variables[label]
      end
    end
  end
  if monitor.isList then
    return {}
  end
  if self.vars[label] ~= nil then
    return self.vars[label]
  end
  if monitor.value ~= nil then
    return monitor.value
  end
  return 0
end

function Runtime:_draw_monitors()
  for _, monitor in pairs(self.monitors) do
    local show = true
    if monitor.isList then
      show = self.list_visible[monitor.id] and true or false
    else
      show = self.monitor_visible[monitor.id] and true or false
    end
    if show then
      local value = self:_monitor_value(monitor)
      local mx, my = self:_stage_to_canvas(tonumber(monitor.x) or 0, tonumber(monitor.y) or 0)
      if monitor.mode == "large" then
        love.graphics.setFont(self.big_font)
        local text = s_str(value)
        local text_w = self.big_font:getWidth(text)
        love.graphics.setColor(1, 1, 1, 1)
        love.graphics.print(text, mx + 2, my + 40 * self.scale + 2)
        love.graphics.setColor(0.43, 0.9, 1, 1)
        love.graphics.print(text, mx, my + 40 * self.scale)
        love.graphics.setFont(self.font)
      else
        local label = tostring(monitor.label or "")
        local text = s_str(value)
        local labelW = self.font:getWidth(label)
        local valueW = self.font:getWidth(text)
        local boxW = labelW + valueW + 22 * self.scale
        local boxH = math.max(20 * self.scale, 14 * self.scale + 6 * self.scale)
        love.graphics.setColor(0.96, 0.96, 0.96, 1)
        love.graphics.rectangle("fill", mx, my, boxW, boxH)
        love.graphics.setColor(0.69, 0.69, 0.69, 1)
        love.graphics.rectangle("line", mx, my, boxW, boxH)
        love.graphics.setColor(0.24, 0.24, 0.24, 1)
        love.graphics.print(label, mx + 6 * self.scale, my + 4 * self.scale)
        love.graphics.setColor(0.08, 0.08, 0.08, 1)
        love.graphics.print(text, mx + boxW - valueW - 6 * self.scale, my + 4 * self.scale)
      end
    end
  end
  love.graphics.setColor(1, 1, 1, 1)
end

function Runtime:_draw_ask()
  local height = 60 * self.scale
  local y = love.graphics.getHeight() - height
  love.graphics.setColor(0.96, 0.96, 0.96, 1)
  love.graphics.rectangle("fill", 0, y, love.graphics.getWidth(), height)
  love.graphics.setColor(0.63, 0.63, 0.63, 1)
  love.graphics.rectangle("line", 0, y, love.graphics.getWidth(), height)
  love.graphics.setColor(0.08, 0.08, 0.08, 1)
  local question = s_str(self.ask_question)
  if #question > 90 then
    question = question:sub(1, 90)
  end
  love.graphics.print(question, 10 * self.scale, y + 10 * self.scale)
  love.graphics.print(self.ask_buffer .. "_", 10 * self.scale, y + 34 * self.scale)
  love.graphics.setColor(1, 1, 1, 1)
end

function Runtime:draw()
  love.graphics.clear(15 / 255, 15 / 255, 30 / 255, 1)

  local backdrop = nil
  if #self.stage_def.costumes > 0 then
    backdrop = self.stage_def.costumes[self.stage_def.current_costume + 1]
  end
  if backdrop and backdrop.image then
    local img_w = backdrop.image:getWidth()
    local img_h = backdrop.image:getHeight()
    love.graphics.setColor(1, 1, 1, 1)
    love.graphics.draw(backdrop.image, 0, 0, 0,
      love.graphics.getWidth() / img_w, love.graphics.getHeight() / img_h)
  end

  for _, actor in ipairs(self.layers) do
    if not actor.dead and actor.visible then
      self:_draw_actor(actor, self.scale)
    end
  end

  for _, actor in ipairs(self.layers) do
    if not actor.dead and (actor.say ~= nil or actor.think ~= nil) then
      self:_draw_bubble(actor)
    end
  end
  if not self.stage_actor.dead and (self.stage_actor.say ~= nil or self.stage_actor.think ~= nil) then
    self:_draw_bubble(self.stage_actor)
  end
  self:_draw_monitors()
  if self.asking then
    self:_draw_ask()
  end
  love.graphics.setColor(1, 1, 1, 1)
end

-- ---------------------------------------------------------------------------
-- events
-- ------------------------------------------------------------------

function Runtime:_update_mouse()
  local mx = love.mouse.getX()
  local my = love.mouse.getY()
  local w = love.graphics.getWidth()
  local h = love.graphics.getHeight()
  if w > 0 and h > 0 then
    local px = mx * (STAGE_W * self.scale / w)
    local py = my * (STAGE_H * self.scale / h)
    self.mouse_x = px / self.scale - STAGE_W / 2
    self.mouse_y = STAGE_H / 2 - py / self.scale
  end
  self.mouse_down = love.mouse.isDown(1)
end

function Runtime:_fire_click()
  for i = #self.layers, 1, -1 do
    local actor = self.layers[i]
    if not actor.dead and actor.visible then
      if actor:opaqueAt(self.mouse_x, self.mouse_y) then
        for _, reg in ipairs(self.routes.click[actor.target.name] or {}) do
          self:spawn(reg, actor)
        end
        return
      end
    end
  end
end

function Runtime:_handle_key_pressed(key)
  if self.asking then
    if key == "return" or key == "kpenter" then
      self.answer = self.ask_buffer
      self.asking = false
    elseif key == "backspace" then
      self.ask_buffer = self.ask_buffer:sub(1, -2)
    end
    return
  end
  local name = key_to_scratch(key)
  if name == nil then
    return
  end
  self.down_keys[name] = true
  for _, event_key in ipairs({ name, "any" }) do
    for _, reg in ipairs(self.routes.key[event_key] or {}) do
      self:spawn(reg, self:_actor_for(reg.sprite))
    end
  end
end

function Runtime:_handle_key_released(key)
  local name = key_to_scratch(key)
  if name ~= nil then
    self.down_keys[name] = nil
  end
end

-- ---------------------------------------------------------------------------
-- main loop
-- ---------------------------------------------------------------------------

function M.run(scripts, manifest, options)
  if type(love) ~= "table" then
    print("runtime: no LÖVE available; run the project with: love .")
    return nil
  end
  local runtime = Runtime.new(manifest, scripts, options or {})

  function love.load()
    love.window.setMode(STAGE_W * runtime.scale, STAGE_H * runtime.scale,
      { resizable = false, vsync = 1 })
    love.window.setTitle(tostring(manifest.name or "Scratch project"))
    runtime.font = love.graphics.newFont(14)
    runtime.big_font = love.graphics.newFont(48)
    love.graphics.setFont(runtime.font)
    runtime:green_flag()
  end

  function love.update(dt)
    runtime:_update_mouse()
    runtime._acc = runtime._acc + dt
    local guard = 0
    while runtime._acc >= runtime.frame_time and guard < 10 do
      runtime._acc = runtime._acc - runtime.frame_time
      runtime:step()
      guard = guard + 1
    end
  end

  function love.draw()
    runtime:draw()
  end

  function love.keypressed(key)
    runtime:_handle_key_pressed(key)
  end

  function love.keyreleased(key)
    runtime:_handle_key_released(key)
  end

  function love.textinput(text)
    if runtime.asking then
      runtime.ask_buffer = runtime.ask_buffer .. text
    end
  end

  function love.mousepressed()
    runtime:_update_mouse()
    runtime:_fire_click()
  end

  return runtime
end

-- ---------------------------------------------------------------------------
-- publish globals for generated main.lua (mirrors the JS classic scripts)
-- ---------------------------------------------------------------------------

_G.s_num = s_num
_G.s_str = s_str
_G.s_bool = s_bool
_G.s_add = s_add
_G.s_sub = s_sub
_G.s_mul = s_mul
_G.s_div = s_div
_G.s_random = s_random
_G.s_gt = s_gt
_G.s_lt = s_lt
_G.s_eq = s_eq
_G.s_not = s_not
_G.s_and = s_and
_G.s_or = s_or
_G.s_join = s_join
_G.s_letter = s_letter
_G.s_length = s_length
_G.s_contains = s_contains
_G.s_mod = s_mod
_G.s_round = s_round
_G.s_mathop = s_mathop
_G.s_costume_name = s_costume_name
_G.repeat_count = repeat_count
_G.list_item = list_item
_G.list_delete = list_delete
_G.list_clear = list_clear
_G.list_add = list_add
_G.list_insert = list_insert
_G.list_replace = list_replace
_G.list_index_of = list_index_of
_G.list_length = list_length
_G.list_contains = list_contains
_G.ScriptReg = ScriptReg
_G.run = M.run

return M
