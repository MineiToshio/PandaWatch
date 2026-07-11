---
name: ship-check
description: Gate determinístico pre-commit. Detecta qué áreas tocó el diff actual, corre los checks correspondientes (pytest, dry-runs de retrofits, vitest/build de web-next) y audita que los docs requeridos por la policy de CLAUDE.md se hayan actualizado en el mismo cambio. Reporta un checklist PASS/FAIL con evidencia. Usar antes de cada commit meaningful.
argument-hint: "[--skip-build]"
disable-model-invocation: true
---

# ship-check — gate pre-commit

Automatiza el "Quick sanity check" de CLAUDE.md + la auditoría de
docs-sync. Es casi todo determinístico: corre comandos y lee exit codes.
NO arregles nada sin avisar — reporta y deja que el owner decida.

## Paso 1 — Detectar áreas tocadas

```bash
git status --porcelain && git diff --stat HEAD
```

Clasifica los archivos modificados/staged en áreas:

| Área | Match |
|---|---|
| `pipeline` | `scripts/manga_watch.py`, `scripts/wikis/*`, `scripts/*.py` |
| `filtros` | diff toca `is_likely_manga`, `is_comic_not_manga`, `is_collectible_edition`, `comics_blacklist.yml` |
| `scoring` | diff toca señales/score (`signal_types`, `score_item`, detectores) |
| `titulos` | diff toca `clean_title` |
| `extractores` | diff toca extractores label/value, covers, ISBN, author |
| `cluster` | diff toca `derive_cluster_key` |
| `retrofits` | `scripts/retrofit/*` |
| `web-next` | `web-next/**` |
| `fuentes` | `sources.yml` o un parser de `scripts/wikis/` |
| `skills/docs` | `.claude/skills/**`, `docs/**` (solo gate de docs, sin tests) |

## Paso 2 — Correr los checks del área (solo los que apliquen)

```bash
# SIEMPRE que el área tocada no sea exclusivamente "skills/docs": suite COMPLETA,
# no solo test_extraction.py (2241 tests en 59 archivos, ~53s medido — cubre
# archivos dedicados como test_job_manager.py que test_extraction.py solo nunca
# ejercita). Esto es lo que AI-WORKFLOW.md promete ("la suite completa solo en
# /ship-check final") — antes este paso corría solo el 31% de la suite.
.venv/bin/python -m pytest -q
# filtros:
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run   # esperado: 0 rechazos nuevos
.venv/bin/python scripts/retrofit/filter_collectible.py --dry-run  # solo si tocó is_collectible_edition
# titulos:
.venv/bin/python scripts/retrofit/clean_titles.py --dry-run
# extractores:
.venv/bin/python scripts/retrofit/backfill_metadata.py --dry-run
# cluster:
.venv/bin/python scripts/retrofit/backfill_cluster_key.py --dry-run
# web-next (desde web-next/):
npx vitest run
npm run build        # saltar si --skip-build
```

⚠️ `scoring`: NO correr `rescore.py` real sobre corpus estandarizado
(gotcha #61) — pytest cubre los detectores; si hace falta retrofit,
proponerlo como paso aparte con `--dry-run` y decisión del owner.

Si el diff tocó `derive_cluster_key` o invariantes de datos, agrega:
```bash
.venv/bin/python scripts/validate_corpus.py
```

## Paso 3 — Auditoría docs-sync (la policy dura)

Con `git diff --name-only HEAD`, recorré **TODAS** las filas de la tabla
"Dónde va cada cambio" de CLAUDE.md (no un subconjunto embebido acá — esa
tabla es la fuente única y crece; una lista fija en este SKILL.md driftea en
cuanto CLAUDE.md agrega una fila). Para cada fila cuyo "tipo de cambio"
matchee algo del diff, verificá que el doc correspondiente esté en el mismo
diff; si no → **FAIL** con el nombre exacto del doc que falta.

Ejemplos de la tabla (ilustrativos, no la lista completa — leé CLAUDE.md):

1. **Fuentes (regla dura)**: si cambió un parser de `scripts/wikis/<x>.py`
   o una entrada de `sources.yml` → ¿está `docs/scraper/sources/<x>.md` en
   el diff?
2. **Flujo/DB**: si hay etapa nueva, campo nuevo en items.jsonl o cambio de
   workflow → ¿está `docs/scraper/PIPELINE-WALKTHROUGH.md` en el diff?
3. **Skill/workflow nuevo o cambiado** → ¿`.claude/skills/README.md` actualizado?

Áreas que la lista anterior de este documento **no cubría** y que también son
filas de esa tabla — presta atención especial porque son las que más se
saltean:

- **Imágenes** (extractor, espejo local, carrusel) → `docs/reference/images.md`.
- **Dashboard / serve.py / curación** → `docs/reference/dashboard.md`.
- **Decisión de arquitectura / storage / cluster_key / corpus state** →
  `docs/reference/architecture.md` (+ el gist en CLAUDE.md si cambia).
- **Convención de código nueva** (filtros, backup/flush, registry) →
  `docs/reference/conventions.md`.
- **Scraper — pipeline internals / data flow (deep dive)** →
  `docs/scraper/ARCHITECTURE.md`.
- **Env var / dependencia nueva** → `.env.example` + el doc del componente.
- Script nuevo → ¿está en `scripts/script_registry.py` y en
  `docs/reference/file-map.md`?
- web-next feature/UX → ¿doc en `docs/web-next/` tocado?
- Cambio al proceso de implementación con IA → `docs/process/AI-WORKFLOW.md`.
- Gotcha nueva descubierta durante el trabajo → `docs/reference/gotchas.md`.

Excepciones válidas (no exigir docs): fix que restaura comportamiento ya
documentado, refactor puro verde, typos, tests de reglas ya documentadas.

## Paso 4 — Reporte

Tabla única con: check | resultado (✅/❌/⏭ n/a) | evidencia (línea clave del
output). Si todo verde, decirlo y sugerir el mensaje de commit. Si hay ❌,
listar exactamente qué falta y NO commitear.
