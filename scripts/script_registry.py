"""script_registry.py — fuente de verdad para el Panel de Control web.

Describe cada script que se puede ejecutar desde web/control.html con:
- una explicación "para dummies" de qué hace y cuándo se usa
- todos sus flags clasificados como básicos (siempre visibles) o avanzados
- presets pre-armados (combinaciones de flags recomendadas)

scripts/serve.py expone este registry vía GET /api/scripts y valida que
cualquier run venga de un id conocido + flags conocidas.

Convenciones de tipos de flag:
- "bool"   → toggle. Solo agrega el flag si está en True (acción 'store_true').
- "int"    → input numérico. Si vacío, no se agrega el flag.
- "float"  → input numérico decimal. Idem.
- "str"    → input texto libre. Si vacío, no se agrega el flag.
- "choice" → select desplegable. choices: lista de strings.
- "csv"    → input texto que el usuario separa con comas. Mismo tratamiento
             que "str" pero con placeholder distinto.

Mantener este registry en sync con los argparse reales — si rompís uno y no
el otro, el panel ejecutará comandos inválidos.
"""

from __future__ import annotations

from typing import Any


# Ejecutable Python a usar. Se resuelve en serve.py al path absoluto del venv.
PYTHON = ".venv/bin/python"


# ---------------------------------------------------------------------------
# Helpers para construir flags sin repetir kwargs.
# ---------------------------------------------------------------------------

def _flag(arg: str, label: str, help: str, *, type: str = "bool",
          default: Any = None, choices: list[str] | None = None,
          placeholder: str = "", advanced: bool = False) -> dict[str, Any]:
    return {
        "arg": arg,
        "label": label,
        "help": help,
        "type": type,
        "default": default,
        "choices": choices or [],
        "placeholder": placeholder,
        "advanced": advanced,
    }


# ---------------------------------------------------------------------------
# Scripts
# ---------------------------------------------------------------------------

