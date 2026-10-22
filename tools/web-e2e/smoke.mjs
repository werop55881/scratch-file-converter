// Headless proof that the browser path works: Pyodide (wasm) + our wheel +
// a real .sb3 -> play html + zip, no native dependencies.
//
//   npm install
//   npm run smoke -- <wheel> <file.sb3>
import { readFileSync } from "node:fs";
import { loadPyodide } from "pyodide";

const [, , wheelPath, sb3Path] = process.argv;
if (!wheelPath || !sb3Path) {
  console.error("usage: node smoke.mjs <wheel> <file.sb3>");
  process.exit(2);
}

const t0 = Date.now();
const py = await loadPyodide();
console.log(
  `pyodide ready in ${((Date.now() - t0) / 1000).toFixed(1)}s (python ${py.runPython("import sys; sys.version.split()[0]")})`,
);

py.FS.writeFile("/tmp/sb3conv-web.whl", new Uint8Array(readFileSync(wheelPath)));
py.runPython(`
import sys
import zipfile
from pathlib import Path
target = Path("/tmp/sb3conv-wheel")
target.mkdir(parents=True, exist_ok=True)
zipfile.ZipFile("/tmp/sb3conv-web.whl").extractall(target)
sys.path.insert(0, str(target))
from sb3conv.web import web_run_job
print("wheel installed, sb3conv.web imported")
`);

py.globals.set("upload_bytes", new Uint8Array(readFileSync(sb3Path)));
py.globals.set(
  "upload_job",
  JSON.stringify({ lang: "javascript", scale: 2, fps: 30, name: "fighting-game" }),
);

const t1 = Date.now();
const proxy = await py.runPythonAsync("web_run_job(upload_bytes, upload_job)");
const result = proxy.toJs({ dict_converter: Object.fromEntries });
proxy.destroy();
console.log(`converted in ${((Date.now() - t1) / 1000).toFixed(1)}s`);

const names = Object.keys(result.files);
console.log(`files: ${names.length}`);
console.log(`zip: ${result.zip.byteLength} bytes`);
console.log(`html: ${result.html ? `${result.html.byteLength} bytes` : "MISSING"}`);

const problems = [];
if (!result.html) problems.push("no play html");
else {
  const html = new TextDecoder().decode(result.html);
  if (!html.includes("window.__SB3_ASSETS")) problems.push("assets not inlined");
  if (html.includes("<script src=")) problems.push("html not self-contained");
}
if (!names.includes("original.sb3")) problems.push("original.sb3 not embedded");
if (result.zip.byteLength < 1000) problems.push("zip suspiciously small");
for (const w of result.log) console.log(`log: ${w}`);
for (const w of result.warnings) console.log(`warning: ${w}`);

// second job: the lua target must convert in the browser too (.love = pure zip)
py.globals.set(
  "upload_job",
  JSON.stringify({ lang: "lua", scale: 2, fps: 30, name: "fighting-game" }),
);
const luaProxy = await py.runPythonAsync("web_run_job(upload_bytes, upload_job)");
const luaResult = luaProxy.toJs({ dict_converter: Object.fromEntries });
luaProxy.destroy();
const luaNames = Object.keys(luaResult.files);
console.log(
  `lua: ${luaNames.length} files, zip ${luaResult.zip.byteLength} bytes, ` +
    `html ${luaResult.html ? "yes" : "no"}`,
);
if (!luaNames.includes("main.lua")) problems.push("lua target: no main.lua");
if (!luaNames.includes("manifest.lua")) problems.push("lua target: no manifest.lua");
if (!luaNames.some((name) => name.endsWith(".love"))) problems.push("lua target: no .love");
if (luaResult.html) problems.push("lua target: unexpected play html");
if (luaResult.zip.byteLength < 1000) problems.push("lua zip suspiciously small");
for (const w of luaResult.log) console.log(`lua log: ${w}`);
for (const w of luaResult.warnings) console.log(`lua warning: ${w}`);

// third job: the godot target must convert in the browser too (project
// folder straight into a .zip - no build step, no toolchain)
py.globals.set(
  "upload_job",
  JSON.stringify({ lang: "godot", scale: 2, fps: 30, name: "fighting-game" }),
);
const godotProxy = await py.runPythonAsync("web_run_job(upload_bytes, upload_job)");
const godotResult = godotProxy.toJs({ dict_converter: Object.fromEntries });
godotProxy.destroy();
const godotNames = Object.keys(godotResult.files);
console.log(
  `godot: ${godotNames.length} files, zip ${godotResult.zip.byteLength} bytes, ` +
    `html ${godotResult.html ? "yes" : "no"}`,
);
if (!godotNames.includes("project.godot")) problems.push("godot target: no project.godot");
if (!godotNames.includes("main.tscn")) problems.push("godot target: no main.tscn");
if (!godotNames.includes("runtime.gd")) problems.push("godot target: no runtime.gd");
if (!godotNames.includes("scripts.gd")) problems.push("godot target: no scripts.gd");
if (godotResult.html) problems.push("godot target: unexpected play html");
if (godotResult.zip.byteLength < 1000) problems.push("godot zip suspiciously small");
for (const w of godotResult.log) console.log(`godot log: ${w}`);
for (const w of godotResult.warnings) console.log(`godot warning: ${w}`);

if (problems.length) {
  console.error(`FAIL: ${problems.join("; ")}`);
  process.exit(1);
}
console.log("PYODIDE E2E OK");
