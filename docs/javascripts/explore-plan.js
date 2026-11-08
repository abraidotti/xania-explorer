// Which files the explorer downloads from a commit, and whether the repo is Xania at all.
// Mirrors xania_explorer/explore.py plan() using the rules in explore-manifest.json, so the browser can
// reject a non-Xania repo before Pyodide has loaded. tests/pyodide/budget.mjs checks the two agree.
(function (root) {
  function needsAny(manifest, slug, missing) {
    var bySlug = {};
    manifest.systems.forEach(function (s) { bySlug[s.slug] = s; });
    var seen = {}, todo = [slug];
    while (todo.length) {
      var s = bySlug[todo.pop()];
      if (!s || seen[s.slug]) continue;
      seen[s.slug] = true;
      if (s.needs.some(function (f) { return missing.indexOf(f) >= 0; })) return true;
      todo = todo.concat(s.uses);
    }
    return false;
  }

  function plan(tree, manifest, repo) {
    repo = repo || "this repository";
    var blobs = {};
    tree.forEach(function (e) {
      if (typeof e === "string") e = { path: e, type: "blob", size: 0 };
      if (e.type === "blob") blobs[e.path] = e;
    });
    if (!blobs[manifest.required]) {
      var hasSrc = Object.keys(blobs).some(function (p) { return p.indexOf("src/") === 0; });
      return {
        ok: false, files: [], missing_sources: [], unavailable: [], warning: "",
        error: repo + " doesn't look like a Xania checkout: it has no " + manifest.required + "." +
          (hasSrc ? " It has a src/ folder but no area files, so it may be another MUD or a code-only fork." : ""),
      };
    }
    var dir = manifest.areaDir;
    var files = Object.keys(blobs).filter(function (p) {
      var name = p.slice(dir.length);  // area/ itself, as boot_db reads it; dotfiles are never read
      return p.indexOf(dir) === 0 && name.indexOf("/") < 0 && name.charAt(0) !== "." &&
        (blobs[p].size || 0) <= manifest.maxAreaFile;
    });
    manifest.sourceFiles.forEach(function (f) { if (blobs["src/" + f]) files.push("src/" + f); });
    var missing = manifest.sourceFiles.filter(function (f) { return !blobs["src/" + f]; });
    var unavailable = manifest.systems.filter(function (s) { return needsAny(manifest, s.slug, missing); })
      .map(function (s) { return s.title; });
    var warning = unavailable.length
      ? missing.length + " of the C++ files the assessments read are missing, so " + unavailable.join(", ") +
        " won't be available. If this isn't Xania, results may not mean much."
      : "";
    // Python's sorted(): code-point order, not locale order
    files.sort(function (a, b) { return a < b ? -1 : a > b ? 1 : 0; });
    return { ok: true, error: "", files: files, missing_sources: missing, unavailable: unavailable, warning: warning };
  }

  // xania_explorer/site/targets.py slug_for(): a URL-safe name from repo + branch
  function slugFor(repo, branch, fallback) {
    var clean = function (s) { return s.toLowerCase().replace(/[^a-z0-9_-]+/g, "-").replace(/^-+|-+$/g, ""); };
    var parts = [(repo || "").replace(/\//g, "-"), branch && branch !== "HEAD" ? branch : ""].filter(Boolean);
    return clean(parts.join("-")) || clean(fallback || "") || "xania";
  }

  // xania_explorer/site/builds.py build_slug(): where a GitHub build of these sides lives
  function buildSlug(sides) {
    return sides.map(function (s, i) { return slugFor(s.repo, s.branch, "side" + (i + 1)); }).join("...");
  }

  root.XaniaPlan = { plan: plan, slugFor: slugFor, buildSlug: buildSlug };
})(typeof globalThis !== "undefined" ? globalThis : this);
