var ScratchAudio = (() => {
  var __getOwnPropNames = Object.getOwnPropertyNames;
  var __commonJS = (cb, mod) => function __require() {
    try {
      return mod || (0, cb[__getOwnPropNames(cb)[0]])((mod = { exports: {} }).exports, mod), mod.exports;
    } catch (e) {
      throw mod = 0, e;
    }
  };

  // node_modules/startaudiocontext/StartAudioContext.js
  var require_StartAudioContext = __commonJS({
    "node_modules/startaudiocontext/StartAudioContext.js"(exports, module) {
      (function(root, factory) {
        if (typeof define === "function" && define.amd) {
          define([], factory);
        } else if (typeof module === "object" && module.exports) {
          module.exports = factory();
        } else {
          root.StartAudioContext = factory();
        }
      })(exports, function() {
        var TapListener = function(element, context) {
          this._dragged = false;
          this._element = element;
          this._bindedMove = this._moved.bind(this);
          this._bindedEnd = this._ended.bind(this, context);
          element.addEventListener("touchstart", this._bindedEnd);
          element.addEventListener("touchmove", this._bindedMove);
          element.addEventListener("touchend", this._bindedEnd);
          element.addEventListener("mouseup", this._bindedEnd);
        };
        TapListener.prototype._moved = function(e) {
          this._dragged = true;
        };
        TapListener.prototype._ended = function(context) {
          if (!this._dragged) {
            startContext(context);
          }
          this._dragged = false;
        };
        TapListener.prototype.dispose = function() {
          this._element.removeEventListener("touchstart", this._bindedEnd);
          this._element.removeEventListener("touchmove", this._bindedMove);
          this._element.removeEventListener("touchend", this._bindedEnd);
          this._element.removeEventListener("mouseup", this._bindedEnd);
          this._bindedMove = null;
          this._bindedEnd = null;
          this._element = null;
        };
        function startContext(context) {
          var buffer = context.createBuffer(1, 1, context.sampleRate);
          var source = context.createBufferSource();
          source.buffer = buffer;
          source.connect(context.destination);
          source.start(0);
          if (context.resume) {
            context.resume();
          }
        }
        function isStarted(context) {
          return context.state === "running";
        }
        function onStarted(context, callback) {
          function checkLoop() {
            if (isStarted(context)) {
              callback();
            } else {
              requestAnimationFrame(checkLoop);
              if (context.resume) {
                context.resume();
              }
            }
          }
          if (isStarted(context)) {
            callback();
          } else {
            checkLoop();
          }
        }
        function bindTapListener(element, tapListeners, context) {
          if (Array.isArray(element) || NodeList && element instanceof NodeList) {
            for (var i = 0; i < element.length; i++) {
              bindTapListener(element[i], tapListeners, context);
            }
          } else if (typeof element === "string") {
            bindTapListener(document.querySelectorAll(element), tapListeners, context);
          } else if (element.jquery && typeof element.toArray === "function") {
            bindTapListener(element.toArray(), tapListeners, context);
          } else if (Element && element instanceof Element) {
            var tap = new TapListener(element, context);
            tapListeners.push(tap);
          }
        }
        function StartAudioContext(context, elements, callback) {
          var promise = new Promise(function(success) {
            onStarted(context, success);
          });
          var tapListeners = [];
          if (!elements) {
            elements = document.body;
          }
          bindTapListener(elements, tapListeners, context);
          promise.then(function() {
            for (var i = 0; i < tapListeners.length; i++) {
              tapListeners[i].dispose();
            }
            tapListeners = null;
            if (callback) {
              callback();
            }
          });
          return promise;
        }
        return StartAudioContext;
      });
    }
  });

  // node_modules/scratch-audio/src/StartAudioContext.js
  var require_StartAudioContext2 = __commonJS({
    "node_modules/scratch-audio/src/StartAudioContext.js"(exports, module) {
      var StartAudioContext = require_StartAudioContext();
      module.exports = function(context) {
        if (typeof document !== "undefined") {
          return StartAudioContext(context);
        }
      };
    }
  });

  // node_modules/audio-context/index.js
  var require_audio_context = __commonJS({
    "node_modules/audio-context/index.js"(exports, module) {
      "use strict";
      var cache = {};
      module.exports = function getContext(options) {
        if (typeof window === "undefined") return null;
        var OfflineContext = window.OfflineAudioContext || window.webkitOfflineAudioContext;
        var Context = window.AudioContext || window.webkitAudioContext;
        if (!Context) return null;
        if (typeof options === "number") {
          options = { sampleRate: options };
        }
        var sampleRate = options && options.sampleRate;
        if (options && options.offline) {
          if (!OfflineContext) return null;
          return new OfflineContext(options.channels || 2, options.length, sampleRate || 44100);
        }
        var ctx = cache[sampleRate];
        if (ctx) return ctx;
        try {
          ctx = new Context(options);
        } catch (err) {
          ctx = new Context();
        }
        cache[ctx.sampleRate] = cache[sampleRate] = ctx;
        return ctx;
      };
    }
  });

  // node_modules/microee/index.js
  var require_microee = __commonJS({
    "node_modules/microee/index.js"(exports, module) {
      function M() {
        this._events = {};
      }
      M.prototype = {
        on: function(ev, cb) {
          this._events || (this._events = {});
          var e = this._events;
          (e[ev] || (e[ev] = [])).push(cb);
          return this;
        },
        removeListener: function(ev, cb) {
          var e = this._events[ev] || [], i;
          for (i = e.length - 1; i >= 0 && e[i]; i--) {
            if (e[i] === cb || e[i].cb === cb) {
              e.splice(i, 1);
            }
          }
        },
        removeAllListeners: function(ev) {
          if (!ev) {
            this._events = {};
          } else {
            this._events[ev] && (this._events[ev] = []);
          }
        },
        listeners: function(ev) {
          return this._events ? this._events[ev] || [] : [];
        },
        emit: function(ev) {
          this._events || (this._events = {});
          var args = Array.prototype.slice.call(arguments, 1), i, e = this._events[ev] || [];
          for (i = e.length - 1; i >= 0 && e[i]; i--) {
            e[i].apply(this, args);
          }
          return this;
        },
        when: function(ev, cb) {
          return this.once(ev, cb, true);
        },
        once: function(ev, cb, when) {
          if (!cb) return this;
          function c() {
            if (!when) this.removeListener(ev, c);
            if (cb.apply(this, arguments) && when) this.removeListener(ev, c);
          }
          c.cb = cb;
          this.on(ev, c);
          return this;
        }
      };
      M.mixin = function(dest) {
        var o = M.prototype, k;
        for (k in o) {
          o.hasOwnProperty(k) && (dest.prototype[k] = o[k]);
        }
      };
      module.exports = M;
    }
  });

  // node_modules/minilog/lib/common/transform.js
  var require_transform = __commonJS({
    "node_modules/minilog/lib/common/transform.js"(exports, module) {
      var microee = require_microee();
      function Transform() {
      }
      microee.mixin(Transform);
      Transform.prototype.write = function(name, level, args) {
        this.emit("item", name, level, args);
      };
      Transform.prototype.end = function() {
        this.emit("end");
        this.removeAllListeners();
      };
      Transform.prototype.pipe = function(dest) {
        var s = this;
        s.emit("unpipe", dest);
        dest.emit("pipe", s);
        function onItem() {
          dest.write.apply(dest, Array.prototype.slice.call(arguments));
        }
        function onEnd() {
          !dest._isStdio && dest.end();
        }
        s.on("item", onItem);
        s.on("end", onEnd);
        s.when("unpipe", function(from) {
          var match = from === dest || typeof from == "undefined";
          if (match) {
            s.removeListener("item", onItem);
            s.removeListener("end", onEnd);
            dest.emit("unpipe");
          }
          return match;
        });
        return dest;
      };
      Transform.prototype.unpipe = function(from) {
        this.emit("unpipe", from);
        return this;
      };
      Transform.prototype.format = function(dest) {
        throw new Error([
          "Warning: .format() is deprecated in Minilog v2! Use .pipe() instead. For example:",
          "var Minilog = require('minilog');",
          "Minilog",
          "  .pipe(Minilog.backends.console.formatClean)",
          "  .pipe(Minilog.backends.console);"
        ].join("\n"));
      };
      Transform.mixin = function(dest) {
        var o = Transform.prototype, k;
        for (k in o) {
          o.hasOwnProperty(k) && (dest.prototype[k] = o[k]);
        }
      };
      module.exports = Transform;
    }
  });

  // node_modules/minilog/lib/common/filter.js
  var require_filter = __commonJS({
    "node_modules/minilog/lib/common/filter.js"(exports, module) {
      var Transform = require_transform();
      var levelMap = { debug: 1, info: 2, warn: 3, error: 4 };
      function Filter() {
        this.enabled = true;
        this.defaultResult = true;
        this.clear();
      }
      Transform.mixin(Filter);
      Filter.prototype.allow = function(name, level) {
        this._white.push({ n: name, l: levelMap[level] });
        return this;
      };
      Filter.prototype.deny = function(name, level) {
        this._black.push({ n: name, l: levelMap[level] });
        return this;
      };
      Filter.prototype.clear = function() {
        this._white = [];
        this._black = [];
        return this;
      };
      function test(rule, name) {
        return rule.n.test ? rule.n.test(name) : rule.n == name;
      }
      Filter.prototype.test = function(name, level) {
        var i, len = Math.max(this._white.length, this._black.length);
        for (i = 0; i < len; i++) {
          if (this._white[i] && test(this._white[i], name) && levelMap[level] >= this._white[i].l) {
            return true;
          }
          if (this._black[i] && test(this._black[i], name) && levelMap[level] <= this._black[i].l) {
            return false;
          }
        }
        return this.defaultResult;
      };
      Filter.prototype.write = function(name, level, args) {
        if (!this.enabled || this.test(name, level)) {
          return this.emit("item", name, level, args);
        }
      };
      module.exports = Filter;
    }
  });

  // node_modules/minilog/lib/common/minilog.js
  var require_minilog = __commonJS({
    "node_modules/minilog/lib/common/minilog.js"(exports, module) {
      var Transform = require_transform();
      var Filter = require_filter();
      var log = new Transform();
      var slice = Array.prototype.slice;
      exports = module.exports = function create(name) {
        var o = function() {
          log.write(name, void 0, slice.call(arguments));
          return o;
        };
        o.debug = function() {
          log.write(name, "debug", slice.call(arguments));
          return o;
        };
        o.info = function() {
          log.write(name, "info", slice.call(arguments));
          return o;
        };
        o.warn = function() {
          log.write(name, "warn", slice.call(arguments));
          return o;
        };
        o.error = function() {
          log.write(name, "error", slice.call(arguments));
          return o;
        };
        o.log = o.debug;
        o.suggest = exports.suggest;
        o.format = log.format;
        return o;
      };
      exports.defaultBackend = exports.defaultFormatter = null;
      exports.pipe = function(dest) {
        return log.pipe(dest);
      };
      exports.end = exports.unpipe = exports.disable = function(from) {
        return log.unpipe(from);
      };
      exports.Transform = Transform;
      exports.Filter = Filter;
      exports.suggest = new Filter();
      exports.enable = function() {
        if (exports.defaultFormatter) {
          return log.pipe(exports.suggest).pipe(exports.defaultFormatter).pipe(exports.defaultBackend);
        }
        return log.pipe(exports.suggest).pipe(exports.defaultBackend);
      };
    }
  });

  // node_modules/minilog/lib/web/formatters/util.js
  var require_util = __commonJS({
    "node_modules/minilog/lib/web/formatters/util.js"(exports, module) {
      var hex = {
        black: "#000",
        red: "#c23621",
        green: "#25bc26",
        yellow: "#bbbb00",
        blue: "#492ee1",
        magenta: "#d338d3",
        cyan: "#33bbc8",
        gray: "#808080",
        purple: "#708"
      };
      function color(fg, isInverse) {
        if (isInverse) {
          return "color: #fff; background: " + hex[fg] + ";";
        } else {
          return "color: " + hex[fg] + ";";
        }
      }
      module.exports = color;
    }
  });

  // node_modules/minilog/lib/web/formatters/color.js
  var require_color = __commonJS({
    "node_modules/minilog/lib/web/formatters/color.js"(exports, module) {
      var Transform = require_transform();
      var color = require_util();
      var colors = { debug: ["cyan"], info: ["purple"], warn: ["yellow", true], error: ["red", true] };
      var logger = new Transform();
      logger.write = function(name, level, args) {
        var fn = console.log;
        if (console[level] && console[level].apply) {
          fn = console[level];
          fn.apply(console, ["%c" + name + " %c" + level, color("gray"), color.apply(color, colors[level])].concat(args));
        }
      };
      logger.pipe = function() {
      };
      module.exports = logger;
    }
  });

  // node_modules/minilog/lib/web/formatters/minilog.js
  var require_minilog2 = __commonJS({
    "node_modules/minilog/lib/web/formatters/minilog.js"(exports, module) {
      var Transform = require_transform();
      var color = require_util();
      var colors = { debug: ["gray"], info: ["purple"], warn: ["yellow", true], error: ["red", true] };
      var logger = new Transform();
      logger.write = function(name, level, args) {
        var fn = console.log;
        if (level != "debug" && console[level]) {
          fn = console[level];
        }
        var subset = [], i = 0;
        if (level != "info") {
          for (; i < args.length; i++) {
            if (typeof args[i] != "string") break;
          }
          fn.apply(console, ["%c" + name + " " + args.slice(0, i).join(" "), color.apply(color, colors[level])].concat(args.slice(i)));
        } else {
          fn.apply(console, ["%c" + name, color.apply(color, colors[level])].concat(args));
        }
      };
      logger.pipe = function() {
      };
      module.exports = logger;
    }
  });

  // node_modules/minilog/lib/web/console.js
  var require_console = __commonJS({
    "node_modules/minilog/lib/web/console.js"(exports, module) {
      var Transform = require_transform();
      var newlines = /\n+$/;
      var logger = new Transform();
      logger.write = function(name, level, args) {
        var i = args.length - 1;
        if (typeof console === "undefined" || !console.log) {
          return;
        }
        if (console.log.apply) {
          return console.log.apply(console, [name, level].concat(args));
        } else if (JSON && JSON.stringify) {
          if (args[i] && typeof args[i] == "string") {
            args[i] = args[i].replace(newlines, "");
          }
          try {
            for (i = 0; i < args.length; i++) {
              args[i] = JSON.stringify(args[i]);
            }
          } catch (e) {
          }
          console.log(args.join(" "));
        }
      };
      logger.formatters = ["color", "minilog"];
      logger.color = require_color();
      logger.minilog = require_minilog2();
      module.exports = logger;
    }
  });

  // node_modules/minilog/lib/web/array.js
  var require_array = __commonJS({
    "node_modules/minilog/lib/web/array.js"(exports, module) {
      var Transform = require_transform();
      var cache = [];
      var logger = new Transform();
      logger.write = function(name, level, args) {
        cache.push([name, level, args]);
      };
      logger.get = function() {
        return cache;
      };
      logger.empty = function() {
        cache = [];
      };
      module.exports = logger;
    }
  });

  // node_modules/minilog/lib/web/localstorage.js
  var require_localstorage = __commonJS({
    "node_modules/minilog/lib/web/localstorage.js"(exports, module) {
      var Transform = require_transform();
      var cache = false;
      var logger = new Transform();
      logger.write = function(name, level, args) {
        if (typeof window == "undefined" || typeof JSON == "undefined" || !JSON.stringify || !JSON.parse) return;
        try {
          if (!cache) {
            cache = window.localStorage.minilog ? JSON.parse(window.localStorage.minilog) : [];
          }
          cache.push([(/* @__PURE__ */ new Date()).toString(), name, level, args]);
          window.localStorage.minilog = JSON.stringify(cache);
        } catch (e) {
        }
      };
      module.exports = logger;
    }
  });

  // node_modules/minilog/lib/web/jquery_simple.js
  var require_jquery_simple = __commonJS({
    "node_modules/minilog/lib/web/jquery_simple.js"(exports, module) {
      var Transform = require_transform();
      var cid = (/* @__PURE__ */ new Date()).valueOf().toString(36);
      function AjaxLogger(options) {
        this.url = options.url || "";
        this.cache = [];
        this.timer = null;
        this.interval = options.interval || 30 * 1e3;
        this.enabled = true;
        this.jQuery = window.jQuery;
        this.extras = {};
      }
      Transform.mixin(AjaxLogger);
      AjaxLogger.prototype.write = function(name, level, args) {
        if (!this.timer) {
          this.init();
        }
        this.cache.push([name, level].concat(args));
      };
      AjaxLogger.prototype.init = function() {
        if (!this.enabled || !this.jQuery) return;
        var self = this;
        this.timer = setTimeout(function() {
          var i, logs = [], ajaxData, url = self.url;
          if (self.cache.length == 0) return self.init();
          for (i = 0; i < self.cache.length; i++) {
            try {
              JSON.stringify(self.cache[i]);
              logs.push(self.cache[i]);
            } catch (e) {
            }
          }
          if (self.jQuery.isEmptyObject(self.extras)) {
            ajaxData = JSON.stringify({ logs });
            url = self.url + "?client_id=" + cid;
          } else {
            ajaxData = JSON.stringify(self.jQuery.extend({ logs }, self.extras));
          }
          self.jQuery.ajax(url, {
            type: "POST",
            cache: false,
            processData: false,
            data: ajaxData,
            contentType: "application/json",
            timeout: 1e4
          }).success(function(data, status, jqxhr) {
            if (data.interval) {
              self.interval = Math.max(1e3, data.interval);
            }
          }).error(function() {
            self.interval = 3e4;
          }).always(function() {
            self.init();
          });
          self.cache = [];
        }, this.interval);
      };
      AjaxLogger.prototype.end = function() {
      };
      AjaxLogger.jQueryWait = function(onDone) {
        if (typeof window !== "undefined" && (window.jQuery || window.$)) {
          return onDone(window.jQuery || window.$);
        } else if (typeof window !== "undefined") {
          setTimeout(function() {
            AjaxLogger.jQueryWait(onDone);
          }, 200);
        }
      };
      module.exports = AjaxLogger;
    }
  });

  // node_modules/minilog/lib/web/index.js
  var require_web = __commonJS({
    "node_modules/minilog/lib/web/index.js"(exports, module) {
      var Minilog = require_minilog();
      var oldEnable = Minilog.enable;
      var oldDisable = Minilog.disable;
      var isChrome = typeof navigator != "undefined" && /chrome/i.test(navigator.userAgent);
      var console2 = require_console();
      Minilog.defaultBackend = isChrome ? console2.minilog : console2;
      if (typeof window != "undefined") {
        try {
          Minilog.enable(JSON.parse(window.localStorage["minilogSettings"]));
        } catch (e) {
        }
        if (window.location && window.location.search) {
          match = RegExp("[?&]minilog=([^&]*)").exec(window.location.search);
          match && Minilog.enable(decodeURIComponent(match[1]));
        }
      }
      var match;
      Minilog.enable = function() {
        oldEnable.call(Minilog, true);
        try {
          window.localStorage["minilogSettings"] = JSON.stringify(true);
        } catch (e) {
        }
        return this;
      };
      Minilog.disable = function() {
        oldDisable.call(Minilog);
        try {
          delete window.localStorage.minilogSettings;
        } catch (e) {
        }
        return this;
      };
      exports = module.exports = Minilog;
      exports.backends = {
        array: require_array(),
        browser: Minilog.defaultBackend,
        localStorage: require_localstorage(),
        jQuery: require_jquery_simple()
      };
    }
  });

  // node_modules/scratch-audio/src/log.js
  var require_log = __commonJS({
    "node_modules/scratch-audio/src/log.js"(exports, module) {
      var minilog = require_web();
      minilog.enable();
      module.exports = minilog("scratch-audioengine");
    }
  });

  // node_modules/scratch-audio/src/uid.js
  var require_uid = __commonJS({
    "node_modules/scratch-audio/src/uid.js"(exports, module) {
      var soup_ = "!#%()*+,-./:;=?@[]^_`{|}~ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789";
      var uid = function() {
        const length = 20;
        const soupLength = soup_.length;
        const id = [];
        for (let i = 0; i < length; i++) {
          id[i] = soup_.charAt(Math.random() * soupLength);
        }
        return id.join("");
      };
      module.exports = uid;
    }
  });

  // node_modules/scratch-audio/src/ArrayBufferStream.js
  var require_ArrayBufferStream = __commonJS({
    "node_modules/scratch-audio/src/ArrayBufferStream.js"(exports, module) {
      var ArrayBufferStream = class _ArrayBufferStream {
        /**
         * ArrayBufferStream wraps the built-in javascript ArrayBuffer, adding the ability to access
         * data in it like a stream, tracking its position.
         * You can request to read a value from the front of the array, and it will keep track of the position
         * within the byte array, so that successive reads are consecutive.
         * The available types to read include:
         * Uint8, Uint8String, Int16, Uint16, Int32, Uint32
         * @param {ArrayBuffer} arrayBuffer - array to use as a stream
         * @param {number} start - the start position in the raw buffer. position
         * will be relative to the start value.
         * @param {number} end - the end position in the raw buffer. length and
         * bytes available will be relative to the end value.
         * @param {ArrayBufferStream} parent - if passed reuses the parent's
         * internal objects
         * @constructor
         */
        constructor(arrayBuffer, start = 0, end = arrayBuffer.byteLength, {
          _uint8View = new Uint8Array(arrayBuffer)
        } = {}) {
          this.arrayBuffer = arrayBuffer;
          this.start = start;
          this.end = end;
          this._uint8View = _uint8View;
          this._position = start;
        }
        /**
         * Return a new ArrayBufferStream that is a slice of the existing one
         * @param  {number} length - the number of bytes of extract
         * @return {ArrayBufferStream} the extracted stream
         */
        extract(length) {
          return new _ArrayBufferStream(this.arrayBuffer, this._position, this._position + length, this);
        }
        /**
         * @return {number} the length of the stream in bytes
         */
        getLength() {
          return this.end - this.start;
        }
        /**
         * @return {number} the number of bytes available after the current position in the stream
         */
        getBytesAvailable() {
          return this.end - this._position;
        }
        /**
         * Position relative to the start value in the arrayBuffer of this
         * ArrayBufferStream.
         * @type {number}
         */
        get position() {
          return this._position - this.start;
        }
        /**
         * Set the position to read from in the arrayBuffer.
         * @type {number}
         * @param {number} value - new value to set position to
         */
        set position(value) {
          this._position = value + this.start;
        }
        /**
         * Read an unsigned 8 bit integer from the stream
         * @return {number} the next 8 bit integer in the stream
         */
        readUint8() {
          const val = this._uint8View[this._position];
          this._position += 1;
          return val;
        }
        /**
         * Read a sequence of bytes of the given length and convert to a string.
         * This is a convenience method for use with short strings.
         * @param {number} length - the number of bytes to convert
         * @return {string} a String made by concatenating the chars in the input
         */
        readUint8String(length) {
          const arr = this._uint8View;
          let str = "";
          const end = this._position + length;
          for (let i = this._position; i < end; i++) {
            str += String.fromCharCode(arr[i]);
          }
          this._position += length;
          return str;
        }
        /**
         * Read a 16 bit integer from the stream
         * @return {number} the next 16 bit integer in the stream
         */
        readInt16() {
          const val = new Int16Array(this.arrayBuffer, this._position, 1)[0];
          this._position += 2;
          return val;
        }
        /**
         * Read an unsigned 16 bit integer from the stream
         * @return {number} the next unsigned 16 bit integer in the stream
         */
        readUint16() {
          const val = new Uint16Array(this.arrayBuffer, this._position, 1)[0];
          this._position += 2;
          return val;
        }
        /**
         * Read a 32 bit integer from the stream
         * @return {number} the next 32 bit integer in the stream
         */
        readInt32() {
          let val;
          if (this._position % 4 === 0) {
            val = new Int32Array(this.arrayBuffer, this._position, 1)[0];
          } else {
            val = new Int32Array(
              this.arrayBuffer.slice(this._position, this._position + 4)
            )[0];
          }
          this._position += 4;
          return val;
        }
        /**
         * Read an unsigned 32 bit integer from the stream
         * @return {number} the next unsigned 32 bit integer in the stream
         */
        readUint32() {
          const val = new Uint32Array(this.arrayBuffer, this._position, 1)[0];
          this._position += 4;
          return val;
        }
      };
      module.exports = ArrayBufferStream;
    }
  });

  // node_modules/scratch-audio/src/ADPCMSoundDecoder.js
  var require_ADPCMSoundDecoder = __commonJS({
    "node_modules/scratch-audio/src/ADPCMSoundDecoder.js"(exports, module) {
      var ArrayBufferStream = require_ArrayBufferStream();
      var log = require_log();
      var STEP_TABLE = [
        7,
        8,
        9,
        10,
        11,
        12,
        13,
        14,
        16,
        17,
        19,
        21,
        23,
        25,
        28,
        31,
        34,
        37,
        41,
        45,
        50,
        55,
        60,
        66,
        73,
        80,
        88,
        97,
        107,
        118,
        130,
        143,
        157,
        173,
        190,
        209,
        230,
        253,
        279,
        307,
        337,
        371,
        408,
        449,
        494,
        544,
        598,
        658,
        724,
        796,
        876,
        963,
        1060,
        1166,
        1282,
        1411,
        1552,
        1707,
        1878,
        2066,
        2272,
        2499,
        2749,
        3024,
        3327,
        3660,
        4026,
        4428,
        4871,
        5358,
        5894,
        6484,
        7132,
        7845,
        8630,
        9493,
        10442,
        11487,
        12635,
        13899,
        15289,
        16818,
        18500,
        20350,
        22385,
        24623,
        27086,
        29794,
        32767
      ];
      var INDEX_TABLE = [
        -1,
        -1,
        -1,
        -1,
        2,
        4,
        6,
        8,
        -1,
        -1,
        -1,
        -1,
        2,
        4,
        6,
        8
      ];
      var _deltaTable = null;
      var deltaTable = function() {
        if (_deltaTable === null) {
          const NUM_STEPS = STEP_TABLE.length;
          const NUM_INDICES = INDEX_TABLE.length;
          _deltaTable = new Array(NUM_STEPS * NUM_INDICES).fill(0);
          let i = 0;
          for (let index = 0; index < NUM_STEPS; index++) {
            for (let code = 0; code < NUM_INDICES; code++) {
              const step = STEP_TABLE[index];
              let delta = 0;
              if (code & 4) delta += step;
              if (code & 2) delta += step >> 1;
              if (code & 1) delta += step >> 2;
              delta += step >> 3;
              _deltaTable[i++] = code & 8 ? -delta : delta;
            }
          }
        }
        return _deltaTable;
      };
      var ADPCMSoundDecoder = class {
        /**
         * @param {AudioContext} audioContext - a webAudio context
         * @constructor
         */
        constructor(audioContext) {
          this.audioContext = audioContext;
        }
        /**
         * Data used by the decompression algorithm
         * @type {Array}
         */
        static get STEP_TABLE() {
          return STEP_TABLE;
        }
        /**
         * Data used by the decompression algorithm
         * @type {Array}
         */
        static get INDEX_TABLE() {
          return INDEX_TABLE;
        }
        /**
         * Decode an ADPCM sound stored in an ArrayBuffer and return a promise
         * with the decoded audio buffer.
         * @param  {ArrayBuffer} audioData - containing ADPCM encoded wav audio
         * @return {Promise.<AudioBuffer>} the decoded audio buffer
         */
        decode(audioData) {
          return new Promise((resolve, reject) => {
            const stream = new ArrayBufferStream(audioData);
            const riffStr = stream.readUint8String(4);
            if (riffStr !== "RIFF") {
              log.warn("incorrect adpcm wav header");
              reject(new Error("incorrect adpcm wav header"));
            }
            const lengthInHeader = stream.readInt32();
            if (lengthInHeader + 8 !== audioData.byteLength) {
              log.warn(`adpcm wav length in header: ${lengthInHeader} is incorrect`);
            }
            const wavStr = stream.readUint8String(4);
            if (wavStr !== "WAVE") {
              log.warn("incorrect adpcm wav header");
              reject(new Error("incorrect adpcm wav header"));
            }
            const formatChunk = this.extractChunk("fmt ", stream);
            this.encoding = formatChunk.readUint16();
            this.channels = formatChunk.readUint16();
            this.samplesPerSecond = formatChunk.readUint32();
            this.bytesPerSecond = formatChunk.readUint32();
            this.blockAlignment = formatChunk.readUint16();
            this.bitsPerSample = formatChunk.readUint16();
            formatChunk.position += 2;
            this.samplesPerBlock = formatChunk.readUint16();
            this.adpcmBlockSize = (this.samplesPerBlock - 1) / 2 + 4;
            const compressedData = this.extractChunk("data", stream);
            const sampleCount = this.numberOfSamples(compressedData, this.adpcmBlockSize);
            const buffer = this.audioContext.createBuffer(1, sampleCount, this.samplesPerSecond);
            this.imaDecompress(compressedData, this.adpcmBlockSize, buffer.getChannelData(0));
            resolve(buffer);
          });
        }
        /**
         * Extract a chunk of audio data from the stream, consisting of a set of audio data bytes
         * @param  {string} chunkType - the type of chunk to extract. 'data' or 'fmt' (format)
         * @param  {ArrayBufferStream} stream - an stream containing the audio data
         * @return {ArrayBufferStream} a stream containing the desired chunk
         */
        extractChunk(chunkType, stream) {
          stream.position = 12;
          while (stream.position < stream.getLength() - 8) {
            const typeStr = stream.readUint8String(4);
            const chunkSize = stream.readInt32();
            if (typeStr === chunkType) {
              const chunk = stream.extract(chunkSize);
              return chunk;
            }
            stream.position += chunkSize;
          }
        }
        /**
         * Count the exact number of samples in the compressed data.
         * @param {ArrayBufferStream} compressedData - the compressed data
         * @param {number} blockSize - size of each block in the data in bytes
         * @return {number} number of samples in the compressed data
         */
        numberOfSamples(compressedData, blockSize) {
          if (!compressedData) return 0;
          compressedData.position = 0;
          const available = compressedData.getBytesAvailable();
          const blocks = available / blockSize | 0;
          const fullBlocks = blocks * (2 * (blockSize - 4)) + 1;
          const subBlock = Math.max(available % blockSize - 4, 0) * 2;
          const incompleteBlock = Math.min(available % blockSize, 1);
          return fullBlocks + subBlock + incompleteBlock;
        }
        /**
         * Decompress sample data using the IMA ADPCM algorithm.
         * Note: Handles only one channel, 4-bits per sample.
         * @param  {ArrayBufferStream} compressedData - a stream of compressed audio samples
         * @param  {number} blockSize - the number of bytes in the stream
         * @param  {Float32Array} out - the uncompressed audio samples
         */
        imaDecompress(compressedData, blockSize, out) {
          let sample;
          let code;
          let delta;
          let index = 0;
          let lastByte = -1;
          if (!compressedData) return;
          compressedData.position = 0;
          const size = out.length;
          const samplesAfterBlockHeader = (blockSize - 4) * 2;
          const DELTA_TABLE = deltaTable();
          let i = 0;
          while (i < size) {
            sample = compressedData.readInt16();
            index = compressedData.readUint8();
            compressedData.position++;
            if (index > 88) index = 88;
            out[i++] = sample / 32768;
            const blockLength = Math.min(samplesAfterBlockHeader, size - i);
            const blockStart = i;
            while (i - blockStart < blockLength) {
              lastByte = compressedData.readUint8();
              code = lastByte & 15;
              delta = DELTA_TABLE[index * 16 + code];
              index += INDEX_TABLE[code];
              if (index > 88) index = 88;
              else if (index < 0) index = 0;
              sample += delta;
              if (sample > 32767) sample = 32767;
              else if (sample < -32768) sample = -32768;
              out[i++] = sample / 32768;
              code = lastByte >> 4 & 15;
              delta = DELTA_TABLE[index * 16 + code];
              index += INDEX_TABLE[code];
              if (index > 88) index = 88;
              else if (index < 0) index = 0;
              sample += delta;
              if (sample > 32767) sample = 32767;
              else if (sample < -32768) sample = -32768;
              out[i++] = sample / 32768;
            }
          }
        }
      };
      module.exports = ADPCMSoundDecoder;
    }
  });

  // node_modules/scratch-audio/src/Loudness.js
  var require_Loudness = __commonJS({
    "node_modules/scratch-audio/src/Loudness.js"(exports, module) {
      var log = require_log();
      var Loudness = class {
        /**
         * Instrument and detect a loudness value from a local microphone.
         * @param {AudioContext} audioContext - context to create nodes from for
         *     detecting loudness
         * @constructor
         */
        constructor(audioContext) {
          this.audioContext = audioContext;
          this.connectingToMic = false;
          this.mic = null;
        }
        /**
         * Get the current loudness of sound received by the microphone.
         * Sound is measured in RMS and smoothed.
         * Some code adapted from Tone.js: https://github.com/Tonejs/Tone.js
         * @return {number} loudness scaled 0 to 100
         */
        getLoudness() {
          if (!this.mic && !this.connectingToMic) {
            this.connectingToMic = true;
            navigator.mediaDevices.getUserMedia({ audio: true }).then((stream) => {
              this.audioStream = stream;
              this.mic = this.audioContext.createMediaStreamSource(stream);
              this.analyser = this.audioContext.createAnalyser();
              this.mic.connect(this.analyser);
              this.micDataArray = new Float32Array(this.analyser.fftSize);
            }).catch((err) => {
              log.warn(err);
            });
          }
          if (this.mic && this.audioStream.active) {
            this.analyser.getFloatTimeDomainData(this.micDataArray);
            let sum = 0;
            for (let i = 0; i < this.micDataArray.length; i++) {
              sum += Math.pow(this.micDataArray[i], 2);
            }
            let rms = Math.sqrt(sum / this.micDataArray.length);
            if (this._lastValue) {
              rms = Math.max(rms, this._lastValue * 0.6);
            }
            this._lastValue = rms;
            rms *= 1.63;
            rms = Math.sqrt(rms);
            rms = Math.round(rms * 100);
            rms = Math.min(rms, 100);
            return rms;
          }
          return -1;
        }
      };
      module.exports = Loudness;
    }
  });

  // node_modules/events/events.js
  var require_events = __commonJS({
    "node_modules/events/events.js"(exports, module) {
      "use strict";
      var R = typeof Reflect === "object" ? Reflect : null;
      var ReflectApply = R && typeof R.apply === "function" ? R.apply : function ReflectApply2(target, receiver, args) {
        return Function.prototype.apply.call(target, receiver, args);
      };
      var ReflectOwnKeys;
      if (R && typeof R.ownKeys === "function") {
        ReflectOwnKeys = R.ownKeys;
      } else if (Object.getOwnPropertySymbols) {
        ReflectOwnKeys = function ReflectOwnKeys2(target) {
          return Object.getOwnPropertyNames(target).concat(Object.getOwnPropertySymbols(target));
        };
      } else {
        ReflectOwnKeys = function ReflectOwnKeys2(target) {
          return Object.getOwnPropertyNames(target);
        };
      }
      function ProcessEmitWarning(warning) {
        if (console && console.warn) console.warn(warning);
      }
      var NumberIsNaN = Number.isNaN || function NumberIsNaN2(value) {
        return value !== value;
      };
      function EventEmitter() {
        EventEmitter.init.call(this);
      }
      module.exports = EventEmitter;
      module.exports.once = once;
      EventEmitter.EventEmitter = EventEmitter;
      EventEmitter.prototype._events = void 0;
      EventEmitter.prototype._eventsCount = 0;
      EventEmitter.prototype._maxListeners = void 0;
      var defaultMaxListeners = 10;
      function checkListener(listener) {
        if (typeof listener !== "function") {
          throw new TypeError('The "listener" argument must be of type Function. Received type ' + typeof listener);
        }
      }
      Object.defineProperty(EventEmitter, "defaultMaxListeners", {
        enumerable: true,
        get: function() {
          return defaultMaxListeners;
        },
        set: function(arg) {
          if (typeof arg !== "number" || arg < 0 || NumberIsNaN(arg)) {
            throw new RangeError('The value of "defaultMaxListeners" is out of range. It must be a non-negative number. Received ' + arg + ".");
          }
          defaultMaxListeners = arg;
        }
      });
      EventEmitter.init = function() {
        if (this._events === void 0 || this._events === Object.getPrototypeOf(this)._events) {
          this._events = /* @__PURE__ */ Object.create(null);
          this._eventsCount = 0;
        }
        this._maxListeners = this._maxListeners || void 0;
      };
      EventEmitter.prototype.setMaxListeners = function setMaxListeners(n) {
        if (typeof n !== "number" || n < 0 || NumberIsNaN(n)) {
          throw new RangeError('The value of "n" is out of range. It must be a non-negative number. Received ' + n + ".");
        }
        this._maxListeners = n;
        return this;
      };
      function _getMaxListeners(that) {
        if (that._maxListeners === void 0)
          return EventEmitter.defaultMaxListeners;
        return that._maxListeners;
      }
      EventEmitter.prototype.getMaxListeners = function getMaxListeners() {
        return _getMaxListeners(this);
      };
      EventEmitter.prototype.emit = function emit(type) {
        var args = [];
        for (var i = 1; i < arguments.length; i++) args.push(arguments[i]);
        var doError = type === "error";
        var events = this._events;
        if (events !== void 0)
          doError = doError && events.error === void 0;
        else if (!doError)
          return false;
        if (doError) {
          var er;
          if (args.length > 0)
            er = args[0];
          if (er instanceof Error) {
            throw er;
          }
          var err = new Error("Unhandled error." + (er ? " (" + er.message + ")" : ""));
          err.context = er;
          throw err;
        }
        var handler = events[type];
        if (handler === void 0)
          return false;
        if (typeof handler === "function") {
          ReflectApply(handler, this, args);
        } else {
          var len = handler.length;
          var listeners = arrayClone(handler, len);
          for (var i = 0; i < len; ++i)
            ReflectApply(listeners[i], this, args);
        }
        return true;
      };
      function _addListener(target, type, listener, prepend) {
        var m;
        var events;
        var existing;
        checkListener(listener);
        events = target._events;
        if (events === void 0) {
          events = target._events = /* @__PURE__ */ Object.create(null);
          target._eventsCount = 0;
        } else {
          if (events.newListener !== void 0) {
            target.emit(
              "newListener",
              type,
              listener.listener ? listener.listener : listener
            );
            events = target._events;
          }
          existing = events[type];
        }
        if (existing === void 0) {
          existing = events[type] = listener;
          ++target._eventsCount;
        } else {
          if (typeof existing === "function") {
            existing = events[type] = prepend ? [listener, existing] : [existing, listener];
          } else if (prepend) {
            existing.unshift(listener);
          } else {
            existing.push(listener);
          }
          m = _getMaxListeners(target);
          if (m > 0 && existing.length > m && !existing.warned) {
            existing.warned = true;
            var w = new Error("Possible EventEmitter memory leak detected. " + existing.length + " " + String(type) + " listeners added. Use emitter.setMaxListeners() to increase limit");
            w.name = "MaxListenersExceededWarning";
            w.emitter = target;
            w.type = type;
            w.count = existing.length;
            ProcessEmitWarning(w);
          }
        }
        return target;
      }
      EventEmitter.prototype.addListener = function addListener(type, listener) {
        return _addListener(this, type, listener, false);
      };
      EventEmitter.prototype.on = EventEmitter.prototype.addListener;
      EventEmitter.prototype.prependListener = function prependListener(type, listener) {
        return _addListener(this, type, listener, true);
      };
      function onceWrapper() {
        if (!this.fired) {
          this.target.removeListener(this.type, this.wrapFn);
          this.fired = true;
          if (arguments.length === 0)
            return this.listener.call(this.target);
          return this.listener.apply(this.target, arguments);
        }
      }
      function _onceWrap(target, type, listener) {
        var state = { fired: false, wrapFn: void 0, target, type, listener };
        var wrapped = onceWrapper.bind(state);
        wrapped.listener = listener;
        state.wrapFn = wrapped;
        return wrapped;
      }
      EventEmitter.prototype.once = function once2(type, listener) {
        checkListener(listener);
        this.on(type, _onceWrap(this, type, listener));
        return this;
      };
      EventEmitter.prototype.prependOnceListener = function prependOnceListener(type, listener) {
        checkListener(listener);
        this.prependListener(type, _onceWrap(this, type, listener));
        return this;
      };
      EventEmitter.prototype.removeListener = function removeListener(type, listener) {
        var list, events, position, i, originalListener;
        checkListener(listener);
        events = this._events;
        if (events === void 0)
          return this;
        list = events[type];
        if (list === void 0)
          return this;
        if (list === listener || list.listener === listener) {
          if (--this._eventsCount === 0)
            this._events = /* @__PURE__ */ Object.create(null);
          else {
            delete events[type];
            if (events.removeListener)
              this.emit("removeListener", type, list.listener || listener);
          }
        } else if (typeof list !== "function") {
          position = -1;
          for (i = list.length - 1; i >= 0; i--) {
            if (list[i] === listener || list[i].listener === listener) {
              originalListener = list[i].listener;
              position = i;
              break;
            }
          }
          if (position < 0)
            return this;
          if (position === 0)
            list.shift();
          else {
            spliceOne(list, position);
          }
          if (list.length === 1)
            events[type] = list[0];
          if (events.removeListener !== void 0)
            this.emit("removeListener", type, originalListener || listener);
        }
        return this;
      };
      EventEmitter.prototype.off = EventEmitter.prototype.removeListener;
      EventEmitter.prototype.removeAllListeners = function removeAllListeners(type) {
        var listeners, events, i;
        events = this._events;
        if (events === void 0)
          return this;
        if (events.removeListener === void 0) {
          if (arguments.length === 0) {
            this._events = /* @__PURE__ */ Object.create(null);
            this._eventsCount = 0;
          } else if (events[type] !== void 0) {
            if (--this._eventsCount === 0)
              this._events = /* @__PURE__ */ Object.create(null);
            else
              delete events[type];
          }
          return this;
        }
        if (arguments.length === 0) {
          var keys = Object.keys(events);
          var key;
          for (i = 0; i < keys.length; ++i) {
            key = keys[i];
            if (key === "removeListener") continue;
            this.removeAllListeners(key);
          }
          this.removeAllListeners("removeListener");
          this._events = /* @__PURE__ */ Object.create(null);
          this._eventsCount = 0;
          return this;
        }
        listeners = events[type];
        if (typeof listeners === "function") {
          this.removeListener(type, listeners);
        } else if (listeners !== void 0) {
          for (i = listeners.length - 1; i >= 0; i--) {
            this.removeListener(type, listeners[i]);
          }
        }
        return this;
      };
      function _listeners(target, type, unwrap) {
        var events = target._events;
        if (events === void 0)
          return [];
        var evlistener = events[type];
        if (evlistener === void 0)
          return [];
        if (typeof evlistener === "function")
          return unwrap ? [evlistener.listener || evlistener] : [evlistener];
        return unwrap ? unwrapListeners(evlistener) : arrayClone(evlistener, evlistener.length);
      }
      EventEmitter.prototype.listeners = function listeners(type) {
        return _listeners(this, type, true);
      };
      EventEmitter.prototype.rawListeners = function rawListeners(type) {
        return _listeners(this, type, false);
      };
      EventEmitter.listenerCount = function(emitter, type) {
        if (typeof emitter.listenerCount === "function") {
          return emitter.listenerCount(type);
        } else {
          return listenerCount.call(emitter, type);
        }
      };
      EventEmitter.prototype.listenerCount = listenerCount;
      function listenerCount(type) {
        var events = this._events;
        if (events !== void 0) {
          var evlistener = events[type];
          if (typeof evlistener === "function") {
            return 1;
          } else if (evlistener !== void 0) {
            return evlistener.length;
          }
        }
        return 0;
      }
      EventEmitter.prototype.eventNames = function eventNames() {
        return this._eventsCount > 0 ? ReflectOwnKeys(this._events) : [];
      };
      function arrayClone(arr, n) {
        var copy = new Array(n);
        for (var i = 0; i < n; ++i)
          copy[i] = arr[i];
        return copy;
      }
      function spliceOne(list, index) {
        for (; index + 1 < list.length; index++)
          list[index] = list[index + 1];
        list.pop();
      }
      function unwrapListeners(arr) {
        var ret = new Array(arr.length);
        for (var i = 0; i < ret.length; ++i) {
          ret[i] = arr[i].listener || arr[i];
        }
        return ret;
      }
      function once(emitter, name) {
        return new Promise(function(resolve, reject) {
          function errorListener(err) {
            emitter.removeListener(name, resolver);
            reject(err);
          }
          function resolver() {
            if (typeof emitter.removeListener === "function") {
              emitter.removeListener("error", errorListener);
            }
            resolve([].slice.call(arguments));
          }
          ;
          eventTargetAgnosticAddListener(emitter, name, resolver, { once: true });
          if (name !== "error") {
            addErrorHandlerIfEventEmitter(emitter, errorListener, { once: true });
          }
        });
      }
      function addErrorHandlerIfEventEmitter(emitter, handler, flags) {
        if (typeof emitter.on === "function") {
          eventTargetAgnosticAddListener(emitter, "error", handler, flags);
        }
      }
      function eventTargetAgnosticAddListener(emitter, name, listener, flags) {
        if (typeof emitter.on === "function") {
          if (flags.once) {
            emitter.once(name, listener);
          } else {
            emitter.on(name, listener);
          }
        } else if (typeof emitter.addEventListener === "function") {
          emitter.addEventListener(name, function wrapListener(arg) {
            if (flags.once) {
              emitter.removeEventListener(name, wrapListener);
            }
            listener(arg);
          });
        } else {
          throw new TypeError('The "emitter" argument must be of type EventEmitter. Received type ' + typeof emitter);
        }
      }
    }
  });

  // node_modules/scratch-audio/src/effects/Effect.js
  var require_Effect = __commonJS({
    "node_modules/scratch-audio/src/effects/Effect.js"(exports, module) {
      var Effect = class {
        /**
          * @param {AudioEngine} audioEngine - audio engine this runs with
          * @param {AudioPlayer} audioPlayer - audio player this affects
          * @param {Effect} lastEffect - effect in the chain before this one
          * @constructor
          */
        constructor(audioEngine, audioPlayer, lastEffect) {
          this.audioEngine = audioEngine;
          this.audioPlayer = audioPlayer;
          this.lastEffect = lastEffect;
          this.value = this.DEFAULT_VALUE;
          this.initialized = false;
          this.inputNode = null;
          this.outputNode = null;
          this.target = null;
        }
        /**
         * Return the name of the effect.
         * @type {string}
         */
        get name() {
          throw new Error(`${this.constructor.name}.name is not implemented`);
        }
        /**
         * Default value to set the Effect to when constructed and when clear'ed.
         * @const {number}
         */
        get DEFAULT_VALUE() {
          return 0;
        }
        /**
         * Should the effect be connected to the audio graph?
         * The pitch effect is an example that does not need to be patched in.
         * Instead of affecting the graph it affects the player directly.
         * @return {boolean} is the effect affecting the graph?
         */
        get _isPatch() {
          return this.initialized && (this.value !== this.DEFAULT_VALUE || this.audioPlayer === null);
        }
        /**
         * Get the input node.
         * @return {AudioNode} - audio node that is the input for this effect
         */
        getInputNode() {
          if (this._isPatch) {
            return this.inputNode;
          }
          return this.target.getInputNode();
        }
        /**
         * Initialize the Effect.
         * Effects start out uninitialized. Then initialize when they are first set
         * with some value.
         * @throws {Error} throws when left unimplemented
         */
        initialize() {
          throw new Error(`${this.constructor.name}.initialize is not implemented.`);
        }
        /**
         * Set the effects value.
         * @private
         * @param {number} value - new value to set effect to
         */
        _set() {
          throw new Error(`${this.constructor.name}._set is not implemented.`);
        }
        /**
         * Set the effects value.
         * @param {number} value - new value to set effect to
         */
        set(value) {
          if (!this.initialized) {
            this.initialize();
          }
          const wasPatch = this._isPatch;
          if (wasPatch) {
            this._lastPatch = this.audioEngine.currentTime;
          }
          this._set(value);
          if (this._isPatch !== wasPatch && this.target !== null) {
            this.connect(this.target);
          }
        }
        /**
         * Update the effect for changes in the audioPlayer.
         */
        update() {
        }
        /**
         * Clear the value back to the default.
         */
        clear() {
          this.set(this.DEFAULT_VALUE);
        }
        /**
         * Connnect this effect's output to another audio node
         * @param {object} target - target whose node to should be connected
         */
        connect(target) {
          if (target === null) {
            throw new Error("target may not be null");
          }
          const checkForCircularReference = (subtarget) => {
            if (subtarget) {
              if (subtarget === this) {
                return true;
              }
              return checkForCircularReference(subtarget.target);
            }
          };
          if (checkForCircularReference(target)) {
            throw new Error("Effect cannot connect to itself");
          }
          this.target = target;
          if (this.outputNode !== null) {
            this.outputNode.disconnect();
          }
          if (this._isPatch || this._lastPatch + this.audioEngine.DECAY_DURATION < this.audioEngine.currentTime) {
            this.outputNode.connect(target.getInputNode());
          }
          if (this.lastEffect === null) {
            if (this.audioPlayer !== null) {
              this.audioPlayer.connect(this);
            }
          } else {
            this.lastEffect.connect(this);
          }
        }
        /**
         * Clean up and disconnect audio nodes.
         */
        dispose() {
          this.inputNode = null;
          this.outputNode = null;
          this.target = null;
          this.initialized = false;
        }
      };
      module.exports = Effect;
    }
  });

  // node_modules/scratch-audio/src/effects/VolumeEffect.js
  var require_VolumeEffect = __commonJS({
    "node_modules/scratch-audio/src/effects/VolumeEffect.js"(exports, module) {
      var Effect = require_Effect();
      var VolumeEffect = class extends Effect {
        /**
         * Default value to set the Effect to when constructed and when clear'ed.
         * @const {number}
         */
        get DEFAULT_VALUE() {
          return 100;
        }
        /**
         * Return the name of the effect.
         * @type {string}
         */
        get name() {
          return "volume";
        }
        /**
         * Initialize the Effect.
         * Effects start out uninitialized. Then initialize when they are first set
         * with some value.
         * @throws {Error} throws when left unimplemented
         */
        initialize() {
          this.inputNode = this.audioEngine.audioContext.createGain();
          this.outputNode = this.inputNode;
          this.initialized = true;
        }
        /**
         * Set the effects value.
         * @private
         * @param {number} value - new value to set effect to
         */
        _set(value) {
          this.value = value;
          const { gain } = this.outputNode;
          const { currentTime, DECAY_DURATION } = this.audioEngine;
          gain.linearRampToValueAtTime(value / 100, currentTime + DECAY_DURATION);
        }
        /**
         * Clean up and disconnect audio nodes.
         */
        dispose() {
          if (!this.initialized) {
            return;
          }
          this.outputNode.disconnect();
          this.inputNode = null;
          this.outputNode = null;
          this.target = null;
          this.initialized = false;
        }
      };
      module.exports = VolumeEffect;
    }
  });

  // node_modules/scratch-audio/src/SoundPlayer.js
  var require_SoundPlayer = __commonJS({
    "node_modules/scratch-audio/src/SoundPlayer.js"(exports, module) {
      var { EventEmitter } = require_events();
      var VolumeEffect = require_VolumeEffect();
      var ON_ENDED = "ended";
      var SoundPlayer = class _SoundPlayer extends EventEmitter {
        /**
         * Play sounds that stop without audible clipping.
         *
         * @param {AudioEngine} audioEngine - engine to play sounds on
         * @param {object} data - required data for sound playback
         * @param {string} data.id - a unique id for this sound
         * @param {ArrayBuffer} data.buffer - buffer of the sound's waveform to play
         * @constructor
         */
        constructor(audioEngine, { id, buffer }) {
          super();
          this.id = id;
          this.audioEngine = audioEngine;
          this.buffer = buffer;
          this.outputNode = null;
          this.volumeEffect = null;
          this.target = null;
          this.initialized = false;
          this.isPlaying = false;
          this.startingUntil = 0;
          this.playbackRate = 1;
          this.handleEvent = this.handleEvent.bind(this);
        }
        /**
         * Is plaback currently starting?
         * @type {boolean}
         */
        get isStarting() {
          return this.isPlaying && this.startingUntil > this.audioEngine.currentTime;
        }
        /**
         * Handle any event we have told the output node to listen for.
         * @param {Event} event - dom event to handle
         */
        handleEvent(event) {
          if (event.type === ON_ENDED) {
            this.onEnded();
          }
        }
        /**
         * Event listener for when playback ends.
         */
        onEnded() {
          this.emit("stop");
          this.isPlaying = false;
        }
        /**
         * Create the buffer source node during initialization or secondary
         * playback.
         */
        _createSource() {
          if (this.outputNode !== null) {
            this.outputNode.removeEventListener(ON_ENDED, this.handleEvent);
            this.outputNode.disconnect();
          }
          this.outputNode = this.audioEngine.audioContext.createBufferSource();
          this.outputNode.playbackRate.value = this.playbackRate;
          this.outputNode.buffer = this.buffer;
          this.outputNode.addEventListener(ON_ENDED, this.handleEvent);
          if (this.target !== null) {
            this.connect(this.target);
          }
        }
        /**
         * Initialize the player for first playback.
         */
        initialize() {
          this.initialized = true;
          this._createSource();
        }
        /**
         * Connect the player to the engine or an effect chain.
         * @param {object} target - object to connect to
         * @returns {object} - return this sound player
         */
        connect(target) {
          if (target === this.volumeEffect) {
            this.outputNode.disconnect();
            this.outputNode.connect(this.volumeEffect.getInputNode());
            return;
          }
          this.target = target;
          if (!this.initialized) {
            return;
          }
          if (this.volumeEffect === null) {
            this.outputNode.disconnect();
            this.outputNode.connect(target.getInputNode());
          } else {
            this.volumeEffect.connect(target);
          }
          return this;
        }
        /**
         * Teardown the player.
         */
        dispose() {
          if (!this.initialized) {
            return;
          }
          this.stopImmediately();
          if (this.volumeEffect !== null) {
            this.volumeEffect.dispose();
            this.volumeEffect = null;
          }
          this.outputNode.disconnect();
          this.outputNode = null;
          this.target = null;
          this.initialized = false;
        }
        /**
         * Take the internal state of this player and create a new player from
         * that. Restore the state of this player to that before its first playback.
         *
         * The returned player can be used to stop the original playback or
         * continue it without manipulation from the original player.
         *
         * @returns {SoundPlayer} - new SoundPlayer with old state
         */
        take() {
          if (this.outputNode) {
            this.outputNode.removeEventListener(ON_ENDED, this.handleEvent);
          }
          const taken = new _SoundPlayer(this.audioEngine, this);
          taken.playbackRate = this.playbackRate;
          if (this.isPlaying) {
            taken.startingUntil = this.startingUntil;
            taken.isPlaying = this.isPlaying;
            taken.initialized = this.initialized;
            taken.outputNode = this.outputNode;
            taken.outputNode.addEventListener(ON_ENDED, taken.handleEvent);
            taken.volumeEffect = this.volumeEffect;
            if (taken.volumeEffect) {
              taken.volumeEffect.audioPlayer = taken;
            }
            if (this.target !== null) {
              taken.connect(this.target);
            }
            this.emit("stop");
            taken.emit("play");
          }
          this.outputNode = null;
          this.volumeEffect = null;
          this.initialized = false;
          this.startingUntil = 0;
          this.isPlaying = false;
          return taken;
        }
        /**
         * Start playback for this sound.
         *
         * If the sound is already playing it will stop playback with a quick fade
         * out.
         */
        play() {
          if (this.isStarting) {
            this.emit("stop");
            this.emit("play");
            return;
          }
          if (this.isPlaying) {
            this.stop();
          }
          if (this.initialized) {
            this._createSource();
          } else {
            this.initialize();
          }
          this.outputNode.start();
          this.isPlaying = true;
          const { currentTime, DECAY_DURATION } = this.audioEngine;
          this.startingUntil = currentTime + DECAY_DURATION;
          this.emit("play");
        }
        /**
         * Stop playback after quickly fading out.
         */
        stop() {
          if (!this.isPlaying) {
            return;
          }
          const taken = this.take();
          taken.volumeEffect = new VolumeEffect(taken.audioEngine, taken, null);
          taken.volumeEffect.connect(taken.target);
          taken.finished().then(() => taken.dispose());
          taken.volumeEffect.set(0);
          const { currentTime, DECAY_DURATION } = this.audioEngine;
          taken.outputNode.stop(currentTime + DECAY_DURATION);
        }
        /**
         * Stop immediately without fading out. May cause audible clipping.
         */
        stopImmediately() {
          if (!this.isPlaying) {
            return;
          }
          this.outputNode.stop();
          this.isPlaying = false;
          this.startingUntil = 0;
          this.emit("stop");
        }
        /**
         * Return a promise that resolves when the sound next finishes.
         * @returns {Promise} - resolves when the sound finishes
         */
        finished() {
          return new Promise((resolve) => {
            this.once("stop", resolve);
          });
        }
        /**
         * Set the sound's playback rate.
         * @param {number} value - playback rate. Default is 1.
         */
        setPlaybackRate(value) {
          this.playbackRate = value;
          if (this.initialized) {
            this.outputNode.playbackRate.value = value;
          }
        }
      };
      module.exports = SoundPlayer;
    }
  });

  // node_modules/scratch-audio/src/effects/EffectChain.js
  var require_EffectChain = __commonJS({
    "node_modules/scratch-audio/src/effects/EffectChain.js"(exports, module) {
      var EffectChain = class _EffectChain {
        /**
         * Chain of effects that can be applied to a group of SoundPlayers.
         * @param {AudioEngine} audioEngine - engine whose effects these belong to
         * @param {Array<Effect>} effects - array of Effect classes to construct
         */
        constructor(audioEngine, effects) {
          this.audioEngine = audioEngine;
          this.inputNode = this.audioEngine.audioContext.createGain();
          this.effects = effects;
          let lastEffect = null;
          this._effects = effects.reverse().map((Effect) => {
            const effect = new Effect(audioEngine, this, lastEffect);
            this[effect.name] = effect;
            lastEffect = effect;
            return effect;
          }).reverse();
          this.firstEffect = this._effects[0];
          this.lastEffect = this._effects[this._effects.length - 1];
          this._soundPlayers = /* @__PURE__ */ new Set();
        }
        /**
         * Create a clone of the EffectChain.
         * @returns {EffectChain} a clone of this EffectChain
         */
        clone() {
          const chain = new _EffectChain(this.audioEngine, this.effects);
          if (this.target) {
            chain.connect(this.target);
          }
          return chain;
        }
        /**
         * Add a sound player.
         * @param {SoundPlayer} soundPlayer - a sound player to manage
         */
        addSoundPlayer(soundPlayer) {
          if (!this._soundPlayers.has(soundPlayer)) {
            this._soundPlayers.add(soundPlayer);
            this.update();
          }
        }
        /**
         * Remove a sound player.
         * @param {SoundPlayer} soundPlayer - a sound player to stop managing
         */
        removeSoundPlayer(soundPlayer) {
          this._soundPlayers.remove(soundPlayer);
        }
        /**
         * Get the audio input node.
         * @returns {AudioNode} audio node the upstream can connect to
         */
        getInputNode() {
          return this.inputNode;
        }
        /**
         * Connnect this player's output to another audio node.
         * @param {object} target - target whose node to should be connected
         */
        connect(target) {
          const { firstEffect, lastEffect } = this;
          if (target === lastEffect) {
            this.inputNode.disconnect();
            this.inputNode.connect(lastEffect.getInputNode());
            return;
          } else if (target === firstEffect) {
            return;
          }
          this.target = target;
          firstEffect.connect(target);
        }
        /**
         * Array of SoundPlayers managed by this EffectChain.
         * @returns {Array<SoundPlayer>} sound players managed by this chain
         */
        getSoundPlayers() {
          return [...this._soundPlayers];
        }
        /**
         * Set Effect values with named values on target.soundEffects if it exist
         * and then from target itself.
         * @param {Target} target - target to set values from
         */
        setEffectsFromTarget(target) {
          this._effects.forEach((effect) => {
            if ("soundEffects" in target && effect.name in target.soundEffects) {
              effect.set(target.soundEffects[effect.name]);
            } else if (effect.name in target) {
              effect.set(target[effect.name]);
            }
          });
        }
        /**
         * Set an effect value by its name.
         * @param {string} effect - effect name to change
         * @param {number} value - value to set effect to
         */
        set(effect, value) {
          if (effect in this) {
            this[effect].set(value);
          }
        }
        /**
         * Update managed sound players with the effects on this chain.
         */
        update() {
          this._effects.forEach((effect) => effect.update());
        }
        /**
         * Clear all effects to their default values.
         */
        clear() {
          this._effects.forEach((effect) => effect.clear());
        }
        /**
         * Dispose of all effects in this chain. Nothing is done to managed
         * SoundPlayers.
         */
        dispose() {
          this._soundPlayers = null;
          this._effects.forEach((effect) => effect.dispose());
          this._effects = null;
        }
      };
      module.exports = EffectChain;
    }
  });

  // node_modules/scratch-audio/src/effects/PanEffect.js
  var require_PanEffect = __commonJS({
    "node_modules/scratch-audio/src/effects/PanEffect.js"(exports, module) {
      var Effect = require_Effect();
      var PanEffect = class extends Effect {
        /**
         * @param {AudioEngine} audioEngine - audio engine this runs with
         * @param {AudioPlayer} audioPlayer - audio player this affects
         * @param {Effect} lastEffect - effect in the chain before this one
         * @constructor
         */
        constructor(audioEngine, audioPlayer, lastEffect) {
          super(audioEngine, audioPlayer, lastEffect);
          this.leftGain = null;
          this.rightGain = null;
          this.channelMerger = null;
        }
        /**
         * Return the name of the effect.
         * @type {string}
         */
        get name() {
          return "pan";
        }
        /**
         * Initialize the Effect.
         * Effects start out uninitialized. Then initialize when they are first set
         * with some value.
         * @throws {Error} throws when left unimplemented
         */
        initialize() {
          const audioContext = this.audioEngine.audioContext;
          this.inputNode = audioContext.createGain();
          this.leftGain = audioContext.createGain();
          this.rightGain = audioContext.createGain();
          this.channelMerger = audioContext.createChannelMerger(2);
          this.outputNode = this.channelMerger;
          this.inputNode.connect(this.leftGain);
          this.inputNode.connect(this.rightGain);
          this.leftGain.connect(this.channelMerger, 0, 0);
          this.rightGain.connect(this.channelMerger, 0, 1);
          this.initialized = true;
        }
        /**
         * Set the effect value
         * @param {number} value - the new value to set the effect to
         */
        _set(value) {
          this.value = value;
          const p = (value + 100) / 200;
          const leftVal = Math.cos(p * Math.PI / 2);
          const rightVal = Math.sin(p * Math.PI / 2);
          const { currentTime, DECAY_WAIT, DECAY_DURATION } = this.audioEngine;
          this.leftGain.gain.setTargetAtTime(leftVal, currentTime + DECAY_WAIT, DECAY_DURATION);
          this.rightGain.gain.setTargetAtTime(rightVal, currentTime + DECAY_WAIT, DECAY_DURATION);
        }
        /**
         * Clean up and disconnect audio nodes.
         */
        dispose() {
          if (!this.initialized) {
            return;
          }
          this.inputNode.disconnect();
          this.leftGain.disconnect();
          this.rightGain.disconnect();
          this.channelMerger.disconnect();
          this.inputNode = null;
          this.leftGain = null;
          this.rightGain = null;
          this.channelMerger = null;
          this.outputNode = null;
          this.target = null;
          this.initialized = false;
        }
      };
      module.exports = PanEffect;
    }
  });

  // node_modules/scratch-audio/src/effects/PitchEffect.js
  var require_PitchEffect = __commonJS({
    "node_modules/scratch-audio/src/effects/PitchEffect.js"(exports, module) {
      var Effect = require_Effect();
      var PitchEffect = class extends Effect {
        /**
         * @param {AudioEngine} audioEngine - audio engine this runs with
         * @param {AudioPlayer} audioPlayer - audio player this affects
         * @param {Effect} lastEffect - effect in the chain before this one
         * @constructor
         */
        constructor(audioEngine, audioPlayer, lastEffect) {
          super(audioEngine, audioPlayer, lastEffect);
          this.ratio = 1;
        }
        /**
         * Return the name of the effect.
         * @type {string}
         */
        get name() {
          return "pitch";
        }
        /**
         * Should the effect be connected to the audio graph?
         * @return {boolean} is the effect affecting the graph?
         */
        get _isPatch() {
          return false;
        }
        /**
         * Get the input node.
         * @return {AudioNode} - audio node that is the input for this effect
         */
        getInputNode() {
          return this.target.getInputNode();
        }
        /**
         * Initialize the Effect.
         * Effects start out uninitialized. Then initialize when they are first set
         * with some value.
         * @throws {Error} throws when left unimplemented
         */
        initialize() {
          this.initialized = true;
        }
        /**
         * Set the effect value.
         * @param {number} value - the new value to set the effect to
         */
        _set(value) {
          this.value = value;
          this.ratio = this.getRatio(this.value);
          this.updatePlayers(this.audioPlayer.getSoundPlayers());
        }
        /**
         * Update the effect for changes in the audioPlayer.
         */
        update() {
          this.updatePlayers(this.audioPlayer.getSoundPlayers());
        }
        /**
         * Compute the playback ratio for an effect value.
         * The playback ratio is scaled so that a change of 10 in the effect value
         * gives a change of 1 semitone in the ratio.
         * @param {number} val - an effect value
         * @returns {number} a playback ratio
         */
        getRatio(val) {
          const interval = val / 10;
          return Math.pow(2, interval / 12);
        }
        /**
         * Update a sound player's playback rate using the current ratio for the
         * effect
         * @param {object} player - a SoundPlayer object
         */
        updatePlayer(player) {
          player.setPlaybackRate(this.ratio);
        }
        /**
         * Update a sound player's playback rate using the current ratio for the
         * effect
         * @param {object} players - a dictionary of SoundPlayer objects to update,
         *     indexed by md5
         */
        updatePlayers(players) {
          if (!players) return;
          for (const id in players) {
            if (Object.prototype.hasOwnProperty.call(players, id)) {
              this.updatePlayer(players[id]);
            }
          }
        }
      };
      module.exports = PitchEffect;
    }
  });

  // node_modules/scratch-audio/src/SoundBank.js
  var require_SoundBank = __commonJS({
    "node_modules/scratch-audio/src/SoundBank.js"(exports, module) {
      var log = require_log();
      var ALL_TARGETS = "*";
      var SoundBank = class {
        /**
         * A bank of sounds that can be played.
         * @constructor
         * @param {AudioEngine} audioEngine - related AudioEngine
         * @param {EffectChain} effectChainPrime - original EffectChain cloned for
         *     playing sounds
         */
        constructor(audioEngine, effectChainPrime) {
          this.audioEngine = audioEngine;
          this.soundPlayers = {};
          this.playerTargets = /* @__PURE__ */ new Map();
          this.soundEffects = /* @__PURE__ */ new Map();
          this.effectChainPrime = effectChainPrime;
        }
        /**
         * Add a sound player instance likely from AudioEngine.decodeSoundPlayer
         * @param {SoundPlayer} soundPlayer - SoundPlayer to add
         */
        addSoundPlayer(soundPlayer) {
          this.soundPlayers[soundPlayer.id] = soundPlayer;
        }
        /**
         * Get a sound player by id.
         * @param {string} soundId - sound to look for
         * @returns {SoundPlayer} instance of sound player for the id
         */
        getSoundPlayer(soundId) {
          if (!this.soundPlayers[soundId]) {
            log.error(`SoundBank.getSoundPlayer(${soundId}): called missing sound in bank`);
          }
          return this.soundPlayers[soundId];
        }
        /**
         * Get a sound EffectChain by id.
         * @param {string} sound - sound to look for an EffectChain
         * @returns {EffectChain} available EffectChain for this id
         */
        getSoundEffects(sound) {
          if (!this.soundEffects.has(sound)) {
            this.soundEffects.set(sound, this.effectChainPrime.clone());
          }
          return this.soundEffects.get(sound);
        }
        /**
         * Play a sound.
         * @param {Target} target - Target to play for
         * @param {string} soundId - id of sound to play
         * @returns {Promise} promise that resolves when the sound finishes playback
         */
        playSound(target, soundId) {
          const effects = this.getSoundEffects(soundId);
          const player = this.getSoundPlayer(soundId);
          if (this.playerTargets.get(soundId) !== target) {
            player.stop();
          }
          this.playerTargets.set(soundId, target);
          effects.addSoundPlayer(player);
          effects.setEffectsFromTarget(target);
          player.connect(effects);
          player.play();
          return player.finished();
        }
        /**
         * Set the effects (pan, pitch, and volume) from values on the given target.
         * @param {Target} target - target to set values from
         */
        setEffects(target) {
          this.playerTargets.forEach((playerTarget, key) => {
            if (playerTarget === target) {
              this.getSoundEffects(key).setEffectsFromTarget(target);
            }
          });
        }
        /**
         * Stop playback of sound by id if was lasted played by the target.
         * @param {Target} target - target to check if it last played the sound
         * @param {string} soundId - id of the sound to stop
         */
        stop(target, soundId) {
          if (this.playerTargets.get(soundId) === target) {
            this.soundPlayers[soundId].stop();
          }
        }
        /**
         * Stop all sounds for all targets or a specific target.
         * @param {Target|string} target - a symbol for all targets or the target
         *     to stop sounds for
         */
        stopAllSounds(target = ALL_TARGETS) {
          this.playerTargets.forEach((playerTarget, key) => {
            if (target === ALL_TARGETS || playerTarget === target) {
              this.getSoundPlayer(key).stop();
            }
          });
        }
        /**
         * Dispose of all EffectChains and SoundPlayers.
         */
        dispose() {
          this.playerTargets.clear();
          this.soundEffects.forEach((effects) => effects.dispose());
          this.soundEffects.clear();
          for (const soundId in this.soundPlayers) {
            if (Object.prototype.hasOwnProperty.call(this.soundPlayers, soundId)) {
              this.soundPlayers[soundId].dispose();
            }
          }
          this.soundPlayers = {};
        }
      };
      module.exports = SoundBank;
    }
  });

  // node_modules/scratch-audio/src/AudioEngine.js
  var require_AudioEngine = __commonJS({
    "node_modules/scratch-audio/src/AudioEngine.js"(exports, module) {
      var StartAudioContext = require_StartAudioContext2();
      var AudioContext = require_audio_context();
      var log = require_log();
      var uid = require_uid();
      var ADPCMSoundDecoder = require_ADPCMSoundDecoder();
      var Loudness = require_Loudness();
      var SoundPlayer = require_SoundPlayer();
      var EffectChain = require_EffectChain();
      var PanEffect = require_PanEffect();
      var PitchEffect = require_PitchEffect();
      var VolumeEffect = require_VolumeEffect();
      var SoundBank = require_SoundBank();
      var decodeAudioData = function(audioContext, buffer) {
        if (audioContext.decodeAudioData.length === 1) {
          return audioContext.decodeAudioData(buffer);
        }
        return new Promise((resolve, reject) => {
          audioContext.decodeAudioData(
            buffer,
            (decodedAudio) => resolve(decodedAudio),
            (error) => reject(error)
          );
        });
      };
      var AudioEngine = class {
        constructor(audioContext = new AudioContext()) {
          this.audioContext = audioContext;
          StartAudioContext(this.audioContext);
          this.inputNode = this.audioContext.createGain();
          this.inputNode.connect(this.audioContext.destination);
          this.audioBuffers = {};
          this.loudness = null;
          this.effects = [PanEffect, PitchEffect, VolumeEffect];
        }
        /**
         * Current time in the AudioEngine.
         * @type {number}
         */
        get currentTime() {
          return this.audioContext.currentTime;
        }
        /**
         * Names of the audio effects.
         * @enum {string}
         */
        get EFFECT_NAMES() {
          return {
            pitch: "pitch",
            pan: "pan"
          };
        }
        /**
         * A short duration to transition audio prarameters.
         *
         * Used as a time constant for exponential transitions. A general value
         * must be large enough that it does not cute off lower frequency, or bass,
         * sounds. Human hearing lower limit is ~20Hz making a safe value 25
         * milliseconds or 0.025 seconds, where half of a 20Hz wave will play along
         * with the DECAY. Higher frequencies will play multiple waves during the
         * same amount of time and avoid clipping.
         *
         * @see {@link https://developer.mozilla.org/en-US/docs/Web/API/AudioParam/setTargetAtTime}
         * @const {number}
         */
        get DECAY_DURATION() {
          return 0.025;
        }
        /**
         * Some environments cannot smoothly change parameters immediately, provide
         * a small delay before decaying.
         *
         * @see {@link https://bugzilla.mozilla.org/show_bug.cgi?id=1228207}
         * @const {number}
         */
        get DECAY_WAIT() {
          return 0.05;
        }
        /**
         * Get the input node.
         * @return {AudioNode} - audio node that is the input for this effect
         */
        getInputNode() {
          return this.inputNode;
        }
        /**
         * Decode a sound, decompressing it into audio samples.
         * @param {object} sound - an object containing audio data and metadata for
         *     a sound
         * @param {Buffer} sound.data - sound data loaded from scratch-storage
         * @returns {?Promise} - a promise which will resolve to the sound id and
         *     buffer if decoded
         */
        _decodeSound(sound) {
          const bufferCopy1 = sound.data.buffer.slice(0);
          const soundId = uid();
          const decoding = decodeAudioData(this.audioContext, bufferCopy1).catch(() => {
            if (sound.data.length === 0) {
              return this._emptySound();
            }
            const bufferCopy2 = sound.data.buffer.slice(0);
            return new ADPCMSoundDecoder(this.audioContext).decode(bufferCopy2).catch(() => this._emptySound());
          }).then(
            (buffer) => [soundId, buffer],
            (error) => {
              log.warn("audio data could not be decoded", error);
            }
          );
          return decoding;
        }
        /**
         * An empty sound buffer, for use when we are unable to decode a sound file.
         * @returns {AudioBuffer} - an empty audio buffer.
         */
        _emptySound() {
          return this.audioContext.createBuffer(1, 1, this.audioContext.sampleRate);
        }
        /**
         * Decode a sound, decompressing it into audio samples.
         *
         * Store a reference to it the sound in the audioBuffers dictionary,
         * indexed by soundId.
         *
         * @param {object} sound - an object containing audio data and metadata for
         *     a sound
         * @param {Buffer} sound.data - sound data loaded from scratch-storage
         * @returns {?Promise} - a promise which will resolve to the sound id
         */
        decodeSound(sound) {
          return this._decodeSound(sound).then(([id, buffer]) => {
            this.audioBuffers[id] = buffer;
            return id;
          });
        }
        /**
         * Decode a sound, decompressing it into audio samples.
         *
         * Create a SoundPlayer instance that can be used to play the sound and
         * stop and fade out playback.
         *
         * @param {object} sound - an object containing audio data and metadata for
         *     a sound
         * @param {Buffer} sound.data - sound data loaded from scratch-storage
         * @returns {?Promise} - a promise which will resolve to the buffer
         */
        decodeSoundPlayer(sound) {
          return this._decodeSound(sound).then(([id, buffer]) => new SoundPlayer(this, { id, buffer }));
        }
        /**
         * Get the current loudness of sound received by the microphone.
         * Sound is measured in RMS and smoothed.
         * @return {number} loudness scaled 0 to 100
         */
        getLoudness() {
          if (!this.loudness) {
            this.loudness = new Loudness(this.audioContext);
          }
          return this.loudness.getLoudness();
        }
        /**
         * Create an effect chain.
         * @returns {EffectChain} chain of effects defined by this AudioEngine
         */
        createEffectChain() {
          const effects = new EffectChain(this, this.effects);
          effects.connect(this);
          return effects;
        }
        /**
         * Create a sound bank and effect chain.
         * @returns {SoundBank} a sound bank configured with an effect chain
         *     defined by this AudioEngine
         */
        createBank() {
          return new SoundBank(this, this.createEffectChain());
        }
      };
      module.exports = AudioEngine;
    }
  });

  // node_modules/scratch-audio/src/index.js
  var require_index = __commonJS({
    "node_modules/scratch-audio/src/index.js"(exports, module) {
      var AudioEngine = require_AudioEngine();
      module.exports = AudioEngine;
    }
  });
  return require_index();
})();
/*! Bundled license information:

startaudiocontext/StartAudioContext.js:
  (**
   *  StartAudioContext.js
   *  @author Yotam Mann
   *  @license http://opensource.org/licenses/MIT MIT License
   *  @copyright 2016 Yotam Mann
   *)
*/
