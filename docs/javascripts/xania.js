// Renders Vega-Lite charts embedded by xania_utils/site/charts.py and makes tables sortable.
// Material's `document$` fires on every page load, including instant navigation.
(function () {
  function isDark() {
    return document.body.getAttribute("data-md-color-scheme") === "slate";
  }

  function renderCharts() {
    if (typeof vegaEmbed === "undefined") return;
    document.querySelectorAll(".xu-chart").forEach(function (holder) {
      var script = holder.querySelector("script[type='application/json']");
      if (!script) return;
      var spec = JSON.parse(script.textContent);
      var target = holder.querySelector(".xu-chart-body");
      if (!target) {
        target = document.createElement("div");
        target.className = "xu-chart-body";
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

  function onPage() {
    renderCharts();
    sortTables();
  }

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
