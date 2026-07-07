# Fuente: Arechi Manga

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-07-07.

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | Arechi Manga (entrada `ES - Arechi Manga Próximamente`) |
| **URL base** | `https://arechimanga.com` |
| **Índice / punto de entrada** | `https://arechimanga.com/novedades/` |
| **Tipo de fuente** | Editorial (sitio oficial de la editorial) |
| **`kind` en sources.yml** | `html` |
| **`source_class`** | `official` |
| **País(es)** | España (`es`) |
| **Idioma(s)** | ES |
| **Cobertura** | Novedades / próximos lanzamientos de Arechi Manga en su tienda WooCommerce |
| **Aporte al corpus** | 0 items hoy (ningún producto de `arechimanga` en `items.jsonl`) |
| **Parser / módulo** | Entrada en `sources.yml` (extractor genérico, sin parser propio) |

**Por qué importa / qué aporta de único**: es el canal oficial de la editorial
Arechi para anunciar próximos lanzamientos. El catálogo de Arechi en España ya
está cubierto por ListadoManga (≈70 items); esta fuente lo complementa con
novedades directas del editor. Hoy no aporta items netos.

---

## 2. Descripción técnica de la fuente

- **Estructura de URLs / páginas**: una sola página índice de novedades
  (`/novedades/`); cada producto enlaza a su ficha de tienda.
- **Estructura del HTML/feed**: sitio **WooCommerce** (WordPress blocks). Los
  productos se listan con bloques `wc-block-grid`. Selectores del YAML
  (verbatim):
  - `item_selector`: `li.wc-block-grid__product`
  - `title_selector`: `.wc-block-grid__product-title, a`
- **Identificador de producto**: URL canónica de la ficha del producto.
- **Anti-bot / quirks**: las plantillas WooCommerce suelen servir imágenes lazy
  / placeholder; la portada real va en `data-src` / `data-lazy-src` (#6).
- **Calidad de imágenes**: {{pendiente: no verificado — sin items en el corpus}}.

---

## 5. Proceso de ingestión — técnico

- **Entrada en `sources.yml`**: `ES - Arechi Manga Próximamente`
  (`kind: html`, `enabled: true`).
- Se ingesta en **FASE 1** del pipeline (`manga_watch.py --workers 8`, scrape de
  sources del YAML) vía el **extractor genérico**, usando el `item_selector` y
  `title_selector` declarados. **No tiene parser propio** ni helper dedicado.
- No participa de discovery full vs delta diferenciado: se scrapea igual en
  ambos scripts (`scrape_full.sh` / `scrape_delta.sh`).

---

## 8. Problemas encontrados — qué funcionó y qué NO

- **0 items netos — CAUSA CONFIRMADA (2026-07-07, auditoría de ingestión): NO es un
  bug del parser.** El `item_selector` (`li.wc-block-grid__product`) funciona: la
  auditoría verificó en vivo que `/novedades/` expone 5 productos visibles y el
  selector los matchea. El 0-yield histórico es correcto de acuerdo a las reglas
  de negocio: el contenido actual de `/novedades/` son **tomos regulares** (sin
  edición especial/deluxe/kanzenban), y el gate `is_collectible_edition` los
  descarta correctamente — un tomo normal sin señal coleccionable no debe entrar
  al catálogo. Antes de este hallazgo se sospechaba selector roto o layout
  cambiado; ninguna de las dos cosas es cierta.
- **#6 (imágenes lazy/placeholder)**: layout WooCommerce típico; tenerlo presente
  si se depura la extracción de portadas.

---

## 9. Pendientes / limitaciones conocidas

- Fuente con **0 aporte** hoy — pero **esperado** (ver §8): el selector funciona,
  la causa es que `/novedades/` hoy sólo lista tomos regulares sin señal
  coleccionable. Si Arechi anuncia una edición especial/deluxe, debería pasar el
  gate sin cambios de código. No hay nada que arreglar en el parser.
- La editorial Arechi ya está cubierta vía ListadoManga; el valor de esta fuente
  es captar novedades antes/directo del editor. {{pendiente: validar solape real
  con ListadoManga.}}

---

## 10. Runbook / comandos útiles

```bash
# Scrape sólo esta fuente:
.venv/bin/python scripts/manga_watch.py --only-source "ES - Arechi Manga Próximamente"

# Validar:
.venv/bin/python scripts/validate_corpus.py

# Ver items reales de esta fuente en el corpus:
.venv/bin/python - <<'PY'
import json
from collections import Counter
NEEDLE = "arechimanga"
def hit(it):
    blobs=[it.get('url','') or '']+[ (s.get('url','') or '') for s in it.get('sources',[]) ]
    return any(NEEDLE in b for b in blobs)
items=[json.loads(l) for l in open("data/items.jsonl") if l.strip()]
sel=[it for it in items if hit(it)]
print("items:", len(sel))
print("editoriales:", Counter((it.get('publisher') or '') for it in sel if it.get('publisher')).most_common(20))
PY
```

**Antes de cerrar cualquier cambio en esta fuente**: validar
(`validate_corpus`, 0 duras) → tests (`pytest tests/test_extraction.py`) → build.
Si tocaste algo meaningful, actualiza esta ficha.
