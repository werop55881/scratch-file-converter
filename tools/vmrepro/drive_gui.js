// Drive the full scratch-GUI repro (gui_repro.html) in headless Chrome.
// - Serves this dir over HTTP
// - Uses trusted CDP mouse clicks: File > Load from your computer
//   (the in-page input[type=file] patch injects star-game.sb3 via DataTransfer)
// - Auto-accepts JS dialogs, captures console errors / exceptions
// - Clicks the green flag, waits, reports
// usage: node drive_gui.js [sb3Path] [runSec] [timeoutSec]
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

const CHROME =
  process.env.CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const SB3 = path.resolve(
  process.argv[2] || path.join(__dirname, "..", "..", "game", "star-game.sb3")
);
const RUN_SEC = Number(process.argv[3] || 45);
const timeoutMs = Number(process.argv[4] || 180) * 1000;
const HERE = __dirname;

if (!fs.existsSync(SB3)) {
  console.error("sb3 not found: " + SB3);
  process.exit(2);
}

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".map": "application/json",
  ".json": "application/json",
  ".css": "text/css",
  ".png": "image/png",
  ".gif": "image/gif",
  ".jpg": "image/jpeg",
  ".svg": "image/svg+xml",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".ttf": "font/ttf",
  ".mp3": "audio/mpeg",
  ".wav": "audio/wav",
  ".sb3": "application/zip",
};

function startServer() {
  return new Promise((resolve, reject) => {
    let port = 8100 + Math.floor(Math.random() * 400);
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
      const rel = urlPath === "/" ? "gui_repro.html" : urlPath.replace(/^\/+/, "");
      const file = path.join(HERE, rel);
      if (!file.startsWith(HERE)) {
        res.writeHead(403);
        return res.end("forbidden");
      }
      fs.readFile(file, (err, data) => {
        if (err) {
          res.writeHead(404);
          return res.end("not found: " + rel);
        }
        res.writeHead(200, {
          "Content-Type": MIME[path.extname(file).toLowerCase()] || "application/octet-stream",
        });
        res.end(data);
      });
    });
    const tryListen = () => {
      server.once("error", () => {
        port += 1;
        if (port > 9000) return reject(new Error("no free port"));
        tryListen();
      });
      server.listen(port, "127.0.0.1", () => resolve({ server, port }));
    };
    tryListen();
  });
}

const cdpPort = 9600 + Math.floor(Math.random() * 300);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "gui-chrome-"));
let chrome = null;
let ws = null;
let serverRef = null;
let nextId = 1;
const pending = new Map();

const consoleLines = [];
const exceptions = [];
let fileChooserHandled = false;

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}

async function ev(expression) {
  const r = await send("Runtime.evaluate", {
    expression,
    returnByValue: true,
    awaitPromise: true,
  });
  if (r.exceptionDetails) {
    throw new Error(
      "evaluate failed: " +
        JSON.stringify(
          (r.exceptionDetails.exception && r.exceptionDetails.exception.value) ||
            r.exceptionDetails.text
        )
    );
  }
  return r.result && r.result.value;
}

// trusted (real) mouse click at viewport coords -> gives Chrome user activation
async function trustedClick(rect) {
  await send("Input.dispatchMouseEvent", {
    type: "mouseMoved",
    x: rect.x,
    y: rect.y,
  });
  await send("Input.dispatchMouseEvent", {
    type: "mousePressed",
    x: rect.x,
    y: rect.y,
    button: "left",
    clickCount: 1,
  });
  await send("Input.dispatchMouseEvent", {
    type: "mouseReleased",
    x: rect.x,
    y: rect.y,
    button: "left",
    clickCount: 1,
  });
}

async function connect() {
  for (let i = 0; i < 100; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${cdpPort}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {
      // chrome not up yet
    }
    await sleep(200);
  }
  throw new Error("chrome devtools endpoint never came up");
}

