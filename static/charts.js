/* charts.js — helpers Chart.js para el dashboard de Stratmap.
 *
 * Requiere que Chart.js esté cargado antes via:
 *   <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
 *
 * Defaults globales para que todos los charts compartan look & feel.
 */
(function () {
  if (typeof Chart === 'undefined') {
    console.warn('charts.js: Chart.js no está cargado');
    return;
  }

  Chart.defaults.font.family = "'Inter', ui-sans-serif, system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = '#64748b';
  Chart.defaults.borderColor = '#e5e7eb';
  Chart.defaults.plugins.legend.labels.usePointStyle = true;
  Chart.defaults.plugins.legend.labels.padding = 16;
  Chart.defaults.plugins.tooltip.backgroundColor = '#0f172a';
  Chart.defaults.plugins.tooltip.padding = 10;
  Chart.defaults.plugins.tooltip.cornerRadius = 8;
  Chart.defaults.plugins.tooltip.titleFont = { size: 12, weight: '600' };
  Chart.defaults.plugins.tooltip.bodyFont = { size: 12 };
})();


/** Sparkline mini line chart sin axes ni labels.
 *  Uso: window.sparkline(canvasEl, [v1, v2, ..., vN], { color: '#6366f1' })
 */
window.sparkline = function (canvas, values, opts) {
  if (!canvas) return null;
  opts = opts || {};
  const color = opts.color || '#6366f1';
  const ctx = canvas.getContext('2d');
  const data = (values || []).map((v, i) => ({ x: i, y: v }));
  return new Chart(ctx, {
    type: 'line',
    data: {
      labels: data.map(d => d.x),
      datasets: [{
        data: data.map(d => d.y),
        borderColor: color,
        backgroundColor: color + '20',
        fill: true,
        tension: 0.35,
        borderWidth: 1.5,
        pointRadius: 0,
        pointHoverRadius: 0,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false }, tooltip: { enabled: false } },
      scales: {
        x: { display: false },
        y: { display: false, beginAtZero: true },
      },
      animation: false,
    },
  });
};


/** Stacked area chart de actividad por categoría.
 *  Uso: window.activityChart(canvasEl, { dates: [...], series: { licitacion:[...], ... } })
 */
window.activityChart = function (canvas, payload) {
  if (!canvas) return null;
  const ctx = canvas.getContext('2d');
  const COLORS = {
    licitacion: '#6366f1',
    prospecto:  '#10b981',
    concesion:  '#f59e0b',
    noticia:    '#94a3b8',
  };
  const LABELS = {
    licitacion: 'Licitaciones',
    prospecto:  'Prospectos SEA',
    concesion:  'Concesiones',
    noticia:    'Noticias',
  };
  const series = payload.series || {};
  const datasets = Object.keys(COLORS).map(k => ({
    label: LABELS[k],
    data: series[k] || [],
    backgroundColor: COLORS[k] + '30',
    borderColor: COLORS[k],
    borderWidth: 1.5,
    fill: true,
    tension: 0.3,
    pointRadius: 0,
    pointHoverRadius: 4,
  }));
  return new Chart(ctx, {
    type: 'line',
    data: { labels: payload.dates || [], datasets },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', align: 'start' },
        tooltip: { mode: 'index', intersect: false },
      },
      scales: {
        x: {
          grid: { display: false },
          ticks: {
            maxRotation: 0,
            autoSkip: true,
            maxTicksLimit: 8,
            callback: function (val, i) {
              const d = (payload.dates || [])[i] || '';
              return d.slice(5); // MM-DD
            },
          },
        },
        y: {
          beginAtZero: true,
          grid: { color: '#f3f4f6' },
          ticks: { precision: 0, padding: 8 },
        },
      },
    },
  });
};


/** Donut por categoría.
 *  Uso: window.categoryDonut(canvasEl, { licitacion: 50, prospecto: 30, ... })
 */
window.categoryDonut = function (canvas, counts) {
  if (!canvas) return null;
  const ctx = canvas.getContext('2d');
  const ORDER = ['licitacion', 'prospecto', 'concesion', 'noticia', 'empleo'];
  const COLORS = {
    licitacion: '#6366f1',
    prospecto:  '#10b981',
    concesion:  '#f59e0b',
    noticia:    '#94a3b8',
    empleo:     '#8b5cf6',
  };
  const LABELS = {
    licitacion: 'Licitaciones',
    prospecto:  'Prospectos SEA',
    concesion:  'Concesiones',
    noticia:    'Noticias',
    empleo:     'Empleos',
  };
  const labels = [], data = [], colors = [];
  for (const k of ORDER) {
    if ((counts[k] || 0) > 0) {
      labels.push(LABELS[k]);
      data.push(counts[k]);
      colors.push(COLORS[k]);
    }
  }
  return new Chart(ctx, {
    type: 'doughnut',
    data: { labels, datasets: [{ data, backgroundColor: colors, borderWidth: 0, hoverOffset: 6 }] },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      cutout: '65%',
      plugins: {
        legend: { position: 'right', align: 'center' },
        tooltip: {
          callbacks: {
            label: function (ctx) {
              const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
              const pct = total > 0 ? Math.round(ctx.raw / total * 100) : 0;
              return `${ctx.label}: ${ctx.raw} (${pct}%)`;
            },
          },
        },
      },
    },
  });
};
