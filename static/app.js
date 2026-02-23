const NEWS_SOURCES = ["Portal Minero","BioBioChile","Emol","Cooperativa",
  "Minería Chilena","COCHILCO Noticias","Diario Financiero",
  "Revista EI","Radio U. de Chile","RSS"];

const PIPELINE_STATUSES = ["Detectada","En análisis","Postular","No postular","Presentada","Adjudicada","Perdida"];

const STATUS_COLORS = {
  "Detectada":    ["#1d4ed8","#eff6ff"],
  "En análisis":  ["#92400e","#fef3c7"],
  "Postular":     ["#15803d","#f0fdf4"],
  "No postular":  ["#64748b","#f1f5f9"],
  "Presentada":   ["#7c3aed","#f5f3ff"],
  "Adjudicada":   ["#15803d","#dcfce7"],
  "Perdida":      ["#dc2626","#fef2f2"],
};

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

function statusChip(status) {
  if (!status) return `<span class="status-chip" style="color:#64748b;background:#f1f5f9">Sin estado</span>`;
  const [color, bg] = STATUS_COLORS[status] || ["#64748b","#f1f5f9"];
  return `<span class="status-chip" style="color:${color};background:${bg}">${escapeHTML(status)}</span>`;
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

function fmtDatetime(d) {
  if (!d) return "—";
  return new Date(d).toLocaleString("es-CL",{day:"2-digit",month:"2-digit",hour:"2-digit",minute:"2-digit"});
}

// ── Drawer map ────────────────────────────────────────────────────────────────
const drawerMap = {};
let drawerIdx = 0;

function drawerKey(type, value) {
  const key = `dk_${drawerIdx++}`;
  drawerMap[key] = { type, value };
  return key;
}

// ── Pipeline drawer ───────────────────────────────────────────────────────────

let currentOppId = null;

window.openOppDrawer = async function(oppId) {
  currentOppId = oppId;
  const item = allItems.find(i => i.id === oppId);
  if (!item) return;

  el("drawer-title").textContent = item.title;
  el("drawer-subtitle").textContent = item.company || item.source || "";
  el("drawer-body").innerHTML = `<p class="drawer-empty">Cargando...</p>`;
  el("drawer").classList.add("open");
  el("drawer-overlay").classList.add("open");

  // Cargar pipeline y notas en paralelo
  const [pipelineRes, notesRes] = await Promise.all([
    fetch(`/opportunities/${oppId}/pipeline`).then(r => r.json()),
    fetch(`/opportunities/${oppId}/notes`).then(r => r.json()),
  ]);

  const score = item.radar_score ?? item.score ?? 0;
  const [sc, sbg] = scoreColor(score);
  const notes = notesRes.items || [];

  el("drawer-body").innerHTML = `
    <div class="drawer-stats" style="grid-template-columns:repeat(3,1fr)">
      <div class="drawer-stat"><div class="drawer-stat-val" style="color:${sc}">${score}</div><div class="drawer-stat-lbl">Score</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${escapeHTML(item.region||"—")}</div><div class="drawer-stat-lbl">Región</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${escapeHTML(item.industry||"—")}</div><div class="drawer-stat-lbl">Industria</div></div>
    </div>

    <div class="drawer-section-title">Estado Pipeline</div>
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px;flex-wrap:wrap">
      <select id="pipeline-status" class="cf-input" style="flex:1;min-width:160px">
        ${PIPELINE_STATUSES.map(s => `<option value="${s}" ${s === pipelineRes.status ? "selected" : ""}>${s}</option>`).join("")}
      </select>
      <input id="pipeline-assignee" class="cf-input" placeholder="Responsable" value="${escapeHTML(pipelineRes.assignee||"")}" style="flex:1;min-width:120px" />
      <button class="cf-btn-save" onclick="savePipeline(${oppId})">Guardar</button>
    </div>
    <div id="pipeline-feedback" style="font-size:12px;color:#15803d;margin-bottom:12px;display:none">✓ Guardado</div>

    <div class="drawer-section-title">Notas <span style="font-weight:400;color:#94a3b8">(${notes.length})</span></div>
    <div id="notes-list" style="margin-bottom:12px">
      ${notes.length ? notes.map(n => `
        <div class="note-card">
          <div class="note-text">${escapeHTML(n.note)}</div>
          <div class="note-meta">${n.author ? escapeHTML(n.author) + " · " : ""}${fmtDatetime(n.created_at)}</div>
        </div>
      `).join("") : `<p class="drawer-empty">Sin notas</p>`}
    </div>
    <div class="contact-form" style="display:block">
      <textarea id="note-text" class="cf-input" rows="2" placeholder="Agregar nota..." style="width:100%;resize:vertical;margin-bottom:8px"></textarea>
      <div class="cf-actions">
        <input id="note-author" class="cf-input" placeholder="Tu nombre (opcional)" style="flex:1" />
        <button class="cf-btn-save" onclick="saveNote(${oppId})">Agregar nota</button>
      </div>
    </div>

    <div class="drawer-section-title" style="margin-top:20px">Detalles</div>
    <div style="font-size:12px;color:#64748b;display:flex;flex-direction:column;gap:4px">
      <span>Fuente: ${sourceChip(item.source||"")}</span>
      <span>Mandante: ${escapeHTML(item.company||"—")}</span>
      <span>Fase: ${escapeHTML(item.phase||"—")}</span>
      <span>Actualizado: ${fmtDate(item.updated_at)}</span>
      ${item.url ? `<a href="${item.url}" target="_blank" class="contact-link" style="margin-top:4px">🔗 Ver fuente original</a>` : ""}
    </div>
  `;
};

window.savePipeline = async function(oppId) {
  const status = el("pipeline-status").value;
  const assignee = el("pipeline-assignee").value.trim() || null;
  await fetch(`/opportunities/${oppId}/pipeline`, {
    method: "PUT",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({status, assignee})
  });
  // Actualizar en allItems
  const item = allItems.find(i => i.id === oppId);
  if (item) item.pipeline_status = status;
  renderFiltered();
  const fb = el("pipeline-feedback");
  fb.style.display = "block";
  setTimeout(() => { fb.style.display = "none"; }, 2000);
};

window.saveNote = async function(oppId) {
  const note = el("note-text").value.trim();
  const author = el("note-author").value.trim() || null;
  if (!note) return;
  const res = await fetch(`/opportunities/${oppId}/notes`, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({note, author})
  });
  const saved = await res.json();
  el("note-text").value = "";
  const list = el("notes-list");
  const card = document.createElement("div");
  card.className = "note-card";
  card.innerHTML = `<div class="note-text">${escapeHTML(saved.note)}</div>
    <div class="note-meta">${saved.author ? escapeHTML(saved.author) + " · " : ""}${fmtDatetime(saved.created_at)}</div>`;
  list.insertBefore(card, list.firstChild);
  if (list.querySelector(".drawer-empty")) list.querySelector(".drawer-empty").remove();
};

