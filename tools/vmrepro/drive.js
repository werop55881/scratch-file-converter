// Serve this directory over HTTP, drive headless Chrome to repro.html via CDP,
// poll document.title for SMOKE OK / JSERROR.
// usage: node drive.js ["hashArgs"] [timeoutSec]
//   e.g. node drive.js "45"            -> run 45s, no clicks
//        node drive.js "45,0,0,5"      -> run 45s, click (0,0) at t=5s
"use strict";
const { spawn } = require("child_process");
const fs = require("fs");
const http = require("http");
const os = require("os");
const path = require("path");

const CHROME =
  process.env.CHROME ||
  "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const HASH = process.argv[2] || "45";
const timeoutMs = Number(process.argv[3] || 150) * 1000;
const HERE = __dirname;

const MIME = {
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".map": "application/json",
  ".json": "application/json",
  ".css": "text/css",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".sb3": "application/zip",
  ".wav": "audio/wav",
};

function startServer() {
  return new Promise((resolve, reject) => {
    let port = 8100 + Math.floor(Math.random() * 400);
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split("?")[0].split("#")[0]);
      const rel = urlPath === "/" ? "repro.html" : urlPath.replace(/^\/+/, "");
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
const profile = fs.mkdtempSync(path.join(os.tmpdir(), "repro-chrome-"));
let chrome = null;
let ws = null;
let serverRef = null;
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
      const res = await fetch(`http://127.0.0.1:${cdpPort}/json/list`);
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
    }
  });

  await send("Page.enable");
  await send("Runtime.enable");
  const target = `http://127.0.0.1:${port}/repro.html#${HASH}`;
  console.log("navigating:", target);
  await send("Page.navigate", { url: target });

  const start = Date.now();
  let lastTitle = "";
  while (Date.now() - start < timeoutMs) {
    await new Promise((r) => setTimeout(r, 500));
    let title = "";
    try {
      const res = await send("Runtime.evaluate", {
        expression: "document.title",
        returnByValue: true,
      });
      title = String((res.result && res.result.value) || "");
    } catch {
      continue; // page may still be navigating
    }
    if (title && title !== lastTitle) {
      console.log(`[+${((Date.now() - start) / 1000).toFixed(1)}s] title: ${title}`);
      lastTitle = title;
    }
    if (title.includes("SMOKE OK")) {
      // grab the log too
      let logText = "";
      try {
        const res = await send("Runtime.evaluate", {
          expression: "document.getElementById('log').textContent",
          returnByValue: true,
        });
        logText = String((res.result && res.result.value) || "");
      } catch {}
      finish(0, `BROWSER SMOKE OK: ${title}\n--- page log ---\n${logText}`);
    }
    if (title.includes("JSERROR")) {
      let logText = "";
      try {
        const res = await send("Runtime.evaluate", {
          expression: "document.getElementById('log').textContent",
          returnByValue: true,
        });
        logText = String((res.result && res.result.value) || "");
      } catch {}
      finish(1, `BROWSER JS ERROR: ${title}\n--- page log ---\n${logText}`);
    }
  }
  finish(1, "timed out waiting for SMOKE OK / JSERROR marker");
}

main().catch((err) => finish(1, `error: ${err.message}`));
