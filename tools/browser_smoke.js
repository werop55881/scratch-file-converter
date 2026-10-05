// Drive a live headless Chrome via CDP and wait for the runtime's smoke marker.
// usage: node browser_smoke.js <index.html url> [timeoutSec]
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const os = require("os");
const path = require("path");

const CHROME =
  process.env.CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const targetUrl = process.argv[2];
const timeoutMs = Number(process.argv[3] || 20) * 1000;
if (!targetUrl) {
  console.error("usage: node browser_smoke.js <url> [timeoutSec]");
  process.exit(2);
}

const port = 9333 + Math.floor(Math.random() * 500);
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "sb3-chrome-"));
const chrome = spawn(
  CHROME,
  [
    "--headless=new",
    "--disable-gpu",
    "--no-first-run",
    "--no-default-browser-check",
    "--autoplay-policy=no-user-gesture-required",
    `--remote-debugging-port=${port}`,
    `--user-data-dir=${profile}`,
    "about:blank",
  ],
  { stdio: "ignore" }
);

let ws = null;
let nextId = 1;
const pending = new Map();

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
      const res = await fetch(`http://127.0.0.1:${port}/json/list`);
      const targets = await res.json();
      const page = targets.find((t) => t.type === "page" && t.webSocketDebuggerUrl);
      if (page) return page.webSocketDebuggerUrl;
    } catch {
      // chrome not up yet
    }
    await new Promise((r) => setTimeout(r, 200));
  }
  throw new Error("chrome devtools endpoint never came up");
}

function finish(code, message) {
  console.log(message);
  try {
    if (ws) ws.close();
  } catch {}
  chrome.kill();
  try {
    fs.rmSync(profile, { recursive: true, force: true });
  } catch {}
  process.exit(code);
}

async function main() {
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
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  await send("Page.navigate", { url: targetUrl });

  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, 500));
    let title = "";
    try {
      const res = await send("Runtime.evaluate", {
        expression: "document.title",
        returnByValue: true,
      });
      title = String((res.result && res.result.value) || "");
    } catch (err) {
      continue; // page may still be navigating
    }
    if (title.includes("SMOKE OK")) {
      finish(0, `BROWSER SMOKE OK: ${title}`);
    }
    if (title.includes("JSERROR")) {
      finish(1, `BROWSER JS ERROR: ${title}`);
    }
  }
  finish(1, "browser smoke timed out waiting for the SMOKE OK marker");
}

main().catch((err) => finish(1, `error: ${err.message}`));
