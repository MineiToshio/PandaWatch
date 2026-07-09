# Ciclo de vida del dato — runbook completo end-to-end

> ⚠️ **DOCUMENTO VIVO — mantener SIEMPRE sincronizado.** Cada cambio en el flujo
> end-to-end o que impacte la base de datos (nueva etapa/paso del ciclo de vida,
> nuevo proceso post-scrape, reordenamiento de etapas, campo nuevo en
> `items.jsonl`, nueva funcionalidad del workflow) **se documenta acá en el mismo
> turn**. Es policy del repo (ver tabla "dónde va cada cambio" en CLAUDE.md).
>
> **Qué es este documento.** El proceso **completo** para llevar el dato de
> PandaWatch desde "no existe" hasta "100% listo para publicar": cómo se
> consigue en las distintas páginas, cómo se transforma/filtra, cómo se
> estandariza, cómo se consiguen y mejoran las fotos, cómo se traduce, cómo se
> generan los slugs, cómo se valida la rareza, cómo se procesa el feedback y
> cómo se aprueban los golden records — **en el orden en que conviene correrlo**.
>
> No es solo el scrape: el scrape es la **Etapa 0**. Las etapas 1–9 son los
> procesos que dejan el dato realmente completo.
>
> Niveles de lectura:
> 0. [Vista de pájaro](#0-vista-de-pájaro-todo-el-flujo-de-un-vistazo) — el flujo entero en un solo gráfico.
> 1. [Mapa de etapas](#1-mapa-de-etapas-el-orden-completo) — el ciclo entero de un vistazo.
> 2. [Diagramas de flujo](#2-diagramas-de-flujo) — visual, por sub-proceso.
> 3. [Detalle por etapa](#3-detalle-por-etapa) — cada paso, comando por comando.
> 4. [Runbooks listos para copiar](#4-runbooks-listos-para-copiar).
>
> Referencias: [`CLAUDE.md`](../../CLAUDE.md), [`ARCHITECTURE.md`](ARCHITECTURE.md),
> [`SOURCES.md`](SOURCES.md), [`scripts/retrofit/README.md`](../../scripts/retrofit/README.md),
> [`docs/reference/images.md`](../reference/images.md),
> [`docs/reference/gotchas.md`](../reference/gotchas.md),
> [`FRD-006-slug-generation.md`](../web-next/FRD-006-slug-generation.md).

---

## 0. Vista de pájaro (todo el flujo de un vistazo)

> **Herramienta: Mermaid.** Es la mejor opción para este repo porque GitHub (y
> VS Code, Obsidian, GitLab) lo renderiza **nativo** desde un bloque ` ```mermaid `,
> sin paso de build ni servidor, y el diagrama es **texto** — versionable y
> revisable en PRs como el resto del código. (Alternativas evaluadas: **D2** tiene
> mejor auto-layout pero no renderiza nativo en ningún lado — necesita compilar a
> SVG/PNG; **PlantUML** requiere un servidor Java. Para docs en Markdown, Mermaid
> gana.) Si querés editarlo visualmente: [mermaid.live](https://mermaid.live).

El flujo completo, de la web hasta el dashboard, en 6 bloques. **Azul** = automático
(scrape); **gris** = dato crudo; **morado** = curación con IA (skills); **verde** =
enriquecimiento mecánico; **ámbar** = decisión humana; **turquesa** = publicación.

```mermaid
flowchart LR
    WEB["🌍 ~63 fuentes + 26 wikis<br/>20 países · 14 idiomas"]:::src
    SCRAPE["⚙️ SCRAPE<br/>full / delta<br/>(fetch · filtra · puntúa)"]:::auto
    RAW["📄 items.jsonl<br/>CRUDO"]:::raw
    CURATE["🧠 CURACIÓN IA<br/>standardize · aliases · feedback<br/>(serie · edición · volumen)"]:::ai
    ENRICH["✨ ENRIQUECIMIENTO<br/>imágenes hi-res · traducción<br/>slugs · rareza"]:::enr
    APPROVE["✅ APROBACIÓN<br/>humana<br/>(golden records)"]:::human
    PUB["🌐 PUBLICACIÓN<br/>dashboard + web-next<br/>/item/[slug]"]:::pub

    WEB --> SCRAPE --> RAW --> CURATE --> ENRICH --> APPROVE --> PUB

    classDef src    fill:#e3f2fd,stroke:#1565c0,color:#0d2b4e
    classDef auto   fill:#bbdefb,stroke:#1565c0,color:#0d2b4e
    classDef raw    fill:#eceff1,stroke:#607d8b,color:#263238
    classDef ai     fill:#ede7f6,stroke:#6a1b9a,color:#311b4e
    classDef enr    fill:#e8f5e9,stroke:#2e7d32,color:#1b3a1f
    classDef human  fill:#fff8e1,stroke:#f9a825,color:#5b4300
    classDef pub    fill:#e0f2f1,stroke:#00897b,color:#003d36
```

**Cómo leerlo:** cada bloque entrega lo que el siguiente necesita. El scrape consigue
el dato y lo deja crudo; la curación IA le pone identidad (qué serie/edición/volumen
es); el enriquecimiento lo completa (fotos buenas, traducción, slug, rareza); el humano
aprueba lo correcto (queda congelado); y se publica. El detalle de cada bloque —con sus
~15 pasos, comandos y campos— está en las secciones siguientes.

---

## 1. Mapa de etapas (el orden completo)

El dato pasa por **10 etapas**. Las etapas **0 y 1** son obligatorias siempre.
El resto se corre **según lo que cambió** (todos los procesos son idempotentes e
incrementales: solo tocan lo que falta).

| # | Etapa | Cómo se ejecuta | Output / campo que completa |
|---|---|---|---|
| **0** | **Adquisición** (scrape) | `scrape_full.sh` / `scrape_delta.sh` (automático) | filas crudas en `items.jsonl` |
| **0.5** | **Descubrimiento extra** (opcional) | `search_discovery.py` + `expand_*` | items nuevos vía Gemini/Tavily/DDG |
| **1** | **Transformación / limpieza** | retrofits de cleanup (dentro del scrape, Fase 3) | títulos limpios, filtros, `cluster_key`, `sources[]` |
| **2** | **Estandarización** 🧠 | skill `/watch-standardize-catalog` | `series_key`, `edition_key`, `volume`, `standardized_at` (o `standardize_attempts` si queda pendiente) |
| **3** | **Aliases de series** 🧠 | skill `/watch-enrich-series-aliases` | `series_aliases.yml` + backfill |
| **4** | **Slugs** | `generate_slugs.py` (último paso del skill #2) | `slug` |
| **5** | **Traducción** | `translate_descriptions.py` (último paso del skill #2) | `description_es` + `description_es_src_hash` (staleness) |
| **6** | **Imágenes / portadas** | sub-pipeline de 10 pasos (ver §3.6) | `images[]` en hi-res (`images[0]` = portada; cada entry con `url`+`local`) |
| **7** | **Rareza** | `set_rarity.py` + skill `/watch-validate-rarity` 🧠 | `rarity`, `rarity_verified_at` |
| **8** | **Feedback** 🧠 | skill `/watch-review-feedback` | corrige errores reportados (👎) |
| **9** | **Aprobación humana** | dashboard → `approved_at` + `apply_approvals.py` | golden records congelados |
| **★** | **Build / publish** | `consolidate_sources.py` + `build_web.py` | `web/index.html` + web-next |
| **✔** | **Validación estructural** | `validate_corpus.py` (gate DURO, PHASE 4 de scrape_*.sh — **ANTES** del build, 2026-07-07) | reporte de invariantes (0 violaciones duras = corpus válido) + warnings EDSLUG/SERIESDUP/EKPREFIX/PUBMIX (gotchas #69/#70/#71) + 10 invariantes WARN nuevas (2026-07-07): DATEISO/PTYPE_ENUM/LANG_ENUM/VOLRANGE/EKMALFORMED/SLUGUNIQ/SLUGFMT/STDKEYS/MIRRORREF/SRCURL (ver §3.★); exit 2 = violaciones duras → el build (PHASE 5) se OMITE (gotcha #111) y el corpus va a cuarentena + restore automático desde el backup pre-scrape si es válido (ver recuadro PHASE 4 abajo) |

🧠 = LLM-driven (skill). **Nunca corre solo** — el owner lo invoca por nombre (policy de tokens, CLAUDE.md).

> **Gate de validación — exit real vía `PIPESTATUS` (fix 2026-06-13) + gate ANTES del
> build (fix 2026-07-07, gotcha #111).** `scrape_delta.sh`/`scrape_full.sh` corrían
> `validate_corpus.py | tee log || echo "⚠ violaciones"` **DESPUÉS** del build. Sin
> `set -o pipefail`, `$?` del pipe era el de `tee` (siempre 0), así que el `|| echo`
> **nunca disparaba**: un run desatendido que rompiera invariantes no dejaba señal
> visible — y aunque la dejara, el build YA había publicado el corpus corrupto. Ahora:
> (1) se captura `${PIPESTATUS[0]}` (exit real de validate_corpus); (2)
> `validate_corpus.py` devuelve **exit 2** específicamente para violaciones duras (antes
> `1`, ambiguo con errores del propio script); (3) el validador corre como **PHASE 4**,
> ANTES del build; (4) el build (**PHASE 5**) se **OMITE por completo** si
> `CORPUS_INVALID=1`, dejando el build anterior intacto. `CORPUS_INVALID` se surfacea en
> el FINAL SUMMARY (`corpus: ⚠ INVÁLIDO … · build OMITIDO` vs `✓ válido`), junto a
> **`FAILED_STEPS`** — un array bash que acumula el `$?` de CADA bootstrap/retrofit/build
> de la corrida (no solo el gate), impreso también en el FINAL SUMMARY: con `set +e` un
> paso que crashea a mitad de la cadena era antes invisible. Crítico para el LaunchAgent
> nocturno.
>
> **Cuarentena + restore automático (2026-07-07).** "Se omite el build" NO alcanza:
> `serve.py` hace `fetch()` EN VIVO de `data/items.jsonl` (decisión #5) — un corpus
> corrompido queda SERVIDO igual aunque no se reconstruya el HTML. Si `CORPUS_INVALID=1`
> tras PHASE 4: (1) `data/items.jsonl` se mueve a
> `data/quarantine/items-<TIMESTAMP>.jsonl`; (2) si hay backup pre-scrape (capturado al
> INICIO del script, antes de tocar nada), se valida ese backup con `validate_corpus.py
> --file <backup>` — si el backup ES válido, se copia a `data/items.jsonl` (RESTAURADO) y
> se re-aplican las aprobaciones en vivo del dashboard hechas DURANTE esta misma corrida
> (`apply_approvals.py`, porque el restore pisó `items.jsonl` con un backup que no las
> tiene todavía); (3) si el backup TAMBIÉN es inválido, o no hay backup disponible
> (primera corrida), NO se restaura nada — el corpus previo queda en cuarentena para
> revisión manual. El resultado (`restaurado` / `backup_invalido` / `sin_backup` /
> `sin_corpus`) se imprime en el FINAL SUMMARY junto a `CORPUS_INVALID`.

**Regla de oro del flujo.** El scrape (Etapa 0/1) deja `items.jsonl` **crudo**
(sin `standardized_at`/`slug`/`description_es`/`rarity`). Todo lo demás es una
pasada **post-scrape**, manual o semi-manual, que el owner dispara cuando quiere.

**Orden corto recomendado** tras un scrape grande:

```
scrape → standardize → enrich-aliases → imágenes → rarity → translate → feedback → aprobar → build
         (slugs+translate van adentro de standardize)
```

---

## 2. Diagramas de flujo

### 2.1 Ciclo de vida completo (las 10 etapas)

```mermaid
flowchart TD
    subgraph E0["ETAPA 0 · ADQUISICIÓN (automática)"]
        SCRAPE["scrape_full.sh / scrape_delta.sh<br/>~63 fuentes + 26 wikis"]
        DISC["search_discovery.py + expand_*<br/>(descubrimiento extra, opcional)"]
    end
    SCRAPE --> RAW
    DISC --> RAW
    RAW["📄 items.jsonl CRUDO<br/>(sin standardized_at/slug/rarity)"]

    RAW --> E2["ETAPA 2 · 🧠 /watch-standardize-catalog<br/>series_key · edition_key · volume<br/>+ dedup + non_manga_blacklist"]
    E2 --> E3["ETAPA 3 · 🧠 /watch-enrich-series-aliases<br/>(si aparecen series_key nuevos)"]
    E2 -.incluye.-> E4["ETAPA 4 · generate_slugs.py → slug"]
    E2 -.incluye.-> E5["ETAPA 5 · translate_descriptions.py → description_es"]

    E3 --> E6
    E6["ETAPA 6 · IMÁGENES (sub-pipeline 7 pasos)<br/>mirror → upgrade-res → PRH → better-covers<br/>→ upscale → search-covers → sync"]
    E6 --> E7["ETAPA 7 · set_rarity.py + 🧠 /watch-validate-rarity"]
    E7 --> E8["ETAPA 8 · 🧠 /watch-review-feedback<br/>(procesa los 👎)"]
    E8 --> E9["ETAPA 9 · Aprobación humana (dashboard)<br/>approved_at + approvals.jsonl"]

    E9 --> BUILD["★ consolidate_sources.py → build_web.py"]
    BUILD --> PUB["🌐 Dashboard (serve.py) + web-next /item/[slug]"]
```

### 2.2 Etapa 0 — el scrape automático (fases 1→6)

```mermaid
flowchart TD
    START([./scripts/scrape_delta.sh<br/>o scrape_full.sh]) --> BAK["Backup pre-scrape items.jsonl<br/>(2026-07-07, ANTES de tocar nada)"]
    BAK --> LOG["logs/scrape-*-TS/"]
    LOG --> F1["FASE 1 · manga_watch.py<br/>--enable-js --fetch-details --workers 8<br/>--min-score 20 · timeout 90m/3h"]
    F1 --> F2{"FASE 2 · Wikis<br/>¿delta o full?"}
    F2 -->|DELTA| D2["listadomanga **calendar** (hoy-3m → hoy+3m)<br/>+ 13 wikis recientes<br/>+ **mangavariant incremental** (solo URLs nuevas vs corpus, tope 400)"]
    F2 -->|FULL| FU2["listadomanga **lista** (~3432)<br/>+ **mangavariant sitemap** (~2700, todo)<br/>+ histórico de wikis (--wiki-from 2000/2013/2015)"]
    D2 --> F3
    FU2 --> F3
    F3["FASE 3 · Cleanup retrofits<br/>(= ETAPA 1)"] --> R["rescore → **clean_titles** →<br/>normalize_release_dates →<br/>filter_non_manga → filter_collectible →<br/>backfill imágenes →[full] mirror →<br/>enforcer → consolidate_sources"]
    R --> F4{"FASE 4 · validate_corpus<br/>(gate DURO)"}
    F4 -->|✗ exit 2: violaciones duras| SKIP["build OMITIDO<br/>(build anterior intacto)"]
    F4 -->|✓ válido| F5["FASE 5 · build_web.py"]
    F5 --> F6["FASE 6 · source_health<br/>(+ metrics.jsonl + baseline-alert)<br/>+ staleness_report"]
    SKIP --> F6
    F6 --> END([items.jsonl crudo + web])
```

### 2.3 Per-source pipeline (qué le pasa a CADA candidato en Fase 1/2)

```mermaid
flowchart TD
    FETCH["1· Fetch<br/>html/rss/bluesky/js(Playwright)"] --> PARSE["2· Parse candidates"]
    PARSE --> CLEAN["3a· clean_title()"]
    CLEAN --> MANGA{"3b· is_likely_manga()"}
    MANGA -->|no| D1((drop))
    MANGA -->|sí| NOVEL{"3c· is_pure_novel()?"}
    NOVEL -->|LN| D2((drop))
    NOVEL -->|no| COMIC{"3d· is_comic_not_manga()?"}
    COMIC -->|comic occidental| D3((drop))
    COMIC -->|no| SCORE["3e· score_candidate / detect_signals"]
    SCORE --> DETAIL["4· fetch_metadata_from_detail<br/>ISBN/autor/imagen"]
    DETAIL --> GATE{"5· is_collectible_edition()"}
    GATE -->|tomo regular| D4((drop))
    GATE -->|sí| STATE["6· process_state (new/changed/seen)"]
    STATE --> FLUSH["7· flush incremental"]
    FLUSH --> IMG["8· mirror_candidate_images → data/images/"]
    IMG --> CK["9· derive_cluster_key"]
    CK --> PERSIST["10· append_jsonl + consolidate_by_cluster"]
```

### 2.4 Etapa 2 — estandarización (skill, 3 tiers)

```mermaid
flowchart TD
    AUDIT["Audit · confidence_tier de items SIN standardized_at"] --> T1["Tier 1 ~30%<br/>determinista · 0 tokens"]
    AUDIT --> T2["Tier 2 ~9%<br/>LLM valida (chunks 20)"]
    AUDIT --> T3["Tier 3 ~37%<br/>LLM deriva full (chunks 15)"]
    T1 --> MERGE["Merge + canonical_series_key<br/>+ consistency + coleccion=edicion<br/>+ dedup (consolidate_by_cluster)"]
    T2 --> MERGE
    T3 --> MERGE
    MERGE --> NM["no-manga → PENDIENTE + unmapped_series.jsonl<br/>(llm_non_manga; gates deterministas expulsan después)"]
    MERGE --> SLUG["generate_slugs.py (ETAPA 4)"]
    SLUG --> TR["translate_descriptions.py (ETAPA 5)"]
    TR --> TEST["pytest test_extraction.py"]
```

### 2.5 Etapa 6 — sub-pipeline de imágenes (orden recomendado)

```mermaid
flowchart LR
    A["mirror_images.py<br/>(espejo histórico)"] --> B["upgrade_image_resolution.py<br/>(quita params CDN)"]
    B --> GC1["mirror_images --gc"]
    GC1 --> C["backfill_prh_covers.py<br/>(EN · ISBN→PRH CDN)"]
    C --> D["fetch_better_covers.py<br/>(ISBN CDN + Tavily)"]
    D --> E["upscale_images.py<br/>(AI upscale JP thumbs)"]
    E --> F["🧠 /watch-search-covers<br/>→ cover_preview.json"]
    F --> APPR["aprobación manual<br/>cover-preview.html"]
    APPR --> G["sync_cover_images.py<br/>(saneamiento dups/junk)"]
```

---

## 3. Detalle por etapa

### 3.0 ETAPA 0 — Adquisición (el scrape)

Dos corridas canónicas, misma estructura (4 fases), misma diferencia central:
**solo cambia el discovery de listadomanga + el alcance histórico**.

| Script | listadomanga | Extra | Frecuencia | Tiempo |
|---|---|---|---|---|
| `scrape_delta.sh` | `--coleccion-mode calendar` (3 meses, ~500-600 colecciones) | wikis recientes | diaria/semanal | ~30-60 min |
| `scrape_full.sh` | `--coleccion-mode lista` (~3432 colecciones) | **+ mangavariant** (~2700) + histórico de wikis + galería + mirror | mensual/trimestral | ~2-4 h |

#### Convenciones de ambos scripts
- `set +e` (si una fase falla, las demás corren). Logs por sub-paso en `logs/scrape-{delta,full}-<TS>/`.
- Skippeable por env var: `SKIP_SCRAPE` / `SKIP_WIKIS` / `SKIP_CLEANUP` / `SKIP_BUILD`.
- `_run_timed` (timeout portable) por fuente — una colgada no bloquea el resto.
- Backup de `items.jsonl` antes de tocar (`backup_and_rotate`, 3 copias). **Desde
  2026-07-07** el primer backup ocurre AL INICIO del script (antes de Fase 1), no recién
  en un retrofit puntual de Fase 3 — cubre también scrape+wikis.
- **`FAILED_STEPS` (2026-07-07, ampliado 2026-07-08)**: cada bootstrap/retrofit/build de
  la corrida se envuelve en `record_step <nombre> $?`; los que fallan (rc≠0) quedan
  listados en el FINAL SUMMARY. Con `set +e` un paso que crashea a mitad de la cadena era
  antes invisible entre el resto de la salida. **Desde 2026-07-08 (S1)** la Fase 1
  (scrape principal) TAMBIÉN pasa por `record_step "scrape-principal" $?` — antes un
  crash o timeout (rc=124) de la fase más larga del run no dejaba rastro en
  `FAILED_STEPS`; el SUMMARY decía "ninguno" con el scrape entero muerto.
- **Lock global `data/.scrape.lock`** (2026-06-12, endurecido 2026-07-08): mkdir atómico
  + PID; una segunda corrida (delta, full o `bootstrap.sh`) aborta sola en vez de
  corromper items.jsonl. Lock stale (PID muerto) se recupera automáticamente. **S2**:
  si dos procesos detectan el lock stale a la vez, sólo uno gana el `mkdir` que sigue —
  antes el perdedor seguía corriendo SIN lock (y su trap heredado borraba el del
  ganador al salir); ahora el perdedor aborta con rc=1. **`bootstrap.sh` ahora también
  toma este lock** (antes no tomaba ninguno).
- **Marker de aborto `data/.run-aborted` (S4, 2026-07-08)**: un Ctrl+C/SIGTERM a mitad
  de run saltea el gate `validate_corpus` y dejaba el trap EXIT liberar el lock sin
  validar nada — un corpus inter-pasos inválido podía quedar servido sin que nadie lo
  supiera. Ahora el trap de INT/TERM escribe `data/.run-aborted` (señal + fase +
  timestamp + PID) ANTES de salir; el trap EXIT lo consulta y, si existe, **NO libera
  el lock** (hay que revisar el corpus a mano — `validate_corpus.py` — antes de borrar
  el marker y el lock). Al arrancar, si el marker de una corrida previa existe, el
  script avisa en el log y lo borra recién después de su propio backup pre-scrape.
- **[4f3] `enforce_listadomanga_rules.py --fast`** corre en la FASE 3 de ambos
  (cadena completa de agrupación, incluye merge ISBN/series, dedup sintético,
  consolidate y slugs — invariantes DUPSYN/TITLE/DUPVOL/ISBNDUP).
- **Retrofits network-bound de Fase 3 con `_run_timed` (S3, 2026-07-08)**:
  `backfill_metadata.py --only image_url/images`, `mirror_images.py --no-gc` y
  `wayback_recover.py` (opt-in) hacen 1 request HTTP por item — antes corrían SIN
  timeout (regresión de gotcha #33): un host colgado bloqueaba el run entero y
  mantenía el lock global tomado por horas. Ahora todos están envueltos en
  `_run_timed` igual que el resto de los pasos de red del pipeline.
- **Rotación de `logs/scrape-*` a 14 corridas (B16, 2026-07-08)**: antes de crear el
  `LOG_DIR` de la corrida, se podan los directorios `logs/scrape-*` más viejos
  dejando sólo los últimos 14 (por mtime). `data/metrics.jsonl` (histórico append-only
  que consume `source_health.py` para el baseline) NO se toca acá — es responsabilidad
  de otro paquete si algún día necesita rotación propia.
- **PHASE 4 `validate_corpus.py`, ANTES del build (2026-07-07, gotcha #111)**: gate
  duro — exit 2 = violaciones duras → PHASE 5 (build) se OMITE, el build anterior
  queda intacto. **Cuarentena + restore automático (2026-07-07)**: si el corpus queda
  inválido, se mueve a `data/quarantine/items-<TS>.jsonl` y, si el backup pre-scrape
  resulta válido, se restaura + se re-aplican las aprobaciones en vivo de la corrida.
  Ver el recuadro de "Gate de validación" arriba.
- **PHASE 6 `source_health.py --last-n 1 --metrics-file logs/metrics.jsonl
  --baseline-alert --mode delta|full`** al cierre de ambos: el resumen de fuentes con
  errores/0-candidatos de ESTE run queda en `logs/scrape-*/06-source-health.md`, y desde
  2026-07-07 además acumula histórico por fuente en `logs/metrics.jsonl` y alerta si el
  yield actual cae <50% de la mediana histórica del MISMO modo (warm-up ≥3 runs) — cubre
  el caso "200 OK pero 0 items" que el clasificador de un solo run no puede ver. Cierra
  con **`staleness_report.py --days 90`** (read-only, no bloquea): URLs de `state.json`
  sin verse hace >90 días, por fuente.

#### Delta diario (programación)
`scripts/com.pandawatch.scrape-delta.plist` — LaunchAgent de macOS listo para correr
el delta todos los días a las 3:30 AM (instrucciones de instalación dentro del archivo;
NO está instalado por defecto — decisión del owner). Si la Mac duerme a esa hora,
launchd lo dispara al despertar. Con el lock global, un delta diario nunca pisa un
full manual en curso.

#### FASE 1 — sources del YAML
```bash
manga_watch.py --enable-js --fuzzy-keywords --max-pages 5 --fetch-details \
  --diagnostic --workers 8 --per-host-limit 2 --sleep-seconds 0.5 --min-score 20
```
- Lee `sources.yml` (151 entradas, 63 habilitadas), despacha cada fuente a `_scrape_one`.
- `ThreadPoolExecutor(workers=8)` + `Semaphore` por host. Fuentes `kind: js` → **Playwright worker thread + queue** dedicado (gotcha #12).
- Timeout 90 min (delta) / 3 h (full).

#### FASE 2 — Wiki bootstraps
La **diferencia central** full vs delta:

| | listadomanga | wikis extra |
|---|---|---|
| DELTA | `calendar`, `--wiki-from` últimos 3 meses **`--wiki-to` próximos 3 meses** (2026-07-07) | 15 wikis recientes (manga-sanctuary, otaku-calendar, manga-mexico, socialanime, blogbbm, sumikko, mangapassion, animeclick, prhcomics, kinokuniya, yenpress, shueisha, viz, **sevenseas**, **kodansha-us**) **+ mangavariant incremental** (2026-07-07) |
| FULL | `lista` ~3432, `--min-score 30` | **+ mangavariant sitemap ~2700 (todo)** + cada wiki con `--wiki-from 2000/2013/2015` (histórico) + **sevenseas** (full, catálogo completo) + **kodansha-us** (full) |

Notas: `booksprivilege` **deshabilitado** (2026-05-26); `whakoom` y el histórico de `listadomanga-blog` son **opt-in/fuera** del canónico. Mangavariant: sus items son **siempre** manga válido (nunca van a blacklist). **Mangavariant ya NO es full-only** (2026-07-07): el delta lo corre en modo **incremental** — baja los sitemaps (costo fijo: sitemaps + 1 resolución del challenge sgcaptcha) y fetchea SOLO las variantes cuya URL no está ya en `items.jsonl` (diff contra el corpus), ordenadas por `lastmod` desc y acotadas por `MANGAVARIANT_MAX_NEW` (default 400). Selección desde el shell vía env vars (`MANGAVARIANT_INCREMENTAL=1`), sin tocar `manga_watch.py`. Cierra el lag de ~3 meses que tenían las variantes nuevas. Con esto **no queda ninguna fuente de descubrimiento full-only** (los pasos full-only restantes son de imagen/calidad: backfill galleries, mirror, upgrade-resolution, dedup-carousel `--all`). **`kodansha-us`** (alta 2026-06-12): API propia `/wp-json/kodansha/v1/search-series` + JSON-LD por volumen (~61 series especiales, ~200-300 vols). Reemplaza la fuente search `US - Kodansha USA (search)` que devolvía artículos de blog (0 candidatos). **`sevenseas`** (alta 2026-06-12): API WordPress, ~150-250 especiales EN.

**Ventana futura del delta (2026-07-07, P1 de la auditoría de ingestión).** El delta
pasa `LISTADO_CAL_TO` (default hoy+3 meses) a `listadomanga-collections`, además del
`LISTADO_CAL_FROM` (hoy-2 meses) que ya existía — antes la ventana quedaba
`[hoy-2m..hoy]` y se perdían los anuncios/"en preparación" que `calendario.php` YA
tiene poblados para meses futuros (el delta era ciego al futuro). El dedup (synthetic
URL + cluster_key) absorbe el solapamiento entre corridas cuando esos anuncios pasan a
confirmados.

**Campo nuevo `original_title` (2026-07-07).** `listadomanga_collections.py` ahora
extrae el bloque "Título original:" del header de cada `/coleccion`
(`_extract_original_title_from_header`) y lo persiste como `original_title` (solo si
no-vacío) — típicamente romaji, a veces + el título japonés entre paréntesis y/o el
título en inglés tras " / ". Es semilla para el flujo de aliases (Etapas 2-3 lo pueden
usar para poblar `series_aliases.yml`); **nunca** toca `title` ni `title_original`
(gotcha #22) — es un campo aparte y opcional. Detalle en architecture.md → "Política
de títulos".

Cada candidato pasa por el **per-source pipeline** (§3.0.bis).

#### FASE 3 = ETAPA 1 (cleanup) — ver §3.1.
#### FASE 4 — `validate_corpus.py` (gate DURO, ANTES del build) — ver §3.★.
#### FASE 5 — `build_web.py` (solo si el corpus es válido) — ver §3.★.
#### FASE 6 — `source_health.py` (+ metrics/baseline-alert) + `staleness_report.py` — ver "Convenciones de ambos scripts" arriba.

#### 3.0.bis Per-source pipeline (el corazón del scrape)
Detalle de los 10 pasos por cada candidato (vale para sources y wikis):

1. **Fetch** — `html`→requests (+paginación), `rss`→feedparser, `bluesky`→XRPC público, `js`→Playwright.
2. **Parse candidates** → `extract_listing_candidates` / `extract_rss` / `extract_bluesky_posts` → objetos `Candidate`.
3. **Filter & score**:
   - `clean_title()` — mojibake (round-trip cp1252/latin-1), prefijos/sufijos junk.
   - `is_likely_manga()` — cascada 4 reglas (HARD→STRONG→extras→SOFT→default) + filtro de tags (`type:oav`…).
   - `is_pure_novel()` — rechaza light novels (salvo adaptación/artbook).
   - `is_comic_not_manga()` — blacklist Marvel/DC (`comics_blacklist.yml`); bypass si el título dice "manga".
   - `score_candidate()` → `detect_signals()` (~70 keywords, **word-boundary regex no substring**, clamp [0,300]) → `signals`, `signal_types`, `product_type`, `stock_type`.
   - ⚠️ Invariante: `detect_signals` corre **solo sobre title+description**, nunca fuente/tags/keywords.
4. **Detail enrichment** (`--fetch-details`) — HTTP por item: JSON-LD → OpenGraph → `_extract_label_value_pairs` (FR/ES/EN/IT/JP) → fallbacks → name/author/image/isbn/release_date/publisher/description. `release_date` se normaliza a ISO (`normalize_release_date()`: YYYY-MM-DD, o YYYY-MM/YYYY si la fuente solo da granularidad parcial) en TODOS los puntos de asignación — al corpus no entran fechas crudas DD/MM/YYYY ni 年月日 (gotcha #80).
5. **Collectible gate** `is_collectible_edition()` — solo ediciones especiales/variants/deluxe/limited/boxsets/artbooks/fanbooks/magazines. Signals **recomputados desde el título** dentro del gate.
6. **State diff** `process_state()` — `content_hash` vs `state.json`: new/changed/seen.
7. **Flush incremental** — escribe tras CADA fuente (resiliencia).
8. **Image mirror** `mirror_candidate_images()` — descarga CADA imagen a `data/images/<sha256>.<ext>` y setea su `local` en `images[]` (`images[0]` = portada). `_extract_images_from_detail_soup` trae el carrusel a `images[]`. (Ya no hay campos top-level `image_url`/`image_local`; el `Candidate` runtime los lleva como input y `candidate_to_json` los vuelca en `images[0]`.) **Desde 2026-06-15 `download_image` ESTANDARIZA cada imagen al bajarla** (AVIF Q60, lado largo ≤1600px, sin metadata; fuente única `image_store.normalize_image`) → el espejo entra ya optimizado. Solo achica (el upscale es aparte); los placeholders pasan crudos para no romper la detección por firma (gotcha #100).
9. **`derive_cluster_key`** — tiers `lmc:` > `edition:` > `isbn:` > `fuzzy:` > `url:`. Se deriva DESPUÉS de escribir el edition_key heurístico en el row (gotcha #65): la fila fresca entra ya consistente con la invariante CLKEY.
10. **Persist** `append_jsonl` — upsert por URL normalizada + `consolidate_by_cluster` (1 fila/producto + `sources[]`). Escritura atómica. `_CURATED_FIELDS` sticky (incluye `slug`/`detected_at`/`score`/`signals`/`signal_types` desde gotcha #65; el merge re-deriva `cluster_key` con los curados restaurados); `slug` es sticky para TODOS los items; `approved_at` congela la fila.

#### 0.5 — Descubrimiento extra (opcional, no es scrape)
- `search_discovery.py` — descubre items **nuevos** vía Gemini grounding → Tavily → DuckDuckGo HTML (queries en `data/search_queries.yml`). Corre ~1×/semana para ampliar corpus sin esperar al overnight.
- Tras un discovery, limpiar páginas-índice que entran como productos:
  - `expand_whakoom_ediciones.py` — convierte `/ediciones/<id>` en N filas por tomo.
  - `expand_index_pages.py` — expande/elimina `/publisher/`, Shopify multi-variant, `/blogs/news/`, `/collections/X` sin `/products/`.

---

### 3.1 ETAPA 1 — Transformación / limpieza (Fase 3 del scrape)

Cadena de retrofits que limpia y consolida lo recién scrapeado (corre **dentro** del scrape; también se puede correr suelta tras tocar reglas). **El orden importa.**

| Paso | Script | Qué hace |
|---|---|---|
| 4a | `rescore.py` | Recalcula `score`/`signals`/`signal_types`/`product_type`. **Guard gotcha #61 (2026-06-11)**: items con `standardized_at` se saltean por defecto (`--include-standardized` para override) — el paso es seguro sobre corpus estandarizado. |
| 4b | `clean_titles.py` | Re-corre `clean_title` (mojibake, junk). **Reordenado ANTES de los filtros (2026-07-07, gotcha #110)**: antes corría al final (4d) y los gates de 4c/4d evaluaban el título SUCIO en un run y el LIMPIO recién en el siguiente — un título que solo pasa/rechaza tras limpiarse (ej. 한정판 recortado por `_strip_korean_retailer_tail`) daba resultado distinto según en qué run cayera. Ahora los filtros ven SIEMPRE el título ya limpio, en la misma corrida. |
| 4b2 | `normalize_release_dates.py --all-formats` | **Automático desde 2026-07-07**: re-normaliza `release_date` legacy a ISO (`normalize_release_date()`, fuente única). `--all-formats` porque el backlog real (113 filas, invariante DATEISO) es casi todo datetime de tienda JP (`YYYY/MM/DD hh:mm:ss`), fuera de la familia DD/MM/YYYY que cubre el modo default. Barato (compute-only, sin red) y no-op cuando el corpus ya está limpio — `normalize_release_date()` ya es la guardia universal en el sink del scraper (`candidate_to_json`), así que items nuevos entran normalizados; este paso sólo limpia legacy que sobrevivió (backups restaurados, merges crudos). |
| 4c | `filter_non_manga.py` | Re-aplica `is_likely_manga`+`is_pure_novel`+`is_comic_not_manga`; expulsa rechazados. |
| 4d | `filter_collectible.py` | Re-aplica `is_collectible_edition`; expulsa tomos regulares. ⚠️ puede quitar referencias Mangavariant — el skill standardize las preserva. **Guard de estandarizados (gotcha #61)**: items con `standardized_at` solo pasan gates duros (junk de título, umbrella_magazine URL-gate), bucket `kept_standardized` — NO se les recomputa `signal_types` desde el texto. `rescore.py` tiene el mismo guard desde 2026-06-11 (salta `standardized_at` por defecto). |
| 4e | `backfill_metadata.py --only image_url` | Rellena portadas faltantes (HTTP por item). |
| 4e2 | `backfill_metadata.py --only images` | **[full]** galería multi-imagen (carrusel). |
| 4e3 | `mirror_images.py --no-gc` | **[full]** descarga galería al espejo local. |
| 4f | `wayback_recover.py` | **opt-in** — rescata items 404 vía archive.org. |
| 4f2 | `align_raw_to_std_coleccion.py` | Alinea items raw a la edición estandarizada de su MISMA coleccion (regla coleccion=edición). Evita el dup raw-vs-std al re-scrapear una colección ya conocida (ej. "Bastard!! nº1" vs "Bastard!! Deluxe 1"). Corre ANTES del enforcer para que el merge los fusione. |
| 4f3 | `enforce_listadomanga_rules.py --fast` | **Cadena COMPLETA de agrupación (2026-06-12)** — reemplaza a los pasos sueltos fix_edition_country / unify_coleccion / backfill_cluster_key / generate_slugs / consolidate / merge_isbn que el pipeline corría antes: el re-scrape del calendario sobre colecciones YA estandarizadas deja duplicados raw-vs-std (DUPSYN/DUPVOL/TITLE) que solo la cadena completa repara (la corrida real del delta del 2026-06-12 dejaba **53 violaciones duras** con la cadena vieja; con el enforcer → 0). `--fast` salta el dedup de carrusel (corre aparte en 4h). Incluye: edition_display, país=edición, anomalías ek, unify/disambiguate/collapse/merge_crosssource, títulos lmc, canonicalize slugs, merge series/ISBN dups, publishers, cluster_key, dedup sintético, consolidate, slugs. Idempotente. **El paso `unify_coleccion_edition` además AUTO-CORTA (2026-07-08, WO-1) las variantes especiales de una coleccion (título "Edición Especial/Limitada/de Lujo") en su propia edición del tipo en vez de plegarlas al regular — sin tocar el cluster_key, respetando cofre-1ªed=regular y descartando el folleto promocional (#127). Namespacea `-c{cole}` sólo ante colisión cross-coleccion.** |
| 4g2 | `upgrade_image_resolution.py` | **[full only]** Re-descarga portadas en resolución completa: quita segmentos/params CDN de resize (Buscalibre `fit-in/`, Cultura `cdn-cgi/image/`, Whakoom `small→large`, Magento cache path, WP -NxM, Shopify _Nx, Rakuten `?_ex=`). Pasa Referer del item para evitar 403 anti-hotlink. Compara píxeles (`--min-gain 0.10`). Corre DESPUÉS de `consolidate_sources` (la portada canónica final ya está en su lugar) y ANTES de `dedup_carousel` (que puede necesitar la versión hi-res). |
| 4g3/4g4 | `backfill_prh_covers.py` + `fetch_better_covers.py` | **[full only, OPT-IN 2026-07-07]** `RUN_COVER_BACKFILL=1` — portadas vía fuentes EXTERNAS (CDN de Penguin Random House por ISBN + búsqueda web Serper/Tavily), más allá de lo que 4g2 puede hacer intra-dominio. Default OFF (network-heavy). `fetch_better_covers` sin `--apply` no reemplaza nada — todo a `data/cover_preview.json` para aprobación manual. Ubicados entre 4g2 y 4h. Detalle: `docs/reference/images.md`. |
| 4h | `dedup_carousel_images.py` | Quita la MISMA portada repetida en baja resolución del carrusel (hash perceptual; solo `kind=gallery`). Corre acá porque 4g une imágenes de fuentes hermanas → crea el dup. |
| 4i | `purge_placeholder_images.py` | Quita de `images[]` las fotos que NO son portadas reales: placeholders que la fuente sirve sin tener carátula (1×1 de Amazon, blanco de listadomanga/CDNs, "Cover Coming Soon"/"Immagine non disponibile"/"Image coming soon"), pixeles 1×1 y archivos rotos → la card cae al 📚 por defecto. Detección via `image_store.placeholder_reason()` (estructural + firmas sha1 en `data/placeholder_signatures.json`). Quita la ENTRY completa y limpia `sources[]`; huérfanos a cuarentena `_orphans/`. Sin red, idempotente. Corre acá (último paso de imágenes, antes del build) para que un placeholder que reentre durante el scrape no llegue al build. Gotcha #97. |
| 4j | `mirror_images.py --gc-only` | **GC rutinario** (delta y full): manda a cuarentena `data/images/_orphans/` los archivos del espejo que ningún item referencia (portadas reemplazadas por el skill/scripts, masters viejos). Reversible, NO toca `_originals/` (solo escanea archivos top-level). Evita que el espejo crezca con archivos muertos. Vaciar `_orphans/` (o `--gc-delete`) periódicamente para reclamar disco. |

> Todos los retrofits que reescriben metadata descriptiva **saltean items `approved_at`** por defecto (guard `is_approved()`).

---

### 3.2 ETAPA 2 — Estandarización 🧠 `/watch-standardize-catalog`

Procesa items **sin `standardized_at`** (incremental). Nunca toca golden records. Es la **verificación/corrección** del rough-assignment que hizo el scraper (`derive_series_metadata` = pass 1; este skill = pass 2, gotcha #21).

> **Política de títulos (2026-06-12, gotcha #92)**: el `title` es el nombre OFICIAL
> scrapeado y esta etapa **NO lo toca** — no se traduce, no se renombra a la serie
> canónica, no se le inyecta tipo de edición. El campo `title_standardized` quedó
> RETIRADO. La encontrabilidad la da la búsqueda por aliases
> (`data/series_aliases.json`, ver ETAPA 3 y Build) y el tipo de edición se muestra
> como badge en las UIs. Detalle en architecture.md → "Política de títulos".

> **Anti-drift (2026-06-11)**: la lógica de audit/tiering y de merge que vivía COPIADA
> en `SKILL.md` y en el workflow (y había divergido) ahora es **fuente única** en dos
> scripts compartidos que ambos invocan: `scripts/standardize_audit.py` y
> `scripts/standardize_apply.py`.

**Flujo** (workflow con checkpoints en `data/standardize-progress.json`):
1. **Audit** — `standardize_audit.py` (flags `--limit`/`--force-all`; markers TOTAL/PENDING/TIER1/2/3) re-deriva `confidence_tier` y escribe proyecciones `tier{1,2,3}.json` con `proposed_*` (la propuesta heurística), `existing_edition_key` (el LLM NO re-agrupa items con edición asignada) y `known_edition_keys` (las keys YA existentes en el corpus para esa serie — el LLM debe REUSAR en vez de acuñar variantes special/limited, gotcha #69):
   - **Tier 1 ~30%**: serie en `series_aliases.yml`, publisher conocido → **determinista, 0 tokens**.
   - **Tier 2 ~9%**: edición ambigua → **LLM valida** la propuesta (chunks de 20).
   - **Tier 3 ~37%**: serie desconocida / CJK → **LLM deriva** desde cero (chunks de 15).
2. **Tier 1** — `standardize_apply.py tier1` aplica la heurística, marca `standardized_at`.
3. **Tier 2** — subagentes paralelos validan/corrigen contra allowlists de **publisher slug** + **edition slug** (output schema-validado; reglas anti-compound, artbook-vs-special, 画集付き=bonus; tabla determinística término→slug de tipo de edición, gotcha #69).
4. **Tier 3** — subagentes derivan todo desde cero.
5. **Merge** — `standardize_apply.py merge`: **preserva el `edition_key` existente**, fallback a la propuesta heurística si el LLM devolvió keys vacías (sin keys usables → el item queda PENDIENTE y se reintenta, con `standardize_attempts` +1 — ver abajo), `canonical_series_key()` (consolida multilingüe), recomputa `cluster_key`, **fusiona duplicados** con `consolidate_by_cluster` (no borra — preserva fuentes hermanas) y emite reporte INTEGRITY. `product_type` se valida contra un enum cerrado (nunca un edition-kind como special/deluxe — eso vive en `edition_key`); si el LLM devolvió algo fuera del enum, se re-deriva con `derive_product_type()`.
   > **`is_manga=false` (2026-07-07, gotcha #122) YA NO expulsa a `non_manga_blacklist.jsonl`.** El item queda PENDIENTE (sin `standardized_at`) y se registra en `data/unmapped_series.jsonl` (reason `llm_non_manga`) para curación manual — son los gates DETERMINISTAS del pipeline (`filter_non_manga`/`filter_collectible`, Fase 3 del scrape) los que deciden la expulsión real en la próxima corrida, nunca el veredicto crudo del LLM. Excepción dura: Mangavariant NUNCA se expulsa (el veredicto se ignora con WARN).
   > **Escalado de retry (`standardize_attempts`)**: cada vez que el merge deja un item pendiente por keys inusables, incrementa `item.standardize_attempts`. Al auditar la próxima vez (`standardize_audit.py`), un item Tier 2/3 con `standardize_attempts >= MAX_STANDARDIZE_ATTEMPTS` (3) se EXCLUYE de las proyecciones (no vuelve a gastar LLM) y se manda directo a `unmapped_series.jsonl` (reason `standardize_exhausted`) — evita el loop infinito de un título irromanizable.
6. **Enforcer** — `enforce_listadomanga_rules.py` (Step 6b del skill): re-aplica determinísticamente TODAS las reglas duras de agrupación sobre lo que el LLM dejó. Desde 2026-06-11 incluye 5 pasos nuevos (3c1 `canonicalize_edition_slugs.py` #69, 3c2 `merge_duplicate_series.py` #70, 3c3 `normalize_edition_publishers.py`, 3c4 `fix_edition_key_prefix.py` #71, 3c5 `fix_title_edition_words.py` #72, antes de `backfill_cluster_key`) y **ya no es solo-listadomanga**: esos pasos aplican a todas las fuentes. Además el **paso 4b** re-corre `fix_lmc_display_titles` + `fix_especial_title_order` DESPUÉS de consolidate — el merge de filas podía revivir un título contaminado ya limpiado y el enforcer necesitaba 2 pasadas para converger; con 4b converge en UNA (verificado: 2ª corrida → items.jsonl byte-idéntico).
7. **→ ETAPA 4 (slugs)** y **→ ETAPA 5 (traducción)**.
8. `pytest tests/test_extraction.py` + `validate_corpus.py` (0 violaciones duras; warnings EDSLUG/SERIESDUP/EKPREFIX/PUBMIX en 0 o justificados).

> **Modelos del workflow (ahorro de tokens, 2026-06-11)**: TODOS los agentes mecánicos
> (audit, tier1, chunkers, checkpoints, merge-and-finalize, cleanup, load-progress) y la
> validación **Tier 2** corren con `model: 'haiku'`; SOLO la derivación **Tier 3** usa
> `'sonnet'`. El costo fijo por corrida es ~200k tokens de subagentes
> (audit+chunk+merge+checkpoints) — conviene correr **lotes de ≥100 items** para
> amortizarlo (corrida de 250 items ≈ 750k tokens en total con esta config).
> **`args` del workflow**: el harness puede pasarlos como STRING JSON — el script hace
> `JSON.parse` defensivo, así que `limit`/`force_all` funcionan (sin el parse se
> ignoraban y caía al default `limit=2000`). Verificado: `limit: 8` procesó exactamente
> 8 y dejó el resto pendiente para la siguiente corrida incremental.

**Output:** `series_key`, `series_display`, `edition_key`, `edition_display`, `volume`, `standardized_at` (`title` queda INTACTO = nombre oficial; `title_original` preservado). El `store_bonus` (perk de compra de un retailer JP, 店舗特典) lo separa el SCRAPER del título oficial (`mw.split_store_bonus`, gotcha #93), no esta etapa.

> Si aparecen `series_key` nuevos no canónicos → correr **ETAPA 3**.

---

### 3.3 ETAPA 3 — Aliases de series 🧠 `/watch-enrich-series-aliases`

Consume `data/unmapped_series.jsonl` (log de `series_key` no canónicos que el scraper detecta). Agrupa series bajo canonicals existentes o crea entradas nuevas en `data/series_aliases.yml` vía **Anilist API + web search**, luego corre el backfill sobre `items.jsonl`.

`series_aliases.yml` es la fuente de verdad de `canonical_series_key()` — consolida la misma obra en distintos idiomas (`kimetsu no yaiba` / `鬼滅の刃` / `guardianes de la noche` → `demon-slayer`). Lookup exact-match-only (no substring).

**Cuándo:** después de cada standardize que reportó series nuevas.

---

### 3.4 ETAPA 4 — Slugs · `generate_slugs.py`
Determinista, idempotente. Asigna `slug` URL-safe por **cluster** para la ruta `/item/[slug]` de web-next. **Corre como último paso del skill #2** (no en el scrape).

**Prioridad** (FRD-006): `isbn:X`→`isbn-X` · `edition_key+volume`→`berserk-darkhorse-deluxe-42` · `edition_key` solo→`gon-norma-collector` · isbn directo → fallback `item-{sha1(url)[:12]}`.
- Volumen: `42.0→42`, `1.5→1-5`, `第42巻→42`. Seguridad: `^[a-z0-9][a-z0-9-]*[a-z0-9]$`.
- Colisiones: el más viejo conserva el slug limpio; los demás `-b`/`-c`.
- Idempotencia: solo re-escribe si vacío o si cambió `edition_key`/`volume`.
```bash
generate_slugs.py --only-missing --verbose
```

---

### 3.5 ETAPA 5 — Traducción · `translate_descriptions.py`
Pobla `description_es` y `extras[].description_es`. **Último paso del skill #2** (`--workers 4`).
- `langdetect` detecta idioma; si ya es ES → vacío (skip). `DetectorFactory.seed=0`
  (2026-07-07) fija el determinismo — sin esto, el mismo texto borderline podía
  detectarse "es" un día y "it" al siguiente.
- PRIMARY: **Google Translate** (`deep-translator`, gratis, sin key, todos los idiomas). UPGRADE: **DeepL Free** si `DEEPL_API_KEY` (1M chars one-time), fallback a Google.
- **`description` original NUNCA se modifica** (`detect_signals` lee de ahí). Naming `description_{ISO-639-1}` → multi-idioma a costo cero.
- Sticky (`_CURATED_FIELDS`): un re-scrape no la pisa. Frontend muestra `description_es` si existe, si no cae a `description`.
- **Tres estados separados (2026-07-07, gotcha #118)** — `description_es=""` YA NO
  significa "ya-ES o falló, no importa cuál": ahora es RESERVADO exclusivamente para
  "el original ya está en español / sin contenido traducible / no-op (la API devolvió
  el mismo texto)". Si **TODOS** los servicios de traducción fallan (excepción o
  resultado vacío), la key `description_es` **NO se escribe** — el item queda pendiente
  y se reintenta solo, sin flag especial, en el próximo run + WARN por slug/servicio/
  error a stderr. Flag `--retry-empty` recupera los fallos de API que quedaron mal
  marcados como "ya-ES" ANTES de este fix (reprocesa sólo `description_es==""` cuya
  `description` NO detecta como español).
- **`description_es_src_hash` (staleness, 2026-07-07)** — junto a cada `description_es`
  se escribe `sha1(description)[:12]`. En el merge/upsert del scraper, si un re-scrape
  trae una `description` cuyo hash no coincide con el guardado, la traducción vieja NO
  se preserva por el sticky (se deja re-traducir) — evita mostrar una traducción de un
  texto que ya cambió. Backward-compatible: rows sin el hash (traducciones previas a
  este cambio) nunca se consideran stale. Detalle: `docs/reference/architecture.md`.
- **`--workers` ahora es paralelismo real (S11, 2026-07-08)** — antes `_deepl_lock`/
  `_google_lock` envolvían la llamada HTTP completa + el `time.sleep(--sleep)`
  posterior, así que con cualquier `--workers>1` sólo había 1 request DeepL y 1 Google
  en vuelo a la vez (el resto de los threads esperaba el lock, no la red). Ahora
  `_RateLimiter` sólo pacea los ARRANQUES de request (intervalo mínimo `--sleep` entre
  el inicio de una y la siguiente, por servicio); la espera y la request en sí quedan
  fuera del lock, así N workers sí tienen requests en vuelo simultáneamente. Seguro
  porque ninguno de los dos clientes tiene estado mutable compartido en el hot path
  (`GoogleTranslator` se instancia nuevo por llamada; el cliente HTTP de `deepl` está
  hecho para uso concurrente).
```bash
translate_descriptions.py --workers 4
translate_descriptions.py --retry-empty          # recupera fallos de API viejos mal marcados
```

---

### 3.6 ETAPA 6 — Imágenes / portadas (sub-pipeline de 10 pasos)

El scrape ya baja la portada de items nuevos (Fase 1 del espejo), **ya estandarizada** (AVIF Q60, lado largo ≤1600px, sin metadata; desde 2026-06-15, fuente única `image_store.normalize_image` en los 3 cuellos de escritura). Esta etapa **mejora la calidad** del corpus histórico. Orden recomendado (cada paso es idempotente; corré `--dry-run` primero):

> **Backfills one-shot (2026-06-15)** sobre el espejo HISTÓRICO: `optimize_images.py` estandarizó el corpus crudo (resize ≤1600px + strip, archiva originales a `_originals/`), y `migrate_images_to_avif.py` lo re-derivó a **AVIF desde los originales** + **dedup por contenido**. Resultado: 14.58 GB crudo → 2.37 GB WebP → **~1.5 GB AVIF**. No son parte del ciclo recurrente. Ver `scripts/retrofit/README.md`.
>
> **GC rutinario [4j]**: cada scrape (delta y full) corre `mirror_images.py --gc-only` después de `purge_placeholder_images` — manda a cuarentena `_orphans/` los archivos que ningún item referencia (portadas reemplazadas, masters viejos). Reversible, NO toca `_originals/`. Es lo que evita que el espejo crezca con archivos muertos a medida que el skill/scripts reemplazan portadas.
>
> **Umbral único de baja calidad: 90 000 px** (`LOW_QUALITY_PX`, 2026-07-08). Es la MISMA constante en `fetch_better_covers.py` (`DEFAULT_MIN_PIXELS`), `sync_cover_preview.py` y `promote_hires_cover.py` (`LOW_PX_THRESHOLD`) — antes había una banda 90k-100k entre motor y sync que generaba churn (el motor buscaba candidatas que sync podaba al instante). Candado en `tests/test_cover_engine_gates.py::test_low_quality_threshold_locked`.
>
> **Ledger de rechazos + denylist** (`data/cover_rejections.jsonl`, append-only): cada vez que se rechaza una candidata (desde `cover-preview.html` o el retiro automático de `sync_cover_preview`), se apendea `{slug, action, target, rejected_url, a_hash, match_dist, ref_pixels, reason, rejected_at}`. `fetch_better_covers.is_rejected_candidate()` es la fuente única que lo consulta — una candidata ya rechazada **no se vuelve a proponer** (veta por URL exacta siempre; por hash sólo con motivo de IDENTIDAD y distancia ≤2). Detalle: `docs/reference/images.md`.

1. **`mirror_images.py`** — espejo local del histórico: baja a `data/images/` el `local` faltante de CADA entry de `images[]` (portada `images[0]` + galería). GC mark-and-sweep saca archivos huérfanos (cuenta `images[].local` + `sources[].image_local`; → `_orphans/` o `--gc-delete`).
2. **`upgrade_image_resolution.py`** — quita parámetros/segmentos CDN de resize (9 patrones: Magento query params, WP -NxM, Shopify _Nx, Amazon ._SY300_., Rakuten ?_ex=, Buscalibre fit-in/, Cultura cdn-cgi/image/, Whakoom small→large, Magento cache path). Pasa Referer del item para evitar 403. Compara píxeles (`--min-gain 0.10`). **Automático en `scrape_full.sh` [4g2]**. → luego `mirror_images.py --gc`.
3. **`promote_hires_cover.py`** — sin red: cuando `images[0]` es un thumbnail (<90 000 px) y la misma portada en hi-res ya existe en `images[1+]` (vino de otra fuente del cluster, ej. Panini/Norma/Whakoom vs listadomanga), intercambia `images[0] ↔ images[k]`. Usa criterio thumbnail↔full relajado (aHash ≤ 14 bits + aspect ±12%) porque el thumbnail degrada tanto el hash que no pasa `_same_cover` estricto. El thumbnail queda en la galería; correr `dedup_carousel_images.py` después si se quiere eliminar el dup. Flags: `--dry-run`.
4. **`backfill_prh_covers.py`** — items EN con ISBN-13 (978-0/978-1) → URL determinística `images.penguinrandomhouse.com/cover/{isbn13}`. Valida ≥80k px, dedup por ISBN.
5. **`fetch_better_covers.py`** — items con imagen < 90 000 px: candidatas por ISBN (Amazon/PRH CDN/OpenLibrary/Google Books), reverse-image (Google Lens vía Serper) y text search, todas pasando por el AND-gate de identidad `_same_cover` (aHash∧dHash∧pHash∧NCC+entropía) cuando hay referencia utilizable, más el gate de calidad `_is_soft_image` y el denylist del ledger (arriba). Alta confianza (CDN/ISBN verificado por hash) se auto-aplica con `--apply`; el resto va a `data/cover_preview.json` para revisión manual con `verified`/`match_dist`/`ref_pixels` ya calculados (mismo schema que `sc_validate.py`, fuente única). Salta `variant_cover`/`retailer_exclusive`.
6. **`upscale_images.py`** — AI upscale (waifu2x/realesrgan) para thumbnails JP <200k px sin hi-res en origen (sumikko, booksprivilege, Rakuten, animeclick). El resultado pasa por `image_store.normalize_image` (AVIF, 2026-07-07 — antes guardaba el PNG lossless crudo) y cada entry reemplazada queda marcada `upscaled: true` en `images[]` (idempotencia + señal para scripts downstream de que es un upscale de IA, no una foto hi-res real). Guard `approved_at` a nivel de ARCHIVO compartido (`--include-approved`). Requiere `brew install waifu2x-ncnn-vulkan`.
7. **🧠 `/watch-search-covers`** — para lo que sigue malo (típico: **listadomanga** capa a ~150px, gotcha #39): busca en **Chrome** (Google udm=2 + Yandex reverse-image), valida identidad `_same_cover` (misma portada, mejor resolución) **+ calidad de display `_is_soft_image`** (descarta candidatas chicas+blandas que se verían pixeladas aunque tengan más px, gotcha #94), escribe candidatas a `data/cover_preview.json` con `status:"pending"`. Paso final **opcional** (`--serper-fallback`, de pago): tras el loop de Chrome, invoca el MOTOR de producción para reverse-image vía Google Lens sobre los targets que quedaron en 0 matches — acotable a slugs puntuales con `--slugs slug1,slug2`. **NUNCA toca `items.jsonl`** — la aprobación es **manual** vía `web/cover-preview.html`, que desde 2026-07-07 muestra un banner con las candidatas `status:"approved"` que TODAVÍA no se aplicaron al catálogo (badge `approved_unapplied`, P24; "aprobar" y "aplicar" son pasos desacoplados) + botón "Aplicar ahora". Al rechazar una candidata, el panel ofrece **chips de motivo opcionales de 1 clic** (`otro_tomo`/`otra_edicion`/`arte_sin_logo`/`no_es_la_obra`/`mala_calidad`/`otros…`) que alimentan el ledger de rechazos. La cola previa al gate se limpia 1× con `prune_soft_cover_candidates.py`.
8. **`revalidate_cover_preview.py`** — re-validación OFFLINE (sin red) de candidatas `pending` que quedaron con `match_dist: null` (versión vieja del skill, previa al hardening 2026-07-08): re-corre `_same_cover`/`_is_soft_image` sobre los archivos ya espejados en `data/images/` y decide `verified`/`match_dist`/`ref_pixels`, o rechaza (`reject_reason: "auto_revalidation"`) si falla. Correr una vez para sanear una cola heredada, o cuando se endurece el gate del motor y hay que re-medir candidatas viejas. `--dry-run` por defecto (reporta desglose), `--apply` persiste.
9. **`sync_cover_images.py`** — saneamiento integral: portadas placeholder/banner, `images[0]` desincronizado de la card, duplicados/junk (avatares, íconos, banners), galerías que son otros tomos. Idempotente, salta aprobados.
10. **`purge_placeholder_images.py`** — **determinístico y automático ([4i] del pipeline)**: quita las imágenes-placeholder que las fuentes sirven sin tener carátula (1×1, blanco, "no disponible"/"coming soon") + 1×1 + rotas, vía `image_store.placeholder_reason()` (estructural: `tiny`/`solid`/`broken` + firmas sha1 en `data/placeholder_signatures.json`). Quita la ENTRY completa (incluida la `url`, si no la card cargaría el placeholder remoto), limpia `sources[]`, huérfanos a `_orphans/`. NO borra por imagen repetida (cross-cover queda intacto). Complementa a `sync_cover_images` (heurístico/manual) con reglas duras sin falsos positivos. Sin red. Gotcha #97.

**Invariante de imágenes** (docs/reference/images.md): `images[0]` = SIEMPRE la portada (sincronizada con `image_url`/`image_local`). El carrusel es a nivel **cluster** (union dedupeada). El merge vive en TRES lugares que deben coincidir: `web/index.html` (`dedupByUrl`), `build_web.py` (`_merged_canonical`), `web-next/.../ItemHero.tsx`.

---

### 3.7 ETAPA 7 — Rareza

Modelo **default-common** rediseñado en 2026-06-10 (ver detalle completo en
[docs/reference/architecture.md → "Modelo de rareza"](../../reference/architecture.md)).
Resumen: `ultra_rare` = numerado/firmado a mano/lotería/≤500 uds.; `super_rare` = print run
≤2500 o retailer_exclusive+agotado; `rare` = agotado verificado, retailer_exclusive sin
verificar, tokuten, o keyword de no-reimpresión; `common` = **default sin evidencia**.
Campo `stock_status` (`''`|`in_stock`|`out_of_stock`) reservado para el retrofit
`check_stock.py` (PENDIENTE, no escrito).

1. **`set_rarity.py`** — mecánico: aplica `rarity` vía `derive_rarity_tier()`. Solo items sin valor (o `--force`). Respeta valores de web-search (`common` no se degrada).
2. **🧠 `/watch-validate-rarity`** — verifica items ambiguos (boxsets/artbooks `rare` de publishers grandes): busca en la web si están en stock hoy; baja a `common` si confirma stock. Solo items sin `rarity_verified_at` (incremental).

---

### 3.8 ETAPA 8 — Feedback 🧠 `/watch-review-feedback`
Procesa `data/feedback.jsonl` (los 👎 que el owner dejó en el modal del dashboard, cada entrada con el item completo + `reason`). Categoriza (problema de filtro vs. de calidad de dato), propone fixes concretos, los aplica con tests, corre los retrofits relevantes, y **trunca** la cola. Es el loop que mejora el scraper con datos reales.

---

### 3.9 ETAPA 9 — Aprobación humana (golden records)
El owner aprueba cards correctas desde el dashboard (botón aprobar):
- `POST /api/approve` (por cluster) / `POST /api/approve-edition` (por edición) → setea `approved_at`/`approved_by` en `items.jsonl` **y** registra en `data/approvals.jsonl` (log durable).
- Un item `approved_at` queda **congelado**: el re-scrape solo refresca `_VOLATILE_FIELDS` (stock/sources/detected_at); retrofits y skills lo saltan.
- **`apply_approvals.py`** — tras **reconstruir `items.jsonl` de cero** (re-scrape/import), re-materializa `approvals.jsonl` (reduce a estado final por `cluster_key`, re-aplica `approved_at`). Idempotente.

---

### 3.★ Build / publish
1. **`consolidate_sources.py`** — re-consolida 1-fila-por-producto (necesario tras standardize, que reasigna `edition_key` → nuevos clusters).
1.5. **`validate_corpus.py` — gate DURO ANTES de construir (2026-07-07, gotcha #111)**:
   dentro de `scrape_delta.sh`/`scrape_full.sh` este paso corre como PHASE 4, antes de
   `build_web.py` (PHASE 5). Exit 2 = violaciones duras → el build se OMITE y el sitio
   servido sigue siendo el build anterior (nunca se publica un corpus corrupto). Fuera
   del script canónico (build manual) correlo a mano primero:
   `.venv/bin/python scripts/validate_corpus.py` — si el exit code es distinto de 0, no
   corras `build_web.py` todavía.
2. **`build_web.py`** — por **default deja el embed VACÍO** (`web/index.html` ~139 KB; el JS hace `fetch(items.jsonl)` en vivo, requiere `serve.py`). Antes embebía el catálogo (~30 MB en el HTML) que el navegador parseaba ADEMÁS del fetch en vivo → trabajo doble; eso se quitó el 2026-06-14 (gotcha #100). Con `--embed` vuelve a poblar el `<script id="manga-data">` (normaliza URLs, agrupa por `cluster_key`, construye `sources[]`) para el fallback `file://`. `serve.py` además sirve el `items.jsonl` con **gzip** (~31 MB → ~4 MB) si el cliente lo acepta.
   También regenera **`data/series_aliases.json`** (`export_series_aliases.py`, vista
   de búsqueda del YAML de aliases): ambas UIs buscan también contra los aliases del
   `series_key`, así "demon slayer" / "kimetsu no yaiba" / "guardianes de la noche"
   devuelven los mismos items aunque el `title` sea el nombre oficial de cada edición
   (política de títulos 2026-06-12). Si editás `series_aliases.yml` a mano y no querés
   un build completo: `.venv/bin/python scripts/export_series_aliases.py`.
3. Servir: `scripts/serve.py` (público, :8000) — `scripts/run_local.sh` lanza también el panel admin (:8001, no deployable).

---

## 4. Runbooks listos para copiar

### 4.1 Después de un `scrape_delta` (incremental, lo más común)
```bash
# 0. scrape ya corrió y dejó items.jsonl crudo
/watch-standardize-catalog            # → series/edition/volume + slugs + traducción
/watch-enrich-series-aliases          # SOLO si standardize reportó series nuevas
.venv/bin/python scripts/retrofit/set_rarity.py
.venv/bin/python scripts/validate_corpus.py   # gate: si exit≠0, no corras build_web todavía
.venv/bin/python scripts/build_web.py
.venv/bin/python scripts/serve.py     # ver el resultado en :8000
```

### 4.2 Después de un `scrape_full` (refresh grande — el ciclo completo)
```bash
# Etapa 0 ya corrió (scrape_full.sh)

# Etapa 2-5 (standardize incluye slugs + traducción)
/watch-standardize-catalog
/watch-enrich-series-aliases

# Etapa 6 — imágenes (correr cada uno con --dry-run primero)
.venv/bin/python scripts/retrofit/mirror_images.py
.venv/bin/python scripts/retrofit/upgrade_image_resolution.py --workers 8
.venv/bin/python scripts/retrofit/mirror_images.py --gc
.venv/bin/python scripts/retrofit/backfill_prh_covers.py --workers 8
.venv/bin/python scripts/retrofit/fetch_better_covers.py        # requiere TAVILY_API_KEY
.venv/bin/python scripts/retrofit/upscale_images.py             # requiere waifu2x
/watch-search-covers                                            # → aprobar en cover-preview.html
.venv/bin/python scripts/retrofit/revalidate_cover_preview.py --dry-run  # sólo si hay pending con match_dist null
.venv/bin/python scripts/retrofit/sync_cover_images.py

# Etapa 7 — rareza
.venv/bin/python scripts/retrofit/set_rarity.py
/watch-validate-rarity

# Etapa 8-9 (según haya feedback / aprobaciones)
/watch-review-feedback                # si hay 👎 en la cola
# (aprobaciones se hacen desde el dashboard)

# ★ build
.venv/bin/python scripts/retrofit/consolidate_sources.py
.venv/bin/python scripts/validate_corpus.py    # gate: si exit≠0, no corras build_web todavía
.venv/bin/python scripts/build_web.py
```

### 4.3 Reconstruí items.jsonl de cero (re-import / migración)
```bash
.venv/bin/python scripts/retrofit/apply_approvals.py   # re-aplica golden records
# luego el ciclo normal 4.2
```

### 4.4 ¿No sabés qué falta correr? — Panel de preparación del dato

En vez de razonarlo a mano, abrí **`/quality.html` → sección "🧰 Preparación del
dato"** (servida por `serve.py`). Muestra, por cada paso post-scrape de este
runbook, cuántos items están **pendientes** y cuántos quedaron
**desincronizados/stale** (p. ej. el `slug` se generó bien pero la edición cambió
después y ya no coincide). Los pasos mecánicos traen un botón **▶ Arreglar** que
corre el script ahí mismo con progreso en vivo y re-audita al terminar; los pasos
con IA muestran el **skill** a correr en Claude. Cómputo en `_compute_readiness()`
de [`scripts/audit/data_quality.py`](../../scripts/audit/data_quality.py); UI en
[`docs/web-html/PRD.md`](../web-html/PRD.md) → "Panel de Calidad de datos".

**Cambios 2026-07-07 (auditoría post-scrape)**:
- **`rarity_verify` alineado al criterio REAL del skill** (156→127 en el corpus de
  referencia): el filtro viejo confundía "boxset/artbook de publisher grande" con "rare
  por INCERTIDUMBRE" — ahora replica 1:1 el Step 0 de `watch-validate-rarity/SKILL.md`
  (rare sin `rarity_verified_at`, sin `approved_at`, cuyo `rare` viene de fallback de
  fuente de referencia o `retailer_exclusive` sin stock verificado — nunca de evidencia
  ESTRUCTURAL, que el skill no toca).
- **Traducción partida en dos filas**: `translate` (pendiente_traduccion — descripción
  en idioma extranjero de verdad) y `translate_mark_es` (pendiente_marca_es — fuente
  hispanohablante cuyo contenido YA está en español, sólo falta backfillear la key). El
  viejo `trans_pending` único inflaba el conteo mezclando ambos casos.
- **Filas nuevas**: `dates_iso` (release_date que no matchea el patrón ISO — mismo
  criterio que la invariante `DATEISO` de `validate_corpus.py`) y `no_image` (items sin
  portada NI foto de galería, script sugerido: `/watch-search-covers`).

### 4.5 Sanity check tras cualquier cambio
```bash
.venv/bin/python -m pytest tests/test_extraction.py -q
.venv/bin/python scripts/retrofit/filter_non_manga.py --dry-run   # 0 rechazos si patterns estables
```

---

*Generado 2026-06-06. Mantener sincronizado con `scrape_delta.sh`, `scrape_full.sh`,
`scripts/retrofit/README.md`, `ARCHITECTURE.md`, `FRD-006-slug-generation.md` y los
skills `watch-standardize-catalog` / `watch-enrich-series-aliases` /
`watch-validate-rarity` / `watch-search-covers` / `watch-review-feedback` si cambia
el orden de etapas o se agrega/quita un proceso.*
