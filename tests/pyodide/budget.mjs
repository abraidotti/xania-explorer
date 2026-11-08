// Runs the explorer under Pyodide in Node, exactly as the browser does, and enforces the budget.
//
//   node tests/pyodide/budget.mjs --pyodide DIR --wheels DIR --xania DIR [--xania DIR] [--seconds 60]
//                                 [--max-wheel-kb 1024] [--dump FILE]
//
// --pyodide: the pyodide npm package directory; --wheels: xania_explorer + markdown + pymdown wheels;
// --xania: one or two Xania checkouts (two = a comparison). --dump writes the generated Markdown pages as
// JSON, to compare with the CPython output for the same checkout.
import { readFileSync, readdirSync, statSync, writeFileSync } from "node:fs";
import { dirname, join, relative, resolve, sep } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { execFileSync } from "node:child_process";

const args = { xania: [] };
for (let i = 2; i < process.argv.length; i += 2) {
  const key = process.argv[i].replace(/^--/, "");
  if (key === "xania") args.xania.push(process.argv[i + 1]);
  else args[key] = process.argv[i + 1];
}
const seconds = Number(args.seconds || 60);
const maxWheelKb = Number(args["max-wheel-kb"] || 1024);

const wheels = readdirSync(args.wheels).filter((f) => f.endsWith(".whl"));
const own = wheels.find((f) => f.startsWith("xania_explorer-"));
if (!own) throw new Error(`no xania_explorer wheel in ${args.wheels}`);
const ownKb = statSync(join(args.wheels, own)).size / 1024;

function tree(root) {
  const out = [];
  (function walk(dir) {
    for (const name of readdirSync(dir)) {
      if (name === ".git" || name === "node_modules") continue;
      const p = join(dir, name);
      const st = statSync(p);
      if (st.isDirectory()) walk(p);
      else out.push({ path: relative(root, p).split(sep).join("/"), type: "blob", size: st.size });
    }
  })(root);
  return out;
}

function identity(root) {
  const git = (...a) => {
    try { return execFileSync("git", ["-C", root, ...a], { encoding: "utf8" }).trim(); } catch { return ""; }
  };
  const remote = git("remote", "get-url", "origin").replace(/^git@github\.com:/, "https://github.com/");
  return {
    repo: remote.replace(/^https:\/\/github\.com\//, "").replace(/\.git$/, "") || "local/xania",
    branch: git("rev-parse", "--abbrev-ref", "HEAD") || "main",
    commit: git("rev-parse", "HEAD") || "0000000",
  };
}

const t0 = performance.now();
const pyodideDir = resolve(args.pyodide);
const { loadPyodide } = await import(pathToFileURL(join(pyodideDir, "pyodide.mjs")).href);
const py = await loadPyodide({ indexURL: pyodideDir + sep });
const sitePackages = py.runPython("import site; site.getsitepackages()[0]");
for (const w of wheels) py.unpackArchive(new Uint8Array(readFileSync(join(args.wheels, w))), "wheel", { extractDir: sitePackages });
const tBoot = performance.now();

const X = py.pyimport("xania_explorer.explore");
// The browser plans downloads in JS (explore-plan.js) before Python loads; it must agree with plan().
await import(pathToFileURL(join(dirname(fileURLToPath(import.meta.url)), "../../docs/javascripts/explore-plan.js")).href);
const manifest = JSON.parse(py.runPython("import json; from xania_explorer.explore import manifest; json.dumps(manifest())"));
const failures = [];
const sides = [];
let downloadedBytes = 0;
args.xania.forEach((root, i) => {
  const id = identity(root);
  const plan = X.plan(py.toPy(tree(root)), id.repo);
  if (!plan.ok) throw new Error(plan.error);
  if (plan.warning) console.warn(plan.warning);
  const jsPlan = globalThis.XaniaPlan.plan(tree(root), manifest, id.repo);
  if (JSON.stringify(jsPlan.files) !== JSON.stringify(plan.files.toJs()) || jsPlan.warning !== plan.warning) {
    failures.push(`explore-plan.js disagrees with plan() for ${root}`);
  }
  const dest = `/xania/side${i + 1}`;
  for (const f of plan.files.toJs()) {
    const data = new Uint8Array(readFileSync(join(root, f)));
    downloadedBytes += data.length;
    py.FS.mkdirTree(dest + "/" + f.split("/").slice(0, -1).join("/"));
    py.FS.writeFile(`${dest}/${f}`, data);
  }
  X.write_identity(py.toPy(dest), id.repo, id.branch, id.commit);
  sides.push({ root: dest });
});
const tFiles = performance.now();

const progress = [];
const result = JSON.parse(X.run_json(JSON.stringify(sides), (msg) => progress.push(msg)));
const tRun = performance.now();

if (args.dump) {
  const md = X.run(py.toPy(sides)).toJs({ dict_converter: Object.fromEntries });
  writeFileSync(args.dump, JSON.stringify(md.pages));
}

const s = (a, b) => ((b - a) / 1000).toFixed(1);
const summary = {
  boot_s: s(t0, tBoot), files_s: s(tBoot, tFiles), analysis_s: s(tFiles, tRun), total_s: s(t0, tRun),
  pages: Object.keys(result.pages).length, html_mb: (JSON.stringify(result.pages).length / 1e6).toFixed(2),
  downloaded_mb: (downloadedBytes / 1e6).toFixed(2), wheel_kb: ownKb.toFixed(0), progress_steps: progress.length,
  names: result.names,
};
console.log(JSON.stringify(summary, null, 2));
if ((tRun - tFiles) / 1000 > seconds) failures.push(`analysis took ${summary.analysis_s}s (budget ${seconds}s)`);
if (ownKb > maxWheelKb) failures.push(`wheel is ${summary.wheel_kb} KB (budget ${maxWheelKb} KB)`);
if (failures.length) {
  console.error("BUDGET EXCEEDED: " + failures.join("; "));
  process.exit(1);
}