// ── Company/Region drawer ──────────────────────────────────────────────────────

async function fetchContacts(company) {
  try {
    const r = await fetch(`/contacts?company=${encodeURIComponent(company)}`);
    const data = await r.json();
    return data.items || [];
  } catch(e) { return []; }
}

window.deleteContact = async function(contactId, company) {
  if (!confirm("¿Eliminar este contacto?")) return;
  await fetch(`/contacts/${contactId}`, {method:"DELETE"});
  const contacts = await fetchContacts(company);
  el("drawer-contacts").innerHTML = renderContactsList(contacts, company);
};

window.submitNewContact = async function(company) {
  const name = el("nc-name").value.trim();
  const role = el("nc-role").value.trim();
  const email = el("nc-email").value.trim();
  const phone = el("nc-phone").value.trim();
  const linkedin = el("nc-linkedin").value.trim();
  if (!name) { alert("El nombre es obligatorio"); return; }
  await fetch("/contacts", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({name, company, role:role||null, email:email||null, phone:phone||null, linkedin_url:linkedin||null})
  });
  const contacts = await fetchContacts(company);
  el("drawer-contacts").innerHTML = renderContactsList(contacts, company);
};

function renderContactsList(contacts, company) {
  const ec = escapeHTML(company);
  const list = contacts.length ? contacts.map(c => `
    <div class="contact-card">
      <div class="contact-info">
        <div class="contact-name">${escapeHTML(c.name)}</div>
        <div class="contact-role">${escapeHTML(c.role||"")}</div>
        <div class="contact-meta">
          ${c.email ? `<a href="mailto:${escapeHTML(c.email)}" class="contact-link">✉ ${escapeHTML(c.email)}</a>` : ""}
          ${c.phone ? `<span class="contact-link">📞 ${escapeHTML(c.phone)}</span>` : ""}
          ${c.linkedin_url ? `<a href="${escapeHTML(c.linkedin_url)}" target="_blank" class="contact-link linkedin">in LinkedIn</a>` : ""}
        </div>
      </div>
      <button class="contact-delete" onclick="deleteContact(${c.id},'${ec}')">✕</button>
    </div>`).join("") : `<p class="drawer-empty">Sin contactos registrados</p>`;

  return `${list}
    <div class="contact-form" id="contact-form" style="display:none">
      <div class="cf-row">
        <input id="nc-name" placeholder="Nombre *" class="cf-input" />
        <input id="nc-role" placeholder="Cargo" class="cf-input" />
      </div>
      <div class="cf-row">
        <input id="nc-email" placeholder="Email" class="cf-input" type="email" />
        <input id="nc-phone" placeholder="Teléfono" class="cf-input" />
      </div>
      <input id="nc-linkedin" placeholder="URL LinkedIn" class="cf-input" style="width:100%;margin-bottom:8px" />
      <div class="cf-actions">
        <button class="cf-btn-cancel" onclick="el('contact-form').style.display='none'">Cancelar</button>
        <button class="cf-btn-save" onclick="submitNewContact('${ec}')">Guardar</button>
      </div>
    </div>
    <button class="btn-add-contact" onclick="el('contact-form').style.display=el('contact-form').style.display==='none'?'block':'none'">+ Agregar contacto</button>`;
}

