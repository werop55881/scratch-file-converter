// Open a converted single-file .html in headless Chrome over file://, collect
// console errors/exceptions, check the stage canvas is present and NOT
// security-tainted (toDataURL would throw), then save a screenshot.
// usage: node drive_singlefile.js <path/to/game.html> [waitSeconds] [shotPath]
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const CHROME =
  process.env.CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const target = process.argv[2];
const waitMs = (Number(process.argv[3] || 8)) * 1000;
const shotPath = process.argv[4] || path.join(__dirname, "..", "..", "build", "singlefile.png");
if (!target) {
  console.error("usage: node drive_singlefile.js <html> [waitSec] [shotPath]");
  process.exit(2);
}

const cdpPort = 9600 + Math.floor(Math.random() * 300);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "sf-chrome-"));
let chrome = null;
let ws = null;
let nextId = 1;
const pending = new Map();
const errors = [];

function send(method, params = {}) {
  return new Promise((resolve, reject) => {
    const id = nextId++;
    pending.set(id, { resolve, reject });
    ws.send(JSON.stringify({ id, method, params }));
  });
}

async function connect() {
  for (let i = 0; i < 100; i++) {
    try {
      const res = await fetch(`http://127.0.0.1:${cdpPort}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {}
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("chrome devtools endpoint never came up");
}

function finish(code, message) {
  console.log(message);
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
  const url = "file:///" + path.resolve(target).replace(/\\/g, "/").replace(/ /g, "%20");
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
    if (msg.method === "Runtime.exceptionThrown") {
      const d = msg.params.exceptionDetails;
      errors.push(`exception: ${d.text} ${d.exception ? d.exception.description || d.exception.value || "" : ""}`);
    }
    if (msg.method === "Runtime.consoleAPICalled" && msg.params.type === "error") {
      errors.push(
        "console.error: " +
          msg.params.args.map((a) => a.value ?? a.description ?? "").join(" ")
      );
    }
    if (msg.method === "Log.entryAdded" && msg.params.entry.level === "error") {
      errors.push(`log: ${msg.params.entry.text}`);
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Log.enable");
  console.log("navigating:", url);
  await send("Page.navigate", { url });
  await new Promise((r) => setTimeout(r, waitMs));

  const probe = await send("Runtime.evaluate", {
    expression: `(function () {
      const canvas = document.querySelector("canvas");
      const out = {
        title: document.title,
        hasCanvas: !!canvas,
        hasAssetMap: !!window.__SB3_ASSETS,
        assetCount: window.__SB3_ASSETS ? Object.keys(window.__SB3_ASSETS).length : 0,
      };
      if (canvas) {
        out.canvasSize = canvas.width + "x" + canvas.height;
        try {
          out.tainted = false;
          out.dataUrlHead = canvas.toDataURL("image/png").slice(0, 30);
        } catch (e) {
          out.tainted = true;
          out.taintError = String(e);
        }
      }
      return out;
    })()`,
    returnByValue: true,
  });
  const info = (probe && probe.result && probe.result.value) || {};

  const shot = await send("Page.captureScreenshot", { format: "png" });
  fs.mkdirSync(path.dirname(shotPath), { recursive: true });
  fs.writeFileSync(shotPath, Buffer.from(shot.data, "base64"));

  const report = JSON.stringify({ ...info, errors }, null, 2);
  const ok =
    info.hasCanvas &&
    info.hasAssetMap &&
    info.assetCount > 0 &&
    info.tainted === false &&
    errors.length === 0;
  finish(ok ? 0 : 1, `${ok ? "SINGLEFILE OK" : "SINGLEFILE FAIL"}\n${report}\nscreenshot: ${shotPath}`);
}

main().catch((err) => finish(1, `error: ${err.message}`));
