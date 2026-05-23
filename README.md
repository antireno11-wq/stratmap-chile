# Stratmap Chile

Plataforma SaaS de inteligencia de oportunidades comerciales para el sector minero chileno. Agrega licitaciones, concesiones, proyectos SEA, noticias y señales de contratación; las puntúa con un motor de scoring propio + IA personalizada por usuario; y las presenta como radar, kanban y mapa.

## Stack

- **Backend:** FastAPI 0.115 (Python 3.12) + PostgreSQL (vía `psycopg[binary]` 3.2).
- **Auth:** JWT firmado con HS256 (bcrypt para passwords).
- **Frontend:** HTML/CSS/JS vanilla servido como estáticos. Sin framework.
- **Scrapers:** `requests` + BeautifulSoup + Playwright (Chromium headless) para portales JS.
- **IA:** Anthropic Claude (`claude-sonnet-4-6`) para AI matching y resúmenes de mandantes.
- **Deploy:** Railway (1 servicio web + 1 worker + Postgres).

## Estructura del repo

```
.
├── main.py               entrypoint FastAPI (lifespan, scheduler, /health, rate limit)
├── auth.py               crypto JWT (HS256) + bcrypt
├── deps.py               get_current_user, require_admin
├── schemas.py            modelos Pydantic
├── helpers.py            run_rss_ingest (compartido scheduler + admin)
├── db.py                 acceso a Postgres + scoring engine + migraciones idempotentes
├── ai_matcher.py         batch nocturno: Claude scorea proyectos contra perfil del usuario
├── ai_scorer.py          AI scoring zona gris (re-scorea proyectos score 45-65)
├── mandante_scorer.py    "temperatura" de cada mandante por actividad reciente
├── demand_intel.py       inferencia IA de servicios necesarios por proyecto
├── faenas_mineras.py     fetcher de la API ArcGIS de SERNAGEOMIN (mapa)
├── sea_ingest.py         ingestor SEA (entrypoint del worker)
├── routers/
│   ├── auth.py            /auth/login, /setup/first-user
│   ├── opportunities.py   /opportunities, /noticias, /feed, /ingest, /opportunities/{id}/services
│   ├── pipeline.py        /pipeline, /opportunities/{id}/pipeline, notes
│   ├── contacts.py        /contacts CRUD + import + export
│   ├── me.py              /me/*, /ai/fits
│   ├── mandantes.py       /mandantes/*, /faenas
│   ├── empleos.py         /empleos/*
│   ├── admin.py           /admin/* (scrapers + ops manuales)
│   └── static_pages.py    rutas explícitas para *.html
├── connectors/           scrapers individuales (ENAMI, Codelco, SIGEX, MOP, ChileCompra, RSS, etc.)
├── signals/              detectores de señales (LinkedIn, careers pages)
├── sql/                  esquemas DDL (referencia; las migraciones reales viven en db.py)
└── static/               frontend (HTML, CSS, JS, imágenes)
```

## Variables de entorno requeridas

Setearlas en Railway (Variables tab) o en un `.env` local para desarrollo.

| Variable | Obligatoria | Descripción |
|---|---|---|
| `DATABASE_URL` | sí | Connection string Postgres (`postgresql://user:pass@host:port/db`). Railway lo provee automáticamente. |
| `SECRET_KEY` | sí | Clave HS256 para firmar JWTs. **Mínimo 32 caracteres.** La app no arranca sin esto. |
| `ANTHROPIC_API_KEY` | sí para IA | API key de Anthropic. Sin esto, AI matching, mandante summaries y demand-intel devuelven error pero el resto funciona. |
| `ADMIN_EMAILS` | sí | Lista CSV de emails que pueden llamar `/admin/*` y `POST /ingest`. Ejemplo: `alice@acme.cl,bob@acme.cl`. |
| `ALLOW_SETUP` | bootstrap | Setear `true` solo mientras creás el primer usuario via `/setup/first-user`. Después borrar. La app igual se autoprotege: el endpoint falla si ya hay usuarios en la DB. |
| `PORT` | Railway | Puerto HTTP. Railway lo provee. Local: default `8080`. |
| `BASE_URL` / `PUBLIC_URL` | no | Base URL pública (usada por algunos scrapers para callbacks). |
| `SEA_DAYS_BACK` | no | Días hacia atrás que mira el ingestor SEA. Default 30. |
| `SEA_LIMIT` | no | Tope de proyectos SEA por corrida. Default 500. |
| `RUN_INGEST_ON_START` | no | Si `1`, dispara un scrape inicial al arrancar el worker. |
| `RAILWAY_GIT_COMMIT_SHA` | auto | Railway lo provee. `/health` lo expone como `version`. |
| `SENTRY_DSN` | no | Si está seteada, web y worker reportan excepciones a Sentry (5% trace sampling). Si no, no se cargan errores a ningún lado externo. |
| `LOG_LEVEL` | no | `INFO` por default. `DEBUG` para verbosidad, `WARNING` para silencio. Logs salen como JSON a stdout. |
| `MP_ACCESS_TOKEN` | sí para pagos | Access Token de Mercado Pago. Usá `TEST-...` en sandbox, `APP_USR-...` en prod. Sacalo de https://www.mercadopago.cl/developers > tu app > Credenciales. |
| `MP_WEBHOOK_SECRET` | sí para pagos | Secret para validar firma del webhook. En el panel MP > tu app > Webhooks > Configurar notificaciones. Si falta, las firmas no se validan (NO usar así en prod). |
| `PUBLIC_URL` | sí para pagos | Base URL pública del web service (ej: `https://stratmap-chile.up.railway.app`). MP redirige acá tras el pago y manda webhooks a `PUBLIC_URL/billing/webhook`. |

