// Helper de autenticación compartido.
// Carga este script ANTES de cualquier otro JS que llame a la API.
// No lo cargues en /login.html (esa página usa fetch directo).

function getAuthToken() {
  try {
    const s = JSON.parse(localStorage.getItem('stratmap_session') || '{}');
    return s.token || null;
  } catch (e) {
    return null;
  }
}

function getSession() {
  try {
    return JSON.parse(localStorage.getItem('stratmap_session') || '{}');
  } catch (e) {
    return {};
  }
}

// Redirige a /login.html si no hay token. Llamar al inicio de cada página protegida.
function requireLogin() {
  if (!getAuthToken()) {
    window.location.href = '/login.html';
    return false;
  }
  return true;
}

function logout() {
  localStorage.removeItem('stratmap_session');
  window.location.href = '/login.html';
}

// Wrapper de fetch que inyecta Authorization: Bearer <token>
// y redirige a /login.html si recibe 401.
async function apiFetch(url, options = {}) {
  const token = getAuthToken();
  const headers = new Headers(options.headers || {});
  if (token && !headers.has('Authorization')) {
    headers.set('Authorization', 'Bearer ' + token);
  }
  const resp = await fetch(url, Object.assign({}, options, { headers }));
  if (resp.status === 401) {
    localStorage.removeItem('stratmap_session');
    window.location.href = '/login.html';
    throw new Error('unauthenticated');
  }
  return resp;
}
