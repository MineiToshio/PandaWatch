# Fuente: Mangastore.pl (Polonia, agregador)

> Ficha del catálogo de fuentes de PandaWatch. Léela ANTES de tocar su ingestión.
> Gotchas por número (#N) → [docs/reference/gotchas.md](../../reference/gotchas.md).
> Última revisión: 2026-06-12 (alta de la fuente).

---

## 1. Información general

| Campo | Valor |
|---|---|
| **Nombre** | PL - Mangastore (twarda) |
| **URL base** | `https://mangastore.pl` |
| **Punto de entrada** | `/szukaj.html?szukaj=twarda&postget=tak` (búsqueda "twarda" vía GET, ~70 hits, 4 págs) |
| **Tipo de fuente** | Tienda agregadora multi-editorial (retailer) |
| **`kind`** | `html` |
| **`source_class`** | `retailer` |
| **País / idioma** | Polonia / Polaco |
| **`publisher`** | **VACÍO** (gotcha #44) — el real (Kotori, Hanami, Czarna Owca, JPF…) sale de la ficha |
| **Aporte al corpus** | ~63 reportables; ~30-40 netos vs Mangarden |
| **Parser** | Entrada en `sources.yml` con selectores |

**Por qué importa**: complementa a Mangarden cubriendo editoriales PL **sin tienda
propia**: Kotori (HC de Atelier of Witch Hat, DDDD 2-in-1, Punpun), Hanami
(Przypadek Darwina), danmei HC con cantos teñidos de Czarna Owca (Błogosławieństwo
Niebios = TGCF — ojo, es de Czarna Owca, NO de Kotori).

---

## 2. Descripción técnica

- osCommerce-like, HTML estático, sin anti-bot. La búsqueda funciona vía **GET**
  (el sitio la reescribe a path-style; paginación por segmento `/s=N` que el
  paginador genérico sigue).
- **Selectores obligatorios** (`div.Okno.OknoRwd` + `a[href*='-p-']:not(.Zoom)`):
  el extractor genérico truncaba el título perdiendo "(twarda okładka)" → el gate
  rechazaba 59/63. Con selectores: 63 reportables.
- ISBN presente en la ficha de detalle. Fecha solo año.

## 8. Problemas conocidos

- ~15% ruido por matches de descripción (la búsqueda usa `opis=tak`): tomos
  regulares, prosa (Baśnie japońskie = cuentos, no manga). El gate y
  filter_non_manga lo limpian aguas abajo.
- Alta rotación de stock (muchos "Produkt niedostępny") — las fichas persisten;
  útil como referencia (la URL como referencia es válida — ver memoria del owner).
- **NO scrapear la categoría Kotori completa** (`/kotori-c-2_8.html`, 498 items,
  mayoría tankōbon regulares — C1 fail en la evaluación).

## 10. Runbook

```bash
.venv/bin/python scripts/manga_watch.py --only-source "PL - Mangastore (twarda)" --dry-run
```
