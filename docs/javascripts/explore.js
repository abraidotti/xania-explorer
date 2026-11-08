// The live explorer (docs/explore.md): pick a base and optionally a head (repo + branch), fetch them from
// GitHub, analyse them in the browser with Pyodide (explore-worker.js), and show the same dashboards, system
// pages and comparison as the static site. Public repos only; no tokens; everything stays in the browser.
(function () {
  var CANONICAL = "mattgodbolt/xania";
  var API = "https://api.github.com";
  var RAW = "https://raw.githubusercontent.com";
  var REPO_RE = /^[A-Za-z0-9](?:[A-Za-z0-9-]{0,38})\/[A-Za-z0-9._-]{1,100}$/;
  var CONCURRENCY = 8;
  var scriptSrc = document.currentScript && document.currentScript.src;
  var SITE = scriptSrc ? new URL("../", scriptSrc).href : new URL("../", location.href).href;

  // ---------------------------------------------------------------- errors
  function XError(stage, message, side) {
    this.stage = stage; this.message = message; this.side = side;
  }

  function when(epochSeconds) {
    return new Date(epochSeconds * 1000).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
  }

  // ---------------------------------------------------------------- GitHub API (anonymous, cached briefly)
  var rate = { remaining: null, limit: null };

  async function gh(path, opts) {
    opts = opts || {};
    var key = "xe-gh:" + path;
    try {
      var hit = JSON.parse(sessionStorage.getItem(key) || "null");
      if (hit && Date.now() - hit.t < 5 * 60 * 1000) return hit.v;
    } catch (e) { /* storage unavailable: just fetch */ }
    var r;
    try {
      r = await fetch(API + path, { headers: { Accept: "application/vnd.github+json" } });
    } catch (e) {
      throw new XError("github", "Couldn't reach GitHub (network error). Check your connection and try again.", opts.side);
    }
    rate.remaining = r.headers.get("x-ratelimit-remaining");
    rate.limit = r.headers.get("x-ratelimit-limit");
    if ((r.status === 403 || r.status === 429) && rate.remaining === "0") {
      var reset = Number(r.headers.get("x-ratelimit-reset"));
      throw new XError("github", "GitHub's limit for anonymous requests (" + (rate.limit || 60) + " an hour) is " +
        "reached. Try again at " + when(reset) + ". Runs you've already done stay cached in this browser.", opts.side);
    }
    if (r.status === 404 || r.status === 422) {
      throw new XError("github", opts.notFound || ("GitHub has nothing at " + path + "."), opts.side);
    }
    if (!r.ok) throw new XError("github", "GitHub returned HTTP " + r.status + " for " + path + ".", opts.side);
    var v = await r.json();
    try { sessionStorage.setItem(key, JSON.stringify({ t: Date.now(), v: v })); } catch (e) { /* full: skip */ }
    return v;
  }

  function encRef(ref) { return ref.split("/").map(encodeURIComponent).join("/"); }

  async function listTree(repo, sha, side) {
    var t = await gh("/repos/" + repo + "/git/trees/" + sha + "?recursive=1", { side: side });
    if (!t.truncated) return t.tree;
    // Very large repos: fetch just the folders we read.
    var top = await gh("/repos/" + repo + "/git/trees/" + sha, { side: side });
    var out = top.tree.slice();
    for (var i = 0; i < top.tree.length; i++) {
      var e = top.tree[i];
      if (e.type === "tree" && (e.path === "area" || e.path === "src")) {
        var sub = await gh("/repos/" + repo + "/git/trees/" + e.sha + (e.path === "src" ? "?recursive=1" : ""), { side: side });
        sub.tree.forEach(function (x) { out.push({ path: e.path + "/" + x.path, type: x.type, size: x.size }); });
      }
    }
    return out;
  }

  // Validate and resolve one side: repo → branch → commit → file list → plan. Nothing is downloaded yet.
  async function resolveSide(input, manifest, sideName) {
    var repo = input.repo;
    if (!REPO_RE.test(repo)) {
      throw new XError("input", "Enter a repository as owner/name, e.g. " + CANONICAL + ".", sideName);
    }
    var info = await gh("/repos/" + repo, { side: sideName,
      notFound: "Repository " + repo + " wasn't found, or it's private (only public repositories can be explored)." });
    var full = info.full_name;
    var branch = input.branch || info.default_branch;
    var commit = await gh("/repos/" + full + "/commits/" + encRef(branch), { side: sideName,
      notFound: "There's no branch called “" + branch + "” in " + full + "." });
    var tree = await listTree(full, commit.sha, sideName);
    var plan = XaniaPlan.plan(tree, manifest, full);
    if (!plan.ok) throw new XError("input", plan.error, sideName);
    return { repo: full, branch: branch, commit: commit.sha, plan: plan, side: full + " @ " + branch,
             isDefault: branch === info.default_branch };
  }

  // ---------------------------------------------------------------- IndexedDB cache (files per commit, results per build)
  var dbPromise = null;
  function db() {
    if (!dbPromise) {
      dbPromise = new Promise(function (resolve) {
        try {
          var req = indexedDB.open("xania-explorer", 1);
          req.onupgradeneeded = function () { req.result.createObjectStore("cache"); };
          req.onsuccess = function () { resolve(req.result); };
          req.onerror = function () { resolve(null); };
        } catch (e) { resolve(null); }
      });
    }
    return dbPromise;
  }
  async function cacheGet(key) {
    var d = await db();
    if (!d) return null;
    return new Promise(function (resolve) {
      try {
        var req = d.transaction("cache").objectStore("cache").get(key);
        req.onsuccess = function () { resolve(req.result || null); };
        req.onerror = function () { resolve(null); };
      } catch (e) { resolve(null); }
    });
  }
  async function cachePut(key, value) {
    var d = await db();
    if (!d) return;
    try { d.transaction("cache", "readwrite").objectStore("cache").put(value, key); } catch (e) { /* quota: skip */ }
  }

  // ---------------------------------------------------------------- downloads
  async function fetchRaw(repo, sha, path) {
    var url = RAW + "/" + repo + "/" + sha + "/" + path.split("/").map(encodeURIComponent).join("/");
    for (var attempt = 1; attempt <= 3; attempt++) {
      try {
        var r = await fetch(url);
        if (r.ok) return await r.arrayBuffer();
        // 404 is retried too: raw.githubusercontent.com can lag behind a freshly pushed commit on forks
      } catch (e) { /* network: retry */ }
      await new Promise(function (ok) { setTimeout(ok, 600 * attempt); });
    }
    throw new XError("download", "Couldn't download " + path + " from " + repo + ". Check your connection and try again.");
  }

  async function download(side, onProgress) {
    var key = "files:" + side.repo + "@" + side.commit;
    var cached = await cacheGet(key);
    if (cached) { onProgress(side.plan.files.length, side.plan.files.length, true); return cached; }
    var files = {}, done = 0, queue = side.plan.files.slice();
    async function worker() {
      while (queue.length) {
        var path = queue.shift();
        files[path] = await fetchRaw(side.repo, side.commit, path);
        done += 1;
        onProgress(done, side.plan.files.length, false);
      }
    }
    var workers = [];
    for (var i = 0; i < CONCURRENCY; i++) workers.push(worker());
    await Promise.all(workers);
    await cachePut(key, files);
    return files;
  }

  // ---------------------------------------------------------------- the Pyodide worker
  var pyWorker = null, pyReady = null, pending = {}, nextId = 1, onWorkerProgress = null, manifestVersion = "";
  function startWorker() {
    if (pyReady) return pyReady;
    pyReady = new Promise(function (resolve, reject) {
      try {
        pyWorker = new Worker(new URL("javascripts/explore-worker.js", SITE), { type: "module" });
      } catch (e) {
        reject(new XError("runtime", "This browser can't start the explorer's background worker (module workers " +
          "are needed: a recent Chrome, Edge, Firefox or Safari)."));
        return;
      }
      pyWorker.onmessage = function (ev) {
        var m = ev.data;
        if (m.type === "ready") resolve(m);
        else if (m.type === "progress") { if (onWorkerProgress) onWorkerProgress(m); }
        else if (m.type === "result" && pending[m.id]) { pending[m.id].resolve(m.result); delete pending[m.id]; }
        else if (m.type === "error") {
          var err = new XError(m.stage, m.stage === "runtime" ? runtimeMessage(m.message)
            : "The analysis failed: " + m.message);
          if (pending[m.id]) { pending[m.id].reject(err); delete pending[m.id]; } else reject(err);
        }
      };
      pyWorker.onerror = function (ev) {
        reject(new XError("runtime", runtimeMessage(ev.message || "the worker failed to start")));
      };
      pyWorker.postMessage({ type: "init", base: SITE, version: manifestVersion });
    });
    pyReady.catch(function () { pyReady = null; });  // allow a retry
    return pyReady;
  }
  function runtimeMessage(detail) {
    if (/index\.json|Unexpected token|404/.test(detail)) {
      return "This copy of the site was built without the explorer runtime. (Maintainers: run " +
        "`python -m xania_explorer bundle` before building.) Details: " + detail;
    }
    return "Python couldn't start in this browser: " + detail;
  }
  function analyse(sides) {
    var id = nextId++;
    return new Promise(function (resolve, reject) {
      pending[id] = { resolve: resolve, reject: reject };
      pyWorker.postMessage({ type: "run", id: id, sides: sides });
    });
  }

  // ---------------------------------------------------------------- UI helpers
  function el(tag, attrs, children) {
    var e = document.createElement(tag);
    Object.keys(attrs || {}).forEach(function (k) {
      if (k === "text") e.textContent = attrs[k];
      else if (k === "class") e.className = attrs[k];
      else e.setAttribute(k, attrs[k]);
    });
    (children || []).forEach(function (c) { e.appendChild(typeof c === "string" ? document.createTextNode(c) : c); });
    return e;
  }

  function sideFieldset(name, legend, hint) {
    var repo = el("input", { name: "repo", list: "xe-" + name + "-repos", autocomplete: "off", spellcheck: "false",
                             placeholder: name === "base" ? CANONICAL : "owner/repo (optional)" });
    var branch = el("input", { name: "branch", list: "xe-" + name + "-branches", autocomplete: "off",
                               spellcheck: "false", placeholder: "default branch" });
    var error = el("p", { class: "xe-side-error", role: "alert" });
    error.hidden = true;
    var fs = el("fieldset", { class: "xe-side", "data-side": name }, [
      el("legend", { text: legend }),
      el("label", {}, ["Repository", repo]),
      el("label", {}, ["Branch", branch]),
      el("datalist", { id: "xe-" + name + "-repos" }),
      el("datalist", { id: "xe-" + name + "-branches" }),
      el("p", { class: "xe-hint", text: hint }),
      error,
    ]);
    return { fs: fs, repo: repo, branch: branch, error: error,
             repoList: fs.querySelector("#xe-" + name + "-repos"),
             branchList: fs.querySelector("#xe-" + name + "-branches") };
  }

  function fillList(list, values) {
    list.innerHTML = "";
    values.forEach(function (v) { list.appendChild(el("option", { value: v })); });
  }

  // ---------------------------------------------------------------- the app
  function Explorer(root) {
    this.root = root;
    this.manifest = null;
    this.result = null;
    this.current = null;
  }

  Explorer.prototype.init = async function () {
    var self = this;
    this.base = sideFieldset("base", "Base", "Defaults to the canonical Xania, " + CANONICAL + " @ main.");
    this.head = sideFieldset("head", "Compare with", "Optional. Leave empty to explore the base on its own. " +
      "Same repo, different branch works too.");
    var swap = el("button", { type: "button", class: "xe-swap md-button", title: "Swap base and head", text: "⇄" });
    var go = el("button", { type: "submit", class: "md-button md-button--primary xe-go", text: "Explore" });
    this.form = el("form", { class: "xe-form", novalidate: "" }, [this.base.fs, swap, this.head.fs,
      el("div", { class: "xe-actions" }, [go, el("span", { class: "xe-rate" })])]);
    this.go = go;
    this.rateEl = this.form.querySelector(".xe-rate");
    this.status = el("ol", { class: "xe-status" });
    this.notice = el("div", { class: "xe-notice" });
    this.pagesNav = el("nav", { class: "xe-pages", "aria-label": "Pages from this run" });
    this.output = el("div", { class: "xe-output" });
    [this.form, this.status, this.notice, this.pagesNav, this.output].forEach(function (n) { self.root.appendChild(n); });

    try {
      var r = await fetch(new URL("explore-manifest.json", SITE));
      this.manifest = await r.json();
      manifestVersion = this.manifest.version;
    } catch (e) {
      this.fail(null, "This site build has no explore-manifest.json, so the explorer can't run here.");
      go.disabled = true;
      return;
    }
    fillList(this.base.repoList, [CANONICAL]);

    // URL state: ?base=owner/repo@branch&head=owner/repo@branch&page=<page>
    var q = new URLSearchParams(location.search);
    this.setSide(this.base, q.get("base") || CANONICAL + "@main");
    this.setSide(this.head, q.get("head") || "");
    this.form.addEventListener("submit", function (ev) { ev.preventDefault(); self.explore(); });
    swap.addEventListener("click", function () {
      var b = [self.base.repo.value, self.base.branch.value];
      self.base.repo.value = self.head.repo.value || CANONICAL; self.base.branch.value = self.head.branch.value;
      self.head.repo.value = b[0]; self.head.branch.value = b[1];
    });
    [this.base, this.head].forEach(function (s) {
      s.repo.addEventListener("change", function () { self.loadBranches(s); });
      s.repo.addEventListener("input", function () { s.error.hidden = true; });
      s.branch.addEventListener("input", function () { s.error.hidden = true; });
    });
    this.head.repo.addEventListener("focus", function () { self.loadForks(); }, { once: true });
    this.form.addEventListener("focusin", function () { startWorker().catch(function () {}); }, { once: true });
    this.output.addEventListener("click", function (ev) { self.onLink(ev); });
    window.addEventListener("popstate", function () {
      var page = new URLSearchParams(location.search).get("page");
      if (self.result && page && self.result.pages[page]) self.show(page, location.hash, false);
    });
    if (q.get("base") || q.get("head")) this.explore(q.get("page"));
  };

  Explorer.prototype.setSide = function (s, text) {
    var at = text.indexOf("@");
    s.repo.value = at >= 0 ? text.slice(0, at) : text;
    s.branch.value = at >= 0 ? text.slice(at + 1) : "";
  };

  Explorer.prototype.readSide = function (s) {
    return { repo: s.repo.value.trim().replace(/^https?:\/\/github\.com\//, "").replace(/\.git$/, "").replace(/\/+$/, ""),
             branch: s.branch.value.trim() };
  };

  Explorer.prototype.updateRate = function () {
    if (rate.remaining !== null) {
      this.rateEl.textContent = "GitHub API: " + rate.remaining + " of " + (rate.limit || 60) + " requests left this hour";
    }
  };

  Explorer.prototype.loadForks = async function () {
    try {
      var forks = await gh("/repos/" + CANONICAL + "/forks?per_page=100&sort=newest");
      var base = this.readSide(this.base).repo;
      fillList(this.head.repoList, [base].concat(forks.map(function (f) { return f.full_name; })
        .filter(function (n) { return n !== base; })));
      this.updateRate();
    } catch (e) { /* suggestions are optional */ }
  };

  Explorer.prototype.loadBranches = async function (s) {
    var repo = this.readSide(s).repo;
    fillList(s.branchList, []);
    if (!REPO_RE.test(repo)) return;
    try {
      var info = await gh("/repos/" + repo);
      var branches = await gh("/repos/" + info.full_name + "/branches?per_page=100");
      var names = branches.map(function (b) { return b.name; });
      names.sort(function (a, b) { return (b === info.default_branch) - (a === info.default_branch); });
      fillList(s.branchList, names);
      s.branch.placeholder = info.default_branch + " (default)";
      this.updateRate();
    } catch (e) {
      if (e instanceof XError) this.sideError(s, e.message);
    }
  };

  Explorer.prototype.sideError = function (s, message) {
    s.error.textContent = message;
    s.error.hidden = false;
  };

  // ---------------------------------------------------------------- progress
  Explorer.prototype.step = function (id, text, state) {
    var li = this.status.querySelector('[data-step="' + id + '"]');
    if (!li) { li = el("li", { "data-step": id }); this.status.appendChild(li); }
    li.className = "xe-step xe-step-" + (state || "active");
    li.textContent = text;
  };
  Explorer.prototype.fail = function (side, message) {
    this.status.querySelectorAll(".xe-step-active").forEach(function (li) { li.className = "xe-step xe-step-stopped"; });
    var where = side === "base" ? "the Base box" : side === "head" ? "the “Compare with” box" : "";
    this.step("error", where ? "Stopped: see " + where + " above." : message, "failed");
  };

  // ---------------------------------------------------------------- a run
  Explorer.prototype.explore = async function (page) {
    var self = this, m = this.manifest;
    this.status.innerHTML = ""; this.notice.innerHTML = "";
    [this.base, this.head].forEach(function (s) { s.error.hidden = true; });
    var base = this.readSide(this.base), head = this.readSide(this.head);
    if (!base.repo) base.repo = CANONICAL;
    if (!head.repo && head.branch) head.repo = base.repo;  // a branch alone means "this repo, that branch"
    var wanted = [base].concat(head.repo ? [head] : []);
    var params = new URLSearchParams();
    params.set("base", base.repo + (base.branch ? "@" + base.branch : ""));
    if (head.repo) params.set("head", head.repo + (head.branch ? "@" + head.branch : ""));
    history.replaceState(null, "", "?" + params.toString());
    this.go.disabled = true;
    var runtime = startWorker();
    try {
      this.step("check", "Checking " + wanted.map(function (w) { return w.repo; }).join(" and ") + " on GitHub");
      var sides = [];
      for (var i = 0; i < wanted.length; i++) {
        try {
          sides.push(await resolveSide(wanted[i], m, i ? "head" : "base"));
        } finally { this.updateRate(); }
      }
      if (sides.length === 2 && sides[0].repo === sides[1].repo && sides[0].commit === sides[1].commit) {
        var same = sides[0].branch === sides[1].branch ? "is the same branch as the base"
          : "points at the same commit as the base (" + sides[0].commit.slice(0, 7) + ")";
        throw new XError("input", "This " + same + ", so there's nothing to compare. Pick another branch or repo.",
                         "head");
      }
      this.step("check", sides.map(function (s) { return s.side + " (" + s.commit.slice(0, 7) + ")"; }).join(" vs ") +
        ": Xania checkout" + (sides.length > 1 ? "s" : "") + " found", "done");
      sides.forEach(function (s) { if (s.plan.warning) self.step("warn-" + s.repo, s.side + ": " + s.plan.warning, "warning"); });

      var prebuilt = sides.length === 1 && (m.prebuilt || []).find(function (p) {
        return p.repo && p.repo.toLowerCase() === sides[0].repo.toLowerCase() && p.commit === sides[0].commit;
      });
      if (prebuilt) {
        this.notice.innerHTML = "";
        this.notice.appendChild(el("p", {}, ["This exact commit is prebuilt on this site: ",
          el("a", { href: new URL(prebuilt.name + "/", SITE).href, text: prebuilt.label }),
          " opens instantly and is searchable. The live run below shows the same pages."]));
      }

      var resultKey = "result:" + m.version + ":" + sides.map(function (s) { return s.repo + "@" + s.commit; }).join("|");
      var result = await cacheGet(resultKey);
      if (result) {
        this.step("analysis", "Loaded from this browser's cache (same commits, same Explorer version)", "done");
      } else {
        var payload = [];
        for (var j = 0; j < sides.length; j++) {
          var s = sides[j];
          var files = await download(s, function (done, total, fromCache) {
            self.step("dl-" + j, (fromCache ? "Using cached files for " : "Downloading ") + s.side + ": " + done + " of " +
              total + " files", done === total ? "done" : "active");
          });
          payload.push({ repo: s.repo, branch: s.branch, commit: s.commit, files: files });
        }
        this.step("runtime", "Starting Python in your browser");
        onWorkerProgress = function (msg) {
          self.step(msg.stage === "runtime" ? "runtime" : "analysis", msg.text);
        };
        var ready = await runtime;
        this.step("runtime", "Python ready (" + (ready.ms / 1000).toFixed(1) + " s)", "done");
        var t0 = performance.now();
        result = await analyse(payload);
        this.step("analysis", "Analysed in " + ((performance.now() - t0) / 1000).toFixed(1) + " s", "done");
        cachePut(resultKey, result);
      }
      result.sides = sides;
      this.result = result;
      this.renderNav();
      var first = page && result.pages[page] ? page : result.order[0];
      this.show(first, location.hash, false);
    } catch (e) {
      var msg = e instanceof XError ? e.message : "Something went wrong: " + (e && e.message || e);
      if (e instanceof XError && e.side) this.sideError(e.side === "head" ? this.head : this.base, msg);
      this.fail(e instanceof XError ? e.side : null, msg);
    } finally {
      this.go.disabled = false;
      onWorkerProgress = null;
    }
  };

  // ---------------------------------------------------------------- results
  Explorer.prototype.renderNav = function () {
    var self = this, r = this.result, nav = this.pagesNav;
    nav.innerHTML = "";
    function button(key, text) {
      var b = el("button", { type: "button", class: "xe-page", "data-page": key, text: text });
      b.addEventListener("click", function () { self.show(key, "", true); });
      return b;
    }
    if (r.pages["compare.md"]) nav.appendChild(el("div", { class: "xe-group" }, [button("compare.md", "Compare")]));
    var titles = {};
    this.manifest.systems.forEach(function (s) { titles[s.slug] = s.title; });
    r.names.forEach(function (name, i) {
      var group = el("div", { class: "xe-group" }, [el("span", { class: "xe-group-label",
        text: (r.names.length > 1 ? (i ? "Head: " : "Base: ") : "") + r.labels[name] })]);
      group.appendChild(button(name + "/index.md", "Dashboard"));
      self.manifest.systems.forEach(function (s) { group.appendChild(button(name + "/" + s.slug + ".md", s.title)); });
      if (r.pages[name + "/areas.md"]) group.appendChild(button(name + "/areas.md", "Areas"));
      nav.appendChild(group);
    });
  };

  Explorer.prototype.show = function (key, hash, push) {
    var html = this.result.pages[key];
    if (html === undefined) return;
    this.current = key;
    this.output.innerHTML = html;
    this.pagesNav.querySelectorAll(".xe-page").forEach(function (b) {
      b.classList.toggle("xe-current", b.getAttribute("data-page") === key);
    });
    var params = new URLSearchParams(location.search);
    params.set("page", key);
    var url = "?" + params.toString() + (hash || "");
    if (push) history.pushState(null, "", url); else history.replaceState(null, "", url);
    if (window.XaniaRender) window.XaniaRender(this.output);
    var target = hash && document.getElementById(decodeURIComponent(hash.slice(1)));
    (target || this.pagesNav).scrollIntoView({ block: "start" });
  };

  Explorer.prototype.onLink = function (ev) {
    var a = ev.target.closest("a");
    if (!a || !this.result) return;
    var href = a.getAttribute("href") || "";
    if (/^[a-z]+:/i.test(href) || href.indexOf("//") === 0) return;  // GitHub source links etc.
    if (href.charAt(0) === "#") return;  // in-page anchors
    ev.preventDefault();
    var u = new URL(href, "https://x.invalid/" + this.current);
    var key = decodeURIComponent(u.pathname.slice(1));
    if (/\.csv$/.test(key) && this.result.pages[key] !== undefined) {
      var blob = new Blob([this.result.pages[key]], { type: "text/csv" });
      var link = el("a", { href: URL.createObjectURL(blob), download: key.replace(/\//g, "-") });
      document.body.appendChild(link); link.click(); link.remove();
      return;
    }
    if (this.result.pages[key] !== undefined) { this.show(key, u.hash, true); return; }
    // a page of the static site (a guide, say)
    location.href = new URL(key.replace(/index\.md$/, "").replace(/\.md$/, "/") + u.hash, SITE).href;
  };

  function start() {
    var root = document.getElementById("xe-app");
    if (!root || root.dataset.ready) return;
    root.dataset.ready = "1";
    new Explorer(root).init();
  }
  if (typeof document$ !== "undefined") document$.subscribe(start);
  else document.addEventListener("DOMContentLoaded", start);
})();