SCRIPTS: list[dict[str, Any]] = [
    # =====================================================================
    # ⭐ SCRIPTS CANÓNICOS — los 2 que ejecutás regularmente
    # =====================================================================
    {
        "id": "scrape_delta",
        "category": "⭐ Canónicos",
        "icon": "⚡",
        "name": "Scrape DELTA (incremental, diario/semanal)",
        "tagline": "Detecta novedades de los últimos meses. Rápido (~30-60 min).",
        "what": (
            "Encadena toda la pipeline en modo INCREMENTAL: scrape de las "
            "fuentes del YAML + listadomanga CALENDARIO (mes actual + 2 "
            "anteriores) + manga-sanctuary + otaku-calendar + manga-mexico + "
            "socialanime + blogbbm + search discovery + cleanup retrofits + "
            "build_web. NO recorre las ~3432 colecciones de listadomanga "
            "lista.php — eso es del scrape FULL."
        ),
        "when": (
            "Diario o semanal. Es lo que querés correr cuando solo querés "
            "agarrar lo nuevo. Tiempo: 30-60 min. Para correr el catálogo "
            "completo de listadomanga, usar 'Scrape FULL' (mensual)."
        ),
        "command": ["bash", "scripts/scrape_delta.sh"],
        "presets": [
            {
                "id": "default",
                "label": "🟢 Estándar (recomendado)",
                "desc": "Todas las fases activas, sin Whakoom ni Wayback (riesgo/lento).",
                "values": {},
            },
            {
                "id": "with_whakoom",
                "label": "🟡 + Whakoom spider (riesgo Cloudflare)",
                "desc": "Agrega spider profundo de Whakoom. Puede bloquearse por Cloudflare.",
                "env": {"INCLUDE_WHAKOOM_SPIDER": "1"},
                "values": {},
            },
        ],
        "flags": [],  # se controla por env vars (INCLUDE_*, SKIP_*)
    },
    {
        "id": "scrape_full",
        "category": "⭐ Canónicos",
        "icon": "📚",
        "name": "Scrape FULL (catálogo completo, mensual)",
        "tagline": "Recorre las ~3432 colecciones de listadomanga.es vía lista.php. ~2-4 horas.",
        "what": (
            "Encadena toda la pipeline en modo COMPLETO. Lo más importante: "
            "recorre las ~3432 colecciones del catálogo de listadomanga.es "
            "vía lista.php (índice oficial alfabético), buscando en cada "
            "una ediciones especiales / portadas alternativas / cofres / "
            "extras de primera edición / formato premium. También corre "
            "listadomanga-blog histórico, manga-sanctuary, otaku-calendar, "
            "manga-mexico, mangavariant (sitemap completo), socialanime, "
            "blogbbm + search discovery + cleanup retrofits + build_web."
        ),
        "when": (
            "1x/mes o 1x/trimestre. Cuando querés un refresh completo del "
            "catálogo o cuando agregaste reglas/patterns nuevos al parser. "
            "Tiempo: 2-4 horas. Para deltas diarios: usar 'Scrape DELTA'."
        ),
        "command": ["bash", "scripts/scrape_full.sh"],
        "presets": [
            {
                "id": "default",
                "label": "🟢 Estándar (recomendado)",
                "desc": "Todas las fases activas, sin Whakoom ni Wayback.",
                "values": {},
            },
            {
                "id": "with_extras",
                "label": "🟡 + Whakoom + Wayback recovery (lento ~6h)",
                "desc": "Agrega Whakoom spider y Wayback recovery. Para refresh ultra-completo.",
                "env": {"INCLUDE_WHAKOOM_SPIDER": "1", "INCLUDE_WAYBACK_RECOVERY": "1"},
                "values": {},
            },
        ],
        "flags": [],
    },

    # =====================================================================
    # DÍA A DÍA — scripts individuales (avanzado)
    # =====================================================================
    {
        "id": "scrape",
        "category": "Día a día",
        "icon": "🔍",
        "name": "Buscar mangas nuevos (Scraper principal)",
        "tagline": "Recorre las ~160 fuentes y agrega items nuevos a tu catálogo.",
        "what": (
            "Esto es lo que más vas a usar. Va a entrar a todas las fuentes "
            "(Amazon JP, editoriales como Glénat, Panini, tiendas, blogs…) "
            "y se queda con los manga que parezcan ediciones especiales, "
            "deluxe, kanzenban, artbooks, box sets, etc. Cada cosa que "
            "encuentre se guarda en data/items.jsonl."
        ),
        "when": (
            "Cuando quieras detectar mangas nuevos. Lo podés correr cada "
            "pocos días. Si es la primera vez o pasó mucho tiempo, dura un "
            "rato largo (30-60 min). En corridas siguientes va más rápido "
            "porque ya tiene cache."
        ),
        "command": [PYTHON, "scripts/manga_watch.py"],
        "presets": [
            {
                "id": "normal",
                "label": "🟢 Normal (recomendado)",
                "desc": "Busca en todas las fuentes con detalles completos, paralelizado a 8 workers.",
                "values": {"--fetch-details": True, "--enable-js": True,
                           "--fuzzy-keywords": True, "--workers": 8,
                           "--per-host-limit": 2, "--sleep-seconds": 0.5},
            },
            {
                "id": "rapido",
                "label": "⚡ Rápido (sin JS ni detalles)",
                "desc": "Más veloz, pero algunas fuentes JS-only se saltean y faltan portadas/autor.",
                "values": {"--workers": 8, "--per-host-limit": 2, "--sleep-seconds": 0.5},
            },
            {
                "id": "dryrun",
                "label": "🧪 Prueba (no guarda nada)",
                "desc": "Corre todo en modo dry-run; ideal para ver qué haría antes de comprometer.",
                "values": {"--dry-run": True, "--fetch-details": True},
            },
            {
                "id": "una_fuente",
                "label": "🎯 Solo una fuente (debug)",
                "desc": "Cargá el nombre exacto de la fuente en el campo 'Solo esta fuente'.",
                "values": {"--fetch-details": True, "--enable-js": True},
            },
        ],
        "flags": [
            _flag("--fetch-details", "Buscar portada, autor, ISBN y precio",
                  "Después de detectar un item entra a su página y rescata "
                  "portada, autor, ISBN, precio y fecha. Más lento pero deja "
                  "los items completos. RECOMENDADO.",
                  type="bool", default=True),
            _flag("--enable-js", "Activar navegador (Playwright) para sitios JS",
                  "Algunas tiendas solo cargan su catálogo con JavaScript. "
                  "Esta opción lanza un navegador real (Playwright) para esos "
                  "casos. Más lento pero necesario. RECOMENDADO.",
                  type="bool", default=True),
            _flag("--fuzzy-keywords", "Búsqueda flexible (palabras sueltas)",
                  "Detecta 'edición especial' aunque el título diga "
                  "'edición exclusiva especial'. Mejora detección a costa "
                  "de un poco más de falsos positivos.",
                  type="bool", default=True),
            _flag("--workers", "Cantidad de fuentes en paralelo",
                  "Cuántas fuentes scrapear al mismo tiempo. 1 = una a una "
                  "(seguro pero lento, ~25 min). 8 = recomendado para "
                  "overnight (corta a ~5 min). Las fuentes JS-only se "
                  "serializan solas internamente.",
                  type="int", default=1, placeholder="8"),
            _flag("--per-host-limit", "Máx requests por dominio",
                  "Cuando paralelizás con --workers, cuántos requests "
                  "concurrentes permite al mismo dominio. Default 2. Bajalo "
                  "a 1 si una tienda te bloquea.",
                  type="int", default=2),
            _flag("--dry-run", "Modo prueba (no guarda nada)",
                  "Corre todo igual pero NO escribe en data/items.jsonl. "
                  "Sirve para ver qué pasaría sin tocar tu catálogo.",
                  type="bool", default=False),
            _flag("--skip-image-download", "No descargar portadas al espejo local",
                  "Por defecto el scrape descarga cada portada a "
                  "data/images/ (espejo local, así somos dueños de la "
                  "imagen aunque la fuente muera). Activá esto para "
                  "saltear la descarga en corridas de prueba rápidas.",
                  type="bool", default=False, advanced=True),

            _flag("--countries", "Solo estos países",
                  "Lista de países separados por coma. Ejemplo: España,Japón. "
                  "Dejá vacío para todos.",
                  type="csv", default="",
                  placeholder="España,Japón"),
            _flag("--only-source", "Solo esta fuente",
                  "Nombre EXACTO de una sola fuente (ej. 'ES - Norma'). "
                  "Útil para depurar una fuente específica.",
                  type="str", default="",
                  placeholder="ES - Norma"),
            _flag("--include-tags", "Solo fuentes con estos tags",
                  "Lista de tags separados por coma. Solo procesa fuentes "
                  "que tengan AL MENOS uno. Ejemplo: expansion,new-source",
                  type="csv", default="",
                  placeholder="expansion,new-source"),
            _flag("--exclude-tags", "Saltar fuentes con estos tags",
                  "Lista de tags separados por coma. Excluye fuentes que "
                  "tengan alguno. Ejemplo: expansion (para saltear las "
                  "búsquedas que son lentas).",
                  type="csv", default="",
                  placeholder="expansion"),
            _flag("--source-classes", "Solo estas clases de fuente",
                  "Separadas por coma. Valores válidos: official, retailer, "
                  "trusted_media, social.",
                  type="csv", default="",
                  placeholder="official,retailer"),

            _flag("--list-sources", "Solo listar fuentes (no scrapear)",
                  "Imprime las fuentes que pasarían los filtros y termina. "
                  "No hace ningún HTTP request al catálogo.",
                  type="bool", default=False, advanced=True),
            _flag("--list-empty-sources", "Reportar fuentes vacías al final",
                  "Al terminar lista las fuentes que devolvieron 0 candidatos. "
                  "Útil para detectar selectores rotos.",
                  type="bool", default=False, advanced=True),
            _flag("--include-seen", "Incluir items ya vistos",
                  "Por defecto el reporte solo muestra nuevos. Esta opción "
                  "muestra TODOS aunque ya estuvieran.",
                  type="bool", default=False, advanced=True),
            _flag("--include-disabled", "Incluir fuentes deshabilitadas",
                  "Procesa también fuentes marcadas como enabled: false en "
                  "sources.yml.",
                  type="bool", default=False, advanced=True),
            _flag("--respect-robots", "Respetar robots.txt",
                  "Consulta robots.txt antes de cada fuente y skipea si "
                  "está bloqueado.",
                  type="bool", default=False, advanced=True),
            _flag("--diagnostic", "Modo diagnóstico (guarda HTML crudo)",
                  "Para debug profundo. Guarda HTML y stats de fuentes "
                  "problemáticas en logs/.",
                  type="bool", default=False, advanced=True),
            _flag("--send-telegram", "Enviar resumen por Telegram",
                  "Requiere TELEGRAM_BOT_TOKEN y TELEGRAM_CHAT_ID en .env.",
                  type="bool", default=False, advanced=True),
            _flag("--discover-sitemaps", "Descubrir vía /sitemap.xml",
                  "Fase 3 experimental: descubre URLs de producto vía el "
                  "sitemap de cada source HTML. Muy útil pero lento.",
                  type="bool", default=False, advanced=True),

            _flag("--min-score", "Score mínimo",
                  "Solo items con score ≥ N se reportan. Default 30 ya "
                  "incluye artbooks.",
                  type="int", default=30, advanced=True),
            _flag("--max-age-days", "Antigüedad máx en días (RSS)",
                  "Para feeds RSS ignora entradas más viejas que N días. "
                  "0 = sin filtro. Default 30.",
                  type="int", default=30, advanced=True),
            _flag("--max-items-per-source", "Máx items por fuente",
                  "Top de candidatos a quedarte de cada fuente. Default 80.",
                  type="int", default=80, advanced=True),
            _flag("--max-pages", "Máx páginas por fuente",
                  "Cuántas páginas de paginación seguir por fuente. "
                  "Default 5.",
                  type="int", default=5, advanced=True),
            _flag("--sleep-seconds", "Pausa entre fuentes (seg)",
                  "Sé amable con los servidores. Default 1.5.",
                  type="float", default=1.5, advanced=True),
            _flag("--sitemap-max-urls", "Máx URLs por sitemap",
                  "Solo aplica si activaste 'Descubrir vía sitemap'. "
                  "Default 500.",
                  type="int", default=500, advanced=True),
            _flag("--fetch-details-min-score", "Score mínimo para detail-fetch",
                  "Solo se entra al detalle de items con score ≥ N. "
                  "Default 70.",
                  type="int", default=70, advanced=True),
        ],
    },

    {
        "id": "bootstrap_wiki",
        "category": "Día a día",
        "icon": "📚",
        "name": "Importar desde Wiki comunitaria",
        "tagline": "Trae items históricos desde calendarios y wikis de fans.",
        "what": (
            "En lugar de scrapear las fuentes del YAML, importa items "
            "directamente desde una wiki comunitaria: Listado Manga (ES), "
            "su blog histórico, Manga-Sanctuary (FR), Otaku Calendar (EN), "
            "Manga México o Whakoom. Es la forma más rápida de poblar el "
            "catálogo con anuncios y exclusivas que las tiendas todavía no "
            "publican."
        ),
        "when": (
            "Una vez al mes para refrescar el calendario, o cuando agregás "
            "una wiki por primera vez (corrida histórica del rango "
            "completo)."
        ),
        "command": [PYTHON, "scripts/manga_watch.py"],
        "presets": [
            {
                "id": "listadomanga_actual",
                "label": "📅 Listado Manga - últimos 3 meses",
                "desc": "Calendario español, refresca lo reciente.",
                "values": {"--bootstrap-wiki": "listadomanga", "--wiki-from": "2026-03"},
            },
            {
                "id": "mangasanctuary",
                "label": "🇫🇷 Manga-Sanctuary - últimos 6 meses",
                "desc": "Calendario francés.",
                "values": {"--bootstrap-wiki": "manga-sanctuary", "--wiki-from": "2025-12"},
            },
            {
                "id": "otakucalendar",
                "label": "🇺🇸 Otaku Calendar - mes actual",
                "desc": "EN/US. (Esta wiki solo expone el mes actual.)",
                "values": {"--bootstrap-wiki": "otaku-calendar"},
            },
            {
                "id": "mangamexico",
                "label": "🇲🇽 Manga México - catálogo completo",
                "desc": "Catálogo por editorial. No usa rango de fechas.",
                "values": {"--bootstrap-wiki": "manga-mexico"},
            },
            {
                "id": "mangavariant",
                "label": "🌍 Mangavariant - base global de variants",
                "desc": (
                    "Base curada de variants/ediciones especiales en 13 países "
                    "(~2700 entries). Ignora el rango de fechas: baja todo "
                    "el sitemap. Las URLs son páginas-referencia, no de tienda."
                ),
                "values": {"--bootstrap-wiki": "mangavariant"},
            },
            {
                "id": "socialanime",
                "label": "🇮🇹 SocialAnime - variant + cofanetti italianos",
                "desc": (
                    "MangaStore de socialanime.it: ~840 items entre variant/"
                    "limited/special editions y cofanetti (Star Comics, Panini, "
                    "Edizioni BD, Goen, Magic Press, Dynit, 001 Edizioni...). "
                    "Las URLs van a Amazon Italia. Ignora el rango de fechas."
                ),
                "values": {"--bootstrap-wiki": "socialanime"},
            },
            {
                "id": "blogbbm",
                "label": "🇧🇷 Biblioteca Brasileira de Mangás - capas variantes + extras",
                "desc": (
                    "Dos posts curados de blogbbm.com: ediciones con capa variante "
                    "(~25 items) y volúmenes con extras/brindes (~10 items). "
                    "Cubre publishers BR (Panini, JBC, NewPOP, MPEG, Pipoca & Nanquim) "
                    "con clasificación explícita de variant/special/bonus. "
                    "Ignora el rango de fechas."
                ),
                "values": {"--bootstrap-wiki": "blogbbm"},
            },
            {
                "id": "listadomanga_collections_piloto",
                "label": "🇪🇸 Listado Manga - colecciones (piloto Fase 1, primeros 100 ids)",
                "desc": (
                    "Parser por colección individual coleccion.php?id=N. "
                    "Fase 1: ediciones especiales / portadas alternativas / "
                    "packs con extras / formato premium (kanzenban, cartoné A5, "
                    "tapa dura, artbook). Piloto: ids 1-100 para validar antes de "
                    "iterar todo el catálogo. Usa --coleccion-from / --coleccion-to "
                    "en vez de --wiki-from / --wiki-to."
                ),
                "values": {
                    "--bootstrap-wiki": "listadomanga-collections",
                    "--coleccion-from": "1",
                    "--coleccion-to": "100",
                },
            },
            {
                "id": "listadomanga_collections_full",
                "label": "🇪🇸 Listado Manga - colecciones (Fase 3, todo el catálogo)",
                "desc": (
                    "Iteración completa coleccion.php?id=1..6500. ~6500 ids = "
                    "~30-60 min con sleep 0.3s. Para automatizar semanalmente; "
                    "ojo con el volumen de items resultante (estimado ~2-5k "
                    "items nuevos en Fase 1, mucho más con Fase 2 cuando se "
                    "active la vinculación extra→tomo)."
                ),
                "values": {
                    "--bootstrap-wiki": "listadomanga-collections",
                    "--coleccion-from": "1",
                    "--coleccion-to": "6500",
                },
            },
        ],
        "flags": [
            _flag("--bootstrap-wiki", "Wiki a importar",
                  "Elegí qué wiki recorrer. Cada una cubre un país/idioma.",
                  type="choice", default="listadomanga",
                  choices=["listadomanga", "listadomanga-blog", "whakoom",
                           "manga-sanctuary", "otaku-calendar", "manga-mexico",
                           "mangavariant", "socialanime", "blogbbm",
                           "listadomanga-collections"]),
            _flag("--wiki-from", "Mes inicial (YYYY-MM)",
                  "Desde qué mes traer items. Aplica a wikis basadas en "
                  "calendario (listadomanga, manga-sanctuary, otaku-calendar). "
                  "Formato YYYY-MM. Default 2024-01.",
                  type="str", default="2024-01",
                  placeholder="2026-01"),
            _flag("--wiki-to", "Mes final (YYYY-MM)",
                  "Hasta qué mes. Vacío = mes actual.",
                  type="str", default="",
                  placeholder="2026-05"),
            _flag("--coleccion-from", "Id inicial (listadomanga-collections)",
                  "Para listadomanga-collections, id inicial de la iteración "
                  "secuencial. Default 1. Los otros bootstrap-wiki lo ignoran.",
                  type="int", default=1, advanced=True),
            _flag("--coleccion-to", "Id final (listadomanga-collections)",
                  "Para listadomanga-collections, id final. Default 6500 (cubre "
                  "todo el catálogo a 2026-05). El bootstrap también se detiene "
                  "automáticamente tras 50 ids consecutivos sin contenido.",
                  type="int", default=6500, advanced=True),
            _flag("--fetch-details", "Rellenar detalles después",
                  "Tras importar entra a cada detalle para portada/autor/ISBN. "
                  "RECOMENDADO.",
                  type="bool", default=True),
            _flag("--dry-run", "Modo prueba (no guarda)",
                  "Lista lo que importaría sin escribir nada.",
                  type="bool", default=False),
            _flag("--skip-image-download", "No descargar portadas al espejo local",
                  "Por defecto el import descarga cada portada a "
                  "data/images/. Activá esto para saltear la descarga en "
                  "corridas de prueba.",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "search_discovery",
        "category": "Día a día",
        "icon": "🤖",
        "name": "Descubrir vía buscadores (Gemini + Tavily + DDG)",
        "tagline": "Encuentra items que ninguna fuente directa cubre.",
        "what": (
            "Usa motores de búsqueda (Gemini con Google grounding, Tavily, "
            "DuckDuckGo) para descubrir items que están en Whakoom, Fnac, "
            "Amazon, Reddit, etc. — sitios que bloquean scraping directo "
            "pero Google sí indexa. Las queries vienen de data/search_queries.yml."
        ),
        "when": (
            "Una vez por semana o cuando agregás queries nuevas. Si no "
            "tenés GEMINI_API_KEY ni TAVILY_API_KEY configurados en .env "
            "solo correrá con DuckDuckGo (resultados limitados)."
        ),
        "command": [PYTHON, "scripts/retrofit/search_discovery.py"],
        "presets": [
            {
                "id": "normal",
                "label": "🟢 Todas las queries",
                "desc": "Corre cada query del archivo con los engines configurados.",
                "values": {},
            },
            {
                "id": "ddg_only",
                "label": "🦆 Solo DuckDuckGo (sin API key)",
                "desc": "Si no tenés GEMINI ni TAVILY key, usa solo DDG.",
                "values": {"--engines": "ddg"},
            },
            {
                "id": "dryrun",
                "label": "🧪 Prueba (no fetchea)",
                "desc": "Lista las queries que se correrían y los engines disponibles.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--engines", "Motores a usar (CSV)",
                  "Restringe a estos engines. Opciones: gemini, tavily, ddg. "
                  "Vacío = respeta lo que diga cada query en el YAML.",
                  type="csv", default="",
                  placeholder="ddg,tavily"),
            _flag("--limit", "Solo las primeras N queries",
                  "0 = todas. Útil para probar.",
                  type="int", default=0,
                  placeholder="5"),
            _flag("--max-results", "Máx resultados por query",
                  "Default 10 (Google cap).",
                  type="int", default=10, advanced=True),
            _flag("--sleep-google", "Pausa entre queries Gemini (seg)",
                  "Default 4.5 (=15 RPM, free tier). Bajarlo solo si tenés "
                  "tier pago.",
                  type="float", default=4.5, advanced=True),
            _flag("--sleep-ddg", "Pausa entre queries DDG (seg)",
                  "Default depende. Subirlo si te rate-limitea.",
                  type="float", default=None, advanced=True),
            _flag("--dry-run", "Modo prueba (no fetchea)",
                  "Solo lista las queries a correr.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "build_web",
        "category": "Día a día",
        "icon": "🌐",
        "name": "Generar dashboard estático",
        "tagline": "Embebe items.jsonl dentro del HTML para uso offline.",
        "what": (
            "Por defecto el dashboard web carga los datos via fetch() de "
            "data/items.jsonl. Si querés un HTML autocontenido (abrir el "
            "archivo con doble-click sin server), este script embebe los "
            "items dentro del HTML."
        ),
        "when": (
            "Casi nunca. Solo si querés compartir el HTML como archivo "
            "único o usarlo offline."
        ),
        "command": [PYTHON, "scripts/build_web.py"],
        "presets": [
            {
                "id": "embed",
                "label": "📦 Embeber datos en HTML",
                "desc": "Mete items.jsonl dentro de web/index.html.",
                "values": {},
            },
            {
                "id": "clear",
                "label": "🧹 Vaciar (volver a fetch dinámico)",
                "desc": "Quita los datos embebidos. El HTML vuelve a leer via fetch.",
                "values": {"--clear": True},
            },
        ],
        "flags": [
            _flag("--clear", "Vaciar datos embebidos",
                  "Deja [] en el script embebido. La página volverá a hacer "
                  "fetch dinámico al JSONL.",
                  type="bool", default=False),
            _flag("--input", "Archivo de entrada",
                  "Default data/items.jsonl.",
                  type="str", default="data/items.jsonl", advanced=True),
            _flag("--output", "Archivo HTML destino",
                  "Default web/index.html.",
                  type="str", default="web/index.html", advanced=True),
        ],
    },

    # =====================================================================
    # MANTENIMIENTO (retrofits)
    # =====================================================================
    {
        "id": "filter_non_manga",
        "category": "Mantenimiento",
        "icon": "🚫",
        "name": "Filtrar lo que NO es manga",
        "tagline": "Reaplica el filtro is_likely_manga a items ya guardados.",
        "what": (
            "Revisa todos los items del catálogo y saca los que ya no "
            "cumplen el filtro de 'esto es manga' (figuras, comics, prints, "
            "noticias). Los movidos van a data/items.non_manga.jsonl para "
            "que los puedas revisar."
        ),
        "when": (
            "Después de tocar las reglas de _NON_MANGA_HARD / "
            "_NON_MANGA_SOFT / purity en scripts/manga_watch.py."
        ),
        "command": [PYTHON, "scripts/retrofit/filter_non_manga.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba (recomendado primero)",
                "desc": "Solo cuenta cuántos se filtrarían sin tocar el JSONL.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Aplicar el filtro",
                "desc": "Filtra de verdad. Hace backup automático.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Cuenta cuántos items se descartarían sin modificar el JSONL.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "filter_collectible",
        "category": "Mantenimiento",
        "icon": "💎",
        "name": "Filtrar lo que NO es coleccionable",
        "tagline": "Saca los tomos regulares — solo queremos ediciones especiales.",
        "what": (
            "Aplica el gate is_collectible_edition. Mueve los 'tomos "
            "regulares sin nada especial' a data/items.non_collectible.jsonl. "
            "Solo se conservan ediciones limitadas, deluxe, artbooks, "
            "magazines de serie y tomos con extras de primera edición."
        ),
        "when": (
            "Después de tocar las reglas de is_collectible_edition. "
            "Correlo después de filter_non_manga."
        ),
        "command": [PYTHON, "scripts/retrofit/filter_collectible.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba (recomendado primero)",
                "desc": "Solo cuenta cuántos se filtrarían.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Aplicar el filtro",
                "desc": "Filtra de verdad. Hace backup automático.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Cuenta cuántos se filtrarían sin tocar el JSONL.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "clean_titles",
        "category": "Mantenimiento",
        "icon": "🧼",
        "name": "Re-limpiar títulos",
        "tagline": "Reaplica clean_title() a los items existentes.",
        "what": (
            "Reaplica la función clean_title sobre todos los items. Quita "
            "prefijos de tienda ('Panini Manga - …'), mojibake ('Ã©' → 'é'), "
            "colas de menu, etc. Es seguro correrla varias veces."
        ),
        "when": (
            "Después de tocar la función clean_title o de detectar títulos "
            "feos en el catálogo."
        ),
        "command": [PYTHON, "scripts/retrofit/clean_titles.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Cuenta cuántos cambiarían sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Limpiar",
                "desc": "Aplica la limpieza con backup.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Cuenta cuántos títulos cambiarían sin guardar nada.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "rescore",
        "category": "Mantenimiento",
        "icon": "📊",
        "name": "Recalcular score y tipo",
        "tagline": "Recomputa score, signal_types y product_type con el código actual.",
        "what": (
            "Toma cada item y vuelve a calcular su score, sus signal_types "
            "y su product_type usando el código de scoring actual. NO toca "
            "title/url/source/portada/precio/etc. — solo los campos "
            "derivados. Sirve para limpiar residuos de bugs viejos."
        ),
        "when": (
            "Después de tocar score_candidate, detect_signals o "
            "derive_product_type en scripts/manga_watch.py."
        ),
        "command": [PYTHON, "scripts/retrofit/rescore.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba (reporta drift)",
                "desc": "Muestra cuántos items cambiarían de tipo/score.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Recalcular",
                "desc": "Aplica el rescore.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Reporta drift sin escribir.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "backfill_metadata",
        "category": "Mantenimiento",
        "icon": "📥",
        "name": "Rellenar metadata faltante",
        "tagline": "Va a las URLs de items incompletos y trae portada, autor, ISBN, precio.",
        "what": (
            "Para cada item con campos vacíos (portada, autor, ISBN, fecha, "
            "precio), entra a su URL y rellena lo que falte. NO sobreescribe "
            "lo que ya está. Hace cientos de HTTP requests, así que va con "
            "pausa entre cada uno."
        ),
        "when": (
            "Cuando notes que faltan portadas o autores en el dashboard, "
            "o tras tocar los extractores en scripts/manga_watch.py."
        ),
        "command": [PYTHON, "scripts/retrofit/backfill_metadata.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Solo cuenta cuántos items necesitarían backfill.",
                "values": {"--dry-run": True},
            },
            {
                "id": "all",
                "label": "🟢 Rellenar todo lo que falte",
                "desc": "Backfill completo. Puede demorar horas si hay miles de items.",
                "values": {},
            },
            {
                "id": "only_covers",
                "label": "🖼️ Solo portadas",
                "desc": "Sólo image_url. Más rápido.",
                "values": {"--only": "image_url"},
            },
        ],
        "flags": [
            _flag("--only", "Solo este campo",
                  "Si querés rellenar solo uno: image_url, author, isbn, "
                  "release_date o price.",
                  type="choice", default="",
                  choices=["", "image_url", "author", "isbn", "release_date", "price"]),
            _flag("--limit", "Máx items a procesar",
                  "0 = sin límite. Útil para probar con --limit 50.",
                  type="int", default=0, placeholder="50"),
            _flag("--max-per-source", "Máx items por fuente",
                  "0 = sin límite. Evita martillar a una sola tienda.",
                  type="int", default=0, advanced=True),
            _flag("--sleep", "Pausa entre requests (seg)",
                  "Default 0.3.",
                  type="float", default=0.3, advanced=True),
            _flag("--skip-domain", "Saltar este dominio",
                  "Match por substring. Ej: darkhorse.com. Solo uno por "
                  "ahora (TODO: múltiple).",
                  type="str", default="", advanced=True,
                  placeholder="darkhorse.com"),
            _flag("--dry-run", "Modo prueba (no fetchea)",
                  "Solo cuenta cuántos serían candidatos.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "mirror_images",
        "category": "Mantenimiento",
        "icon": "🖼️",
        "name": "Espejo local de portadas (bajar + limpiar)",
        "tagline": "Descarga las portadas a data/images/ así sos dueño de las imágenes.",
        "what": (
            "PandaWatch guarda las portadas en su propia carpeta "
            "(data/images/) en vez de depender de la web de la tienda — "
            "si esa web se cae o bloquea el enlace, la imagen sigue "
            "funcionando. Este script (1) descarga la portada de cada item "
            "que todavía no la tenga bajada, y (2) limpia de data/images/ "
            "las imágenes de items que ya no están en el catálogo. La "
            "primera vez baja miles de imágenes y demora varios minutos."
        ),
        "when": (
            "La primera vez, para bajar todo el catálogo histórico. "
            "Después el scraper ya baja las portadas de los items nuevos "
            "solo — alcanza con correr esto de vez en cuando para limpiar "
            "imágenes huérfanas."
        ),
        "command": [PYTHON, "scripts/retrofit/mirror_images.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Solo reporta cuántas portadas faltan y cuántos archivos sobran.",
                "values": {"--dry-run": True},
            },
            {
                "id": "all",
                "label": "🟢 Bajar todo + limpiar",
                "desc": "Backfill completo del catálogo + limpieza de huérfanos a cuarentena.",
                "values": {},
            },
            {
                "id": "gc_only",
                "label": "🧹 Solo limpiar huérfanos",
                "desc": "Sin descargar nada; solo saca de data/images/ lo que ya no se usa.",
                "values": {"--gc-only": True},
            },
        ],
        "flags": [
            _flag("--workers", "Descargas en paralelo",
                  "Cuántas portadas bajar al mismo tiempo. Default 8.",
                  type="int", default=8),
            _flag("--limit", "Máx items a bajar",
                  "0 = sin límite. Útil para probar con --limit 100.",
                  type="int", default=0, placeholder="100"),
            _flag("--no-gc", "No limpiar huérfanos",
                  "Solo descarga las portadas faltantes, sin la pasada de "
                  "limpieza.",
                  type="bool", default=False, advanced=True),
            _flag("--gc-only", "Solo limpiar (no descargar)",
                  "Salta el backfill y corre únicamente la limpieza de "
                  "imágenes huérfanas.",
                  type="bool", default=False, advanced=True),
            _flag("--gc-delete", "Borrar huérfanos (no cuarentena)",
                  "Por defecto los archivos huérfanos se mueven a "
                  "data/images/_orphans/ (reversible). Esto los borra de "
                  "verdad.",
                  type="bool", default=False, advanced=True),
            _flag("--dry-run", "Modo prueba (no baja ni borra)",
                  "Solo reporta qué haría, sin tocar nada.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "wayback_recover",
        "category": "Mantenimiento",
        "icon": "🕰️",
        "name": "Recuperar items 404 vía Wayback Machine",
        "tagline": "Para items que daban 404, busca un snapshot en archive.org.",
        "what": (
            "Algunos items existieron pero la tienda los descatalogó y "
            "ahora dan 404. Este script consulta archive.org/wayback, "
            "descarga el snapshot guardado y rescata título/portada/"
            "descripción. Marca el item con recovered_from_wayback: true."
        ),
        "when": (
            "1 vez por semana como mucho. Es pesado (chequea status de "
            "miles de URLs)."
        ),
        "command": [PYTHON, "scripts/retrofit/wayback_recover.py"],
        "presets": [
            {
                "id": "check",
                "label": "🩺 Solo chequear 404s",
                "desc": "Recorre URLs y reporta cuáles están caídas. No toca Wayback.",
                "values": {"--check": True},
            },
            {
                "id": "dryrun_first50",
                "label": "🧪 Prueba: primeros 50",
                "desc": "Consulta Wayback para los primeros 50 sin escribir.",
                "values": {"--dry-run": True, "--limit": 50},
            },
            {
                "id": "full",
                "label": "✅ Recuperación completa",
                "desc": "Aplica recovery a todos los 404s detectados.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--check", "Solo chequear 404s",
                  "Marca URLs como caídas pero no consulta Wayback ni escribe.",
                  type="bool", default=False),
            _flag("--dry-run", "Modo prueba",
                  "Chequea + consulta Wayback pero no guarda cambios.",
                  type="bool", default=False),
            _flag("--limit", "Máx items a procesar",
                  "0 = sin límite.",
                  type="int", default=0, placeholder="50"),
            _flag("--sleep", "Pausa entre requests (seg)",
                  "Default 1.0. Sé amable con archive.org.",
                  type="float", default=1.0, advanced=True),
            _flag("--urls", "Solo estas URLs (CSV)",
                  "Recovery puntual: pasá una o varias URLs separadas por "
                  "coma en lugar de barrer todo el JSONL.",
                  type="csv", default="", advanced=True),
        ],
    },

    {
        "id": "expand_whakoom_ediciones",
        "category": "Mantenimiento",
        "icon": "📚",
        "name": "Expandir ediciones Whakoom en tomos",
        "tagline": "Convierte URLs /ediciones/ (la colección entera) en N filas /comics/ (una por tomo).",
        "what": (
            "Whakoom usa /ediciones/<id>/<slug> como índice de una "
            "colección (ej. Berserk Deluxe Edition = 14 tomos), no de un "
            "único tomo. Nuestro catálogo es por tomo, así que estas URLs "
            "se expanden a N filas /comics/<X>/<slug>/<vol>, una por "
            "volumen. Soporta one-shots (1 solo tomo) vía login-ReturnUrl."
        ),
        "when": (
            "Cuando se detecten filas /ediciones/ en items.jsonl (ej. tras "
            "una corrida de search_discovery que las trae de Gemini). "
            "Idealmente: 0 filas /ediciones/ residuales en el catálogo."
        ),
        "command": [PYTHON, "scripts/retrofit/expand_whakoom_ediciones.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Modo prueba (no escribe)",
                "desc": "Reporta qué se expandiría sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Aplicar expansión",
                "desc": "Reemplaza filas /ediciones/ por tomos /comics/ en items.jsonl.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Reporta el impacto sin tocar items.jsonl.",
                  type="bool", default=False),
            _flag("--sleep", "Pausa entre requests (seg)",
                  "Default 1.5. Whakoom rate-limita agresivo; subir a 2-3 "
                  "si ves 429s.",
                  type="float", default=1.5, advanced=True),
            _flag("--max", "Máx ediciones a procesar",
                  "0 = sin límite. Útil para probar con un subset chico.",
                  type="int", default=0, placeholder="10", advanced=True),
        ],
    },

    {
        "id": "expand_index_pages",
        "category": "Mantenimiento",
        "icon": "🧹",
        "name": "Limpiar páginas-índice guardadas como productos",
        "tagline": "Detecta y expande/elimina catálogos, blog posts y Shopify variants multi-tomo.",
        "what": (
            "Audita items.jsonl en busca de filas que NO son tomos sino "
            "páginas-índice: pubs de Whakoom (/publisher/), variants Shopify "
            "multi-tomo (Dark Horse Direct: 'Volumes' con dropdown 1/2/3), "
            "blog posts (/blogs/news/) y colecciones Shopify sin /products/. "
            "Para cada tipo: las páginas-de-publisher y variants se expanden "
            "en N tomos individuales; blog/news y colecciones se eliminan. "
            "Cubre los casos detectados por la auditoría del 2026-05-22."
        ),
        "when": (
            "Tras correr search_discovery o cuando notes items raros tipo "
            "'Berserk Deluxe Hardcover Volumes' (plural) o blog posts en el "
            "catálogo. Es idempotente: si volvés a correrlo no toca filas "
            "ya limpias."
        ),
        "command": [PYTHON, "scripts/retrofit/expand_index_pages.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Modo prueba (no escribe)",
                "desc": "Reporta qué expandiría/eliminaría sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Aplicar limpieza",
                "desc": "Aplica todas las expansiones + eliminaciones.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Reporta el impacto sin tocar items.jsonl.",
                  type="bool", default=False),
            _flag("--sleep", "Pausa entre requests (seg)",
                  "Default 1.5. Bajar a 0.5 si la corrida es chica; subir "
                  "a 3.0 si una tienda te rate-limita.",
                  type="float", default=1.5, advanced=True),
        ],
    },

    # =====================================================================
    # AUDITORÍA
    # =====================================================================
    {
        "id": "source_health",
        "category": "Auditoría",
        "icon": "🩺",
        "name": "Auditoría de salud de fuentes",
        "tagline": "Lee los logs y dice qué fuentes están rotas o quietas.",
        "what": (
            "Recorre los logs de los últimos N runs (logs/overnight-*, "
            "logs/retry-*) y clasifica cada fuente: sana, sin items en "
            "varias corridas (posible selector roto), con muchos errores "
            "HTTP, o en clara decadencia."
        ),
        "when": "Después de cada corrida nocturna o cuando algo se siente raro.",
        "command": [PYTHON, "scripts/audit/source_health.py"],
        "presets": [
            {
                "id": "md",
                "label": "📄 Reporte Markdown (últimos 10)",
                "desc": "Salida humana, fácil de leer.",
                "values": {"--output": "md"},
            },
            {
                "id": "json",
                "label": "🧾 Reporte JSON",
                "desc": "Para procesamiento programático.",
                "values": {"--output": "json"},
            },
        ],
        "flags": [
            _flag("--last-n", "Cuántos runs analizar",
                  "Default 10. Subilo si tenés muchas corridas.",
                  type="int", default=10),
            _flag("--output", "Formato de salida",
                  "md para Markdown legible; json para máquina.",
                  type="choice", default="md", choices=["md", "json"]),
            _flag("--output-file", "Guardar a archivo",
                  "Si lo dejás vacío, imprime en pantalla. Si ponés ruta, "
                  "guarda ahí.",
                  type="str", default="",
                  placeholder="reports/source-health.md", advanced=True),
        ],
    },
]


# Diccionario por id para lookups rápidos.
SCRIPTS_BY_ID: dict[str, dict[str, Any]] = {s["id"]: s for s in SCRIPTS}


def get_script(script_id: str) -> dict[str, Any] | None:
    return SCRIPTS_BY_ID.get(script_id)


def known_flags(script_id: str) -> set[str]:
    """Devuelve los args válidos para validar payloads del API."""
    s = SCRIPTS_BY_ID.get(script_id)
    if not s:
        return set()
    return {f["arg"] for f in s["flags"]}
