# Guía de Despliegue en Railway (Stratmap)

Este documento centraliza todas las variables de entorno y los pasos necesarios para desplegar y poner en marcha el proyecto en **Railway** (tanto el servicio **web** como el **worker**).

---

## 📋 Variables de Entorno

### 1. Compartidas (Shared) — Configurar en AMBOS servicios (`web` + `worker`)

Railway permite definir variables compartidas en el entorno para no tener que duplicarlas.

| Variable | Valor Recomendado / Ejemplo | Notas |
| :--- | :--- | :--- |
| **`DATABASE_URL`** | `${{Postgres.DATABASE_URL}}` | Referencia al plugin de Postgres de Railway. **No la pegues a mano**, usa la referencia para que Railway la asocie automáticamente. |
| **`SECRET_KEY`** | `FzLkNSVACWrWVNXjwCpesRZj3dbtkA3FWO0bVz7q7SWZMwsylKoWxPD-jvLC88UM` | Clave para firmar los JWT. Debe tener $\ge 32$ caracteres. *Si es un redeploy sobre usuarios existentes, NO la cambies o invalidarás sus sesiones.* |
| **`OPENROUTER_API_KEY`** | `sk-or-v1-xxx...` | Requerido por el worker y servicio web para toda la lógica de IA (matching, scoring, correos) mediante OpenRouter (con fallback automático a `ANTHROPIC_API_KEY` si no se configura). |
| **`OPENROUTER_MODEL`** | *(Opcional)* `openrouter/free` | Modelo gratuito o de pago a utilizar en OpenRouter (por defecto es `openrouter/free`, el cual redirige automáticamente a modelos gratuitos disponibles). |
| **`SENTRY_DSN`** | *(Opcional)* `https://...@sentry.io/...` | DSN para monitoreo y tracking de errores con Sentry. |

> [!TIP]
> **Generar una nueva SECRET_KEY en local:**
> Si necesitas cambiar la clave secreta o generar una nueva para producción, ejecuta en tu terminal:
> ```bash
> python -c "import secrets; print(secrets.token_urlsafe(48))"
> ```

---

### 2. Específicas del Servicio Web (`web`)

Estas variables controlan la autenticación, flujos de pago y acceso inicial. **Solo deben configurarse en el servicio web.**

| Variable | Valor Recomendado / Ejemplo | Notas |
| :--- | :--- | :--- |
| **`PUBLIC_URL`** | `https://web-production-e8e0d.up.railway.app` | URL pública HTTPS de tu servicio de Railway. La usa Mercado Pago como retorno de checkout. |
| **`ADMIN_EMAILS`** | `copydollar@gmail.com` | Correos autorizados como administradores (separados por coma si son varios). |
| **`ALLOW_SETUP`** | `true` | **Temporal.** Permite registrar el primer administrador en `/setup/first-user`. Una vez creado, cámbialo a `false` o elimínalo. |
| **`MP_ACCESS_TOKEN`** | *Ver abajo* | Token de Mercado Pago (Sandbox para pruebas o Producción para cobros reales). |
| **`MP_WEBHOOK_SECRET`** | `2ae0bef05d4f119d381be9337273bbd0379dfd1d968f5139ed70e4c79b35f304` | Clave secreta para validar las notificaciones de pago (webhooks). |

#### 🔑 Tokens de Mercado Pago (`MP_ACCESS_TOKEN`):
*   **Sandbox (Pruebas - Recomendado inicialmente):**
    `TEST-3406984516260363-061519-95e72055df1f5d3b006407e65b2b345a-223445802`
*   **Producción (Cobros reales):**
    `APP_USR-3406984516260363-061519-dabce625ade51c11913ed2439c2191b3-223445802`

> [!WARNING]
> Recuerda **rotar tus credenciales de Mercado Pago** cuando finalices la fase de pruebas si las compartiste públicamente o en logs del chat (se hace desde tu panel de integraciones en Mercado Pago).

---

### 3. Conectores e Ingesta — Específicas del Servicio Worker (`worker`)

Estas variables configuran las credenciales de los scraper y conectores automáticos. **Solo son necesarias en el worker si planeas usarlos.**

| Variable | Descripción / Notas |
| :--- | :--- |
| **`CHILEBCOMPRA_TICKET`** | Token de la API de Mercado Público / ChileCompra. Si no se provee, usará el token por defecto del sistema. |
| **`SICEP_USER`** | Usuario de la plataforma SICEP. |
| **`SICEP_PASS`** | Contraseña de la plataforma SICEP. |
| **`ARIBA_USER`** | Usuario de SAP Ariba. |
| **`ARIBA_PASS`** | Contraseña de SAP Ariba. |
| **`ARIBA_URL`** | URL base del portal de SAP Ariba (opcional, tiene un valor default en el código). |

---

### 4. Variables Gestionadas por Railway (Automáticas)

Railway inyecta estas variables de forma nativa en cada build, por lo que **no es necesario que las configures manualmente**:
*   `RAILWAY_ENVIRONMENT_NAME`: Usado para indicar el entorno (`production`, `staging`, etc.) en Sentry y flujos internos.
*   `RAILWAY_GIT_COMMIT_SHA`: Usado por Sentry para registrar el release del código y mostrar la versión en `/health`.

---

## 🚀 Checklist Post-Despliegue

Sigue estos pasos inmediatamente después de que el deploy en Railway marque **Success**:

1. **Configuración del Primer Usuario:**
   * Asegúrate de que `ALLOW_SETUP=true` esté configurada en el servicio `web`.
   * Entra a la ruta `/setup/first-user` en tu dominio (ej: `https://tu-dominio.up.railway.app/setup/first-user`).
   * Crea la cuenta de administrador con tu correo (el cual debe coincidir con alguno en `ADMIN_EMAILS`).
   * **¡Importante!** Vuelve al panel de Railway y cambia `ALLOW_SETUP` a `false` (o elimínala) para evitar accesos indebidos.

2. **Prueba E2E de Mercado Pago (Sandbox):**
   * Configura `MP_ACCESS_TOKEN` con tu clave `TEST-...`.
   * Realiza un flujo de checkout de prueba en la app.
   * Utiliza las cuentas de prueba de Mercado Pago provistas en el archivo `.env` local para loguearte como comprador y las tarjetas de prueba correspondientes (ej: Visa/Mastercard con titular que defina resultado `APRO`).
   * Verifica en los logs del servicio `web` que la ruta `/pagos` o `/pago` reciba la notificación del webhook correctamente y active el plan del usuario.

3. **Verificación de Logs:**
   * Revisa que el servicio `worker` inicie correctamente sin fallos de importación o de conexión a la base de datos PostgreSQL.
   * Monitorea que las migraciones de Alembic se apliquen al arranque.
