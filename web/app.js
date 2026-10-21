// UI glue: pick a file, run the worker, show play + downloads.

const $ = (id) => document.getElementById(id);

const els = {
  dropzone: $("dropzone"),
  fileInput: $("file-input"),
  fileChip: $("file-chip"),
  fileName: $("file-name"),
  fileSize: $("file-size"),
  fileClear: $("file-clear"),
  scale: $("scale"),
  fps: $("fps"),
  convert: $("convert-btn"),
  cancel: $("cancel-btn"),
  elapsed: $("elapsed"),
  log: $("log"),
  result: $("result"),
  playCard: $("play-card"),
  frame: $("play-frame"),
  zipLink: $("zip-link"),
  htmlLink: $("html-link"),
  again: $("again-btn"),
  zipNote: $("zip-note"),
  fileList: $("file-list"),
};

let worker = null;
let jobId = 0;
let activeJob = null;
let currentFile = null;
let startedAt = 0;
let ticker = null;
let zipUrl = null;
let htmlUrl = null;
let fileUrls = [];

const MIME = new Map([
  ["png", "image/png"],
  ["svg", "image/svg+xml"],
  ["jpg", "image/jpeg"],
  ["jpeg", "image/jpeg"],
  ["wav", "audio/wav"],
  ["html", "text/html"],
  ["js", "text/javascript"],
  ["json", "application/json"],
  ["py", "text/x-python"],
  ["c", "text/x-c"],
  ["h", "text/x-c"],
  ["ts", "text/x-typescript"],
  ["lua", "text/x-lua"],
  ["love", "application/zip"],
]);

function mimeFor(name) {
  const dot = name.lastIndexOf(".");
  const ext = dot === -1 ? "" : name.slice(dot + 1).toLowerCase();
  return MIME.get(ext) || "application/octet-stream";
}

function log(text, kind = "") {
  const line = document.createElement("div");
  if (kind) line.className = kind;
  line.textContent = text;
  els.log.appendChild(line);
  els.log.scrollTop = els.log.scrollHeight;
}