Generar un `SECRET_KEY` fuerte:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Setup local

Requisitos: Python 3.12, Postgres 14+, opcionalmente Playwright para scrapers que necesiten JS.

```bash
# Clonar y entrar
git clone https://github.com/antireno11-wq/stratmap-chile.git
cd stratmap-chile

# Crear venv + instalar
python3.12 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium  # solo si vas a correr scrapers que usan Playwright

# Configurar env
cat > .env <<EOF
DATABASE_URL=postgresql://stratmap:stratmap@localhost:5432/stratmap
SECRET_KEY=$(python -c "import secrets; print(secrets.token_urlsafe(48))")
ADMIN_EMAILS=tu-email@dominio.cl
ALLOW_SETUP=true
ANTHROPIC_API_KEY=sk-ant-...
EOF

# Crear DB local (Postgres ya corriendo)
createdb stratmap

# Levantar la app — las migraciones idempotentes corren en lifespan
uvicorn main:app --reload --port 8080
```

Bootstrap del primer usuario (con `ALLOW_SETUP=true`):

```bash
curl -X POST http://localhost:8080/setup/first-user \
  -H "Content-Type: application/json" \
  -d '{"email":"tu-email@dominio.cl","password":"<password-fuerte>","name":"Tu Nombre"}'
```

Después, desactivar `ALLOW_SETUP` y entrar via `http://localhost:8080/login.html`.

## Correr scrapers manualmente

Cada scraper se puede disparar desde un endpoint admin (requiere admin token):

```bash
TOKEN="$(curl -s -X POST http://localhost:8080/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"tu-email","password":"tu-pwd"}' | jq -r .token)"

# RSS (noticias)
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/admin/run-rss

# SIGEX
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/admin/run-sigex

# BHP Careers (señales de empleo)
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/admin/run-bhp-careers

# AI scoring (zona gris) — re-scorea proyectos score 45-65 con Claude
curl -X POST -H "Authorization: Bearer $TOKEN" http://localhost:8080/admin/run-ai-scorer
```

El scheduler en `main.py` corre RSS cada 6h y AI scorer + expire-stale cada 24h automáticamente.

## Deploy a Railway

1. **Crear el proyecto:** New Project → Deploy from GitHub repo → seleccionar `stratmap-chile`.
2. **Agregar Postgres:** `+ New` → Database → PostgreSQL. Railway setea `DATABASE_URL` automáticamente.
3. **Setear variables** (Variables tab del servicio web):
   - `SECRET_KEY` (generado con el comando de arriba)
   - `ANTHROPIC_API_KEY`
   - `ADMIN_EMAILS`
   - `ALLOW_SETUP=true` (temporalmente, para crear el primer usuario)
4. **Deploy.** El build usa `nixpacks.toml` (Python 3.12, `pip install -r requirements.txt`, `playwright install chromium --with-deps`). El comando de arranque sale del `Procfile`.
5. **Crear primer usuario** via `POST /setup/first-user` (ver arriba).
6. **Borrar `ALLOW_SETUP`** de las variables.
7. **Worker:** crear un segundo servicio en el mismo proyecto apuntando al mismo repo, con `dockerfile.worker` como build (incluye Playwright + Chromium para scrapers JS-heavy). El comando de arranque sale del `Procfile`:
   - `web: uvicorn main:app --host 0.0.0.0 --port 8080`
   - `worker: python worker.py` — corre el scheduler RSS cada 6h + full ingest + AI scorer + expire-stale cada 24h.

   La web no corre tareas de background: si la escalás a >1 instancia, no se duplican scrapes. `/health` infiere liveness del worker desde `MAX(updated_at)` en `opportunities` (campo `worker.stale=true` si pasaron >8h sin scrape).

## Migraciones (Alembic)

El repo trae el scaffolding de Alembic (`alembic.ini` + `alembic/`) listo para activar, pero **todavía no maneja la DB de producción**. Hoy las migraciones siguen viviendo como `CREATE TABLE IF NOT EXISTS` + `ALTER ... ADD COLUMN IF NOT EXISTS` dentro de `db.init_*_db()`, que corren en el lifespan.

### Cómo activar Alembic en prod (transición)

1. **Stampear** la DB de prod con la revisión baseline (le decimos a Alembic "este es el estado actual"):

   ```bash
   DATABASE_URL=$PROD_DATABASE_URL alembic stamp 0001_baseline
   ```

