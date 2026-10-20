// Pyodide runs the converter inside this Web Worker so the page stays
// responsive during conversion. The wheel is served next to this file
// (built by CI into vendor/sb3conv-web.whl).

const PYODIDE_VERSION = "314.0.7";
const PYODIDE_INDEX = `https://cdn.jsdelivr.net/pyodide/v${PYODIDE_VERSION}/full/`;

let bootPromise = null;

function stage(text) {
  postMessage({ type: "stage", text });
}

function boot() {
  if (bootPromise === null) {
    bootPromise = (async () => {
      stage("Fetching the Python runtime (one-time ~10 MB)...");
      const { loadPyodide } = await import(`${PYODIDE_INDEX}pyodide.mjs`);
      const py = await loadPyodide({ indexURL: PYODIDE_INDEX });
      stage("Unpacking the converter...");
      const wheelUrl = new URL("./vendor/sb3conv-web.whl", import.meta.url).href;
      const response = await fetch(wheelUrl);
      if (!response.ok) {
        throw new Error(`converter wheel missing (HTTP ${response.status})`);
      }
      py.FS.writeFile("/tmp/sb3conv-web.whl", new Uint8Array(await response.arrayBuffer()));
      py.runPython(`
import sys
import zipfile
from pathlib import Path

_target = Path("/tmp/sb3conv-wheel")
_target.mkdir(parents=True, exist_ok=True)
zipfile.ZipFile("/tmp/sb3conv-web.whl").extractall(_target)
sys.path.insert(0, str(_target))
from sb3conv.web import web_run_job
`);
      return py;
    })().catch((error) => {
      bootPromise = null;
      throw error;
    });
  }
  return bootPromise;
}

function friendly(error) {
  const message = String((error && error.message) || error);
  const lines = message.split("\n").filter((line) => line.trim());
  for (let i = lines.length - 1; i >= 0; i -= 1) {
    if (/Error:|Exception/.test(lines[i])) {
      return lines[i].trim().slice(0, 400);
    }
  }
  return (lines[lines.length - 1] || message).slice(0, 400);
}

async function convert(bytes, job) {
  const py = await boot();
  stage("Converting...");
  py.globals.set("upload_bytes", bytes);
  py.globals.set("upload_job", JSON.stringify(job));
  try {
    const proxy = await py.runPythonAsync("web_run_job(upload_bytes, upload_job)");
    const result = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();
    return result;
  } finally {
    py.globals.delete("upload_bytes");
    py.globals.delete("upload_job");
  }
}

self.onmessage = async (event) => {
  const { id, bytes, job } = event.data;
  try {
    const result = await convert(bytes, job);
    const transfer = [result.zip.buffer];
    if (result.html) {
      transfer.push(result.html.buffer);
    }
    for (const view of Object.values(result.files)) {
      transfer.push(view.buffer);
    }
    postMessage(
      {
        type: "done",
        id,
        zip: result.zip,
        html: result.html || null,
        files: result.files,
        name: result.name,
        entrypoint: result.entrypoint,
        log: [...result.log],
        warnings: [...result.warnings],
      },
      transfer,
    );
  } catch (error) {
    postMessage({ type: "error", id, message: friendly(error) });
  }
};
