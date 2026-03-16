# AutoMatch

> No busques auto en 10 páginas. AutoMatch reúne el mercado, estima el precio justo y te muestra qué autos están realmente bajo mercado.

AutoMatch es una plataforma web que reúne autos usados desde múltiples fuentes, normaliza la información, compara precios contra el mercado y detecta las mejores oportunidades de compra.

---

## Qué es AutoMatch

Plataforma MVP para el mercado chileno de autos usados. Agrega publicaciones de múltiples fuentes (Chileautos, Auto.cl, Yapo, Automotoras), calcula un score de oportunidad comparando el precio publicado contra comparables del mercado, y permite enviar ofertas directamente desde la plataforma.

---

## Arquitectura del proyecto

```
automatch/
├── app/                        # Next.js App Router
│   ├── page.tsx                # Landing page
│   ├── buscar/page.tsx         # Búsqueda + filtros
│   ├── autos/[id]/page.tsx     # Detalle de publicación
│   ├── admin/                  # Panel admin (protegido por cookie)
│   │   ├── login/page.tsx
│   │   ├── page.tsx            # Dashboard KPIs
│   │   ├── autos/page.tsx
│   │   ├── ofertas/page.tsx
│   │   └── fuentes/page.tsx
│   └── api/                    # API Routes
│       ├── vehicles/route.ts
│       ├── vehicles/[id]/route.ts
│       ├── offers/route.ts
│       └── admin/...
├── components/
│   ├── ui/                     # badge, button, input, select, spinner
│   ├── vehicles/               # VehicleCard, OpportunityBadge, VehicleFilters
│   ├── offers/                 # OfferForm
│   └── layout/                 # Navbar, Footer
├── lib/
│   ├── db.ts                   # Prisma singleton
│   ├── scoring.ts              # Motor de scoring v1
│   ├── vehicles.ts             # Queries de búsqueda y detalle
│   ├── offers.ts               # Validación Zod + creación de ofertas
│   ├── admin.ts                # Queries panel admin
│   ├── auth.ts                 # Auth simple por cookie
│   └── utils.ts                # Formatters CLP/km/%, constantes Chile
├── sources/                    # Providers desacoplados (listos para fuentes reales)
│   ├── base.ts                 # Interfaz BaseProvider abstracta
│   ├── chileautos/index.ts     # Mock
│   ├── auto-cl/index.ts        # Mock
│   ├── yapo/index.ts           # Mock
│   └── automotoras/index.ts    # Mock
├── types/index.ts
├── prisma/
│   ├── schema.prisma
│   └── seed.ts                 # 92 autos mock con scoring real
├── __tests__/
│   ├── scoring.test.ts
│   └── offers.test.ts
└── middleware.ts               # Protección rutas /admin/*
```

---

## Modelo de datos

| Entidad | Descripción |
|---------|-------------|
| `Source` | Origen del aviso (Chileautos, Yapo, etc.) |
| `Vehicle` | Auto normalizado con atributos técnicos |
| `Listing` | Publicación en una fuente, con precio publicado y score calculado |
| `Offer` | Oferta enviada por un usuario |
| `PriceSnapshot` | Historial de precios (tracking futuro) |

---

## Cómo correrlo localmente

### Requisitos
- Node.js 18+
- PostgreSQL corriendo localmente

### Pasos

```bash
# 1. Instalar dependencias
cd automatch
npm install

# 2. Variables de entorno
cp .env.example .env
# Edita DATABASE_URL, ADMIN_SECRET

# 3. Crear DB
createdb automatch

# 4. Migraciones
npx prisma migrate dev --name init

# 5. Generar cliente Prisma
npx prisma generate

# 6. Seed (92 autos mock)
npx prisma db seed

# 7. Dev server
npm run dev
```

Abre http://localhost:3000

---

## Variables de entorno

```env
DATABASE_URL="postgresql://postgres:postgres@localhost:5432/automatch"
NEXT_PUBLIC_APP_URL="http://localhost:3000"
ADMIN_SECRET="automatch-admin-2024"
```

---

## Panel Admin

URL: http://localhost:3000/admin  
Contraseña: valor de `ADMIN_SECRET` en `.env`

> Auth MVP-grade (cookie simple). Para producción usar NextAuth / Clerk.

---

## Tests

```bash
npm test
```

Cubre: motor de scoring (boundaries, edge cases) + validación de ofertas.

---

## Partes mockeadas

| Parte | Estado |
|-------|--------|
| Datos de vehículos | Mock — 92 autos en `prisma/seed.ts` |
| Providers de fuentes | Mock — `fetchListings()` vacío en cada provider |
| Imágenes | Placeholder SVG |
| URLs de publicaciones | Generadas como ejemplo |
| Motor de scoring | **Funcional** — calcula con comparables reales |
| Flujo de oferta | **Funcional** — guarda en PostgreSQL |
| Panel admin | **Funcional** — lee desde PostgreSQL |

---

## Cómo conectar fuentes reales

1. Abre `sources/[slug]/index.ts`
2. Implementa `fetchListings()` (scraping HTTP o API)
3. Retorna `RawListing[]` (ver interfaz en `sources/base.ts`)
4. Crea un job de sincronización que: fetch → normalize → calculateScore → upsert DB

---

## Motor de scoring

`lib/scoring.ts`:
1. Busca comparables `brand + model`
2. Tolerancia de año progresiva: ±1 → ±2 → ±3
3. Ajuste por kilometraje por diferencia
4. Mediana de precios ajustados = `marketEstimate`
5. `deltaPercentage = (listedPrice − marketEstimate) / marketEstimate × 100`
6. Clasificación:
   - `≤ −12%` → VERY_GOOD_DEAL
   - `−12% a −5%` → GOOD_DEAL
   - `−5% a +5%` → FAIR_PRICE
   - `≥ +5%` → OVERPRICED
7. `confidenceScore` 0–100 por cantidad de comparables y tolerancia

---

## Qué faltaría para producción

- Scraping / APIs reales en providers
- Imágenes reales
- Auth robusta (NextAuth, Clerk)
- Rate limiting
- Job de sincronización periódica (cron)
- Notificaciones email al recibir oferta
- Motor de scoring v2 (ML)
- SEO avanzado (sitemap, schema.org)