2. **De aquí en más, todo cambio de schema nuevo va por Alembic:**

   ```bash
   alembic revision -m "agrego columna foo a contacts"
   # editás la migración generada en alembic/versions/
   DATABASE_URL=$LOCAL_DATABASE_URL alembic upgrade head     # probar local
   DATABASE_URL=$PROD_DATABASE_URL alembic upgrade head      # aplicar en prod
   ```

3. **Cuando todos los cambios pendientes ya estén tracked por Alembic**, sacar las llamadas `init_*_db()` del `lifespan` y dejar solo `alembic upgrade head` corriendo via Railway pre-deploy command.

Esta transición es opcional: el código actual funciona con o sin Alembic. El scaffolding está para que el primer cambio "post-baseline" sea fácil.

## Tests

```bash
pip install -r requirements-dev.txt
pytest -q
```

Tests cubiertos: auth gates (parametrizados sobre 16 endpoints), rate limiter, scoring engine (`calc_score`, `_mandante_size`, etc.), shape de `/health`. CI corre `pytest` en cada push via `.github/workflows/test.yml`.

## Planes y pagos (Mercado Pago)

Stratmap tiene 3 planes definidos en `plans.py`: **Free** (20 opps/día, 50 contactos), **Pro** ($29.000 CLP/mes, 500 opps, 2.000 contactos, AI matching + exports) y **Team** ($89.000 CLP/mes, ilimitado).

### Cómo activar los pagos

1. **Cuenta Mercado Pago Developers:** crear una app en https://www.mercadopago.cl/developers > Aplicaciones > Crear aplicación. Tipo: **Pagos online + presenciales**.
2. **Credenciales:** ir a la app > Credenciales. Copiar el **Access Token** (TEST-... para sandbox, APP_USR-... para producción).
3. **Webhook:** en la misma app > **Webhooks** > Configurar URL `https://<tu-app>.up.railway.app/billing/webhook` y suscribirse a evento `subscription_preapproval`. Copiar el **Secret** generado.
4. **Setear env vars en Railway** (servicio web):
   - `MP_ACCESS_TOKEN=APP_USR-...` (o `TEST-...` para sandbox)
   - `MP_WEBHOOK_SECRET=...` (el secret del paso 3)
   - `PUBLIC_URL=https://<tu-app>.up.railway.app`
5. **Probar:** logueate como user no-admin (free por default), andá a `/pricing.html`, dale a "Suscribirme" a Pro. Te redirige a MP, pagás con tarjeta de prueba, MP llama al webhook, `/me/plan` ya muestra plan=pro.

### Endpoints relevantes

- `POST /billing/checkout {plan: "pro"|"team"}` → crea preapproval, devuelve `init_point` URL.
- `POST /billing/webhook` → público; valida firma HMAC y sincroniza `user_plans`.
- `GET /billing/portal` → info del plan + link a MP para cancelar.
- `GET /me/plan` → plan + features + status (lo lee el frontend para mostrar/ocultar UI).
- 402 (Payment Required) se devuelve cuando `require_feature("ai_matching" | "exports")` falla, o cuando se supera `max_contacts`.

### Tarjetas de prueba MP (sandbox)

| Tipo | Número | CVV | Vencimiento |
|---|---|---|---|
| Aprobada | `5031 7557 3453 0604` (Mastercard) | `123` | `11/30` |
| Rechazada | `4509 9535 6623 3704` (Visa) | `123` | `11/30` |

## Observabilidad

- **Logging:** JSON structured logs a stdout via `logging_config.setup_logging()`, configurado al arrancar tanto en `main.py` (web) como en `worker.py`. Cada log es una línea JSON con `ts`, `level`, `logger`, `msg`, y cualquier campo extra que pase via `logger.info("...", extra={...})`. Nivel por env var `LOG_LEVEL`.
- **Sentry:** opt-in via `SENTRY_DSN`. Se inicializa en web y worker independientemente; reporta excepciones no manejadas + 5% de trazas. Sin `SENTRY_DSN`, no se reporta a ningún lado.
- **Métricas operacionales:** `GET /admin/stats` (admin) devuelve oportunidades por fuente (total + activos + last_scrape), usuarios activos (7d / 30d), y conteo de llamadas IA persistidas (`ai_opportunity_fits` + `mandante_heat`) en los últimos 30 días.
- **Liveness del worker:** `/health` infiere si el worker está vivo desde `MAX(updated_at)` en `opportunities`. Si pasaron >8h sin scrape, `worker.stale = true`.

## Healthcheck

`GET /health` (público, sin rate limit) devuelve:

```json
{
  "status": "ok",
  "db_ok": true,
  "db_msg": "ok",
  "version": "b87d066",
  "uptime_seconds": 1234,
  "scheduler": {"last_run": 1716345678, "seconds_ago": 1800, "stale": false},
  "last_scrape_by_source": {
    "ENAMI": "2026-05-23T10:00:00+00:00",
    "SIGEX": "2026-05-23T08:15:00+00:00",
    ...
  }
}
```

Útil para monitoreo: `scheduler.stale=true` significa >8h sin correr el RSS.
