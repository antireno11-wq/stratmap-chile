const NEWS_SOURCES = ["Portal Minero","BioBioChile","Emol","Cooperativa",
  "Minería Chilena","COCHILCO Noticias","Diario Financiero",
  "Revista EI","Radio U. de Chile","RSS"];

function isNews(item) {
  if (item.phase === "Noticia") return true;
  return NEWS_SOURCES.some(s => (item.source || "").includes(s));
}

function el(id) { return document.getElementById(id); }

function escapeHTML(str) {
  return String(str||"").replaceAll("&","&amp;").replaceAll("<","&lt;")
    .replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}

const SOURCE_COLORS = {
  "SEA":               ["#1d4ed8","#eff6ff"],
  "ChileCompra":       ["#15803d","#f0fdf4"],
  "COCHILCO":          ["#7c3aed","#f5f3ff"],
  "MOP":               ["#c2410c","#fff7ed"],
  "Portal Minero":     ["#0369a1","#f0f9ff"],
  "Diario Financiero": ["#92400e","#fef3c7"],
  "BioBioChile":       ["#dc2626","#fef2f2"],
  "Revista EI":        ["#0f766e","#f0fdfa"],
  "Radio U. de Chile": ["#db2777","#fdf2f8"],
  "Minería Chilena":   ["#1d4ed8","#eff6ff"],
  "COCHILCO Noticias": ["#7c3aed","#f5f3ff"],
};

function sourceChip(source) {
  const entry = Object.entries(SOURCE_COLORS).find(([k]) => source.includes(k));
  const [color, bg] = entry ? entry[1] : ["#64748b","#f1f5f9"];
  return `<span class="source-chip" style="color:${color};background:${bg}">${escapeHTML(source)}</span>`;
}

function scoreColor(s) {
  if (s >= 80) return ["#15803d","#f0fdf4"];
  if (s >= 65) return ["#92400e","#fef3c7"];
  if (s >= 50) return ["#c2410c","#fff7ed"];
  return ["#475569","#f1f5f9"];
}

function fmtDate(d) {
  if (!d) return "—";
  return new Date(d).toLocaleDateString("es-CL",{day:"2-digit",month:"2-digit",year:"2-digit"});
}

// ── Drawer ────────────────────────────────────────────────────────────────────

function openDrawer(type, value) {
  const items = type === "company"
    ? allItems.filter(i => (i.company||"") === value)
    : allItems.filter(i => (i.region||"") === value);

  const projects = items.filter(i => !isNews(i));
  const news = items.filter(i => isNews(i));
  const scores = projects.map(i => i.radar_score ?? i.score ?? 0).filter(s => s > 0);
  const avgScore = scores.length ? Math.round(scores.reduce((a,b)=>a+b,0)/scores.length) : 0;
  const withSignals = projects.filter(i => (i.signal_score||0) > 0).length;

  const distKey = type === "company" ? "industry" : "company";
  const dist = {};
  projects.forEach(i => { const k = i[distKey]||"Sin datos"; dist[k]=(dist[k]||0)+1; });

  const phases = {};
  projects.forEach(i => { const k = i.phase||"Sin fase"; phases[k]=(phases[k]||0)+1; });

  const distRows = Object.entries(dist).sort((a,b)=>b[1]-a[1]).slice(0,6)
    .map(([k,v]) => `<div class="drawer-dist-row">
      <span>${escapeHTML(k)}</span>
      <div class="drawer-bar-wrap"><div class="drawer-bar" style="width:${Math.round(v/Math.max(projects.length,1)*100)}%"></div></div>
      <span class="drawer-dist-n">${v}</span>
    </div>`).join("");

  const phaseRows = Object.entries(phases).sort((a,b)=>b[1]-a[1])
    .map(([k,v]) => `<span class="phase-chip">${escapeHTML(k)} <strong>${v}</strong></span>`).join(" ");

  const projRows = projects.slice(0,20).map(i => {
    const score = i.radar_score ?? i.score ?? 0;
    const [c,bg] = scoreColor(score);
    return `<tr>
      <td><span class="score-badge" style="color:${c};background:${bg}">${score}</span></td>
      <td><span class="proj-title" style="max-width:240px">${escapeHTML(i.title||"")}</span>
          <span class="proj-industry">${escapeHTML(i[distKey]||"")}</span></td>
      <td>${fmtDate(i.updated_at)}</td>
      <td><a class="row-link" href="${i.url||"#"}" target="_blank">ver →</a></td>
    </tr>`;
  }).join("");

  el("drawer-title").textContent = value;
  el("drawer-subtitle").textContent = type === "company" ? "Mandante" : "Región";
  el("drawer-body").innerHTML = `
    <div class="drawer-stats">
      <div class="drawer-stat"><div class="drawer-stat-val">${projects.length}</div><div class="drawer-stat-lbl">Proyectos</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${avgScore}</div><div class="drawer-stat-lbl">Score prom.</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${withSignals}</div><div class="drawer-stat-lbl">Con señales ⚡</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${news.length}</div><div class="drawer-stat-lbl">Noticias</div></div>
    </div>
    <div class="drawer-section-title">${type === "company" ? "Por industria" : "Por mandante"}</div>
    <div class="drawer-dist">${distRows || "<p class='drawer-empty'>Sin datos</p>"}</div>
    <div class="drawer-section-title">Fases</div>
    <div style="display:flex;flex-wrap:wrap;gap:6px;margin-bottom:16px">${phaseRows || "—"}</div>
    <div class="drawer-section-title">Proyectos recientes</div>
    <div class="tableWrap">
      <table>
        <thead><tr><th>Score</th><th>Proyecto</th><th>Fecha</th><th>Link</th></tr></thead>
        <tbody>${projRows || "<tr><td colspan='4' class='muted-row'>Sin proyectos</td></tr>"}</tbody>
      </table>
    </div>
  `;

  el("drawer").classList.add("open");
  el("drawer-overlay").classList.add("open");
}

