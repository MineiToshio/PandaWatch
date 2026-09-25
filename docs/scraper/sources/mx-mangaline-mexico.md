# Fuente: MangaLine México

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-08-23. **DESHABILITADA en `sources.yml` desde
> 2026-08-23** (host caído, ver §8/§9) — la editorial sigue activa.
>
> Nota: MangaLine México (`mangaline.com.mx`) y MangaLine España (`mangaline.es`)
> comparten el MISMO theme WooCommerce custom, pero son **sitios y países distintos**.
> Esta ficha es la de **México**. La de España se documenta aparte en
> [es-mangaline-espana.md](es-mangaline-espana.md).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | MangaLine México |
| **URL base** | `https://mangaline.com.mx` |
| **Índice / punto de entrada** | `https://mangaline.com.mx/tienda/` |
| **Tipo de fuente** | Editorial / tienda oficial |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País** | México (`México`) |
| **Idioma** | Español |
| **Cobertura** | Catálogo propio de MangaLine México, concentrado en sobrecubiertas alternativas y ediciones exclusivas |
| **Aporte al corpus** | ~19 items |
| **Parser / módulo** | Entrada en `sources.yml` ("MX - MangaLine México Tienda") — extractor genérico, sin parser propio |

**Editoriales que abarca** (del corpus real): MangaLine México (19 items).

**Por qué importa / qué aporta de único**: aporta el catálogo de **sobrecubiertas
alternativas y ediciones exclusivas** de MangaLine en México (Devilman #1-3,
Q on the Seaside, Tokko, Silent Möbius, Nadesico, Grey, Dark Angel). Es la edición
mexicana — país distinto de la edición española (#46), nunca se mezclan.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: tienda WooCommerce en `tienda/`, paginada
  (`max_pages: 10`). Cada producto es una card del listado.
- **Estructura del HTML**: WooCommerce con **tema custom**. Selectores del YAML:
  - `item_selector`: `li.product:not(.product-category)`
  - `title_selector`: `h3.product-title` (NO el `h2.woocommerce-loop-product__title`
    estándar de WooCommerce — el tema custom usa `h3.product-title`).
- **Quirk del selector**: `li.product` también matchea cards de **"líneas temáticas"**
  (DARK LINE, EPIC LINE…) que son category-cards, no productos. Se filtran con
  `:not(.product-category)`.
- **Pureza**: `manga_only`.

---

## 5. Proceso de ingestión — técnico

Fuente del **YAML**, ingestada en **FASE 1** del pipeline (`manga_watch.py`,
scrape de sources del YAML) vía el **extractor genérico** con los selectores de
arriba. **No tiene parser propio**. Comparte el mismo theme WooCommerce custom que
MangaLine España, por lo que ambos usan los mismos selectores (`h3.product-title`,
`li.product:not(.product-category)`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Outage total 2026-07-07** (primer delta real post-mejoras): `mangaline.com.mx`
  respondió `ConnectTimeoutError` (connect timeout=10s) — el mismo síntoma que
  MangaLine España el mismo día. DNS resuelve (`217.76.130.154`), pero el host no
  responde en el puerto 443; el IP pertenece al hosting compartido **Arsys**
  (`arsys.es`, confirmado por whois — `NET-ARSYS-EURO-4`). El sitio SÍ funcionaba
  en el run del 2026-06-12 (132 candidatos, 6 páginas), así que es probable un
  problema **transitorio de hosting** compartido con la ficha de España, no un
  cambio permanente del sitio. Monitorear el próximo run.
- **Outage SIGUE 2026-08-22** (delta `logs/scrape-delta-2026-08-22-174458/`): mismo
  `ConnectTimeoutError` en el diagnóstico. Verificado en vivo con curl (mismo
  user-agent del scraper, puerto 80 Y 443, `tienda/` y raíz `/`): timeout de conexión
  en ambos puertos, DNS sigue resolviendo (`217.76.130.154`, sin cambios). **Van 2
  runs con más de un mes de diferencia (2026-07-07 → 2026-08-22) con el host
  inalcanzable** — ya no es razonable seguir llamándolo "transitorio de hosting";
  escala a **host caído / posible cese del sitio**. No se reintentó el scrape (host
  caído, no recuperable con un retry). Revisar manualmente en navegador antes del
  próximo delta; si sigue caído, evaluar deshabilitar (`enabled: false`) en
  `sources.yml` en vez de seguir corriendo el intento en vano cada delta.
- **DESHABILITADA 2026-08-23**: re-verificado con `curl -sI` (mismo user-agent,
  puertos 80/443, timeout corto) — `mangaline.com.mx` sigue sin responder
  (`ConnectTimeoutError`, exit 28), tercera confirmación tras 2026-07-07 y
  2026-08-22 (~6 semanas de host inalcanzable). Se puso `enabled: false` en
  `sources.yml` con comentario fechado. **La editorial NO cerró**: sigue activa en
  redes (Instagram @mangalinemx, ~5.5k seguidores, posts recientes de agosto 2026;
  también en TikTok/X/Facebook) y su catálogo se sigue vendiendo en Mixup, Amazon
  México, Mercado Libre y Buscalibre según fuentes públicas — el problema es sólo
  el sitio propio (mismo hosting Arsys que la ficha España). Contexto histórico: en
  2023 hubo un cambio de administración con acusaciones de irregularidades en el
  manejo de licencias (resuelto con un equipo 100% mexicano tomando el control);
  no guarda relación directa con la caída actual del sitio.

---

## 9. Pendientes / limitaciones conocidas

- Catálogo chico (~19 items); no hay ediciones especiales/cofres con lógica propia
  como en ListadoManga, así que entra todo por el extractor genérico.
- **Cobertura tras deshabilitar (2026-08-23)**: los 19 items del corpus con esta
  fuente quedan SOLOS (sin otra fuente en `sources[]`) — a diferencia de España, NO
  existe un agregador equivalente a ListadoManga para México, así que este catálogo
  queda sin cobertura activa mientras la fuente esté apagada. Candidatas a evaluar
  con `/watch-evaluate-sources` (NINGUNA implementada todavía):
  - **Buscalibre México** (`https://www.buscalibre.com.mx/`) — comparador de
    librerías online, ya lista título de MangaLine MX según búsqueda pública; NO
    está en `sources.yml` (candidata nueva).
  - **Mixup** (`https://www.mixup.com.mx/`) — cadena física/online mexicana que
    vende el catálogo MangaLine; NO está en `sources.yml` (candidata nueva).
  - **Amazon México / Mercado Libre** — MangaLine MX vende ahí directamente
    (marketplace del propio sello); ninguna está en `sources.yml` (candidatas
    nuevas, pero marketplaces genéricos suelen tener ruido/purity mixed — evaluar
    con cuidado).
  No hay overlap por ISBN/cluster_key verificado con ninguna de estas — habría que
  correr el discovery real del skill antes de agregar cualquiera al pipeline.

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "MX - MangaLine México Tienda"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver editoriales/países reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "mangaline.com.mx"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`,
0 duras) → tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo
meaningful, actualiza esta ficha.
