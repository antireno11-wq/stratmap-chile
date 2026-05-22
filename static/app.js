const NEWS_SOURCES = new Set([
  "Portal Minero","BioBioChile","Emol","Cooperativa",
  "Minería Chilena","COCHILCO Noticias","Diario Financiero",
  "Revista EI","Radio U. de Chile","Radio Universidad de Chile","RSS",
  "Lithium Chile","InfoMineria","Mundo Minería","MLP Proveedores"
]);

// Fuentes de empleos — aparecen en Empleos activos, NUNCA en Noticias del Sector
const EMPLEOS_SOURCES = new Set(["BHP Careers","AMSA Careers","Lundin Careers","Collahuasi Careers","Teck Careers"]);

// Fuentes que SIEMPRE son proyectos, nunca noticias
const PROJECT_SOURCES = new Set(["MOP","Chile Compra","COCHILCO","SICEP","Ariba Codelco","SIGEX","ENAMI","Codelco"]);
// SEA aparece solo como señal (⚡), no como proyecto en la tabla
const SEA_SOURCES = new Set(["sea","SEA"]);

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

// Keywords that indicate an item is NOT mining-related news
const NON_MINING_KEYWORDS = [
  "fútbol","futbol","deporte","partido","gol","jugador","club","torneo",
  "baleado","disparado","pelea","riña","accidente vial","tránsito",
  "ketamina","droga","detenido","imputado","tribunal",
  "alumbrado público","vertedero municipal","hospital concesionado",
  "dólar cierra","tipo de cambio","bolsa de","mercado financiero",
  "premundi","nómina sub","clasificatorio"
];

function isSea(item) {
  const src = (item.source || "").toLowerCase();
  // Solo ocultar items genuinamente del SEA (evaluación ambiental)
  // ENAMI, Codelco, InfoMineria, etc. tienen su propio source
  return src === "sea" && (item.phase || "").toLowerCase() !== "licitación";
}

function isNews(item) {
  const src = item.source || "";
  if (isSea(item)) return false;
  if (PROJECT_SOURCES.has(src)) return false;
  if (EMPLEOS_SOURCES.has(src)) return false;  // empleos van a sección propia
  if (item.phase === "Noticia") return true;
  return NEWS_SOURCES.has(src);
}

function isRelevantNews(item) {
  if (!isNews(item)) return false;
  const title = (item.title || "").toLowerCase();
  // Filtrar noticias claramente no mineras
  if (NON_MINING_KEYWORDS.some(kw => title.includes(kw))) return false;
  return true;
}

function el(id) { return document.getElementById(id); }

function escapeHTML(str) {
  return String(str||"").replaceAll("&","&amp;").replaceAll("<","&lt;")
    .replaceAll(">","&gt;").replaceAll('"',"&quot;").replaceAll("'","&#039;");
}

