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
# pipeline / filtros / scoring / titulos / extractores / retrofits / cluster:
.venv/bin/python -m pytest tests/test_extraction.py -q
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

Con `git diff --name-only HEAD`, verifica contra la tabla "Dónde va cada
cambio" de CLAUDE.md:

1. **Fuentes (regla dura)**: si cambió un parser de `scripts/wikis/<x>.py`
   o una entrada de `sources.yml` → ¿está `docs/scraper/sources/<x>.md` en
   el diff? Si no → **FAIL**.
2. **Flujo/DB**: si hay etapa nueva, campo nuevo en items.jsonl o cambio de
   workflow → ¿está `docs/scraper/PIPELINE-WALKTHROUGH.md` en el diff?
3. **Skill nuevo/cambiado** → ¿`.claude/skills/README.md` actualizado?
4. **Script nuevo** → ¿está en `scripts/script_registry.py` y en
   `docs/reference/file-map.md`?
5. **web-next feature/UX** → ¿doc en `docs/web-next/` tocado?
6. Gotcha nueva descubierta durante el trabajo → ¿`docs/reference/gotchas.md`?

Excepciones válidas (no exigir docs): fix que restaura comportamiento ya
documentado, refactor puro verde, typos, tests de reglas ya documentadas.

## Paso 4 — Reporte

Tabla única con: check | resultado (✅/❌/⏭ n/a) | evidencia (línea clave del
output). Si todo verde, decirlo y sugerir el mensaje de commit. Si hay ❌,
listar exactamente qué falta y NO commitear.
