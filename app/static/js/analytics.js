/* Draws the Analytics page's charts with Chart.js from the numbers the server
   put in <script id="analyticsData">. Colours: one fixed colour per species
   (checked for colour-blind readers), and olive for single-series charts. */
(function () {
  if (!window.Chart) return;                       // offline: the tables under each chart still work
  const data = JSON.parse(document.getElementById("analyticsData").textContent);
  const css = getComputedStyle(document.documentElement);
  const token = (name) => css.getPropertyValue(name).trim();
  const INK = token("--ink-soft"), LINE = token("--line"), CARD = token("--card"), OLIVE = token("--olive-700");
  const SPECIES_COLOUR = { CATTLE: "#2a78d6", GOAT: "#eb6834", SHEEP: "#1baf7a" };   // fixed: colour follows the species

  Chart.defaults.font.family = token("--sans");
  Chart.defaults.font.size = 12;
  Chart.defaults.color = INK;
  Chart.defaults.plugins.legend.labels.boxWidth = 12;
  Chart.defaults.plugins.legend.labels.boxHeight = 12;
  Chart.defaults.plugins.tooltip.backgroundColor = token("--olive-900");
  Chart.defaults.maintainAspectRatio = false;

  const axes = (stacked) => ({
    x: { stacked, grid: { display: false }, border: { color: LINE }, ticks: { maxRotation: 0, autoSkipPadding: 12 } },
    y: { stacked, beginAtZero: true, grid: { color: LINE }, border: { display: false }, ticks: { precision: 0 } },
  });
  const bar = (label, values, colour) => ({
    label, data: values, backgroundColor: colour, borderColor: CARD, borderWidth: { top: 2 },
    borderRadius: 4, borderSkipped: "start", maxBarThickness: 22,
  });

  // Names at the end of each line, so a line's species can be read without the legend.
  const endLabels = {
    id: "endLabels",
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((ds, i) => {
        const meta = chart.getDatasetMeta(i);
        if (meta.hidden || !meta.data.length) return;
        const point = meta.data[meta.data.length - 1];
        ctx.save();
        ctx.fillStyle = token("--ink");
        ctx.font = `500 12px ${token("--sans")}`;
        ctx.textBaseline = "middle";
        ctx.fillText(ds.label, point.x + 8, point.y);
        ctx.restore();
      });
    },
  };

  new Chart(document.getElementById("herdChart"), {
    type: "line",
    data: {
      labels: data.months,
      datasets: data.species.map((s) => ({
        label: s.name, data: s.herd, borderColor: SPECIES_COLOUR[s.code], backgroundColor: SPECIES_COLOUR[s.code],
        borderWidth: 2, pointRadius: 0, pointHoverRadius: 5, pointHoverBorderColor: CARD, pointHoverBorderWidth: 2, tension: 0.25,
      })),
    },
    options: {
      layout: { padding: { right: 56 } },
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" } },
      scales: axes(false),
    },
    plugins: [endLabels],
  });

  for (const [key, label] of [["born", "Born"], ["died", "Died"], ["sold", "Sold"]]) {
    new Chart(document.getElementById(key + "Chart"), {
      type: "bar",
      data: { labels: data.months, datasets: [bar(label, data[key], OLIVE)] },
      options: { plugins: { legend: { display: false } }, scales: axes(false) },
    });
  }

  new Chart(document.getElementById("illChart"), {
    type: "bar",
    data: { labels: data.months, datasets: data.species.map((s) => bar(s.name, s.ill, SPECIES_COLOUR[s.code])) },
    options: {
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom" } },
      scales: axes(true),
    },
  });

  const causeCanvas = document.getElementById("causeChart");
  if (causeCanvas) {
    new Chart(causeCanvas, {
      type: "bar",
      data: { labels: data.causes.map((c) => c.cause), datasets: [bar("Deaths", data.causes.map((c) => c.count), OLIVE)] },
      options: {
        indexAxis: "y",
        plugins: { legend: { display: false } },
        scales: {
          x: { beginAtZero: true, grid: { color: LINE }, border: { display: false }, ticks: { precision: 0 } },
          // Long causes are shortened on the axis; the full words are in the hover box and the table.
          y: { grid: { display: false }, border: { color: LINE },
               ticks: { callback(value) { const s = this.getLabelForValue(value); return s.length > 18 ? s.slice(0, 17) + "…" : s; } } },
        },
      },
    });
  }
})();