function closeDrawer() {
  el("drawer").classList.remove("open");
  el("drawer-overlay").classList.remove("open");
}

// ── Rows ──────────────────────────────────────────────────────────────────────

function projectRow(item) {
  const score = item.radar_score ?? item.score ?? 0;
  const [c,bg] = scoreColor(score);
  const signals = item.signal_score > 0
    ? `<span class="signal-badge">⚡ +${item.signal_score}</span>` : "";
  const phase = item.phase ? `<span class="phase-chip">${escapeHTML(item.phase)}</span>` : "—";
  const company = item.company
    ? `<span class="clickable-link" onclick="openDrawer('company',${JSON.stringify(item.company)})">${escapeHTML(item.company)}</span>`
    : "—";
  const region = item.region
    ? `<span class="clickable-link" onclick="openDrawer('region',${JSON.stringify(item.region)})">${escapeHTML(item.region)}</span>`
    : "—";
  return `<tr>
    <td><span class="score-badge" style="color:${c};background:${bg}">${score}</span>${signals}</td>
    <td><span class="proj-title">${escapeHTML(item.title||"")}</span>
        <span class="proj-industry">${escapeHTML(item.industry||"")}</span></td>
    <td>${sourceChip(item.source||"")}</td>
    <td>${company}</td>
    <td>${region}</td>
    <td>${phase}</td>
    <td>${fmtDate(item.updated_at)}</td>
    <td><a class="row-link" href="${item.url||"#"}" target="_blank" rel="noreferrer">ver →</a></td>
  </tr>`;
}

function newsRow(item) {
  return `<tr>
    <td><a class="news-title" href="${item.url||"#"}" target="_blank" rel="noreferrer">${escapeHTML(item.title||"")}</a></td>
    <td>${sourceChip(item.source||"")}</td>
    <td>${escapeHTML(item.industry||"—")}</td>
    <td>${fmtDate(item.updated_at)}</td>
    <td><a class="row-link" href="${item.url||"#"}" target="_blank" rel="noreferrer">ver →</a></td>
  </tr>`;
}

// ── Filters ───────────────────────────────────────────────────────────────────

