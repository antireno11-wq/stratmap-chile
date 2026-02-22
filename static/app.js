// Stratmap Chile — app.js

const NEWS_SOURCES = ["Portal Minero", "BioBioChile", "Emol", "Cooperativa",
  "Minería Chilena", "COCHILCO Noticias", "Diario Financiero",
  "Revista EI", "Radio U. de Chile", "chilebcompra", "RSS"];

function isNews(item) {
  if (item.phase === "Noticia") return true;
  if (NEWS_SOURCES.some(s => (item.source || "").includes(s))) return true;
  return false;
}

function el(id) { return document.getElementById(id); }

function escapeHTML(str) {
  return String(str)
    .replaceAll("&", "&amp;").replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;").replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function sourceBadge(source) {
  const colors = {
    "SEA": "#2563eb", "ChileCompra": "#16a34a", "COCHILCO": "#9333ea",
    "MOP": "#ea580c", "Portal Minero": "#0891b2", "Diario Financiero": "#b45309",
    "BioBioChile": "#dc2626", "Emol": "#7c3aed", "Revista EI": "#0d9488",
    "Radio U. de Chile": "#db2777",
  };
  const color = Object.entries(colors).find(([k]) => source.includes(k))?.[1] ?? "#64748b";
  return `<span class="source-badge" style="background:${color}20;color:${color};border:1px solid ${color}40">${escapeHTML(source)}</span>`;
}

function scoreColor(score) {
  if (score >= 80) return "#16a34a";
  if (score >= 65) return "#ca8a04";
  if (score >= 50) return "#ea580c";
  return "#64748b";
}

function projectRow(item) {
  const score = item.radar_score ?? item.score ?? 0;
  const phase = item.phase ?? "";
  const phaseBadge = phase
    ? `<span class="phase-badge">${escapeHTML(phase)}</span>` : "—";
  const date = item.updated_at
    ? new Date(item.updated_at).toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit", year: "2-digit" })
    : "—";
  const signals = item.signal_score > 0
    ? `<span class="signal-dot" title="+${item.signal_score} señales">⚡</span>` : "";

  return `
    <tr>
      <td><span class="score-badge" style="background:${scoreColor(score)}20;color:${scoreColor(score)}">${score}${signals}</span></td>
      <td class="td-title">
        <div class="proj-title">${escapeHTML(item.title ?? "")}</div>
        <div class="proj-sub">${escapeHTML(item.industry ?? "")}</div>
      </td>
      ${sourceBadge(item.source ?? "")}
      <td>${escapeHTML(item.company ?? "—")}</td>
      <td>${escapeHTML(item.region ?? "—")}</td>
      <td>${phaseBadge}</td>
      <td>${date}</td>
      <td><a class="link" href="${item.url ?? "#"}" target="_blank" rel="noreferrer">ver →</a></td>
    </tr>`;
}

function newsRow(item) {
  const date = item.updated_at
    ? new Date(item.updated_at).toLocaleDateString("es-CL", { day: "2-digit", month: "2-digit", year: "2-digit" })
    : "—";
  return `
    <tr>
      <td class="td-title">
        <div class="proj-title">${escapeHTML(item.title ?? "")}</div>
      </td>
      <td>${sourceBadge(item.source ?? "")}</td>
      <td>${escapeHTML(item.industry ?? "—")}</td>
      <td>${date}</td>
      <td><a class="link" href="${item.url ?? "#"}" target="_blank" rel="noreferrer">ver →</a></td>
    </tr>`;
}

async function fetchJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

async function load() {
  const q = el("q").value.trim();
  const limit = el("limit").value;
  let url = `/opportunities?limit=${encodeURIComponent(limit)}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;

  el("status").textContent = "Cargando…";
  el("tbody-projects").innerHTML = `<tr><td colspan="8" class="muted">Cargando...</td></tr>`;
  el("tbody-news").innerHTML = `<tr><td colspan="5" class="muted">Cargando...</td></tr>`;

  try {
    const data = await fetchJSON(url);
    const items = data.items || [];

    const projects = items.filter(i => !isNews(i));
    const news = items.filter(i => isNews(i));

    el("status").textContent = `${projects.length} proyectos · ${news.length} noticias`;
    el("projects-count").textContent = projects.length;
    el("news-count").textContent = news.length;

    el("tbody-projects").innerHTML = projects.length
      ? projects.map(projectRow).join("")
      : `<tr><td colspan="8" class="muted">Sin proyectos</td></tr>`;

    el("tbody-news").innerHTML = news.length
      ? news.map(newsRow).join("")
      : `<tr><td colspan="5" class="muted">Sin noticias</td></tr>`;

  } catch (e) {
    el("status").textContent = `Error: ${e.message}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  el("btnRefresh").addEventListener("click", load);
  el("btnSearch").addEventListener("click", load);
  el("q").addEventListener("keydown", e => { if (e.key === "Enter") load(); });
  load();
});
