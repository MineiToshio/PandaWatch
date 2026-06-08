# Fuente: Distrito Manga (España)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-08.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Distrito Manga (entrada `ES - Distrito Manga` en `sources.yml`) |
| **URL base** | `https://www.penguinlibros.com/es/221600-distrito-manga` |
| **Índice / punto de entrada** | La misma URL (página de catálogo del sello en penguinlibros.com) |
| **Tipo de fuente** | Editorial (sello oficial) |
| **`kind` en sources.yml** | `js` (renderizada con Playwright, requiere `--enable-js`) |
| **`source_class`** | `official` |
| **País** | España (`es`) — mono-país |
| **Idioma** | Español |
| **Cobertura** | Catálogo del sello Distrito Manga (sello de manga de Penguin Random House) |
| **Aporte al corpus** | ~0 items por scrape directo de esta fuente (ver §8). Los 25 items con `publisher` "Distrito Manga" en el corpus llegan vía ListadoManga, no por esta entrada. |
| **Parser / módulo** | Sin parser propio — entrada del YAML, auto-detección de selectores |

**Por qué importa / qué aporta de único**: es la página oficial del sello Distrito
Manga (manga de Penguin Random House en España). Como fuente oficial debería capturar
novedades y ediciones del sello de primera mano, sin pasar por terceros.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: catálogo del sello en penguinlibros.com (una sola
  URL de entrada en el YAML). La paginación/listado se renderiza del lado del cliente.
- **Estructura del HTML/feed**: la entrada del YAML **no define `selectors`** → el
  scraper usa **auto-detección** de items (no hay `item_selector`/`title_selector`
  explícitos). No hay `notes` propias.
- **Identificador de producto**: URL canónica del producto en penguinlibros.com.
- **Anti-bot / quirks**: `kind: js` → la página es **JS-rendered**, se renderiza con
  Playwright (**#12**: `playwright-worker` es un thread único serializado; los workers
  HTTP despachan a `_PLAYWRIGHT_QUEUE`). Requiere correr con `--enable-js`; sin esa flag
  la fuente no entrega contenido. Es la causa más probable del aporte nulo (§8).

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `ES - Distrito Manga` (`kind: js`, `source_class:
  official`, `country: España`). Sin `selectors` → auto-detección.
- **No tiene parser propio**: la maneja el flujo genérico de fuentes del YAML
  (`scripts/manga_watch.py`), no un módulo en `scripts/wikis/`.
- **Flujo end-to-end**: se scrapea en la **FASE 1** de `scrape_full.sh` /
  `scrape_delta.sh` (scrape de sources del YAML con `manga_watch.py --workers 8`). Al ser
  `kind: js`, su render se serializa en el `playwright-worker` (#12) y requiere
  `--enable-js` habilitado. Después pasa por los retrofits de cleanup como cualquier otra
  fuente del YAML.

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **Aporte directo nulo**: el snippet read-only sobre `data/items.jsonl` no encontró
  **ningún** item cuya URL apunte a `penguinlibros` / `221600` (0 hits). Los 25 items con
  `publisher` "Distrito Manga" del corpus provienen de **ListadoManga**, no de esta
  entrada del YAML.
- **#12 (Playwright / JS)**: al ser `kind: js`, sin `--enable-js` la fuente no rinde. La
  causa exacta del aporte 0 (no se ejecutó con JS, auto-detección sin selectores no
  encontró items, o bloqueo del sitio) está **{{pendiente: confirmar}}**.

---

## 9. Pendientes / limitaciones conocidas

- **Aporte 0 sin diagnóstico cerrado**: falta confirmar si el problema es la flag
  `--enable-js`, la auto-detección de selectores en penguinlibros.com, o anti-bot.
- **Sin `selectors` definidos**: si la auto-detección falla, habría que agregar
  `item_selector` / `title_selector` propios a la entrada del YAML.
  Estructura HTML real de la página → **{{pendiente: inspeccionar}}**.

---

## 10. Runbook / comandos útiles

```bash
# Scrape de esta fuente (requiere JS por kind: js, #12):
.venv/bin/python scripts/manga_watch.py --only-source "ES - Distrito Manga" --enable-js

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items de esta fuente en el corpus (read-only, para §1/§8):
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "penguinlibros"   # probar también "221600"
def hit(it):
    blobs=[it.get('url','') or '']+[(s.get('url','') or '') for s in it.get('sources',[])]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("países:", Counter((it.get('country') or '') for it in sel if it.get('country')))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar (`validate_corpus`, 0 duras)
→ tests (`pytest tests/test_extraction.py`) → build. Si tocaste algo meaningful, actualiza
esta ficha.
