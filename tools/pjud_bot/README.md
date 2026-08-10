# Bot de verificación de causas — Poder Judicial de Chile

Herramienta de línea de comandos para revisar la **Oficina Judicial Virtual (OJV)**
del Poder Judicial de Chile y confirmar si una causa realmente existe.

Fuente oficial: <https://oficinajudicialvirtual.pjud.cl/>

## ¿Para qué sirve?

Si recibiste un correo o WhatsApp de un "estudio jurídico" avisándote de una
demanda (típicamente *"BANCO XXX / TU_APELLIDO"*, con un *"plazo de 8 días"* y un
número de contacto), este bot te deja **verificarlo tú mismo en la fuente
oficial**, sin depender de quien te escribió.

> ⚠️ **Por qué importa.** Hay empresas de captación que **raspan el "Estado
> Diario" público de la OJV** para detectar demandas de bancos y enviar correos
> ofreciendo "defensa". El correo puede sonar oficial y apurarte con un plazo, pero
> **el remitente no es el tribunal ni el banco**. Señales de alerta: dominio del
> remitente distinto al sitio que citan, urgencia artificial, y que te empujen a
> llamar/pagar. La causa *puede* ser real — por eso conviene confirmarla aquí, en
> la fuente, antes de hablar con nadie. La consulta de la OJV es **gratuita y
> pública**.

## Instalación

```bash
cd tools/pjud_bot
pip install -r requirements.txt
playwright install chromium
```

## Uso

```bash
# Buscar por nombre del litigante
python buscar_causa.py --nombre "MENA ORTEGA WILFREDO"

# Buscar por RUT (más preciso) — usa tu RUT real
python buscar_causa.py --rut 12.345.678-9

# Si ya conoces el rol exacto
python buscar_causa.py --rol "C-12345-2025"

# Afinar qué resultados se marcan como "calce"
python buscar_causa.py --nombre "MENA ORTEGA WILFREDO" --match BANCO --match MENA

# Intentar autocompletar el formulario (best-effort)
python buscar_causa.py --rut 12.345.678-9 --auto
```

### Cómo funciona (modo asistido)

La consulta pública de la OJV exige resolver un **captcha**, que el bot **no
intenta saltarse a propósito** (sería abusar del sitio). El flujo es:

1. El bot abre un **navegador real** en la Consulta Unificada de Causas.
2. **Tú** eliges la pestaña/jurisdicción, el tipo de búsqueda, ingresas el dato
   y **resuelves el captcha** → "Buscar".
3. Cuando la **tabla de resultados** está en pantalla, vuelves a la terminal y
   presionas **ENTER**.
4. El bot lee la tabla, **filtra las causas que calzan** con lo que buscas y las
   **exporta a JSON y CSV** en `./resultados/`.

Este modo funciona aunque el sitio cambie su diseño, porque sólo lee la tabla ya
renderizada.

### Opciones

| Opción | Descripción |
|---|---|
| `--nombre` | Nombre del litigante (ej: `"MENA ORTEGA WILFREDO"`). |
| `--rut` | RUT del litigante (más preciso), ej: `12.345.678-9`. |
| `--rol` | Rol/RIT exacto si ya lo conoces, ej: `C-12345-2025`. |
| `--jurisdiccion` | Sede a consultar. Default `civil` (típica para cobranza bancaria). Opciones: `suprema, apelaciones, civil, laboral, penal, cobranza, familia, disciplinario`. |
| `--match` | Término que una causa debe contener para marcarla como CALCE. Repetible (deben aparecer todos). Default: el apellido/RUT buscado. |
| `--auto` | Intenta rellenar el formulario automáticamente (best-effort; si falla, sigue en asistido). |
| `--headless` | Sin ventana — **no recomendado**, no podrás resolver el captcha. |
| `--out` | Carpeta de salida (default `./resultados`). |

### Códigos de salida

| Código | Significado |
|---|---|
| `0` | Se encontraron causas que calzan. |
| `3` | Se leyeron causas, pero ninguna calza con los términos. |
| `4` | No se leyó ninguna tabla (¿estaban los resultados en pantalla?). |
| `1` / `2` | Cancelado / error de uso o dependencia faltante. |

## El caso del correo de ejemplo

El correo de "Estudio jurídico Deudafin" menciona el caratulado
**`BANCO DEL ESTADO DE CHILE / MENA`**. Una cobranza de un banco contra una
persona es, casi siempre, un **juicio ejecutivo en sede Civil**. Para verificarlo:

```bash
python buscar_causa.py --nombre "MENA ORTEGA WILFREDO" --match "BANCO DEL ESTADO" --match MENA
```

Si la causa existe, el rol, el tribunal y todas las actuaciones (el "cuaderno")
están en la misma OJV — **no necesitas pagarle a quien te avisó** para enterarte.
Si tienes una demanda real, busca orientación en la
[Corporación de Asistencia Judicial (CAJ)](https://www.cajmetropolitana.cl/),
que es **gratuita**, o en un abogado de tu confianza.

## Notas técnicas

- Sólo automatiza navegación y la **lectura** de resultados públicos; el captcha
  lo resuelve una persona. No hace login con Clave Única ni accede a datos
  privados.
- El DOM de la OJV cambia con frecuencia; por eso el modo asistido es el camino
  robusto y el auto-fill es best-effort.
- Todo ocurre entre tu equipo y el sitio oficial. No se envían datos a terceros.