function finish(code, message) {
  console.log(message);
  if (consoleLines.length) {
    console.log("--- console (" + consoleLines.length + " lines) ---");
    for (const l of consoleLines.slice(0, 40)) console.log("  " + l.slice(0, 300));
  }
  if (exceptions.length) {
    console.log("--- exceptions ---");
    for (const e of exceptions.slice(0, 10)) console.log("  " + String(e).slice(0, 500));
  }
  try {
    if (ws) ws.close();
  } catch {}
  if (chrome) chrome.kill();
  if (serverRef) {
    try {
      serverRef.close();
    } catch {}
  }
  try {
    fs.rmSync(profile, { recursive: true, force: true });
  } catch {}
  process.exit(code);
}

async function main() {
  const { server, port } = await startServer();
  serverRef = server;

  chrome = spawn(
    CHROME,
    [
      "--headless=new",
      "--disable-gpu",
      "--enable-unsafe-swiftshader",
      "--use-angle=swiftshader",
      "--no-first-run",
      "--no-default-browser-check",
      "--autoplay-policy=no-user-gesture-required",
      `--remote-debugging-port=${cdpPort}`,
      `--user-data-dir=${profile}`,
      "about:blank",
    ],
    { stdio: "ignore" }
  );

  const wsUrl = await connect();
  ws = new WebSocket(wsUrl);
  await new Promise((resolve, reject) => {
    ws.addEventListener("open", resolve, { once: true });
    ws.addEventListener("error", reject, { once: true });
  });
  ws.addEventListener("message", (event) => {
    const msg = JSON.parse(event.data);
    if (msg.id && pending.has(msg.id)) {
      const { resolve, reject } = pending.get(msg.id);
      pending.delete(msg.id);
      if (msg.error) reject(new Error(msg.error.message));
      else resolve(msg.result);
      return;
    }
    if (msg.method === "Page.fileChooserOpened") {
      fileChooserHandled = true;
      send("Page.handleFileChooser", { action: "Accept", files: [SB3] }).catch((e) =>
        console.log("handleFileChooser failed: " + e.message)
      );
    } else if (msg.method === "Page.javascriptDialogOpening") {
      send("Page.handleJavaScriptDialog", { accept: true }).catch(() => {});
    } else if (msg.method === "Runtime.consoleAPICalled") {
      const text = (msg.params.args || [])
        .map((a) =>
          a.value !== undefined
            ? String(a.value)
            : a.description ||
              (a.unserializableValue || "") + (a.type === "string" ? a.value : "")
        )
        .join(" ");
      consoleLines.push("[" + msg.params.type + "] " + text);
    } else if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      const desc =
        (d.exception && (d.exception.description || d.exception.value)) || d.text;
      exceptions.push(String(desc));
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.setInterceptFileChooserDialog", { enabled: true });
  // full 1024x768 app visible (default headless window is 800x600)
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1280,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });

  const target = `http://127.0.0.1:${port}/gui_repro.html`;
  console.log("navigating:", target, "| sb3:", SB3);
  await send("Page.navigate", { url: target });

  const t0 = Date.now();
  const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

  // phase 1: mount
  let mounted = false;
  while (Date.now() - t0 < 40000) {
    const title = (await ev("document.title").catch(() => "")) || "";
    if (title.indexOf("JSERROR") === 0) {
      finish(1, `[+${elapsed()}s] FAIL at mount: ${title}`);
    }
    if (title === "MOUNTED") {
      mounted = true;
      console.log(`[+${elapsed()}s] MOUNTED`);
      break;
    }
    await sleep(400);
  }
  if (!mounted) {
    const body = await ev("document.body.innerText.slice(0,500)").catch(() => "?");
    finish(1, `[+${elapsed()}s] timeout waiting for MOUNTED. body: ${body}`);
  }

  // phase 2: File menu (trusted click; item opens on mouseUp)
  let fileOpened = false;
  for (let i = 0; i < 30 && !fileOpened; i++) {
    const rect = await ev("window.__rectByText('File')").catch(() => null);
    if (rect) {
      await trustedClick(rect);
      await sleep(600);
      const uploadRect = await ev(
        "window.__rectByText('Load from your computer')"
      ).catch(() => null);
      if (uploadRect) {
        fileOpened = true;
        break;
      }
    }
    await sleep(500);
  }
  if (!fileOpened) {
    const dump = await ev("window.__menuDump()").catch(() => "?");
    finish(1, `[+${elapsed()}s] could not open File menu. menu dump:\n${dump}`);
  }
  console.log(`[+${elapsed()}s] File menu opened`);

  // phase 3: Load from your computer -> input.click() is patched in-page to
  // inject star-game.sb3 via DataTransfer + native change event
  const uploadRect = await ev("window.__rectByText('Load from your computer')");
  if (!uploadRect) {
    const dump = await ev("window.__menuDump()").catch(() => "?");
    finish(1, `[+${elapsed()}s] no 'Load from your computer' item. menu dump:\n${dump}`);
  }
  await trustedClick(uploadRect);
  console.log(`[+${elapsed()}s] Load-from-computer clicked, waiting for file injection...`);

  let injected = false;
  for (let i = 0; i < 20; i++) {
    if (await ev("window.__fileInjected === true").catch(() => false)) {
      injected = true;
      break;
    }
    await sleep(250);
  }
  if (!injected) {
    const inputState = await ev("window.__inputState()").catch(() => "?");
    finish(
      1,
      `[+${elapsed()}s] file injection never happened (input state: ${inputState})`
    );
  }
  console.log(`[+${elapsed()}s] star-game.sb3 injected into file input + change fired`);

  // phase 4: wait for project to appear (sprite list contains BgStar)
  let loaded = false;
  let lastTitle = "";
  while (Date.now() - t0 < 60000) {
    const title = (await ev("document.title").catch(() => "")) || "";
    if (title && title !== lastTitle) {
      console.log(`[+${elapsed()}s] title: ${title}`);
      lastTitle = title;
      if (title.indexOf("JSERROR") === 0) {
        finish(1, `[+${elapsed()}s] FAIL during load: ${title}`);
      }
    }
    const hasProject = await ev("/BgStar/.test(document.body.innerText)").catch(
      () => false
    );
    if (hasProject) {
      loaded = true;
      console.log(`[+${elapsed()}s] PROJECT LOADED (sprite list shows BgStar)`);
      break;
    }
    await sleep(500);
  }
  if (!loaded) {
    const body = await ev("document.body.innerText.slice(0,800)").catch(() => "?");
    finish(1, `[+${elapsed()}s] project never appeared. body: ${body}`);
  }
  await sleep(1500); // let renderer/fonts settle

  // diagnostic: canvases + sprite positions (pre-flag)
  const canvases = await ev("JSON.stringify(window.__canvases())").catch(
    () => '"?"'
  );
  console.log(`canvases: ${canvases}`);
  const monRects = await ev("JSON.stringify(window.__monRects())").catch(
    () => '"?"'
  );
  console.log(`monitor/stage rects: ${monRects}`);
  for (const name of ["Star", "Shop"]) {
    const pos = await ev(`JSON.stringify(window.__targetsPos('${name}'))`).catch(
      () => '"?"'
    );
    console.log(`targets ${name}: ${pos}`);
  }

  // phase 5: click green flag (trusted click)
  let flagRect = null;
  let flagSel = "";
  for (const sel of [
    'button[class*="green-flag"]',
    'button[class*="greenflag"]',
    'button[title="Go"]',
    'button[aria-label="Go"]',
    '[class*="green-flag"]',
  ]) {
    flagRect = await ev(`window.__rectBySel(${JSON.stringify(sel)})`).catch(
      () => null
    );
    if (flagRect) {
      flagSel = sel;
      break;
    }
  }
  if (!flagRect) {
    const buttons = await ev(
      "[...document.querySelectorAll('button')].map(e=>(e.title||e.getAttribute('aria-label')||e.className).slice(0,50)).join('; ')"
    ).catch(() => "?");
    finish(1, `[+${elapsed()}s] green flag button not found. buttons: ${buttons}`);
  }
  await trustedClick(flagRect);
  console.log(
    `[+${elapsed()}s] green flag clicked via ${flagRect.x},${flagRect.y} (${flagSel})`
  );
  await ev("document.title = 'RUNNING'");
  await sleep(1500); // let flag-started clones spawn

  // post-flag diagnostics: real sprite positions + what pick returns there
  const starPos = await ev(
    "JSON.stringify(window.__targetsPos('Star').slice(0,1))"
  ).catch(() => "[]");
  const shopPos = await ev(
    "JSON.stringify(window.__targetsPos('Shop').filter(p=>p.clone))"
  ).catch(() => "[]");
  console.log(`post-flag Star: ${starPos}`);
  console.log(`post-flag Shop clones: ${shopPos}`);
  const starXY = JSON.parse(starPos || "[]")[0];
  const shopXYS = JSON.parse(shopPos || "[]");
  if (starXY) {
    const d = await ev(
      `JSON.stringify(window.__diag(${starXY.x}, ${starXY.y}))`
    ).catch((e) => '"err ' + e.message + '"');
    console.log(`diag(star): ${d}`);
  }
  for (const p of shopXYS.slice(0, 3)) {
    const d = await ev(
      `JSON.stringify(window.__diag(${p.x}, ${p.y}))`
    ).catch((e) => '"err ' + e.message + '"');
    console.log(`diag(shop ${p.x},${p.y}): ${d}`);
  }

  // phase 6: run with gameplay clicks (actual sprite positions)
  const runStart = Date.now();
  let starClicks = 0;
  let shopClicks = 0;
  let tick = 0;
  let shopTargets = shopXYS;
  while ((Date.now() - runStart) / 1000 < RUN_SEC) {
    await sleep(1000);
    tick++;
    const title = (await ev("document.title").catch(() => "")) || "";
    if (title.indexOf("JSERROR") === 0) {
      const log = await ev("window.__log.slice(0,30).join('\\n')").catch(() => "");
      finish(
        1,
        `[+${elapsed()}s] CRASH after green flag: ${title}\n--- page __log ---\n${log}`
      );
    }
    if (starXY) {
      const r = await ev(`window.__stageClick(${starXY.x}, ${starXY.y})`).catch(
        () => null
      );
      if (r) {
        await trustedClick(r);
        starClicks++;
      }
    }
    if (tick % 3 === 0 && shopTargets.length) {
      const p = shopTargets[Math.floor(tick / 3) % shopTargets.length];
      const r = await ev(`window.__stageClick(${p.x}, ${p.y})`).catch(() => null);
      if (r) {
        await trustedClick(r);
        shopClicks++;
      }
    }
    if (tick % 10 === 0) {
      const fresh = await ev(
        "JSON.stringify(window.__targetsPos('Shop').filter(p=>p.clone))"
      ).catch(() => "");
      if (fresh) {
        try {
          const parsed = JSON.parse(fresh);
          if (parsed.length) shopTargets = parsed;
        } catch (e) { /* keep old */ }
      }
      const partial = await ev("JSON.stringify(window.__stats())").catch(() => "{}");
      console.log(`[+${elapsed()}s] mid-run (${starClicks} star, ${shopClicks} shop): ${partial}`);
    }
  }

  // final stats
  const stats = await ev("JSON.stringify(window.__stats())").catch(() => '"no stats"');
  const pageErrors = await ev("JSON.stringify(window.__errors)").catch(() => "[]");
  const pageLog = await ev("JSON.stringify(window.__log.slice(0,40))").catch(() => "[]");
  finish(
    0,
    `GUI SMOKE OK: ${RUN_SEC}s after green flag with ${starClicks} star + ${shopClicks} shop clicks, no crash\nstats: ${stats}\npage errors: ${pageErrors}\npage log: ${pageLog}`
  );
}

main().catch((err) => finish(1, `error: ${err.message}`));