async function fetchJSON(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

let activeFilters = { industry: new Set(), region: new Set(), source: new Set() };
let allItems = [];

function buildFilters(items) {
  const counts = { industry: {}, region: {}, source: {} };
  items.forEach(i => {
    if (i.industry) counts.industry[i.industry] = (counts.industry[i.industry]||0)+1;
    if (i.region)   counts.region[i.region]     = (counts.region[i.region]||0)+1;
    if (i.source)   counts.source[i.source]     = (counts.source[i.source]||0)+1;
  });
  ["industry","region","source"].forEach(key => {
    const container = el(`filter-${key}`);
    if (!container) return;
    container.innerHTML = Object.entries(counts[key])
      .sort((a,b)=>b[1]-a[1]).slice(0,8)
      .map(([val,count]) => `
        <div class="filter-item">
          <input type="checkbox" id="f-${key}-${escapeHTML(val)}" data-key="${key}" data-val="${val}" />
          <label for="f-${key}-${escapeHTML(val)}">${escapeHTML(val)}</label>
          <span class="fc">${count}</span>
        </div>`).join("");
    container.querySelectorAll("input[type=checkbox]").forEach(cb => {
      cb.addEventListener("change", () => {
        const k = cb.dataset.key, v = cb.dataset.val;
        cb.checked ? activeFilters[k].add(v) : activeFilters[k].delete(v);
        renderFiltered();
      });
    });
  });
}

function applyFilters(items) {
  return items.filter(i => {
    if (activeFilters.industry.size && !activeFilters.industry.has(i.industry)) return false;
    if (activeFilters.region.size && !activeFilters.region.has(i.region)) return false;
    if (activeFilters.source.size && !activeFilters.source.has(i.source)) return false;
    return true;
  });
}

function renderFiltered() {
  const filtered = applyFilters(allItems);
  const projects = filtered.filter(i => !isNews(i));
  const news = filtered.filter(i => isNews(i));

  el("badge-projects").textContent = projects.length;
  el("badge-news").textContent = news.length;
  el("sc-projects").textContent = projects.length;
  el("sc-news").textContent = news.length;

  el("tbody-projects").innerHTML = projects.length
    ? projects.map(projectRow).join("")
    : `<tr><td colspan="8" class="muted-row">Sin proyectos</td></tr>`;

  el("tbody-news").innerHTML = news.length
    ? news.map(newsRow).join("")
    : `<tr><td colspan="5" class="muted-row">Sin noticias</td></tr>`;

  el("stat-projects").textContent = projects.length;
  el("stat-news").textContent = news.length;
  el("stat-signals").textContent = projects.filter(i => (i.signal_score||0) > 0).length;
  const scores = filtered.map(i => i.radar_score ?? i.score ?? 0).filter(s => s > 0);
  el("stat-avg").textContent = scores.length
    ? Math.round(scores.reduce((a,b)=>a+b,0)/scores.length) : "—";

  el("upd-projects").textContent = "Actualizado ahora";
  el("upd-news").textContent = "Actualizado ahora";
  el("status").textContent = `${projects.length} proyectos · ${news.length} noticias`;
}

async function load() {
  const q = el("q").value.trim();
  const limit = el("limit").value;
  let url = `/opportunities?limit=${encodeURIComponent(limit)}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  el("status").textContent = "Cargando…";
  try {
    const data = await fetchJSON(url);
    allItems = data.items || [];
    buildFilters(allItems);
    renderFiltered();
  } catch(e) {
    el("status").textContent = `Error: ${e.message}`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  el("btnRefresh").addEventListener("click", load);
  el("q").addEventListener("keydown", e => { if (e.key === "Enter") load(); });
  el("limit").addEventListener("change", load);
  el("drawer-close").addEventListener("click", closeDrawer);
  el("drawer-overlay").addEventListener("click", closeDrawer);

  // Sidebar navigation
  const sidebarItems = document.querySelectorAll(".sidebar-item");
  sidebarItems.forEach(item => {
    item.addEventListener("click", () => {
      sidebarItems.forEach(i => i.classList.remove("active"));
      item.classList.add("active");
    });
  });
  // Scroll a proyectos
  if (sidebarItems[1]) sidebarItems[1].addEventListener("click", () => {
    el("tbody-projects")?.closest(".section-card")?.scrollIntoView({behavior:"smooth", block:"start"});
  });
  // Scroll a noticias
  if (sidebarItems[2]) sidebarItems[2].addEventListener("click", () => {
    el("tbody-news")?.closest(".section-card")?.scrollIntoView({behavior:"smooth", block:"start"});
  });

  load();
});
