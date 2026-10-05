// Load our .sb3 into the REAL scratch.mit.edu editor (headless Chrome) and
// verify it survives green flag + gameplay without the 'Monitors' Oops.
// usage: node drive_online.js [sb3Path] [runSec] [timeoutSec]
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const CHROME =
  process.env.CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const SB3 = path.resolve(
  process.argv[2] || path.join(__dirname, "..", "..", "game", "star-game.sb3")
);
const RUN_SEC = Number(process.argv[3] || 45);
const timeoutMs = Number(process.argv[4] || 180) * 1000;

if (!fs.existsSync(SB3)) {
  console.error("sb3 not found: " + SB3);
  process.exit(2);
}

const cdpPort = 9700 + Math.floor(Math.random() * 200);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "online-chrome-"));
let chrome = null;
let ws = null;
let nextId = 1;
const pending = new Map();

const consoleLines = [];
const errors = [];

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
async function trustedClick(rect) {
  await send("Input.dispatchMouseEvent", { type: "mouseMoved", x: rect.x, y: rect.y });
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
  for (let i = 0; i < 150; i++) {
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
  if (errors.length) {
    console.log("--- captured errors (" + errors.length + ") ---");
    for (const e of errors.slice(0, 8)) console.log("  " + String(e).slice(0, 600));
  }
  const errConsole = consoleLines.filter((l) => l.indexOf("[error]") === 0);
  if (errConsole.length) {
    console.log("--- console errors (" + errConsole.length + ") ---");
    for (const l of errConsole.slice(0, 12)) console.log("  " + l.slice(0, 600));
  }
  try {
    if (ws) ws.close();
  } catch {}
  if (chrome) chrome.kill();
  try {
    fs.rmSync(profile, { recursive: true, force: true });
  } catch {}
  process.exit(code);
}

async function main() {
  const sb3b64 = fs.readFileSync(SB3).toString("base64");
  console.log("sb3:", SB3, `(${sb3b64.length} b64 chars)`);

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
    if (msg.method === "Runtime.consoleAPICalled") {
      const text = (msg.params.args || [])
        .map((a) =>
          a.value !== undefined
            ? String(a.value)
            : a.description || (a.unserializableValue || "") + (a.type === "string" ? a.value : "")
        )
        .join(" ");
      consoleLines.push("[" + msg.params.type + "] " + text);
      if (/action='Monitors'|Unhandled Error|Element type is invalid/i.test(text)) {
        errors.push("console." + msg.params.type + ": " + text);
      }
    } else if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      const desc =
        (d.exception && (d.exception.description || d.exception.value)) || d.text;
      errors.push("exception: " + String(desc));
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Emulation.setDeviceMetricsOverride", {
    width: 1280,
    height: 900,
    deviceScaleFactor: 1,
    mobile: false,
  });

  const target = "https://scratch.mit.edu/projects/editor/";
  console.log("navigating:", target);
  await send("Page.navigate", { url: target });

  const t0 = Date.now();
  const elapsed = () => ((Date.now() - t0) / 1000).toFixed(1);

  // phase 1: editor ready (File menu visible), detect login walls
  let ready = false;
  while (Date.now() - t0 < timeoutMs) {
    const url = (await ev("location.href").catch(() => "")) || "";
    if (/login|accounts/.test(url)) {
      finish(1, `[+${elapsed()}s] redirected to login: ${url}`);
    }
    if (
      await ev(
        "[...document.querySelectorAll('*')].some(e=>{try{return e.textContent.trim()==='File'&&e.getClientRects().length>0}catch(err){return false}})"
      ).catch(() => false)
    ) {
      ready = true;
      break;
    }
    await sleep(800);
  }
  if (!ready) {
    const body = await ev("document.body.innerText.slice(0,600)").catch(() => "?");
    const url = await ev("location.href").catch(() => "?");
    finish(1, `[+${elapsed()}s] editor never became ready. url=${url} body:\n${body}`);
  }
  console.log(`[+${elapsed()}s] editor ready (File menu visible)`);

  // install helpers + file-input patch + bytes
  await ev(`
    window.__fileInjected = false;
    window.__sb3b64 = ${JSON.stringify(sb3b64)};
    window.__rectByText = function (txt) {
      var all = Array.prototype.slice.call(document.querySelectorAll('*')).filter(function (e) {
        try { return e.textContent.trim() === txt && e.getClientRects().length > 0; }
        catch (err) { return false; }
      });
      if (!all.length) return null;
      all.sort(function (a, b) { return a.getElementsByTagName('*').length - b.getElementsByTagName('*').length; });
      var r = all[0].getBoundingClientRect();
      return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)};
    };
    window.__rectBySel = function (sel) {
      var els = Array.prototype.slice.call(document.querySelectorAll(sel))
        .filter(function (e) { return e.getClientRects().length > 0; });
      if (!els.length) return null;
      var r = els[0].getBoundingClientRect();
      return {x: Math.round(r.left + r.width / 2), y: Math.round(r.top + r.height / 2)};
    };
    window.__inputState = function () {
      var i = document.querySelector('input[type=file]');
      return i ? ('files=' + i.files.length) : 'gone';
    };
    if (!window.__origInputClick) {
      window.__origInputClick = HTMLInputElement.prototype.click;
      HTMLInputElement.prototype.click = function () {
        if (this.type === 'file' && /sb/i.test(this.accept || '')) {
          var input = this;
          var bin = atob(window.__sb3b64);
          var arr = new Uint8Array(bin.length);
          for (var i = 0; i < bin.length; i++) arr[i] = bin.charCodeAt(i);
          var dt = new DataTransfer();
          dt.items.add(new File([arr], 'star-game.sb3', {type: 'application/zip'}));
          input.files = dt.files;
          window.__fileInjected = true;
          input.dispatchEvent(new Event('change', {bubbles: true}));
          return;
        }
        return window.__origInputClick.apply(this, arguments);
      };
    }
    true;
  `);

  // phase 2: File menu
  let fileOpened = false;
  for (let i = 0; i < 30 && !fileOpened; i++) {
    const rect = await ev("window.__rectByText('File')").catch(() => null);
    if (rect) {
      await trustedClick(rect);
      await sleep(600);
      const uploadRect = await ev("window.__rectByText('Load from your computer')").catch(() => null);
      if (uploadRect) fileOpened = true;
    }
    if (!fileOpened) await sleep(500);
  }
  if (!fileOpened) {
    const texts = await ev(
      "[...document.querySelectorAll('*')].filter(e=>e.getClientRects().length>0&&e.children.length<=3).map(e=>e.textContent.trim()).filter(t=>t&&t.length<30).filter((v,i,a)=>a.indexOf(v)===i).slice(0,60).join('|')"
    ).catch(() => "?");
    finish(1, `[+${elapsed()}s] could not open File menu. visible: ${texts}`);
  }
  console.log(`[+${elapsed()}s] File menu opened`);

  // phase 3: load from computer
  const uploadRect = await ev("window.__rectByText('Load from your computer')");
  if (!uploadRect) {
    finish(1, `[+${elapsed()}s] no 'Load from your computer' item`);
  }
  await trustedClick(uploadRect);
  let injected = false;
  for (let i = 0; i < 20; i++) {
    if (await ev("window.__fileInjected === true").catch(() => false)) {
      injected = true;
      break;
    }
    await sleep(250);
  }
  if (!injected) {
    const s = await ev("window.__inputState()").catch(() => "?");
    finish(1, `[+${elapsed()}s] file injection never happened (input: ${s})`);
  }
  console.log(`[+${elapsed()}s] sb3 injected`);

  // phase 4: wait for OUR sprites (BgStar) — crash during load reported here
  let loaded = false;
  while (Date.now() - t0 < timeoutMs) {
    if (errors.length) {
      finish(1, `[+${elapsed()}s] CRASH during load:\n` + errors.join("\n---\n"));
    }
    const body = (await ev("document.body.innerText").catch(() => "")) || "";
    if (/Oops! Something went wrong/.test(body)) {
      finish(1, `[+${elapsed()}s] Oops screen during load`);
    }
    if (/BgStar/.test(body)) {
      loaded = true;
      break;
    }
    await sleep(500);
  }
  if (!loaded) {
    const body = await ev("document.body.innerText.slice(0,600)").catch(() => "?");
    finish(1, `[+${elapsed()}s] project never appeared. body:\n${body}`);
  }
  console.log(`[+${elapsed()}s] PROJECT LOADED (BgStar visible)`);
  await sleep(1500);

  // phase 5: green flag
  let flagRect = null;
  for (const sel of [
    'button[class*="green-flag"]',
    'button[class*="greenflag"]',
    'button[title="Go"]',
    'button[aria-label="Go"]',
    '[class*="green-flag"]',
  ]) {
    flagRect = await ev(`window.__rectBySel(${JSON.stringify(sel)})`).catch(() => null);
    if (flagRect) break;
  }
  if (!flagRect) {
    const buttons = await ev(
      "[...document.querySelectorAll('button')].map(e=>(e.title||e.getAttribute('aria-label')||e.className).slice(0,50)).join('; ')"
    ).catch(() => "?");
    finish(1, `[+${elapsed()}s] green flag not found. buttons: ${buttons}`);
  }
  await trustedClick(flagRect);
  console.log(`[+${elapsed()}s] green flag clicked`);
  await ev("document.title = 'RUNNING'");

  // phase 6: run — watch for Oops / Monitors errors
  const runStart = Date.now();
  while ((Date.now() - runStart) / 1000 < RUN_SEC) {
    await sleep(1000);
    if (errors.length) {
      finish(1, `[+${elapsed()}s] CRASH after green flag:\n` + errors.join("\n---\n"));
    }
    const body = (await ev("document.body.innerText").catch(() => "")) || "";
    if (/Oops! Something went wrong/.test(body)) {
      finish(1, `[+${elapsed()}s] Oops screen after green flag`);
    }
  }

  finish(
    0,
    `ONLINE SMOKE OK: ${RUN_SEC}s after green flag, no crash, no Monitors errors\n` +
      `file: ${SB3}`
  );
}

main().catch((err) => finish(1, `error: ${err.message}`));