function humanSize(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function setFile(file) {
  currentFile = file;
  const ready = Boolean(file);
  els.fileChip.hidden = !ready;
  els.dropzone.classList.toggle("has-file", ready);
  els.convert.disabled = !ready;
  if (ready) {
    els.fileName.textContent = file.name;
    els.fileSize.textContent = humanSize(file.size);
    els.fileInput.value = "";
    if (!/\.sb3$/i.test(file.name)) {
      log(`warning: ${file.name} does not end in .sb3 - trying anyway`, "warn");
    }
  }
}

function selectedLang() {
  return document.querySelector("input[name=lang]:checked").value;
}

function startTicker() {
  startedAt = performance.now();
  stopTicker();
  ticker = setInterval(() => {
    els.elapsed.textContent = `${((performance.now() - startedAt) / 1000).toFixed(0)}s`;
  }, 1000);
}

function stopTicker() {
  if (ticker !== null) clearInterval(ticker);
  ticker = null;
  els.elapsed.textContent = "";
}

function revokeUrls() {
  if (zipUrl) URL.revokeObjectURL(zipUrl);
  if (htmlUrl) URL.revokeObjectURL(htmlUrl);
  for (const url of fileUrls) URL.revokeObjectURL(url);
  zipUrl = null;
  htmlUrl = null;
  fileUrls = [];
}

function resetResult() {
  revokeUrls();
  els.result.hidden = true;
  els.playCard.hidden = true;
  els.frame.removeAttribute("src");
  els.htmlLink.hidden = true;
  els.fileList.replaceChildren();
}

function showResult(message) {
  const fileEntries = Object.entries(message.files || {});
  const zipSize = message.zip.byteLength;
  log(`converted -> ${fileEntries.length} files, zip ${humanSize(zipSize)}`, "ok");
  for (const line of message.log || []) log(line);
  for (const warning of message.warnings) log(`warning: ${warning}`, "warn");

  revokeUrls();
  zipUrl = URL.createObjectURL(new Blob([message.zip], { type: "application/zip" }));
  els.zipLink.href = zipUrl;
  els.zipLink.download = `${message.name}.zip`;
  els.zipNote.textContent =
    "The zip contains original.sb3 - convert it back with sb3conv pack (round trip).";

  if (message.html) {
    htmlUrl = URL.createObjectURL(new Blob([message.html], { type: "text/html" }));
    els.frame.src = htmlUrl;
    els.htmlLink.href = htmlUrl;
    els.htmlLink.download = `${message.name}.html`;
    els.htmlLink.hidden = false;
    els.playCard.hidden = false;
  }

  els.fileList.replaceChildren();
  for (const [name, view] of fileEntries) {
    const item = document.createElement("li");
    const link = document.createElement("a");
    link.textContent = name;
    link.href = URL.createObjectURL(new Blob([view], { type: mimeFor(name) }));
    link.download = name;
    fileUrls.push(link.href);
    const meta = document.createElement("span");
    meta.className = "muted";
    meta.textContent = humanSize(view.byteLength);
    item.append(link, meta);
    els.fileList.appendChild(item);
  }
  els.result.hidden = false;
  els.result.scrollIntoView({ behavior: "smooth", block: "start" });
}

function setRunning(running) {
  els.convert.disabled = running || !currentFile;
  els.cancel.hidden = !running;
  if (running) startTicker();
  else stopTicker();
}

function stopWorker() {
  if (worker) worker.terminate();
  worker = null;
}

async function run() {
  if (!currentFile) return;
  resetResult();
  const id = ++jobId;
  const job = {
    lang: selectedLang(),
    scale: Number(els.scale.value) || 2,
    fps: Number(els.fps.value) || 30,
    name: currentFile.name.replace(/\.sb3$/i, "") || "project",
  };
  activeJob = id;
  setRunning(true);
  log(`converting ${currentFile.name} for ${job.lang}...`);

  stopWorker();
  worker = new Worker("./worker.js", { type: "module" });
  worker.onmessage = (event) => {
    const message = event.data;
    if (message.id !== undefined && message.id !== id) return;
    if (message.type === "stage") {
      log(message.text);
    } else if (message.type === "done") {
      activeJob = null;
      setRunning(false);
      showResult(message);
      log("done.", "ok");
    } else if (message.type === "error") {
      activeJob = null;
      setRunning(false);
      log(`error: ${message.message}`, "err");
    }
  };
  worker.onerror = (event) => {
    activeJob = null;
    setRunning(false);
    log(`error: ${event.message || "worker failed"}`, "err");
  };

  const bytes = new Uint8Array(await currentFile.arrayBuffer());
  worker.postMessage({ id, bytes, job }, [bytes.buffer]);
}

// --- wiring -------------------------------------------------------------

els.dropzone.addEventListener("click", () => els.fileInput.click());
els.dropzone.addEventListener("keydown", (event) => {
  if (event.key === "Enter" || event.key === " ") {
    event.preventDefault();
    els.fileInput.click();
  }
});
els.fileInput.addEventListener("change", () => {
  if (els.fileInput.files.length) setFile(els.fileInput.files[0]);
});
for (const type of ["dragenter", "dragover"]) {
  els.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    els.dropzone.classList.add("over");
  });
}
for (const type of ["dragleave", "drop"]) {
  els.dropzone.addEventListener(type, (event) => {
    event.preventDefault();
    els.dropzone.classList.remove("over");
  });
}
els.dropzone.addEventListener("drop", (event) => {
  const file = event.dataTransfer.files[0];
  if (file) setFile(file);
});
els.fileClear.addEventListener("click", () => setFile(null));
els.convert.addEventListener("click", () => {
  run().catch((error) => log(`error: ${error.message || error}`, "err"));
});
els.cancel.addEventListener("click", () => {
  if (activeJob !== null) {
    stopWorker();
    activeJob = null;
    setRunning(false);
    log("cancelled.", "warn");
  }
});
els.again.addEventListener("click", () => {
  resetResult();
  setFile(null);
  els.log.replaceChildren();
  window.scrollTo({ top: 0, behavior: "smooth" });
});