window.openDrawerByKey = function(key) {
  const entry = drawerMap[key];
  if (!entry) return;
  openDrawer(entry.type, entry.value);
};

async function openDrawer(type, value) {
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

  const total = Math.max(projects.length, 1);
  const distRows = Object.entries(dist).sort((a,b)=>b[1]-a[1]).slice(0,6)
    .map(([k,v]) => `<div class="drawer-dist-row">
      <span>${escapeHTML(k)}</span>
      <div class="drawer-bar-wrap"><div class="drawer-bar" style="width:${Math.round(v/total*100)}%"></div></div>
      <span class="drawer-dist-n">${v}</span>
    </div>`).join("");

  const phaseRows = Object.entries(phases).sort((a,b)=>b[1]-a[1])
    .map(([k,v]) => `<span class="phase-chip">${escapeHTML(k)} <strong>${v}</strong></span>`).join(" ");

  const projRows = projects.slice(0,15).map(i => {
    const score = i.radar_score ?? i.score ?? 0;
    const [c,bg] = scoreColor(score);
    const oppKey = `opp_${i.id}`;
    drawerMap[oppKey] = {type:"opp", id: i.id};
    return `<tr>
      <td><span class="score-badge" style="color:${c};background:${bg}">${score}</span></td>
      <td><span class="proj-title clickable-link" style="max-width:220px" onclick="openOppDrawer(${i.id})">${escapeHTML(i.title||"")}</span>
          <span class="proj-industry">${escapeHTML(i[distKey]||"")}</span></td>
      <td>${statusChip(i.pipeline_status)}</td>
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
    <div class="drawer-section-title">Proyectos</div>
    <div class="tableWrap" style="margin-bottom:20px">
      <table>
        <thead><tr><th>Score</th><th>Proyecto</th><th>Pipeline</th><th>Fecha</th><th>Link</th></tr></thead>
        <tbody>${projRows || "<tr><td colspan='5' class='muted-row'>Sin proyectos</td></tr>"}</tbody>
      </table>
    </div>
    ${type === "company" ? `
    <div class="drawer-section-title">Contactos</div>
    <div id="drawer-contacts"><p class="drawer-empty">Cargando...</p></div>` : ""}
  `;

  el("drawer").classList.add("open");
  el("drawer-overlay").classList.add("open");

  if (type === "company") {
    const contacts = await fetchContacts(value);
    const dcEl = el("drawer-contacts");
    if (dcEl) dcEl.innerHTML = renderContactsList(contacts, value);
  }
}

function closeDrawer() {
  el("drawer").classList.remove("open");
  el("drawer-overlay").classList.remove("open");
  currentOppId = null;
}

// ── Rows ──────────────────────────────────────────────────────────────────────

function projectRow(item) {
  const score = item.radar_score ?? item.score ?? 0;
  const [c,bg] = scoreColor(score);
  const signals = item.signal_score > 0
    ? `<span class="signal-badge">⚡ +${item.signal_score}</span>` : "";
  const phase = item.phase ? `<span class="phase-chip">${escapeHTML(item.phase)}</span>` : "—";

  const companyKey = item.company ? drawerKey("company", item.company) : null;
  const regionKey  = item.region  ? drawerKey("region",  item.region)  : null;

  const company = companyKey
    ? `<span class="clickable-link" onclick="openDrawerByKey('${companyKey}')">${escapeHTML(item.company)}</span>`
    : "—";
  const region = regionKey
    ? `<span class="clickable-link" onclick="openDrawerByKey('${regionKey}')">${escapeHTML(item.region)}</span>`
    : "—";

  return `<tr>
    <td><span class="score-badge" style="color:${c};background:${bg}">${score}</span>${signals}</td>
    <td><span class="proj-title clickable-link" onclick="openOppDrawer(${item.id})">${escapeHTML(item.title||"")}</span>
        <span class="proj-industry">${escapeHTML(item.industry||"")}</span></td>
    <td>${sourceChip(item.source||"")}</td>
    <td>${company}</td>
    <td>${region}</td>
    <td>${statusChip(item.pipeline_status)}</td>
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

// ── Filters & Data ────────────────────────────────────────────────────────────

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

  const sidebarItems = document.querySelectorAll(".sidebar-item");
  sidebarItems.forEach(item => {
    item.addEventListener("click", () => {
      sidebarItems.forEach(i => i.classList.remove("active"));
      item.classList.add("active");
    });
  });
  if (sidebarItems[1]) sidebarItems[1].addEventListener("click", () => {
    el("tbody-projects")?.closest(".section-card")?.scrollIntoView({behavior:"smooth", block:"start"});
  });
  if (sidebarItems[2]) sidebarItems[2].addEventListener("click", () => {
    el("tbody-news")?.closest(".section-card")?.scrollIntoView({behavior:"smooth", block:"start"});
  });

  load();
});
