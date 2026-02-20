async function fetchJSON(url) {
  const res = await fetch(url, { headers: { "Accept": "application/json" }});
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`);
  return await res.json();
}

function el(id){ return document.getElementById(id); }

function rowHTML(item) {
  const score = item.score ?? 0;
  const title = item.title ?? "";
  const company = item.company ?? "";
  const industry = item.industry ?? "";
  const region = item.region ?? "";
  const source = item.source ?? "";
  const url = item.url ?? "#";

  return `
    <tr>
      <td><span class="badge">${score}</span></td>
      <td>${escapeHTML(title)}</td>
      <td>${escapeHTML(company)}</td>
      <td>${escapeHTML(industry)}</td>
      <td>${escapeHTML(region)}</td>
      <td>${escapeHTML(source)}</td>
      <td><a class="link" href="${url}" target="_blank" rel="noreferrer">Abrir</a></td>
    </tr>
  `;
}

function escapeHTML(str) {
  return String(str)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function load() {
  const q = el("q").value.trim();
  const limit = el("limit").value;

  let url = `/opportunities?limit=${encodeURIComponent(limit)}`;
  if (q) url += `&q=${encodeURIComponent(q)}`;

  el("status").textContent = "Cargando oportunidades…";
  el("tbody").innerHTML = `<tr><td colspan="7" class="muted">Cargando...</td></tr>`;

  try {
    const data = await fetchJSON(url);
    const items = data.items || [];
    el("status").textContent = `Listo: ${data.count ?? items.length} resultados`;

    if (!items.length) {
      el("tbody").innerHTML = `<tr><td colspan="7" class="muted">Sin resultados</td></tr>`;
      return;
    }
    el("tbody").innerHTML = items.map(rowHTML).join("");
  } catch (e) {
    el("status").textContent = `Error: ${e.message}`;
    el("tbody").innerHTML = `<tr><td colspan="7" class="muted">Error cargando datos</td></tr>`;
  }
}

document.addEventListener("DOMContentLoaded", () => {
  el("btnRefresh").addEventListener("click", load);
  el("btnSearch").addEventListener("click", load);
  el("q").addEventListener("keydown", (e) => { if (e.key === "Enter") load(); });
  load();
});