const SOURCE_COLORS = {
  "SEA":               ["#1d4ed8","#eff6ff"],
  "Chile Compra":       ["#15803d","#f0fdf4"],
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

// ── Company logo helpers ───────────────────────────────────────────────────
const COMPANY_COLORS = {
  codelco:    "#1e3a5f", bhp:        "#d97706",
  antofagasta:"#7c3aed", sqm:        "#0891b2",
  collahuasi: "#dc2626", teck:       "#15803d",
  enami:      "#b45309", lundin:     "#9333ea",
  escondida:  "#d97706", centinela:  "#0f766e",
  pelambres:  "#1d4ed8", candelaria: "#0f766e",
  spence:     "#d97706", andacollo:  "#7c3aed",
};
function companyColor(name) {
  const lower = (name || "").toLowerCase();
  for (const [k, c] of Object.entries(COMPANY_COLORS)) {
    if (lower.includes(k)) return c;
  }
  let h = 0;
  for (let i = 0; i < (name||"").length; i++) h = (name.charCodeAt(i) + ((h<<5)-h)) | 0;
  return ["#1e3a5f","#7c3aed","#0891b2","#dc2626","#15803d","#d97706","#db2777","#0f766e"][Math.abs(h)%8];
}
function companyInitials(name) {
  if (!name) return "?";
  const clean = name.replace(/\b(minera|mining|compañía|compania|sociedad|s\.a\.|ltda\.?|spa\.?|chile)\b/gi, "").trim();
  const words = clean.split(/\s+/).filter(Boolean);
  if (words.length >= 2) return (words[0][0] + words[1][0]).toUpperCase();
  return clean.substring(0, 2).toUpperCase();
}

function itemDate(item) {
  // Prefer published_at (real publication date) over updated_at (ingestion date)
  return item.published_at || item.updated_at || item.created_at || null;
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

  // Cargar pipeline, notas y servicios en paralelo
  const [pipelineRes, notesRes, aiFitRes, servicesRes] = await Promise.all([
    apiFetch(`/opportunities/${oppId}/pipeline`).then(r => r.json()),
    apiFetch(`/opportunities/${oppId}/notes`).then(r => r.json()),
    apiFetch(`/opportunities/${oppId}/ai-fit`).then(r => r.json()).catch(()=>({})),
    apiFetch(`/opportunities/${oppId}/services`).then(r => r.json()).catch(()=>({})),
  ]);

  const score = item.radar_score ?? item.score ?? 0;
  const [sc, sbg] = scoreColor(score);
  const notes = notesRes.items || [];

  el("drawer-body").innerHTML = `
    <div class="drawer-stats" style="grid-template-columns:repeat(${isLoggedIn ? 3 : 2},1fr)">
      ${isLoggedIn ? `<div class="drawer-stat"><div class="drawer-stat-val" style="color:${sc}">${score}</div><div class="drawer-stat-lbl">Score</div></div>` : ''}
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
      <span>Publicado: ${fmtDate(itemDate(item))}</span>
      ${item.url ? `<a href="${item.url}" target="_blank" class="contact-link" style="margin-top:4px">🔗 Ver fuente original</a>` : ""}
      ${buildMapLink(item)}
    </div>

    ${renderServicesBlock(servicesRes, oppId)}
  `;
};

window.savePipeline = async function(oppId) {
  const status = el("pipeline-status").value;
  const assignee = el("pipeline-assignee").value.trim() || null;
  await apiFetch(`/opportunities/${oppId}/pipeline`, {
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
  const res = await apiFetch(`/opportunities/${oppId}/notes`, {
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
    const r = await apiFetch(`/contacts?company=${encodeURIComponent(company)}`);
    const data = await r.json();
    return data.items || [];
  } catch(e) { return []; }
}

window.deleteContact = async function(contactId, company) {
  if (!confirm("¿Eliminar este contacto?")) return;
  await apiFetch(`/contacts/${contactId}`, {method:"DELETE"});
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
  await apiFetch("/contacts", {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify({name, company, role:role||null, email:email||null, phone:phone||null, linkedin_url:linkedin||null})
  });
  const contacts = await fetchContacts(company);
  el("drawer-contacts").innerHTML = renderContactsList(contacts, company);
};

function renderServicesBlock(servicesData, oppId) {
  const sn = servicesData?.services_needed;

  const PRIORITY_COLOR = { alta: '#dc2626', media: '#d97706', baja: '#16a34a' };
  const PRIORITY_BG    = { alta: '#fef2f2', media: '#fffbeb', baja: '#f0fdf4' };

  if (!sn) {
    return `
      <div style="margin-top:20px">
        <div class="drawer-section-title">🔍 Servicios que se van a necesitar</div>
        <div style="background:#f8fafc;border-radius:10px;padding:14px;text-align:center;border:1.5px dashed #e2e8f0">
          <div style="font-size:13px;color:#94a3b8;margin-bottom:8px">Análisis aún no disponible</div>
          <button onclick="analyzeServices(${oppId})" style="font-size:11px;padding:5px 12px;background:#1e3a5f;color:#fff;border:none;border-radius:6px;cursor:pointer;font-weight:600">
            ✨ Analizar con IA
          </button>
        </div>
      </div>`;
  }

  // Agrupar por categoría
  const byCategory = {};
  (sn.services || []).forEach(s => {
    const cat = s.category || "Otros";
    if (!byCategory[cat]) byCategory[cat] = [];
    byCategory[cat].push(s);
  });

  const cats = Object.entries(byCategory).map(([cat, svcs]) => `
    <div style="margin-bottom:12px">
      <div style="font-size:10px;font-weight:800;text-transform:uppercase;letter-spacing:.06em;color:#475569;margin-bottom:6px">${escapeHTML(cat)}</div>
      <div style="display:flex;flex-direction:column;gap:5px">
        ${svcs.map(s => {
          const pc = PRIORITY_COLOR[s.priority] || '#64748b';
          const pb = PRIORITY_BG[s.priority] || '#f8fafc';
          return `<div style="display:flex;align-items:flex-start;gap:8px;padding:8px 10px;background:${pb};border-radius:8px;border:1px solid ${pc}22">
            <span style="font-size:9px;font-weight:800;color:${pc};background:${pc}18;padding:2px 6px;border-radius:99px;white-space:nowrap;margin-top:1px">${(s.priority||'').toUpperCase()}</span>
            <div>
              <div style="font-size:12px;font-weight:700;color:#1e293b">${escapeHTML(s.name||"")}</div>
              ${s.description ? `<div style="font-size:11px;color:#64748b;margin-top:2px">${escapeHTML(s.description)}</div>` : ''}
            </div>
          </div>`;
        }).join('')}
      </div>
    </div>`).join('');

  return `
    <div style="margin-top:20px">
      <div class="drawer-section-title">🔍 Servicios que se van a necesitar</div>
      <div style="background:linear-gradient(135deg,#1e3a5f08,#0ea5e908);border:1.5px solid #0ea5e920;border-radius:10px;padding:12px;margin-bottom:12px">
        <div style="font-size:12px;font-weight:600;color:#0369a1">${escapeHTML(sn.phase_label||"")} · Horizonte: ~${sn.horizon_months || '?'} meses</div>
        ${sn.summary ? `<div style="font-size:11px;color:#475569;margin-top:3px">${escapeHTML(sn.summary)}</div>` : ''}
      </div>
      ${cats}
    </div>`;
}

window.analyzeServices = async function(oppId) {
  const btn = event.target;
  btn.textContent = "Analizando...";
  btn.disabled = true;
  try {
    const r = await apiFetch(`/admin/run-demand-intel?batch_size=1&max_batches=1&source=`, {method:'POST'});
    // Re-abrir el drawer para refrescar
    await openOppDrawer(oppId);
  } catch(e) {
    btn.textContent = "Error — reintentar";
    btn.disabled = false;
  }
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

function buildMapLink(item) {
  // Construir link al mapa con las coordenadas del proyecto
  const raw = item.raw || {};
  let lat = null, lng = null;

  // SIGEX coords
  if (raw.lat && raw.lng) { lat = parseFloat(raw.lat); lng = parseFloat(raw.lng); }
  // ENAMI/SEA coords
  else if (raw.NUEVO_X && raw.NUEVO_Y) { lng = parseFloat(raw.NUEVO_X); lat = parseFloat(raw.NUEVO_Y); }
  else if (raw.X && raw.Y) { lng = parseFloat(raw.X); lat = parseFloat(raw.Y); }

  // Validar rango Chile
  const valid = lat && lng && lat < -17 && lat > -56 && lng < -60 && lng > -76;
  if (!valid) {
    // Sin coords exactas — ir al mapa filtrado por título
    const q = encodeURIComponent(item.title || '');
    return `<a href="/mapa.html?q=${q}" class="contact-link" style="margin-top:4px">🗺 Ver en mapa</a>`;
  }
  return `<a href="/mapa.html?lat=${lat}&lng=${lng}&zoom=12&id=${item.id}" class="contact-link" style="margin-top:4px">📍 Ver ubicación en mapa</a>`;
}


// ── Company alias matching (espejo de sea_signals.py) ─────────────────────
const SEA_COMPANY_ALIASES = {
  "codelco":             ["codelco", "corporación nacional del cobre", "corp. nac. del cobre"],
  "bhp":                 ["bhp", "escondida", "minera escondida", "bhp billiton"],
  "sqm":                 ["sqm", "soquimich", "sociedad química y minera"],
  "collahuasi":          ["collahuasi", "doña inés de collahuasi"],
  "antofagasta minerals":["antofagasta minerals", "antofagasta plc", "los pelambres", "centinela", "zaldívar", "antucoya"],
  "teck":                ["teck", "quebrada blanca", "carmen de andacollo"],
  "kinross":             ["kinross", "la coipa", "maricunga"],
  "barrick":             ["barrick", "pascua-lama", "veladero"],
  "glencore":            ["glencore", "lomas bayas"],
  "enami":               ["enami", "empresa nacional de minería", "empresa nacional de mineria"],
  "angloamerican":       ["anglo american", "angloamerican", "los bronces", "el soldado"],
};

function seaMatchesCompany(seaCompany, queryCompany) {
  const sc = (seaCompany || "").toLowerCase().trim();
  const qc = (queryCompany || "").toLowerCase().trim();
  if (!sc || !qc) return false;
  if (sc.includes(qc) || qc.includes(sc)) return true;
  for (const variants of Object.values(SEA_COMPANY_ALIASES)) {
    const scMatch = variants.some(v => sc.includes(v));
    const qcMatch = variants.some(v => qc.includes(v));
    if (scMatch && qcMatch) return true;
  }
  return sc.split(" ").filter(w => w.length > 5).some(w => qc.includes(w));
}

async function openDrawer(type, value) {
  const items = type === "company"
    ? allItems.filter(i => (i.company||"") === value)
    : allItems.filter(i => (i.region||"") === value);

  // SEA prospectos: match fuzzy por nombre de empresa (solo en drawer de empresa)
  const seaItems = type === "company"
    ? allItems.filter(i => isSea(i) && seaMatchesCompany(i.company, value) && (i.company||"") !== value)
    : [];

  const LICIT_SRC = new Set(['Codelco','ENAMI','SEA','sea','MLP Proveedores','Ariba Codelco','Chile Compra','MOP','COCHILCO']);
  const projects    = items.filter(i => !isNews(i));
  const licitaciones = projects.filter(i =>  LICIT_SRC.has(i.source));
  const concesiones  = projects.filter(i => !LICIT_SRC.has(i.source));
  const news = items.filter(i => isNews(i));

  const scores = licitaciones.map(i => i.radar_score ?? i.score ?? 0).filter(s => s > 0);
  const avgScore = scores.length ? Math.round(scores.reduce((a,b)=>a+b,0)/scores.length) : 0;
  const withSignals = projects.filter(i => (i.signal_score||0) > 0).length;

  const distKey = type === "company" ? "industry" : "company";
  const dist = {};
  licitaciones.forEach(i => { const k = i[distKey]||"Sin datos"; dist[k]=(dist[k]||0)+1; });

  const total = Math.max(licitaciones.length, 1);
  const distRows = Object.entries(dist).sort((a,b)=>b[1]-a[1]).slice(0,6)
    .map(([k,v]) => `<div class="drawer-dist-row">
      <span>${escapeHTML(k)}</span>
      <div class="drawer-bar-wrap"><div class="drawer-bar" style="width:${Math.round(v/total*100)}%"></div></div>
      <span class="drawer-dist-n">${v}</span>
    </div>`).join("");

  function buildProjRows(list) {
    return list.slice(0, 15).map(i => {
      const score = i.radar_score ?? i.score ?? 0;
      const [c,bg] = scoreColor(score);
      drawerMap[`opp_${i.id}`] = {type:"opp", id: i.id};
      return `<tr>
        <td><span class="score-badge" style="color:${c};background:${bg}">${score}</span></td>
        <td><span class="proj-title clickable-link" style="max-width:220px" onclick="openOppDrawer(${i.id})">${escapeHTML(i.title||"")}</span>
            <span class="proj-industry">${escapeHTML(i[distKey]||"")}</span></td>
        <td>${statusChip(i.pipeline_status)}</td>
        <td>${fmtDate(itemDate(i))}</td>
        <td><a class="row-link" href="${i.url||"#"}" target="_blank">ver →</a></td>
      </tr>`;
    }).join("");
  }

  const licitRows    = buildProjRows(licitaciones);
  const concesRows   = buildProjRows(concesiones);

  const seaRows = seaItems.slice(0, 10).map(i => {
    const pts = i.score ?? 0;
    const phase = escapeHTML(i.phase || "En evaluación");
    return `<tr>
      <td><span class="phase-chip" style="background:#dcfce7;color:#15803d">${phase}</span></td>
      <td><a class="row-link" href="${i.url||"#"}" target="_blank" style="font-weight:600;color:var(--text);text-decoration:none">${escapeHTML(i.title||"")}</a></td>
      <td>${escapeHTML(i.region||"—")}</td>
      <td><a class="row-link" href="${i.url||"#"}" target="_blank">ver →</a></td>
    </tr>`;
  }).join("");

  el("drawer-title").textContent = value;
  el("drawer-subtitle").textContent = type === "company" ? "Mandante" : "Región";
  el("drawer-body").innerHTML = `
    <div class="drawer-stats">
      <div class="drawer-stat"><div class="drawer-stat-val">${licitaciones.length}</div><div class="drawer-stat-lbl">Licitaciones</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${concesiones.length}</div><div class="drawer-stat-lbl">Concesiones</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${withSignals}</div><div class="drawer-stat-lbl">Con señales ⚡</div></div>
      <div class="drawer-stat"><div class="drawer-stat-val">${news.length}</div><div class="drawer-stat-lbl">Noticias</div></div>
    </div>

    ${type === "company" ? `
    <div class="drawer-section-title">🤖 Resumen IA</div>
    <div id="drawer-ai-summary" style="padding:4px 0 12px"><p class="drawer-empty">Cargando...</p></div>

    <div class="drawer-section-title">🌡️ Temperatura</div>
    <div id="drawer-heat" style="padding:4px 0 12px"><p class="drawer-empty">Sin datos de temperatura aún</p></div>
    ` : ""}
    ${licitaciones.length > 0 ? `
    <div class="drawer-section-title">📋 Licitaciones (${licitaciones.length})</div>
    ${distRows ? `<div class="drawer-dist" style="margin-bottom:12px">${distRows}</div>` : ""}
    <div class="tableWrap" style="margin-bottom:20px">
      <table>
        <thead><tr><th>Score</th><th>Licitación</th><th>Pipeline</th><th>Fecha</th><th></th></tr></thead>
        <tbody>${licitRows}</tbody>
      </table>
    </div>` : ""}
    ${concesiones.length > 0 ? `
    <div class="drawer-section-title">⛏️ Concesiones SIGEX (${concesiones.length})</div>
    <div class="tableWrap" style="margin-bottom:20px">
      <table>
        <thead><tr><th>Score</th><th>Concesión</th><th>Pipeline</th><th>Fecha</th><th></th></tr></thead>
        <tbody>${concesRows}</tbody>
      </table>
    </div>` : ""}
    ${seaItems.length > 0 ? `
    <div class="drawer-section-title">🌿 Prospectos SEA (${seaItems.length})</div>
    <div class="tableWrap" style="margin-bottom:20px">
      <table>
        <thead><tr><th>Estado</th><th>Proyecto</th><th>Región</th><th></th></tr></thead>
        <tbody>${seaRows}</tbody>
      </table>
    </div>` : ""}
    ${type === "company" ? `
    <div class="drawer-section-title">🔧 Servicios que van a necesitar</div>
    <div id="drawer-services" style="padding:4px 0 12px"><p class="drawer-empty">Cargando...</p></div>

    <div class="drawer-section-title">📊 Mi pipeline con este mandante</div>
    <div id="drawer-pipeline-dist" style="padding:4px 0 12px"><p class="drawer-empty">Cargando...</p></div>

    <div class="drawer-section-title">Contactos</div>
    <div id="drawer-contacts"><p class="drawer-empty">Cargando...</p></div>` : ""}
  `;

  el("drawer").classList.add("open");
  el("drawer-overlay").classList.add("open");

  if (type === "company") {
    // Cargar todo en paralelo
    const [contacts, detailData, summaryData] = await Promise.allSettled([
      fetchContacts(value),
      apiFetch(`/mandantes/detail?company=${encodeURIComponent(value)}`).then(r => r.json()).catch(() => null),
      apiFetch(`/mandantes/summary/${encodeURIComponent(value)}`).then(r => r.json()).catch(() => null),
    ]);

    // ── Contactos ──────────────────────────────────────────────────────────────
    const dcEl = el("drawer-contacts");
    if (dcEl) dcEl.innerHTML = renderContactsList(
      contacts.status === "fulfilled" ? contacts.value : [], value
    );

    // ── Heat Score (desde mandantesData ya cargado) ────────────────────────────
    const mData = mandantesData.find(m => (m.company||"").toLowerCase() === value.toLowerCase());
    if (mData && mData.heat_score > 0) {
      const heatEl = el("drawer-heat");
      if (heatEl) {
        const hColor = mData.heat_score >= 80 ? "#dc2626" : mData.heat_score >= 60 ? "#d97706" : "#0891b2";
        const topics = (mData.trending_topics || []).slice(0,4)
          .map(t => `<span style="background:#f1f5f9;color:#475569;padding:2px 8px;border-radius:4px;font-size:11px">${escapeHTML(t)}</span>`).join(" ");
        heatEl.innerHTML = `
          <div style="display:flex;align-items:center;gap:10px;margin-bottom:6px">
            <div style="font-size:28px;font-weight:900;color:${hColor}">${mData.heat_score}</div>
            <div>
              <div style="font-weight:700;font-size:13px">${escapeHTML(mData.heat_label||"")}</div>
              <div style="font-size:11px;color:var(--muted)">${escapeHTML(mData.heat_reason||"")}</div>
            </div>
          </div>
          <div style="display:flex;gap:4px;flex-wrap:wrap">${topics}</div>`;
      }
    }

    // ── Resumen IA ─────────────────────────────────────────────────────────────
    const sumEl = el("drawer-ai-summary");
    if (sumEl && summaryData.status === "fulfilled" && summaryData.value?.summary) {
      const s = summaryData.value.summary;
      const minerales = (s.minerales_principales || []).join(" · ");
      sumEl.innerHTML = `
        <div style="font-size:12px;color:var(--text);line-height:1.55;margin-bottom:8px">${escapeHTML(s.descripcion||"")}</div>
        <div style="display:flex;gap:8px;flex-wrap:wrap">
          ${s.tipo ? `<span style="background:#eff6ff;color:#1d4ed8;padding:2px 10px;border-radius:5px;font-size:11px;font-weight:700">${escapeHTML(s.tipo)}</span>` : ""}
          ${minerales ? `<span style="background:#f0fdf4;color:#15803d;padding:2px 10px;border-radius:5px;font-size:11px;font-weight:600">⛏ ${escapeHTML(minerales)}</span>` : ""}
        </div>
        ${s.actividad_reciente ? `<div style="font-size:11px;color:var(--muted);margin-top:6px">${escapeHTML(s.actividad_reciente)}</div>` : ""}`;
    } else if (sumEl) {
      sumEl.innerHTML = `<p class="drawer-empty">Sin resumen disponible</p>`;
    }

    // ── Servicios demandados ───────────────────────────────────────────────────
    const svcEl = el("drawer-services");
    if (svcEl && detailData.status === "fulfilled" && detailData.value?.top_services?.length) {
      const svcs = detailData.value.top_services;
      const maxCount = svcs[0].count || 1;
      svcEl.innerHTML = svcs.map(s => `
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
          <span style="font-size:12px;min-width:160px;color:var(--text)">${escapeHTML(s.category)}</span>
          <div style="flex:1;height:6px;background:#e2e8f0;border-radius:3px">
            <div style="width:${Math.round(s.count/maxCount*100)}%;height:100%;background:#1d4ed8;border-radius:3px"></div>
          </div>
          <span style="font-size:11px;color:var(--muted);min-width:20px;text-align:right">${s.count}</span>
        </div>`).join("");
    } else if (svcEl) {
      svcEl.innerHTML = `<p class="drawer-empty">Sin análisis de demanda aún</p>`;
    }

    // ── Mi Pipeline con este mandante ──────────────────────────────────────────
    const pipeEl = el("drawer-pipeline-dist");
    if (pipeEl) {
      const stages = ["En análisis","Postular","Presentada","Adjudicada","Perdida"];
      const pipeCounts = {};
      stages.forEach(s => { pipeCounts[s] = 0; });
      projects.filter(i => i.pipeline_status && stages.includes(i.pipeline_status))
              .forEach(i => { pipeCounts[i.pipeline_status]++; });
      const PIPE_COLORS = {"En análisis":"#92400e","Postular":"#15803d","Presentada":"#7c3aed","Adjudicada":"#15803d","Perdida":"#dc2626"};
      const PIPE_BG    = {"En análisis":"#fef3c7","Postular":"#f0fdf4","Presentada":"#f5f3ff","Adjudicada":"#dcfce7","Perdida":"#fef2f2"};
      const pipeHtml = stages.filter(s => pipeCounts[s] > 0).map(s =>
        `<div style="display:flex;align-items:center;justify-content:space-between;padding:5px 8px;background:${PIPE_BG[s]};border-radius:6px;margin-bottom:4px">
          <span style="font-size:12px;color:${PIPE_COLORS[s]};font-weight:600">${s}</span>
          <span style="font-size:13px;font-weight:800;color:${PIPE_COLORS[s]}">${pipeCounts[s]}</span>
        </div>`).join("");
      pipeEl.innerHTML = pipeHtml || `<p class="drawer-empty">Sin oportunidades en pipeline</p>`;
    }
  }
}

function closeDrawer() {
  el("drawer").classList.remove("open");
  el("drawer-overlay").classList.remove("open");
  currentOppId = null;
}

// ── Rows ──────────────────────────────────────────────────────────────────────

// AI fits cache
const aiFitsCache = {};

async function loadAiFits() {
  try {
    const res = await apiFetch('/ai/fits?min_score=1&limit=500');
    const data = await res.json();
    (data.items || []).forEach(item => {
      aiFitsCache[item.id] = {
        fit_score: item.fit_score,
        fit_reason: item.fit_reason,
        service_applicable: item.service_applicable,
        contact_suggestion: item.contact_suggestion
      };
    });
  } catch(e) {}
}

function aiFitBadge(oppId) {
  const fit = aiFitsCache[oppId];
  if (!fit || !fit.fit_score) return '<span style="font-size:10px;color:#d1d5db">—</span>';
  let color, bg;
  if (fit.fit_score >= 70) { color='#15803d'; bg='#f0fdf4'; }
  else if (fit.fit_score >= 50) { color='#92400e'; bg='#fef3c7'; }
  else if (fit.fit_score >= 30) { color='#c2410c'; bg='#fff7ed'; }
  else { color='#475569'; bg='#f1f5f9'; }
  return `<span title="${escapeHTML(fit.fit_reason||'')}" style="display:inline-flex;align-items:center;padding:2px 8px;font-size:11px;font-weight:800;border-radius:6px;color:${color};background:${bg};cursor:help">${fit.fit_score}</span>`;
}

function projectRow(item) {
  const score    = item.radar_score ?? item.score ?? 0;
  const [c, bg]  = scoreColor(score);
  const signals  = item.signal_score > 0
    ? `<span class="signal-badge" title="${item.signal_detail ? '📊 ' + item.signal_detail : 'Señal activa'}">⚡ +${item.signal_score}</span>` : "";
  const initials = companyInitials(item.company);
  const logoColor = companyColor(item.company);
  const region = item.region
    ? `<span class="proj-card-region">${escapeHTML(item.region)}</span>` : "";
  const status = item.pipeline_status ? statusChip(item.pipeline_status) : "";

  return `
    <div class="proj-card" onclick="openOppDrawer(${item.id})">
      <div class="proj-card-score-col">
        ${isLoggedIn ? `<div class="proj-card-score" style="color:${c};background:${bg}">${score}</div>` : ""}
      </div>
      <div class="proj-card-logo" style="background:${logoColor}">${escapeHTML(initials)}</div>
      <div class="proj-card-body">
        <div class="proj-card-company">${escapeHTML(item.company || "—")}</div>
        <div class="proj-card-title">${escapeHTML(item.title || "")}</div>
        <div class="proj-card-meta">
          ${region}
          ${sourceChip(item.source || "")}
          ${signals}
          ${status}
        </div>
      </div>
    </div>`;
}

function newsRow(item) {
  return `
    <div class="news-card">
      <div class="news-card-left">
        ${sourceChip(item.source || "")}
        <span class="news-date">${fmtDate(itemDate(item))}</span>
      </div>
      <a class="news-card-title" href="${item.url||"#"}" target="_blank" rel="noreferrer">${escapeHTML(item.title||"")}</a>
    </div>`;
}

// ── Filters & Data ────────────────────────────────────────────────────────────

async function fetchJSON(url) {
  const res = await apiFetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return res.json();
}

let activeFilters = { industry: new Set(), region: new Set(), source: new Set() };
let allItems = [];
let newsItems = []; // cargado desde /noticias separado

function syncFilterUI() {
  // Sync checkboxes to match activeFilters state
  ['industry','region','source'].forEach(key => {
    const container = el(`filter-${key}`);
    if (!container) return;
    container.querySelectorAll('input[type=checkbox]').forEach(cb => {
      cb.checked = activeFilters[key].has(cb.value);
    });
  });
}

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

function renderPagination(containerId, total, currentPg, onPage) {
  const totalPages = Math.ceil(total / PAGE_SIZE);
  if (totalPages <= 1) { const c = document.getElementById(containerId); if(c) c.innerHTML = ''; return; }
  const pages = [];
  for (let i = 1; i <= totalPages; i++) {
    const active = i === currentPg;
    pages.push(`<button onclick="(${onPage})(${i})" style="padding:4px 10px;margin:0 2px;border:1px solid ${active?'#1a56db':'#d1d5db'};background:${active?'#1a56db':'#fff'};color:${active?'#fff':'#374151'};border-radius:6px;font-size:12px;font-weight:${active?700:500};cursor:pointer">${i}</button>`);
  }
  const c = document.getElementById(containerId);
  if (c) c.innerHTML = `<div style="display:flex;align-items:center;gap:4px;padding:10px 0;justify-content:center">${pages.join('')}</div>`;
}

function renderFiltered() {
  const filtered = applyFilters(allItems);

  // Separar fuentes: licitaciones (alta señal comercial) vs concesiones SIGEX
  const LICITACION_SOURCES = new Set(['Codelco','ENAMI','SEA','sea','MLP Proveedores']);
  const allProjects = filtered.filter(i => !isNews(i) && !isSea(i) && !i._isNews && !EMPLEOS_SOURCES.has(i.source));

  let licitaciones = allProjects.filter(i => LICITACION_SOURCES.has(i.source));
  let concesiones  = allProjects.filter(i => !LICITACION_SOURCES.has(i.source));

  // Apply region quick-filter chip to both
  if (window._activeRegion) {
    licitaciones = licitaciones.filter(i => i.region === window._activeRegion);
    concesiones  = concesiones.filter(i  => i.region === window._activeRegion);
  }

  // Sort ambas por score desc (o el sort activo)
  licitaciones = sortItems(licitaciones);
  concesiones  = sortItems(concesiones);

  // Noticias
  const news = newsItems.sort((a,b) => new Date(b.published_at||b.created_at||0) - new Date(a.published_at||a.created_at||0));

  // Reset pagination if out of range
  if ((currentPage.licitaciones - 1) * PAGE_SIZE >= licitaciones.length) currentPage.licitaciones = 1;
  if ((currentPage.projects  - 1) * PAGE_SIZE >= concesiones.length)  currentPage.projects  = 1;
  if ((currentPage.news      - 1) * PAGE_SIZE >= news.length)          currentPage.news      = 1;

  const licitPage = licitaciones.slice((currentPage.licitaciones-1)*PAGE_SIZE, currentPage.licitaciones*PAGE_SIZE);
  const projPage  = concesiones.slice((currentPage.projects-1)*PAGE_SIZE,  currentPage.projects*PAGE_SIZE);
  const newsPage  = news.slice((currentPage.news-1)*PAGE_SIZE, currentPage.news*PAGE_SIZE);

  // Badges
  const badgeLic = document.getElementById('badge-licitaciones');
  if (badgeLic) badgeLic.textContent = licitaciones.length;
  el('badge-projects').textContent = concesiones.length;
  el('badge-news').textContent = news.length;

  const scLic = document.getElementById('sc-licitaciones');
  if (scLic) scLic.textContent = licitaciones.length;
  el('sc-projects').textContent = concesiones.length;
  el('sc-news').textContent = news.length;

  // Render tables
  const tbodyLic = document.getElementById('tbody-licitaciones');
  if (tbodyLic) {
    tbodyLic.innerHTML = licitPage.length
      ? licitPage.map(projectRow).join('')
      : `<div class="muted-row">Sin licitaciones activas</div>`;
  }

  el('tbody-projects').innerHTML = projPage.length
    ? projPage.map(projectRow).join('')
    : `<div class="muted-row">Sin concesiones</div>`;

  el('tbody-news').innerHTML = newsPage.length
    ? newsPage.map(newsRow).join('')
    : `<div class="muted-row">Sin noticias</div>`;

  // Pagination
  renderPagination('pagination-licitaciones', licitaciones.length, currentPage.licitaciones,
    'function(p){currentPage.licitaciones=p;renderFiltered()}');
  renderPagination('pagination-projects', concesiones.length, currentPage.projects,
    'function(p){currentPage.projects=p;renderFiltered()}');
  renderPagination('pagination-news', news.length, currentPage.news,
    'function(p){currentPage.news=p;renderFiltered()}');

  // Stat cards
  el('stat-projects').textContent = allProjects.length.toLocaleString('es-CL');
  el('stat-news').textContent = news.length;
  el('stat-signals').textContent = allProjects.filter(i => (i.radar_score ?? i.score ?? 0) > 50).length;

  // Empleos activos — sumar todos los scrapers de empleo
  const empEl = document.getElementById('stat-empleos');
  if (empEl) {
    const totalEmpleos = (window._empleosData || []).reduce((s, e) => s + (e.total_jobs || 0), 0);
    empEl.textContent = totalEmpleos > 0 ? totalEmpleos.toLocaleString('es-CL') : '—';
  }

  // Hide signal stats if not logged in
  const signalStatEl = document.getElementById('stat-signals')?.closest('.stat-card');
  if (signalStatEl) signalStatEl.style.display = isLoggedIn ? '' : 'none';

  // ── Region quick-filter chips ──
  const chipsEl = document.getElementById('region-chips');
  if (chipsEl) {
    const regionCounts = {};
    allItems.filter(i => !isNews(i) && !i._isNews && !EMPLEOS_SOURCES.has(i.source)).forEach(i => {
      if (i.region) regionCounts[i.region] = (regionCounts[i.region] || 0) + 1;
    });
    const topRegions = Object.entries(regionCounts).sort((a,b) => b[1]-a[1]).slice(0, 8);
    if (topRegions.length > 1) {
      chipsEl.style.paddingBottom = '10px';
      chipsEl.innerHTML = `
        <button onclick="filterByRegion(null)" class="chip ${!window._activeRegion ? 'chip-active' : ''}">Todas las regiones</button>
        ${topRegions.map(([r, n]) =>
          `<button onclick="filterByRegion('${r}')" class="chip ${window._activeRegion === r ? 'chip-active' : ''}">${r} <span style="opacity:.6">${n}</span></button>`
        ).join('')}
      `;
    } else { chipsEl.style.paddingBottom = '0'; }
  }

  const updLic = document.getElementById('upd-licitaciones');
  if (updLic) updLic.textContent = "Actualizado ahora";
  el("upd-projects").textContent = "Actualizado ahora";
  el("upd-news").textContent = "Actualizado ahora";
  el("status").textContent = `${allProjects.length.toLocaleString('es-CL')} proyectos · ${news.length} noticias`;
}


// ── Mandantes ──────────────────────────────────────────────────────────────
let mandantesData = [];

function scoreColorMandante(s) {
  if (s >= 90) return ['#15803d', '#f0fdf4'];
  if (s >= 70) return ['#1a56db', '#eff6ff'];
  if (s >= 50) return ['#92400e', '#fef3c7'];
  return ['#6b7280', '#f9fafb'];
}

async function loadMandantes() {
  const section = document.getElementById('section-mandantes');
  if (!isLoggedIn) { if (section) section.style.display = 'none'; return; }
  if (section) section.style.display = '';

  try {
    const res = await apiFetch('/mandantes');
    const data = await res.json();
    mandantesData = data.mandantes || [];
    renderMandantes();
  } catch(e) {
    const grid = document.getElementById('mandantes-grid');
    if (grid) grid.innerHTML = '<div class="mandantes-login-hint">Error cargando mandantes</div>';
  }
}

function renderMandantes() {
  const grid = document.getElementById('mandantes-grid');
  const badge = document.getElementById('badge-mandantes');
  if (!grid) return;

  if (!mandantesData.length) {
    grid.innerHTML = '<div class="mandantes-login-hint">Sin datos de mandantes aún</div>';
    return;
  }

  // En home solo mostramos top 10; en mandantes.html mostramos todos
  const isHome = !!document.getElementById('section-mandantes');
  const displayData = isHome ? mandantesData.slice(0, 14) : mandantesData;

  if (badge) badge.textContent = mandantesData.length;
  // Update sidebar count
  const scM = document.getElementById('sc-mandantes');
  if (scM) scM.textContent = mandantesData.length;

  const maxScore = Math.max(...displayData.map(m => m.score_consolidado || 0), 1);

  grid.innerHTML = displayData.map(m => {
    const score = m.score_consolidado || 0;
    const [sc, sbg] = scoreColorMandante(score);
    const pct = Math.round((score / maxScore) * 100);
    const slug = encodeURIComponent(m.company);

    const meta = [];
    if (m.n_proyectos > 0) meta.push(`<span class="mandante-meta-item">🏗 ${m.n_proyectos} proy.</span>`);
    if (m.n_sea > 0)       meta.push(`<span class="mandante-meta-item">🌿 ${m.n_sea} SEA</span>`);
    if ((m.total_jobs||0) > 0) meta.push(`<span class="mandante-meta-item">👷 ${m.total_jobs}</span>`);

    // Heat badge — solo si hay score IA calculado
    const heat = m.heat_score || 0;
    let heatBadge = '';
    if (heat >= 80) heatBadge = `<span class="heat-badge heat-hot" title="${escapeHTML(m.heat_reason||'')}">🔥 Muy activa</span>`;
    else if (heat >= 60) heatBadge = `<span class="heat-badge heat-warm" title="${escapeHTML(m.heat_reason||'')}">⚡ Activa</span>`;
    else if (heat >= 40) heatBadge = `<span class="heat-badge heat-mid" title="${escapeHTML(m.heat_reason||'')}">📊 Moderada</span>`;

    // Topics trending
    const topics = (m.trending_topics || []).slice(0,2).map(t =>
      `<span class="mandante-topic">${escapeHTML(t)}</span>`
    ).join('');

    return `
      <div class="mandante-card ${heat >= 60 ? 'mandante-card-hot' : ''}"
           onclick="window.location.href='/mandante.html?empresa=${slug}'">
        ${heatBadge ? `<div class="mandante-heat-row">${heatBadge}</div>` : ''}
        <div class="mandante-card-name">${escapeHTML(m.company)}</div>
        <div class="mandante-card-score" style="color:${sc}">${score}</div>
        <div class="mandante-card-meta">${meta.join('')}</div>
        ${topics ? `<div class="mandante-topics">${topics}</div>` : ''}
        <div class="mandante-card-bar" style="width:${pct}%"></div>
      </div>`;
  }).join('');
}

// ── Session state ─────────────────────────────────────────────────────────────
let isLoggedIn = false;
let currentSort = { by: null, dir: 'desc' };
let currentPage = { projects: 1, news: 1, licitaciones: 1 };
const PAGE_SIZE = 20;

function updateSortArrows() {
  ['score','title','company','region','date'].forEach(f => {
    const el = document.getElementById('arr-' + f);
    if (!el) return;
    el.textContent = (currentSort.by === f) ? (currentSort.dir === 'desc' ? ' ↓' : ' ↑') : '';
  });
}

function setSortBy(field) {
  currentPage.projects = 1;
  currentPage.news = 1;
  if (currentSort.by === field) {
    currentSort.dir = currentSort.dir === 'desc' ? 'asc' : 'desc';
  } else {
    currentSort.by = field;
    currentSort.dir = 'desc';
  }
  updateSortArrows();
  allItems = sortItems(allItems);
  renderFiltered();
}

function sortItems(items) {
  const sortBy = currentSort.by || (isLoggedIn ? 'score' : 'date');
  const dir = currentSort.dir === 'asc' ? 1 : -1;
  return [...items].sort((a, b) => {
    if (sortBy === 'score') {
      const sa = isLoggedIn ? (a.radar_score || a.score || 0) : (a.score || 0);
      const sb = isLoggedIn ? (b.radar_score || b.score || 0) : (b.score || 0);
      return dir * (sb - sa);
    }
    if (sortBy === 'date') {
      return dir * (new Date(itemDate(b)||0) - new Date(itemDate(a)||0));
    }
    if (sortBy === 'company') return dir * (a.company||'').localeCompare(b.company||'', 'es');
    if (sortBy === 'region')  return dir * (a.region||'').localeCompare(b.region||'', 'es');
    if (sortBy === 'title')   return dir * (a.title||'').localeCompare(b.title||'', 'es');
    return 0;
  });
}

// ── Empleos por empresa ────────────────────────────────────────────────────────
async function loadEmpleos() {
  const section = document.getElementById('section-empleos');
  if (!isLoggedIn) { if (section) section.style.display = 'none'; return; }
  if (section) section.style.display = '';

  try {
    const res = await apiFetch('/empleos/resumen');
    const data = await res.json();
    window._empleosData = data.empresas || [];
    renderEmpleos(data.empresas || []);
  } catch(e) {
    const grid = document.getElementById('empleos-grid');
    if (grid) grid.innerHTML = '<div class="mandantes-login-hint">Error cargando señales de empleo</div>';
  }
}

// Normaliza nombres de empresa BHP/AMSA antes de agrupar
const BHP_NORM = {
  "bhp":                    "BHP CHILE INC",
  "bhp chile":              "BHP CHILE INC",
  "bhp chile inc":          "BHP CHILE INC",
  "minera escondida":       "BHP CHILE INC",
  "escondida":              "BHP CHILE INC",
  "minera spence":          "BHP CHILE INC",
  "spence":                 "BHP CHILE INC",
  "cas plazo fijo":         "BHP CHILE INC",
  "bhp billiton":           "BHP CHILE INC",
  "compania minera teck quebrada blanca": "TECK QUEBRADA BLANCA",
  "teck quebrada blanca":                 "TECK QUEBRADA BLANCA",
  "quebrada blanca":                      "TECK QUEBRADA BLANCA",
  "compania minera carmen de andacollo":  "CARMEN DE ANDACOLLO",
  "carmen de andacollo":                  "CARMEN DE ANDACOLLO",
  "teck chile":                           "TECK CHILE",
  "teck":                                 "TECK CHILE",
  "compania minera dona ines de collahuasi": "COLLAHUASI",
  "collahuasi":                              "COLLAHUASI",
  "minera collahuasi":                       "COLLAHUASI",
  "minera candelaria":                       "MINERA CANDELARIA",
  "candelaria":                     "MINERA CANDELARIA",
  "scm minera lumina copper chile": "MINERA CANDELARIA",
  "lumina copper":                  "MINERA CANDELARIA",
  "minera centinela":               "MINERA CENTINELA",
  "centinela":                      "MINERA CENTINELA",
  "minera los pelambres":   "MINERA LOS PELAMBRES",
  "pelambres":              "MINERA LOS PELAMBRES",
  "antofagasta minerals":   "ANTOFAGASTA MINERALS",
  "amsa":                   "ANTOFAGASTA MINERALS",
  "amsa - corporativo":     "ANTOFAGASTA MINERALS",
};

function normalizeEmpresa(name) {
  const k = (name || '').toLowerCase().trim();
  return BHP_NORM[k] || name;
}

function mergeEmpresas(empresas) {
  const merged = {};
  empresas.forEach(e => {
    const key = normalizeEmpresa(e.company || e.empresa || '');
    if (!merged[key]) {
      merged[key] = { ...e, company: key, empresa: key, total_jobs: 0, areas: {} };
    }
    merged[key].total_jobs += (e.total_jobs || 0);
    // Merge areas
    Object.entries(e.areas || {}).forEach(([area, n]) => {
      merged[key].areas[area] = (merged[key].areas[area] || 0) + n;
    });
    // Keep highest signal
    if ((e.top_signal || 0) > (merged[key].top_signal || 0)) {
      merged[key].top_signal = e.top_signal;
      merged[key].ultima_senal = e.ultima_senal;
    }
  });
  return Object.values(merged).sort((a, b) => b.total_jobs - a.total_jobs);
}

function renderEmpleos(empresasRaw) {
  const grid  = document.getElementById('empleos-grid');
  const badge = document.getElementById('badge-empleos');
  if (!grid) return;

  const empresas = mergeEmpresas(empresasRaw);
  const activos = empresas.filter(e => (e.total_jobs || 0) > 0);

  if (!activos.length) {
    grid.innerHTML = '<div class="mandantes-login-hint">Sin señales de empleo activas aún</div>';
    return;
  }

  const totalJobs = activos.reduce((s, e) => s + (e.total_jobs || 0), 0);
  if (badge) badge.textContent = totalJobs + ' empleos';

  // Una sola fila por empresa — consolidado limpio
  grid.innerHTML = `<table style="width:100%;border-collapse:collapse;font-size:13px">
    <thead><tr style="border-bottom:2px solid var(--border)">
      <th style="text-align:left;padding:6px 12px;color:var(--muted);font-size:11px;font-weight:600">EMPRESA</th>
      <th style="text-align:center;padding:6px 8px;color:var(--muted);font-size:11px;font-weight:600">EMPLEOS</th>
      <th style="text-align:left;padding:6px 12px;color:var(--muted);font-size:11px;font-weight:600">ÁREAS ACTIVAS</th>
      <th style="padding:6px 8px"></th>
    </tr></thead>
    <tbody>
    ${activos.map(e => {
      const areas = e.areas || {};
      const topAreas = Object.entries(areas).sort((a,b) => b[1]-a[1]).slice(0,3);
      const areaStr = topAreas.map(([a,c]) =>
        `<span class="empleo-area-tag">${escapeHTML(a)} <strong>${c}</strong></span>`
      ).join('');
      const slug = encodeURIComponent(e.company);
      return `
        <tr class="empleo-table-row" style="border-bottom:1px solid var(--border);cursor:pointer"
            onclick="toggleEmpleoDetail('${slug}', this)">
          <td style="padding:10px 12px;font-weight:600">${escapeHTML(e.company)}</td>
          <td style="text-align:center;padding:10px 8px">
            <span style="font-weight:700;color:var(--blue);font-size:15px">${e.total_jobs}</span>
          </td>
          <td style="padding:10px 12px">
            ${areaStr || '<span style="color:var(--muted);font-size:11px">—</span>'}
            ${e.top_signal > 0 ? '<span class="empleo-area-tag" style="background:#fef3c7;color:#92400e">⚡ activo</span>' : ''}
          </td>
          <td style="padding:10px 8px;color:var(--muted);font-size:16px">›</td>
        </tr>
        <tr id="empleo-detail-row-${slug}" style="display:none">
          <td colspan="4" style="padding:0 12px 12px">
            <div id="empleo-detail-${slug}" style="background:#f8fafc;border-radius:8px;padding:10px"></div>
          </td>
        </tr>`;
    }).join('')}
    </tbody>
  </table>`;
}

async function toggleEmpleoDetail(slug, row) {
  const detail  = document.getElementById('empleo-detail-' + slug);
  const detailRow = document.getElementById('empleo-detail-row-' + slug);
  if (!detail) return;
  const isOpen = detailRow ? detailRow.style.display !== 'none' : detail.style.display !== 'none';
  if (isOpen) {
    if (detailRow) detailRow.style.display = 'none';
    else detail.style.display = 'none';
    return;
  }
  if (detailRow) detailRow.style.display = '';
  detail.style.display = 'block';
  if (detail.innerHTML) return; // ya cargado
  detail.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">Cargando...</div>';
  try {
    const res  = await apiFetch('/empleos/empresa/' + slug);
    const data = await res.json();
    const proyectos = data.proyectos || [];
    if (!proyectos.length) {
      detail.innerHTML = '<div style="padding:8px;color:var(--muted);font-size:12px">Sin detalle disponible</div>';
      return;
    }
    detail.innerHTML = proyectos.map(p => {
      const areas = p.areas || {};
      const areaStr = Object.entries(areas)
        .sort((a,b) => b[1]-a[1])
        .map(([a,c]) => `${a}: ${c}`)
        .join(' · ');
      return `
        <div class="empleo-proyecto">
          <a href="${escapeHTML(p.url||'#')}" target="_blank" class="empleo-proyecto-title">${escapeHTML(p.title)}</a>
          <div class="empleo-proyecto-meta">
            <span>📍 ${escapeHTML(p.region||'—')}</span>
            <span>👷 ${p.jobs_count} empleos</span>
            ${areaStr ? `<span style="color:var(--muted)">${escapeHTML(areaStr)}</span>` : ''}
          </div>
        </div>`;
    }).join('');
  } catch(e) {
    detail.innerHTML = '<div style="padding:8px;color:red;font-size:12px">Error cargando detalle</div>';
  }
}


async function checkSession() {
  const session = JSON.parse(localStorage.getItem('stratmap_session') || '{}');
  const hasSession = !!(session.token);
  isLoggedIn = hasSession;

  if (hasSession) {
    const companyKey = session.company_key || 'default';
    // No redirigir si venimos del onboarding (evita loop)
    const fromOnboarding = new URLSearchParams(window.location.search).get('from') === 'onboarding';

    if (!fromOnboarding && companyKey !== 'default') {
      try {
        const res = await apiFetch(`/me/profile?company_key=${encodeURIComponent(companyKey)}`);
        const data = await res.json();
        if (!data.onboarding_done && window.location.pathname === '/') {
          window.location.href = '/onboarding.html';
          return;
        }
        if (data.company_key && !session.company_key) {
          session.company_key = data.company_key;
          localStorage.setItem('stratmap_session', JSON.stringify(session));
        }
      } catch(e) {}
    }
  }

  updateScoreVisibility();
  updateUserMenuState();
  loadMandantes();
  loadEmpleos();
  if (isLoggedIn) loadPersonalizedScores();
}

async function loadPersonalizedScores() {
  // Cargar fits personalizados para esta empresa y mezclarlos con radar_score
  const session = JSON.parse(localStorage.getItem('stratmap_session') || '{}');
  const companyKey = session.company_key || 'default';
  try {
    const res = await apiFetch(`/ai/fits?company_key=${encodeURIComponent(companyKey)}&min_score=1&limit=500`);
    const data = await res.json();
    const fits = data.fits || data.items || [];
    if (!fits.length) return;

    // Build lookup id → fit_score
    const fitMap = {};
    fits.forEach(f => { fitMap[f.id || f.opportunity_id] = f; });

    // Enrich allItems with personalized scores
    allItems = allItems.map(item => {
      const fit = fitMap[item.id];
      if (fit && fit.fit_score > 0) {
        return {
          ...item,
          radar_score: fit.fit_score,
          fit_reason: fit.fit_reason,
          fit_score: fit.fit_score,
        };
      }
      return item;
    });

    // Re-sort and re-render with new scores
    allItems = sortItems(allItems);
    renderFiltered();
  } catch(e) {
    console.log('[fits] error:', e);
  }
}

function updateScoreVisibility() {
  const show = isLoggedIn;
  // Reset sort to default when session changes
  if (!currentSort.by) {
    currentSort.by = isLoggedIn ? 'score' : 'date';
    updateSortArrows();
  }
  document.querySelectorAll('.col-score, .col-aifit, th.col-score').forEach(el => {
    el.style.display = show ? '' : 'none';
  });
  const banner = document.getElementById('no-session-banner');
  if (banner) banner.style.display = show ? 'none' : 'flex';
}

async function load() {
  const q = el("q").value.trim();
  const limit = el("limit").value;
  let url = `/opportunities?limit=${encodeURIComponent(limit)}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;
  el("status").textContent = "Cargando…";
  try {
    const data = await fetchJSON(url);
    await checkSession();
    loadAiFits();
    const rawItems = data.items || [];
    const scored = applyPrefsScoring(rawItems);
    currentSort.by = currentSort.by || (isLoggedIn ? 'score' : 'date');
    allItems = sortItems(scored);
    updateSortArrows();
    buildFilters(allItems);
    syncFilterUI();
    renderFiltered();
    // Cargar noticias por separado
    loadNoticias();
  } catch(e) {
    el("status").textContent = `Error: ${e.message}`;
  }
}

async function loadNoticias() {
  try {
    const data = await fetchJSON('/noticias?limit=50');
    // Marcar cada noticia para que NUNCA aparezca en tabla de proyectos
    // Filtrar empleos de la sección noticias
    newsItems = (data.items || []).filter(n => !EMPLEOS_SOURCES.has(n.source)).map(n => ({ ...n, _isNews: true }));
    renderFiltered();
  } catch(e) {
    console.warn('Error cargando noticias:', e);
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

// ── Aplicar preferencias de localStorage al scoring ───────────────────────────

function getPrefs() {
  try {
    return JSON.parse(localStorage.getItem("stratmap_prefs") || "{}");
  } catch(e) { return {}; }
}




// ── Score dinámico para proyectos SIGEX ───────────────────────────────────────
// Los proyectos SIGEX vienen con score fijo=93. Recalculamos en base a datos reales.
function calcSigexScore(item) {
  if (item.source !== 'SIGEX') return item.score || 0;

  let score = 30; // base: existe en registro SIGEX

  // Fase del proyecto
  const phase = (item.phase || '').toLowerCase();
  if (phase.includes('tramite') || phase.includes('trámite')) score += 30;
  else if (phase.includes('aprobado'))                          score += 20;
  else if (phase.includes('concesion') || phase.includes('concesión')) score += 15;
  else                                                           score += 5;

  // Mineral (del título o raw.recurso)
  const recurso = ((item.raw?.recurso || item.title || '')).toLowerCase();
  if (/\bli\b|litio/.test(recurso))       score += 25; // litio = estratégico
  else if (/cu|cobre/.test(recurso))       score += 20;
  else if (/au|ag|oro|plata/.test(recurso)) score += 15;
  else if (/fe|hierro|zn|zinc/.test(recurso)) score += 10;
  else                                      score += 5;

  // Señal activa (BHP careers, licitaciones, SEA)
  if ((item.signal_score || 0) > 0)  score += 15;
  if ((item.jobs_count   || 0) > 0)  score += 10;

  // Región activa (norte grande = más actividad histórica)
  const region = (item.region || '').toLowerCase();
  if (/antofagasta|atacama|tarapac/.test(region)) score += 5;

  return Math.min(score, 99); // cap en 99 para no superar señales reales
}

function applyPrefsScoring(items) {
  const prefs = getPrefs();
  if (!prefs || Object.keys(prefs).length === 0) return items;

  return items.map(item => {
    let boost = 0;
    const title = (item.title || "").toLowerCase();

    if (prefs.preferred_industries?.includes(item.industry))
      boost += 30 * (prefs.weight_industry || 1);
    if (prefs.preferred_regions?.includes(item.region))
      boost += 25 * (prefs.weight_region || 1);
    if (prefs.preferred_companies?.includes(item.company))
      boost += 25 * (prefs.weight_company || 1);
    if (prefs.preferred_phases?.includes(item.phase))
      boost += 20 * (prefs.weight_phase || 1);
    if (prefs.preferred_sources?.includes(item.source))
      boost += 15;
    (prefs.keywords || []).forEach(kw => {
      if (title.includes(kw.toLowerCase())) boost += 15;
    });

    return { ...item, radar_score: (item.radar_score || 0) + Math.round(boost) };
  });
}

function applyPrefsFilters(items) {
  const prefs = getPrefs();
  if (!prefs || Object.keys(prefs).length === 0) return items;

  return items.filter(item => {
    if (prefs.min_score && (item.radar_score || 0) < prefs.min_score) return false;
    if (prefs.min_investment_usd && item.raw?.monto && item.raw.monto < prefs.min_investment_usd) return false;
    if (prefs.date_from && item.updated_at && item.updated_at < prefs.date_from) return false;
    if (prefs.date_to && item.updated_at && item.updated_at > prefs.date_to + "T23:59:59") return false;
    return true;
  });
}


// ── User menu ──────────────────────────────────────────────────────────────────
function toggleUserMenu() {
  const dropdown = document.getElementById('userDropdown');
  const btn = document.getElementById('userAvatarBtn');
  const isOpen = dropdown.classList.contains('open');
  dropdown.classList.toggle('open', !isOpen);
  btn.classList.toggle('active', !isOpen);
}

// Close dropdown when clicking outside
document.addEventListener('click', (e) => {
  const menu = document.getElementById('userMenu');
  if (menu && !menu.contains(e.target)) {
    document.getElementById('userDropdown')?.classList.remove('open');
    document.getElementById('userAvatarBtn')?.classList.remove('active');
  }
});

function resetSession() {
  if (!confirm('¿Cerrar sesión? Se borrarán tus preferencias guardadas localmente.')) return;
  localStorage.removeItem('stratmap_prefs');
  localStorage.removeItem('stratmap_services');
  localStorage.removeItem('stratmap_session');
  window.location.href = '/login.html';
}

function updateUserMenuState() {
  const session = JSON.parse(localStorage.getItem('stratmap_session') || '{}');
  const icon = document.getElementById('userAvatarIcon');
  const label = document.getElementById('userAvatarLabel');
  const status = document.getElementById('dropdownStatus');
  const subtitle = document.getElementById('dropdownSubtitle');
  const dot = document.querySelector('.user-avatar-dot');

  // Mostrar/ocultar items del menú según sesión
  const loginLink    = document.getElementById('menu-login-link');
  const prefsLink    = document.getElementById('menu-prefs-link');
  const servicesLink = document.getElementById('menu-services-link');
  const divider      = document.getElementById('menu-divider');
  const logoutBtn    = document.getElementById('menu-logout-btn');

  if (isLoggedIn) {
    if (icon)  icon.textContent  = '✅';
    if (label) label.textContent = session.name || 'Mi perfil';
    if (status)   status.textContent   = session.name || 'Perfil activo';
    if (subtitle) subtitle.textContent = 'Score personalizado activo';
    if (dot) dot.classList.add('active');
    if (loginLink)    loginLink.style.display    = 'none';
    if (prefsLink)    prefsLink.style.display     = '';
    if (servicesLink) servicesLink.style.display  = '';
    if (divider)      divider.style.display       = '';
    if (logoutBtn)    logoutBtn.style.display      = '';
  } else {
    if (icon)  icon.textContent  = '👤';
    if (label) label.textContent = 'Mi cuenta';
    if (status)   status.textContent   = 'Sin sesión';
    if (subtitle) subtitle.textContent = 'Ingresa para ver scores';
    if (dot) dot.classList.remove('active');
    if (loginLink)    loginLink.style.display    = '';
    if (prefsLink)    prefsLink.style.display     = 'none';
    if (servicesLink) servicesLink.style.display  = 'none';
    if (divider)      divider.style.display       = 'none';
    if (logoutBtn)    logoutBtn.style.display      = 'none';
  }
}

// ── Region quick-filter ────────────────────────────────────────────────────
window._activeRegion = null;

function filterByRegion(region) {
  window._activeRegion = region;
  // Update chip active states
  document.querySelectorAll('.chip').forEach(c => c.classList.remove('chip-active'));
  const chips = document.querySelectorAll('.chip');
  chips.forEach(c => {
    if (region === null && c.textContent.startsWith('Todas')) c.classList.add('chip-active');
    else if (region && c.textContent.startsWith(region)) c.classList.add('chip-active');
  });
  renderFiltered();
}

// Hook into getFiltered to apply region filter
const _origGetFiltered = window.getFiltered;

// ── Dark / Light mode toggle ────────────────────────────────────────────────
function toggleTheme() {
  const root = document.documentElement;
  const isDark = root.getAttribute('data-theme') === 'dark';
  root.setAttribute('data-theme', isDark ? 'light' : 'dark');
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.textContent = isDark ? '🌙' : '☀️';
  localStorage.setItem('stratmap-theme', isDark ? 'light' : 'dark');
}

// Apply saved theme on load
(function() {
  const saved = localStorage.getItem('stratmap-theme');
  if (saved === 'dark') {
    document.documentElement.setAttribute('data-theme', 'dark');
    setTimeout(() => {
      const btn = document.getElementById('theme-toggle');
      if (btn) btn.textContent = '☀️';
    }, 100);
  }
})();
