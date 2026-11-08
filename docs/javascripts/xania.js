// Renders Vega-Lite charts embedded by xania_explorer/site/charts.py and makes tables sortable.
// Material's `document$` fires on every page load, including instant navigation.
(function () {
  function isDark() {
    return document.body.getAttribute("data-md-color-scheme") === "slate";
  }

  function renderCharts() {
    if (typeof vegaEmbed === "undefined") return;
    document.querySelectorAll(".xe-chart").forEach(function (holder) {
      var script = holder.querySelector("script[type='application/json']");
      if (!script) return;
      var spec = JSON.parse(script.textContent);
      var target = holder.querySelector(".xe-chart-body");
      if (!target) {
        target = document.createElement("div");
        target.className = "xe-chart-body";
        holder.appendChild(target);
      }
      vegaEmbed(target, spec, {
        renderer: "svg",
        theme: isDark() ? "dark" : undefined,
        actions: { export: true, source: false, compiled: false, editor: true },
      }).catch(function (err) {
        target.textContent = "Chart failed to render: " + err;
      });
    });
  }

  function sortTables() {
    if (typeof Tablesort === "undefined") return;
    document.querySelectorAll("article table:not([class])").forEach(function (table) {
      if (!table.dataset.sortable) {
        table.dataset.sortable = "1";
        new Tablesort(table);
      }
    });
  }

  // The version switcher keeps your place: the same section in the other version.
  function keepPlace() {
    document.querySelectorAll("a.xe-version-link").forEach(function (a) {
      if (a.dataset.keepPlace) return;
      a.dataset.keepPlace = "1";
      a.addEventListener("click", function () {
        if (location.hash) a.href = a.href.split("#")[0] + location.hash;
      });
    });
  }

  function onPage() {
    renderCharts();
    sortTables();
    keepPlace();
  }
  // The live explorer (explore.js) calls this after inserting a generated page.
  window.XaniaRender = onPage;

  if (typeof document$ !== "undefined") {
    document$.subscribe(onPage);
  } else {
    document.addEventListener("DOMContentLoaded", onPage);
  }

  // Re-render charts when the light/dark toggle changes.
  new MutationObserver(function (mutations) {
    if (mutations.some(function (m) { return m.attributeName === "data-md-color-scheme"; })) renderCharts();
  }).observe(document.body, { attributes: true });
})();
