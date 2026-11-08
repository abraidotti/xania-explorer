// The explorer's Web Worker: loads the self-hosted Pyodide and the xania_explorer wheel, then analyses the
// checkouts the page sends it. Runs off the main thread so the page stays responsive during a run.
//
// Messages in:  {type: "init", base}  then  {type: "run", id, sides: [{repo, branch, commit, files: {path: bytes}}]}
// Messages out: {type: "progress", text}, {type: "ready", ms}, {type: "result", id, result}, {type: "error", id, message}
let py = null;
let explore = null;
let runCount = 0;

function post(msg) { self.postMessage(msg); }

async function init(base, version) {
  const t0 = performance.now();
  post({ type: "progress", stage: "runtime", text: "Starting Python (first visit downloads ~5 MB, then it's cached)" });
  const { loadPyodide } = await import(new URL("runtime/pyodide/pyodide.mjs", base).href);
  py = await loadPyodide({ indexURL: new URL("runtime/pyodide/", base).href });
  const index = await (await fetch(new URL("runtime/wheels/index.json", base))).json();
  if (version && index.code && index.code !== version) {
    throw new Error(`the explorer runtime (${index.code}) doesn't match this site build (${version}); ` +
                    "rebuild it with `python -m xania_explorer bundle`");
  }
  const sitePackages = py.runPython("import site; site.getsitepackages()[0]");
  post({ type: "progress", stage: "runtime", text: "Installing Xania Explorer" });
  for (const name of index.wheels) {
    const r = await fetch(new URL("runtime/wheels/" + name, base));
    if (!r.ok) throw new Error(`couldn't download ${name} (HTTP ${r.status})`);
    py.unpackArchive(new Uint8Array(await r.arrayBuffer()), "wheel", { extractDir: sitePackages });
  }
  explore = py.pyimport("xania_explorer.explore");
  post({ type: "ready", ms: Math.round(performance.now() - t0) });
}

function run(id, sides) {
  runCount += 1;
  const roots = sides.map((side, i) => {
    const root = `/xania/run${runCount}/side${i + 1}`;
    for (const [path, bytes] of Object.entries(side.files)) {
      const dir = (root + "/" + path).split("/").slice(0, -1).join("/");
      py.FS.mkdirTree(dir);
      py.FS.writeFile(`${root}/${path}`, new Uint8Array(bytes));
    }
    explore.write_identity(root, side.repo, side.branch, side.commit);
    return { root };
  });
  const progress = (text) => post({ type: "progress", stage: "analysis", text });
  const result = JSON.parse(explore.run_json(JSON.stringify(roots), progress));
  // free the virtual files: a later run starts clean
  py.runPython(`import shutil; shutil.rmtree("/xania/run${runCount}", ignore_errors=True)`);
  post({ type: "result", id, result });
}

self.onmessage = async (event) => {
  const msg = event.data;
  try {
    if (msg.type === "init") await init(msg.base, msg.version);
    else if (msg.type === "run") run(msg.id, msg.sides);
  } catch (err) {
    post({ type: "error", id: msg.id, stage: msg.type === "init" ? "runtime" : "analysis",
           message: String(err && err.message || err) });
  }
};
