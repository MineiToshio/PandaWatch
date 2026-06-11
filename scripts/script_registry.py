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
            "fuentes del YAML + listadomanga-collections modo CALENDAR (parsea "
            "las colecciones con actividad en calendario.php del mes actual + 2 "
            "anteriores, con ediciones especiales/cofres/variantes — misma "
            "riqueza que el full pero acotado) + manga-sanctuary + "
            "otaku-calendar + manga-mexico + socialanime + blogbbm + search "
            "discovery + cleanup retrofits + build_web. NO recorre las ~3432 "
            "colecciones de listadomanga lista.php — eso es del scrape FULL."
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
                "id": "booksprivilege_delta",
                "label": "🇯🇵 BooksPrivilege - 店舗特典 (año en curso)",
                "desc": (
                    "Agregador JP de 店舗特典 (extras de tienda) — por cada release "
                    "lista qué bonus da cada retailer (Animate, Gamers, Toranoana, "
                    "Melonbooks, COMIC ZIN...). Cubre items que las sources JP "
                    "directas no marcan. Modo delta: año en curso. Para ventana "
                    "más fina (mes actual + 2 anteriores) ajustá --wiki-from manual."
                ),
                "values": {
                    "--bootstrap-wiki": "booksprivilege",
                    "--wiki-from": "2026-01",
                },
            },
            {
                "id": "booksprivilege_full",
                "label": "🇯🇵 BooksPrivilege - 店舗特典 (archivo histórico desde 2020)",
                "desc": (
                    "Iteración completa del archivo (2020-01 hasta hoy). ~70 meses "
                    "× ~15-50 items/día con tokuten = varios miles de fetches. "
                    "Pesado, correr ocasionalmente para backfill."
                ),
                "values": {
                    "--bootstrap-wiki": "booksprivilege",
                    "--wiki-from": "2020-01",
                },
            },
            {
                "id": "sumikko",
                "label": "🇯🇵 Sumikko - 限定版・特装版 (catálogo completo ~3178 items)",
                "desc": (
                    "comic.sumikko.info — catálogo JP de ediciones limitadas y "
                    "especiales (限定版/特装版) con extras (acrylic stand, 小冊子, "
                    "缶バッジ, BOX, etc.). 100% ISBN-10 + portada Amazon CDN. "
                    "Iteración de ?p=1..32 cubre todo (~30s). Complementario a "
                    "booksprivilege que cubre 店舗特典 (extras de tienda) en vez "
                    "de las ediciones en sí. Ignora el rango de fechas."
                ),
                "values": {"--bootstrap-wiki": "sumikko"},
            },
            {
                "id": "mangapassion_delta",
                "label": "🇩🇪 Manga-Passion - Sonderausgaben + Variants (últimas novedades)",
                "desc": (
                    "manga-passion.de API — catálogo de referencia alemán (DACH). "
                    "Sonderausgaben (Limited/Collector/Premium/Box editions) y "
                    "Variant-Covers. Modo delta: date[after] basado en --wiki-from. "
                    "API pública REST JSON-LD, sin auth, sin anti-bot. "
                    "Incluye ISBN-13, precio, fecha, portada y extras."
                ),
                "values": {
                    "--bootstrap-wiki": "mangapassion",
                    "--wiki-from": "2026-01",
                },
            },
            {
                "id": "mangapassion_full",
                "label": "🇩🇪 Manga-Passion - Sonderausgaben + Variants (catálogo completo)",
                "desc": (
                    "Descarga todo el catálogo histórico sin filtro de fecha "
                    "(year_from=2000 → sin date[after]). Cubre Sonderausgaben "
                    "desde los orígenes del catálogo. Correr ocasionalmente "
                    "para backfill; el delta cubre lo nuevo en corridas regulares."
                ),
                "values": {
                    "--bootstrap-wiki": "mangapassion",
                    "--wiki-from": "2000-01",
                },
            },
            {
                "id": "animeclick_delta",
                "label": "🇮🇹 AnimeClick - Edizioni speciali (últimas novedades)",
                "desc": (
                    "animeclick.it — calendario semanal IT. Navega ~3 meses atrás. "
                    "Cubre Star Comics, Panini Comics, J-POP, MangaYo!, Crunchyroll IT "
                    "y otros publishers no presentes en SocialAnime. "
                    "Keyword filter en listing (~20% hit rate). Sin ISBN."
                ),
                "values": {
                    "--bootstrap-wiki": "animeclick",
                    "--wiki-from": "2026-01",
                },
            },
            {
                "id": "animeclick_full",
                "label": "🇮🇹 AnimeClick - Edizioni speciali (catálogo desde 2015)",
                "desc": (
                    "Navega el calendario semanal de AnimeClick desde 2015 hasta hoy. "
                    "~500 semanas × keyword filter (~20%) × fetch detalle. "
                    "Correr mensualmente para backfill; el delta cubre las novedades."
                ),
                "values": {
                    "--bootstrap-wiki": "animeclick",
                    "--wiki-from": "2015-01",
                },
            },
            {
                "id": "prhcomics_delta",
                "label": "🇺🇸 PRH Comics - hardcovers + box sets EN (últimos 3 meses)",
                "desc": (
                    "Descarga la página /manga/ de prhcomics.com (una sola request). "
                    "Extrae hardcovers, box sets y collector's editions de los publishers "
                    "distribuidos por PRH: Dark Horse Manga, Kodansha Comics, Seven Seas, "
                    "Square Enix Manga, TOKYOPOP, Titan, Vertical, Inklore. "
                    "Filtra por fecha de lanzamiento ≥ wiki-from."
                ),
                "values": {
                    "--bootstrap-wiki": "prhcomics",
                },
            },
            {
                "id": "prhcomics_full",
                "label": "🇺🇸 PRH Comics - catálogo completo EN/CA",
                "desc": (
                    "Igual que el delta pero sin filtro de fecha — devuelve todo el "
                    "catálogo activo de PRH Comics (hardcovers + box sets, "
                    "publishers distribuidos por PRH). Una sola request HTTP."
                ),
                "values": {
                    "--bootstrap-wiki": "prhcomics",
                    "--wiki-from": "2000-01",
                },
            },
            {
                "id": "kinokuniya_delta",
                "label": "🇺🇸 Kinokuniya USA - exclusivos (catálogo activo)",
                "desc": (
                    "Descarga la página kinokuniya-exclusives de Kinokuniya USA. "
                    "Extrae ISBNs del patrón /bw/{isbn13} en los links de producto. "
                    "Cubre: variant covers, dust jackets exclusivos, shikishi, ID cards, "
                    "sticker packs, limited editions con bonus. Una sola request HTTP. "
                    "El sitio corre sobre Squarespace — CSS class names dinámicos, "
                    "el parser usa URLs en vez de selectores CSS."
                ),
                "values": {
                    "--bootstrap-wiki": "kinokuniya",
                },
            },
            {
                "id": "kinokuniya_full",
                "label": "🇺🇸 Kinokuniya USA - catálogo completo (igual al delta)",
                "desc": (
                    "Igual que kinokuniya_delta. La página Kinokuniya Exclusives "
                    "no tiene paginación histórica — siempre devuelve el catálogo "
                    "activo completo. Este preset es equivalente al delta."
                ),
                "values": {
                    "--bootstrap-wiki": "kinokuniya",
                    "--wiki-from": "2000-01",
                },
            },
            {
                "id": "yenpress_delta",
                "label": "🇺🇸 Yen Press Calendar - últimos 3 meses",
                "desc": (
                    "Descarga el calendario mensual de yenpress.com/calendar para "
                    "los últimos ~3 meses. Filtra categorías manga/comics (excluye "
                    "light novels y audio) y aplica pre-filtro por keywords de "
                    "edición especial: collector's, deluxe, box set, hardcover, "
                    "limited edition, artbook, slipcase, numbered. ~3 requests HTTP."
                ),
                "values": {
                    "--bootstrap-wiki": "yenpress",
                },
            },
            {
                "id": "yenpress_full",
                "label": "🇺🇸 Yen Press Calendar - catálogo histórico desde 2013",
                "desc": (
                    "Descarga el calendario de Yen Press desde 2013-01 hasta hoy. "
                    "~140 meses × 1 request = ~140 HTTP, ~70s con sleep 0.5s. "
                    "Cubre toda la historia editorial de Yen Press EN para "
                    "ediciones especiales (collector's editions, box sets, etc.)."
                ),
                "values": {
                    "--bootstrap-wiki": "yenpress",
                    "--wiki-from": "2013-01",
                },
            },
            {
                "id": "shueisha_delta",
                "label": "🇯🇵 Shueisha Books - nuevos volúmenes",
                "desc": (
                    "Busca nuevos volúmenes en series Shueisha (ONE PIECE Magazine, "
                    "Color Walk, All Faces, Doors). Navega los links '次巻' desde "
                    "los últimos volúmenes conocidos. Rápido (~10 requests)."
                ),
                "values": {
                    "--bootstrap-wiki": "shueisha",
                },
            },
            {
                "id": "shueisha_full",
                "label": "🇯🇵 Shueisha Books - catálogo completo",
                "desc": (
                    "Recorre series completas + standalone (databooks, artbooks, "
                    "cookbooks). ~40-50 pages × 0.5s = ~25s. Cubre el catálogo "
                    "histórico de publicaciones especiales Shueisha para One Piece."
                ),
                "values": {
                    "--bootstrap-wiki": "shueisha",
                    "--wiki-from": "2000-01",
                },
            },
            {
                "id": "viz_full",
                "label": "🇺🇸 VIZ Special Editions - catálogo completo",
                "desc": (
                    "Recorre el calendario mensual de VIZ Media (2013 → hoy) y "
                    "captura TODAS las ediciones especiales EN: box sets, deluxe / "
                    "definitive editions, hardcovers, collector's / anniversary, "
                    "artbooks (Color Walk). Cubre las franquicias Shonen Jump de "
                    "Shueisha en inglés (One Piece, Naruto, Vagabond, Nana…)."
                ),
                "values": {
                    "--bootstrap-wiki": "viz",
                    "--wiki-from": "2013-01",
                },
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
                           "booksprivilege", "sumikko",
                           "listadomanga-collections", "mangapassion",
                           "animeclick", "prhcomics", "kinokuniya", "yenpress"]),
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
            "noticias). Los movidos van a data/diagnostics/items.non_manga.jsonl para "
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
            "regulares sin nada especial' a data/diagnostics/items.non_collectible.jsonl. "
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
        "id": "clean_descriptions",
        "category": "Mantenimiento",
        "icon": "🧹",
        "name": "Re-limpiar descripciones",
        "tagline": "Strip de prefijos de botón 'leer más' en description/description_es.",
        "what": (
            "Aplica clean_description() sobre los campos description y description_es "
            "de todos los items. Elimina prefijos tipo 'EN SAVOIR PLUS', 'MÁS INFORMACIÓN', "
            "'READ MORE', etc. que el scraper captura del wrapper del CTA (gotcha #37). "
            "Es seguro correrla varias veces."
        ),
        "when": (
            "Después de scrapes de fuentes FR - Meian u otras que embeben el botón "
            "'leer más' en el texto de la card."
        ),
        "command": [PYTHON, "scripts/retrofit/clean_descriptions.py"],
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
                  "Cuenta cuántos items cambiarían sin guardar nada.",
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
            {
                "id": "only_galleries",
                "label": "🎞️ Solo carrusel multi-imagen",
                "desc": "Re-fetchea detail pages para poblar images[] (galería completa: cover + tomas adicionales). Procesa items con < 2 imágenes.",
                "values": {"--only": "images"},
            },
        ],
        "flags": [
            _flag("--only", "Solo este campo",
                  "Si querés rellenar solo uno: image_url, author, isbn, "
                  "release_date, price, o images (carrusel multi-imagen).",
                  type="choice", default="",
                  choices=["", "image_url", "author", "isbn", "release_date", "price", "images"]),
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
        "id": "backfill_animeclick_details",
        "category": "Mantenimiento",
        "icon": "🇮🇹",
        "name": "Backfill AnimeClick (fecha, precio, descripción)",
        "tagline": "Rellena release_date / price / description en items AnimeClick que quedaron vacíos.",
        "what": (
            "Cuando se ingestaron los items de AnimeClick sin buscar el "
            "detalle de cada edición, los campos release_date, price y "
            "description quedaron vacíos. Este script los rellena fetching "
            "directamente las páginas de detalle — sin re-navegar el "
            "calendario semana a semana. Con 4 workers tarda ~8 min para "
            "1400 items."
        ),
        "when": (
            "Una sola vez tras la ingesta inicial de AnimeClick. También "
            "si aparecen nuevos items sin fecha/precio después de una "
            "corrida de animeclick."
        ),
        "command": [PYTHON, "scripts/retrofit/backfill_animeclick_details.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba (5 items)",
                "desc": "Muestra qué campos rellenará sin tocar items.jsonl.",
                "values": {"--dry-run": True, "--limit": 5},
            },
            {
                "id": "full",
                "label": "🟢 Rellenar todo",
                "desc": "Backfill completo con 4 workers (~8 min).",
                "values": {"--workers": 4},
            },
        ],
        "flags": [
            _flag("--workers", "Workers paralelos",
                  "Cuántos fetches hacer en paralelo. Default 4.",
                  type="int", default=4),
            _flag("--sleep", "Pausa entre requests (seg)",
                  "Segundos de pausa por worker entre fetches. Default 0.3.",
                  type="float", default=0.3, advanced=True),
            _flag("--limit", "Máx items a procesar",
                  "0 = sin límite. Útil para pruebas.",
                  type="int", default=0, placeholder="50"),
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los cambios que haría sin tocar items.jsonl.",
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
        "id": "upgrade_image_resolution",
        "category": "Mantenimiento",
        "icon": "🔍",
        "name": "Mejorar resolución de portadas",
        "tagline": "Re-descarga portadas en resolución original eliminando parámetros de redimensionado.",
        "what": (
            "Muchos retailers (Panini IT, JBC BR, MangaLine, Mangavariant…) "
            "sirven las portadas con parámetros que las redimensionan a "
            "miniaturas (ej. ?height=222&width=222 o sufijos -300x300.jpg). "
            "Este script detecta esos patrones, descarga la versión original "
            "sin redimensionar y reemplaza el archivo local solo si la nueva "
            "imagen tiene notablemente más píxeles. Actualiza image_url e "
            "images[] en items.jsonl para reflejar la URL original."
        ),
        "when": (
            "1× después de una ingesta grande de fuentes con imágenes "
            "pixeladas (Mangavariant, Panini IT, JBC BR). Luego es "
            "idempotente — URLs ya limpias no se reprocesan. Los archivos "
            "locales viejos (miniaturas) quedan como huérfanos y se limpian "
            "la próxima vez que corras mirror_images con GC."
        ),
        "command": [PYTHON, "scripts/retrofit/upgrade_image_resolution.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Solo reporta cuántas URLs se podrían mejorar, sin descargar.",
                "values": {"--dry-run": True},
            },
            {
                "id": "all",
                "label": "🟢 Mejorar todo",
                "desc": "Upgrade completo del corpus con 8 workers paralelos.",
                "values": {"--workers": 8},
            },
            {
                "id": "test",
                "label": "🔬 Prueba rápida (100 items)",
                "desc": "Procesa solo 100 URLs para verificar que funciona antes del run completo.",
                "values": {"--limit": 100},
            },
        ],
        "flags": [
            _flag("--workers", "Descargas en paralelo",
                  "Cuántas imágenes bajar al mismo tiempo. Default 4.",
                  type="int", default=4),
            _flag("--min-gain", "Ganancia mínima de píxeles",
                  "Fracción mínima de mejora para reemplazar la imagen "
                  "(0.10 = 10% más píxeles). Default 0.10.",
                  type="float", default=0.10, placeholder="0.10", advanced=True),
            _flag("--limit", "Máx URLs a procesar",
                  "0 = sin límite. Útil para probar con --limit 100.",
                  type="int", default=0, placeholder="100"),
            _flag("--dry-run", "Modo prueba (no descarga ni escribe)",
                  "Solo reporta qué haría, sin tocar nada.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "backfill_prh_covers",
        "category": "Mantenimiento",
        "icon": "🇺🇸",
        "name": "Portadas EN via PRH CDN",
        "tagline": "Mejora portadas de items EN con ISBN usando el CDN determinístico de Penguin Random House.",
        "what": (
            "Para items en inglés con ISBN-13 de prefijo 978-0 / 978-1, "
            "prueba la URL determinística del CDN de PRH: "
            "images.penguinrandomhouse.com/cover/{isbn13}. PRH distribuye manga EN "
            "de Dark Horse, Kodansha Comics, Seven Seas, Square Enix, TOKYOPOP, "
            "Titan, Vertical, Inklore, Yen Press y más. Para ISBNs fuera del "
            "catálogo PRH el CDN devuelve 404 (descartado automáticamente). "
            "Compara por píxeles antes de reemplazar (--min-gain 0.10 = 10% mínimo)."
        ),
        "when": (
            "Después de ingestas de fuentes EN con imágenes pequeñas (Yen Press "
            "Calendar, VIZ, Manga-Sanctuary EN). Idempotente — items ya usando PRH "
            "CDN se saltan. 39 candidatos en el corpus actual."
        ),
        "command": [PYTHON, "scripts/retrofit/backfill_prh_covers.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Muestra los candidatos sin descargar ni modificar nada.",
                "values": {"--dry-run": True},
            },
            {
                "id": "all",
                "label": "🟢 Backfill completo",
                "desc": "Procesa todos los items EN con ISBN en paralelo.",
                "values": {"--workers": 8},
            },
            {
                "id": "accept_always",
                "label": "🔓 Aceptar siempre (sin umbral)",
                "desc": "Reemplaza la portada aunque no haya mejora de píxeles (útil cuando la actual es placeholder).",
                "values": {"--min-gain": 0, "--workers": 8},
            },
        ],
        "flags": [
            _flag("--workers", "Descargas en paralelo",
                  "Cuántas ISBNs probar al mismo tiempo. Default 4.",
                  type="int", default=4),
            _flag("--min-gain", "Ganancia mínima de píxeles",
                  "Fracción mínima de mejora para reemplazar (0.10 = 10% más píxeles). "
                  "Usar 0 para aceptar siempre si PRH tiene la imagen.",
                  type="float", default=0.10, placeholder="0.10", advanced=True),
            _flag("--limit", "Máx items a procesar",
                  "0 = sin límite. Útil para probar con --limit 10.",
                  type="int", default=0, placeholder="10"),
            _flag("--dry-run", "Modo prueba (no descarga ni escribe)",
                  "Solo muestra los candidatos que procesaría.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "upscale_images",
        "category": "Mantenimiento",
        "icon": "🔬",
        "name": "Upscaling de portadas pixeladas (IA)",
        "tagline": "Mejora la resolución de portadas pequeñas con waifu2x o Real-ESRGAN.",
        "what": (
            "Muchas fuentes JP (sumikko, booksprivilege, Rakuten) y algunas IT "
            "(animeclick) sólo exponen miniaturas de ~150×220 px — no existe "
            "versión más grande en el servidor. Este script usa IA (waifu2x-ncnn-vulkan "
            "o realesrgan-ncnn-vulkan, modelos optimizados para anime/manga) para "
            "upscalear ×2 esas imágenes a ~300×440 px. El resultado se guarda como "
            "PNG (lossless) en data/images/. Si la extensión cambia de .jpg a .png, "
            "el campo image_local en items.jsonl se actualiza automáticamente."
        ),
        "when": (
            "Después de ingestas de fuentes JP con muchas portadas pixeladas. "
            "Requiere instalar primero: brew install waifu2x-ncnn-vulkan"
        ),
        "command": [PYTHON, "scripts/retrofit/upscale_images.py"],
        "presets": [
            {
                "label": "🔬 Dry-run (ver cuántas hay)",
                "flags": {"--dry-run": True},
            },
            {
                "label": "🔬 Test rápido (20 imágenes)",
                "flags": {"--limit": 20},
            },
            {
                "label": "🔬 Todo (< 200 000 px)",
                "flags": {"--max-pixels": 200000},
            },
        ],
        "flags": [
            _flag("--max-pixels", "Umbral de píxeles",
                  "Solo procesa imágenes con menos de N píxeles totales. "
                  "200 000 ≈ 450×445 px. Subir para procesar más imágenes.",
                  type="int", default=200000, placeholder="200000"),
            _flag("--scale", "Factor de escala",
                  "Multiplicar las dimensiones por este factor (2 o 4). "
                  "Default 2: una imagen de 150×220 pasa a ~300×440 px.",
                  type="choice", default="2", choices=["2", "4"]),
            _flag("--denoise", "Nivel de denoise (waifu2x)",
                  "0 = sin denoise, 1 = leve (recomendado), 3 = agresivo. "
                  "Solo aplica a waifu2x-ncnn-vulkan.",
                  type="int", default=1, placeholder="1", advanced=True),
            _flag("--limit", "Máx imágenes a procesar",
                  "0 = sin límite. Útil para probar con --limit 20.",
                  type="int", default=0, placeholder="20"),
            _flag("--dry-run", "Modo prueba (no upscalea ni escribe)",
                  "Solo muestra las imágenes candidatas con sus píxeles actuales.",
                  type="bool", default=False),
            _flag("--no-delete-original", "Conservar .jpg original",
                  "Por default el .jpg se borra cuando se guarda el .png upscaleado. "
                  "Con este flag se conservan ambos.",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "translate_descriptions",
        "category": "Mantenimiento",
        "icon": "🌐",
        "name": "Traducir descripciones al español",
        "tagline": "Traduce las descripciones (DE/FR/IT/JP/VI/TH…) al español.",
        "what": (
            "El catálogo tiene items de 13 países en 8 idiomas: japonés, "
            "alemán, francés, italiano, vietnamita, tailandés… Las descripciones "
            "vienen en el idioma de la fuente y son ilegibles para un lector en "
            "español. Este script popula el campo description_es con la "
            "traducción al español usando Google Translate (gratuito, sin API key, "
            "funciona con todos los idiomas) y opcionalmente DeepL (mejor calidad "
            "si DEEPL_API_KEY está en .env). El campo description original no se "
            "toca — lo sigue usando el sistema de señales internamente. "
            "Guarda progreso cada --flush-every items para poder retomar si se interrumpe."
        ),
        "when": (
            "Después de cada scrape grande que trajo items nuevos con "
            "descripción en idioma extranjero. Idempotente: solo traduce "
            "items sin description_es (o todos si usás --force). "
            "Funciona sin ninguna API key usando Google Translate."
        ),
        "command": [PYTHON, "scripts/retrofit/translate_descriptions.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba (sin traducir)",
                "desc": "Muestra cuántos items y campos se traducirían. No llama a la API.",
                "values": {"--dry-run": True},
            },
            {
                "id": "translate_all",
                "label": "🟢 Traducir pendientes",
                "desc": "Traduce todos los items sin description_es. Crea backup automático.",
                "values": {},
            },
            {
                "id": "translate_force",
                "label": "🔄 Re-traducir todo",
                "desc": "Re-traduce todos los items aunque ya tengan description_es.",
                "values": {"--force": True},
            },
        ],
        "flags": [
            _flag("--workers", "Hilos paralelos",
                  "Cuántas llamadas a la API hacer en paralelo. Default 4. "
                  "Subir a 8 si la API responde rápido.",
                  type="int", default=4),
            _flag("--limit", "Máx items a traducir",
                  "0 = sin límite. Útil para probar con --limit 50.",
                  type="int", default=0, placeholder="50"),
            _flag("--sleep", "Pausa entre llamadas (seg)",
                  "Segundos de pausa entre llamadas a la API para evitar "
                  "rate-limit. Default 0.15.",
                  type="float", default=0.15, advanced=True),
            _flag("--flush-every", "Guardar cada N items",
                  "Guarda el progreso a disco cada N items procesados. "
                  "Permite retomar sin perder trabajo si el proceso se interrumpe. "
                  "Default 50.",
                  type="int", default=50, advanced=True),
            _flag("--force", "Re-traducir existentes",
                  "Traduce aunque description_es ya esté poblado.",
                  type="bool", default=False, advanced=True),
            _flag("--dry-run", "Modo prueba",
                  "Solo muestra qué se traduciría. No llama a la API.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "fetch_better_covers",
        "category": "Mantenimiento",
        "icon": "🔍",
        "name": "Buscar portadas en mayor resolución",
        "tagline": "Para items con imagen pequeña, busca portadas hi-res y las deja en preview para tu aprobación.",
        "what": (
            "Muchas fuentes IT (AnimeClick) y ES (ListadoManga) sólo exponen portadas pequeñas. "
            "Este script busca la versión hi-res por orden de prioridad: "
            "(1) ISBN → Amazon CDN + PRH CDN (EN) + OpenLibrary — gratis, sin cuota, sin búsqueda web. "
            "(2) Sin ISBN → Serper Google Images API (SERPER_API_KEY, 2 500 queries gratis sin tarjeta) o "
            "Tavily Search API (TAVILY_API_KEY, 1 000 queries/mes) como fallback. "
            "Keys auto-cargadas desde .env. "
            "Verificación: perceptual hash aHash 8×8, distancia Hamming ≤ --max-hash-dist (default 12/64). "
            "SEGURO POR DEFECTO (2026-06-03): NO reemplaza ninguna portada automáticamente — todas las "
            "candidatas van a cover-preview.html para tu aprobación manual; el item conserva su portada "
            "vieja hasta que apruebes. Solo busca imágenes que realmente lo necesitan (debajo de --min-pixels). "
            "Con --apply, las de ALTA confianza (CDN/ISBN hash-verificadas) se aplican directo; la baja "
            "confianza NUNCA se auto-aplica. Aprobás en la página → corrés con --apply-preview."
        ),
        "when": (
            "Después de upgrade_image_resolution.py. Cuando hay items con imagen < 100 000 px "
            "sin versión hi-res en el servidor origen (típico: AnimeClick IT, ListadoManga ES). "
            "Correr primero con --dry-run para estimar. "
            "Requiere: pip install Pillow. "
            "APIs opcionales en .env: SERPER_API_KEY (2 500 gratis, sin tarjeta) o TAVILY_API_KEY (1 000/mes)."
        ),
        "command": [PYTHON, "scripts/retrofit/fetch_better_covers.py"],
        "presets": [
            {
                "label": "🔍 Dry-run (ver candidatos)",
                "flags": {"--dry-run": True, "--limit": 30, "--verbose": True},
            },
            {
                "label": "🔍 Solo CDN + OpenLibrary (sin web search)",
                "flags": {"--no-search": True},
            },
            {
                "label": "🔍 Buscar y mandar a preview (no aplica nada)",
                "flags": {},
            },
            {
                "label": "✅ Aplicar aprobadas del preview",
                "flags": {"--apply-preview": True},
            },
        ],
        "flags": [
            _flag("--min-pixels", "Umbral de calidad baja (px)",
                  "Items con imagen de menos de N píxeles totales son candidatos. "
                  "Default 100 000 ≈ 316×316 px.",
                  type="int", default=100000, placeholder="100000"),
            _flag("--min-gain", "Ganancia mínima requerida (×)",
                  "La candidata debe tener al menos N× más píxeles que la imagen actual. "
                  "Default 1.5: si la actual tiene 30 000 px, la candidata debe tener ≥ 45 000 px.",
                  type="float", default=1.5, placeholder="1.5"),
            _flag("--max-hash-dist", "Distancia hash máxima (0-64)",
                  "Distancia Hamming máxima del perceptual hash para aceptar la candidata "
                  "como 'misma portada'. 0 = imagen idéntica, 64 = completamente diferente. "
                  "Default 12: permite variaciones de iluminación, recorte leve, compresión.",
                  type="int", default=12, placeholder="12"),
            _flag("--no-search", "Solo CDN + OpenLibrary (sin búsqueda web)",
                  "No usa Serper, Brave ni Tavily. Solo lookups determinísticos por ISBN. "
                  "Rápido, sin consumo de cuota API; solo ayuda a items con ISBN.",
                  type="bool", default=False),
            _flag("--apply", "Aplicar directo las de ALTA confianza",
                  "Sin este flag (recomendado), NADA se aplica: todo va a preview para tu "
                  "aprobación. Con --apply, solo las de alta confianza (CDN/ISBN hash-verificadas) "
                  "se aplican directo; la baja confianza NUNCA se auto-aplica.",
                  type="bool", default=False),
            _flag("--apply-preview", "Aplicar las aprobadas del preview",
                  "Procesa cover_preview.json: aplica las que marcaste como aprobadas en la "
                  "página de revisión, descarta las rechazadas, deja las pendientes.",
                  type="bool", default=False),
            _flag("--include-upscaled", "Buscar también para imágenes upscaleadas",
                  "Por defecto solo se buscan portadas para imágenes chicas. Este flag fuerza "
                  "a buscar reemplazos reales también para imágenes agrandadas con AI (úsalo con "
                  "cuidado: estas ya son grandes y la búsqueda puede traer fotos peores).",
                  type="bool", default=False, advanced=True),
            _flag("--serper-key", "Serper API key (recomendado)",
                  "Si no se pasa, se lee SERPER_API_KEY del .env. "
                  "Google Images API — 2 500 queries gratis sin tarjeta de crédito en serper.dev. "
                  "Preferido sobre Brave y Tavily.",
                  type="str", default="", placeholder="abc123...", advanced=True),
            _flag("--tavily-key", "Tavily API key (opcional)",
                  "Si no se pasa, se lee TAVILY_API_KEY del .env. "
                  "Fallback si no hay Serper key. 1 000 queries/mes gratis.",
                  type="str", default="", placeholder="tvly-...", advanced=True),
            _flag("--limit", "Máx items a procesar",
                  "0 = sin límite. Útil para probar con --limit 50.",
                  type="int", default=0, placeholder="50"),
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Solo muestra qué se encontraría. No descarga ni modifica archivos.",
                  type="bool", default=False),
            _flag("--verbose", "Mostrar detalle de cada item",
                  "Imprime URL candidata, píxeles y resultado de verificación por item.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "dedup_carousel_images",
        "category": "Mantenimiento",
        "icon": "🖼️",
        "name": "Dedup portada del carrusel (misma foto, 2 resoluciones)",
        "tagline": "Quita del carrusel la misma portada repetida en baja calidad, conservando la hi-res.",
        "what": (
            "Cuando un item termina con la MISMA portada en dos resoluciones en images[] (ej. la "
            "cover hi-res del publisher + la misma como thumbnail de baja calidad de listadomanga), "
            "la deduplica por hash perceptual (aHash 8×8, Hamming ≤6 + aspect ratio ±12%) y conserva "
            "la de MAYOR resolución. SEGURO: solo toca kind=gallery — los `extra` (cofres, tomos del "
            "box, bonuses) son contenido curado e intocables — y exige dims válidas. Nunca deja un "
            "item sin imágenes; si la cover principal era una descartada, apunta a la kept hi-res. "
            "Corre como paso [4h] del pipeline (después de consolidate_sources, que es donde se crea "
            "el duplicado al unir imágenes de fuentes hermanas)."
        ),
        "when": (
            "Cuando el carrusel muestra la misma portada en alta y baja calidad. Automático en el "
            "pipeline; manual tras correr fetch_better_covers / upgrade_image_resolution. "
            "Correr primero con --dry-run. Requiere: pip install Pillow."
        ),
        "command": [PYTHON, "scripts/retrofit/dedup_carousel_images.py"],
        "presets": [
            {"label": "🖼️ Dry-run (ver qué se quitaría)", "flags": {"--dry-run": True}},
            {"label": "🖼️ Aplicar (solo items con imagen de listadomanga)", "flags": {}},
            {"label": "🖼️ Aplicar a TODOS los items", "flags": {"--all": True}},
        ],
        "flags": [
            _flag("--dry-run", "Solo mostrar, no escribir",
                  "Lista las imágenes que se quitarían sin tocar items.jsonl.",
                  type="bool", default=False),
            _flag("--all", "Todos los items (no solo listadomanga)",
                  "Por defecto solo procesa items que tienen alguna imagen de listadomanga. "
                  "Con --all revisa el carrusel de TODOS los items con ≥2 imágenes.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "promote_hires_cover",
        "category": "Mantenimiento",
        "icon": "⬆️",
        "name": "Promover portada hi-res desde la galería",
        "tagline": "Mueve a images[0] la portada en alta resolución que ya está en images[1+].",
        "what": (
            "Algunos items de listadomanga tienen el thumbnail de la portada en images[0] "
            "(<90 000 px) pero la MISMA portada en alta resolución ya está en images[1+] "
            "(vino de otra fuente del cluster, ej. Panini, Norma, Whakoom). "
            "Este script intercambia images[0] ↔ images[k]: la hi-res pasa a ser la portada. "
            "La identidad se verifica con _same_cover (AND-gate multi-hash + NCC), mismo "
            "umbral que el skill watch-search-covers. El thumbnail NO se elimina — queda en "
            "la galería; dedup_carousel_images puede quitarlo después si lo decide."
        ),
        "when": (
            "Tras una ingesta de listadomanga-collections que trajo thumbnails pequeños, "
            "cuando el cluster ya tiene la portada real en otra fuente. "
            "Correr primero con --dry-run. Requiere: pip install Pillow."
        ),
        "command": [PYTHON, "scripts/retrofit/promote_hires_cover.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🔍 Dry-run (ver qué se promovería)",
                "desc": "Lista los ítems que se beneficiarían sin escribir nada.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "⬆️ Aplicar",
                "desc": "Promueve las portadas hi-res encontradas en la galería.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Solo mostrar, no escribir",
                  "Lista los items que cambiarían sin tocar items.jsonl.",
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

    {
        "id": "generate_slugs",
        "category": "Retrofit",
        "icon": "🔗",
        "name": "Generar slugs para el app Next.js",
        "tagline": "Asigna el campo `slug` a cada item para la ruta /item/[slug] del app.",
        "what": (
            "El app Next.js (web-next/) usa URLs del tipo /item/berserk-darkhorse-"
            "deluxe-42 para las páginas de detalle. Este script genera esas URLs "
            "y las guarda en el campo `slug` de items.jsonl. Prioridad: si el item "
            "tiene ISBN en el cluster_key → isbn-{isbn}; si tiene edition_key + "
            "volumen → {edition_key}-{vol}; si solo edition_key → {edition_key}; "
            "si tiene isbn en el campo → isbn-{isbn}; sino → item-{hash}. "
            "Las colisiones se resuelven con sufijos -b/-c (el más antiguo conserva "
            "el slug limpio). Idempotente: no re-escribe slugs que no cambiaron."
        ),
        "when": (
            "Como último paso del skill /watch-standardize-catalog, después de asignar "
            "edition_key y volume a los items nuevos. También correrlo una vez "
            "para generar slugs en todo el corpus existente. No corre "
            "automáticamente en scrape_delta ni scrape_full."
        ),
        "command": [PYTHON, "scripts/retrofit/generate_slugs.py"],
        "presets": [
            {
                "id": "only_missing",
                "label": "🟢 Solo items sin slug (incremental)",
                "desc": "Asigna slugs únicamente a los items nuevos. Rápido.",
                "values": {"--only-missing": True},
            },
            {
                "id": "all",
                "label": "🔄 Regenerar todos",
                "desc": "Recomputa slugs en todo el corpus. Actualiza los que cambiaron.",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra qué slugs asignaría sin tocar items.jsonl.",
                "values": {"--dry-run": True, "--verbose": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los slugs que asignaría sin modificar items.jsonl.",
                  type="bool", default=False),
            _flag("--only-missing", "Solo items sin slug",
                  "Salta los items que ya tienen slug. Ideal para corridas "
                  "incrementales post-/watch-standardize-catalog.",
                  type="bool", default=False),
            _flag("--verbose", "Log de cada asignación",
                  "Imprime el slug asignado y el título de cada item procesado.",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "set_rarity",
        "category": "Retrofit",
        "icon": "🟪",
        "name": "Asignar rareza",
        "tagline": "Aplica el campo rarity a todos los items",
        "what": "Clasifica cada item en common / rare / super_rare / ultra_rare "
                "usando derive_rarity_tier() de manga_watch.py. Solo recalcula "
                "los items que no tienen rarity asignado (o todos con --force).",
        "when": "Después de scrapes grandes, o cuando cambien las reglas de rareza.",
        "command": [PYTHON, "scripts/retrofit/set_rarity.py"],
        "presets": [
            {
                "id": "missing_only",
                "label": "🟢 Solo items sin rareza (incremental)",
                "desc": "Asigna rareza únicamente a los items nuevos sin clasificar.",
                "values": {},
            },
            {
                "id": "force_all",
                "label": "🔄 Recalcular todos (--force)",
                "desc": "Recomputa rarity en todo el corpus con las reglas actuales.",
                "values": {"--force": True},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra qué cambiaría sin modificar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los cambios que aplicaría sin modificar items.jsonl.",
                  type="bool", default=False),
            _flag("--force", "Recalcular todos",
                  "Recalcula rarity en TODOS los items, incluso los ya clasificados. "
                  "Útil cuando cambian las reglas de derive_rarity_tier().",
                  type="bool", default=False),
        ],
    },
    {
        "id": "apply_approvals",
        "category": "Retrofit",
        "icon": "✅",
        "name": "Re-aplicar aprobaciones",
        "tagline": "Restaura los golden records desde el log durable.",
        "what": "Lee data/approvals.jsonl (el log de las cards aprobadas desde "
                "el dashboard) y vuelve a marcar approved_at/approved_by en "
                "items.jsonl. Sirve después de reconstruir el catálogo de cero "
                "(re-scrape/import), cuando los flags de aprobación se perdieron. "
                "Idempotente.",
        "when": "Tras una reconstrucción de items.jsonl, para no perder lo aprobado.",
        "command": [PYTHON, "scripts/retrofit/apply_approvals.py"],
        "presets": [
            {
                "id": "apply",
                "label": "✅ Re-aplicar aprobaciones",
                "desc": "Marca de nuevo como aprobados los items del log.",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra cuántos items se marcarían sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra cuántos items se marcarían sin modificar items.jsonl.",
                  type="bool", default=False),
        ],
    },
    {
        "id": "sync_cover_images",
        "category": "Retrofit",
        "icon": "🖼️",
        "name": "Sincronizar portada del carrusel",
        "tagline": "Hace que images[0] sea siempre la portada de la card.",
        "what": "Saneamiento integral de imágenes: (1) si la portada es un "
                "placeholder/banner, promueve una imagen real o la limpia (→ 📚); "
                "(2) pone la portada en images[0] (la misma que muestra la card); "
                "(3) elimina duplicados, banners y avatares de UI; (4) descarta "
                "galerías que son otros tomos/series (no fotos del producto).",
        "when": "Cuando una card y su carrusel muestran fotos distintas, hay "
                "imágenes repetidas / banners / avatares, o carruseles con fotos "
                "de otras series.",
        "command": [PYTHON, "scripts/retrofit/sync_cover_images.py"],
        "presets": [
            {
                "id": "apply",
                "label": "🖼️ Sincronizar portadas",
                "desc": "Repara images[0] y limpia duplicados/banners.",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra cuántos items se corregirían sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los cambios que aplicaría sin modificar items.jsonl.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "También re-sincroniza items aprobados (por defecto se saltean).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "align_raw_to_std_coleccion",
        "category": "Retrofit",
        "icon": "🔗",
        "name": "Alinear raw a edición estandarizada (por coleccion)",
        "tagline": "Dedup raw-vs-estandarizado al re-scrapear una coleccion ya conocida.",
        "what": "Re-scrapear una /coleccion que YA tiene items estandarizados deja "
                "el item raw nuevo con edition_key/cluster_key distinto del viejo → "
                "no consolidan y aparece la misma coleccion dos veces (ej. "
                "'Bastard!! nº1' raw vs 'Bastard!! Deluxe 1' estandarizado). Por la "
                "regla coleccion=edición, los raw heredan series/edition del item "
                "estandarizado de su misma coleccion y consolidan. No toca title ni "
                "standardized_at. Idempotente. Corre como paso [4f2] del pipeline, "
                "antes de consolidate_sources.",
        "when": "Tras scrapear listadomanga-collections sobre colecciones que ya "
                "estaban en el corpus estandarizadas.",
        "command": [PYTHON, "scripts/retrofit/align_raw_to_std_coleccion.py"],
        "presets": [
            {
                "id": "apply",
                "label": "🔗 Alinear",
                "desc": "Alinea raw a la edición estandarizada de su coleccion y consolida.",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra qué items raw se re-keyarían sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los items raw a alinear sin modificar items.jsonl.",
                  type="bool", default=False),
        ],
    },
    {
        "id": "fix_store_publisher",
        "category": "Retrofit",
        "icon": "🏪",
        "name": "Sacar nombre de tienda del publisher (Sanyodo/Rakuten)",
        "tagline": "La tienda no es la editorial — limpia publisher y colapsa dups por ISBN.",
        "what": "Las fuentes JP Sanyodo y Rakuten Books seteaban publisher=nombre "
                "de la tienda, que contaminaba el edition_key (…-rakuten-… o "
                "…-unknown-…) y generaba 'posibles productos duplicados' con la "
                "ficha de la editorial oficial (mismo ISBN, distinto cluster_key). "
                "Limpia el campo publisher (top-level y dentro de sources[]), "
                "recupera la editorial real por slug del edition_key o por hermano "
                "con el mismo ISBN (si no se puede, lo deja vacío), y colapsa los "
                "dups de mismo-ISBN+mismo-series cuyo único conflicto era el slug "
                "de publisher. No toca divergencias de romanización ni aprobados. "
                "Idempotente. Correr generate_slugs después.",
        "when": "1× sobre el corpus histórico (las fuentes ya quedaron sin "
                "publisher de tienda para futuras corridas). Ver gotcha #44.",
        "command": [PYTHON, "scripts/retrofit/fix_store_publisher.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Muestra qué cambiaría sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Limpiar",
                "desc": "Aplica la limpieza con backup y consolida.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Cuenta cuántos items cambiarían sin guardar nada.",
                  type="bool", default=False),
        ],
    },
    {
        "id": "fix_listadomanga_edition_display",
        "category": "Retrofit",
        "icon": "🏷️",
        "name": "Nombre oficial de edición (sin traducir)",
        "tagline": "edition_display = título oficial de la /coleccion, no un slug traducido.",
        "what": "El nombre de la edición debe ser el oficial (el título de la "
                "coleccion en ListadoManga), sin traducir — no 'Special (Norma "
                "Editorial)'. Re-fetchea el título de cada coleccion y lo asigna "
                "a todos sus items. Sólo el nombre del tomo se traduce, el de la "
                "edición no. Network-bound (re-fetch ~500 colecciones).",
        "when": "1× sobre el corpus; el parser ya pone el título oficial en items nuevos.",
        "command": [PYTHON, "scripts/retrofit/fix_listadomanga_edition_display.py"],
        "presets": [
            {"id": "apply", "label": "🏷️ Aplicar", "desc": "Asigna el nombre oficial de edición.", "values": {}},
            {"id": "dryrun", "label": "🧪 Preview (no escribe)", "desc": "Muestra los cambios sin escribir.", "values": {"--dry-run": True}},
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)", "Muestra los edition_display a corregir.", type="bool", default=False),
        ],
    },
    {
        "id": "unify_coleccion_edition",
        "category": "Retrofit",
        "icon": "📂",
        "name": "Una coleccion = una edición",
        "tagline": "Agrupa todos los tomos de una /coleccion (regular+especial+cofres) en una página.",
        "what": "Una /coleccion de ListadoManga es UNA página de edición. Unifica "
                "el edition_key de todos sus tomos al de la edición base (regular, o "
                "la predominante). Las variantes del mismo volumen (tomo 34 normal vs "
                "especial) no se fusionan: las distingue el cluster_key por "
                "coleccion+tipo+volumen. Idempotente.",
        "when": "Tras scrapear ListadoManga; corre como paso [4f3] del pipeline.",
        "command": [PYTHON, "scripts/retrofit/unify_coleccion_edition.py"],
        "presets": [
            {"id": "apply", "label": "📂 Unificar", "desc": "Agrupa los tomos de cada coleccion en una edición.", "values": {}},
            {"id": "dryrun", "label": "🧪 Preview (no escribe)", "desc": "Muestra qué items se re-asignarían.", "values": {"--dry-run": True}},
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los items a re-asignar sin modificar items.jsonl.",
                  type="bool", default=False),
        ],
    },
    {
        "id": "fix_edition_country",
        "category": "Retrofit",
        "icon": "🌍",
        "name": "País en edition_key (país = edición)",
        "tagline": "Regla dura: país distinto = edición distinta. Sufija el país al edition_key.",
        "what": "Dos mercados nunca pueden ser la misma edición aunque coincidan "
                "obra+editorial+tipo (Panini IT vs ES vs MX). Sufija el edition_key "
                "con el código de país de la edición y recomputa cluster_key, de modo "
                "que la vista de edición y el dedup separen mercados. El país es el de "
                "la edición (editorial/idioma), NO el de la tienda — una tienda puede "
                "revender la edición de otro país y sigue siendo una sola edición. "
                "Idempotente.",
        "when": "1× tras introducir la regla; el scraper ya hornea el país en items "
                "nuevos. Correr generate_slugs.py después.",
        "command": [PYTHON, "scripts/retrofit/fix_edition_country.py"],
        "presets": [
            {
                "id": "apply",
                "label": "🌍 Aplicar",
                "desc": "Sufija país al edition_key, recomputa cluster_key y consolida.",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra cuántos edition_keys se sufijarían sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los edition_key a sufijar sin modificar items.jsonl.",
                  type="bool", default=False),
        ],
    },
    {
        "id": "fix_publisher_unknown_edition_key",
        "category": "Retrofit",
        "icon": "🏷️",
        "name": "Arreglar editorial 'unknown' en edition_key",
        "tagline": "Reemplaza el slug 'unknown' por la editorial real cuando el publisher está poblado.",
        "what": "El edition_key (series-publisher-edition) quedó con 'unknown' "
                "porque la editorial no estaba en el mapa de slugs al estandarizar "
                "(Norma, Planeta, Astiberri, Ponent Mon, Ediciones B, etc.). Esto "
                "hacía que ediciones de editoriales distintas colapsaran bajo el "
                "mismo slug. Recomputa el slug del publisher, reemplaza el segmento "
                "'unknown', recompute cluster_key y consolida. No toca series ni "
                "edition. Idempotente.",
        "when": "Tras agregar editoriales nuevas al mapa, o tras estandarizar items "
                "de editoriales que aún no estaban mapeadas.",
        "command": [PYTHON, "scripts/retrofit/fix_publisher_unknown_edition_key.py"],
        "presets": [
            {
                "id": "apply",
                "label": "🏷️ Arreglar",
                "desc": "Reemplaza 'unknown' por la editorial real y consolida.",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra qué edition_keys se corregirían sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los edition_key a corregir sin modificar items.jsonl.",
                  type="bool", default=False),
        ],
    },
    {
        "id": "consolidate_sources",
        "category": "Retrofit",
        "icon": "🧩",
        "name": "Consolidar fuentes (1 fila por producto)",
        "tagline": "Colapsa filas duplicadas del mismo producto en una con sources[].",
        "what": "Un producto encontrado en varias fuentes debe ser UNA sola fila "
                "con un array de fuentes (sources[]), no varias filas. Este "
                "retrofit agrupa por producto (cluster_key) y fusiona los "
                "duplicados conservando todas las fuentes, imágenes y extras. "
                "El scraper ya deduplica al ingestar; esto re-consolida tras la "
                "estandarización (que reasigna edition_key). Idempotente.",
        "when": "Después de /watch-standardize-catalog, o si ves cards duplicadas del "
                "mismo producto.",
        "command": [PYTHON, "scripts/retrofit/consolidate_sources.py"],
        "presets": [
            {
                "id": "apply",
                "label": "🧩 Consolidar",
                "desc": "Colapsa duplicados de producto en 1 fila con sources[].",
                "values": {},
            },
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra cuántas filas se colapsarían sin tocar items.jsonl.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra el conteo de consolidación sin modificar items.jsonl.",
                  type="bool", default=False),
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
    {
        "id": "data_quality",
        "category": "🔍 Calidad",
        "icon": "🩺",
        "name": "Auditoría de calidad de datos",
        "tagline": "Detecta fotos malas, mismatches e incongruencias. Solo lectura.",
        "what": (
            "Recorre todo data/items.jsonl SIN modificar nada y levanta alertas: "
            "imágenes (sin foto, ref local rota, archivo basura, portada con URL "
            "basura, pixelada midiendo píxeles con Pillow, card != carrusel, "
            "archivo compartido entre obras), procedencia (sin sources[], source "
            "sin url) y estructura (clusters con >1 fila, estandarizados sin keys, "
            "sin slug) + cobertura. Escribe data/quality_report.json que consume "
            "el Panel de Calidad (web/quality.html) como worklists clickeables."
        ),
        "when": (
            "Cuando quieras revisar la salud del catálogo, después de un scrape "
            "grande, o desde el botón 'Regenerar' del Panel de Calidad. Tarda "
            "~10-30s (la medición de píxeles abre cada imagen)."
        ),
        "command": [PYTHON, "scripts/audit/data_quality.py"],
        "presets": [
            {
                "id": "completo",
                "label": "🩺 Auditoría completa (con píxeles)",
                "desc": "Mide píxeles de cada portada. La más exhaustiva.",
                "values": {},
            },
            {
                "id": "rapido",
                "label": "⚡ Rápida (sin medir píxeles)",
                "desc": "Saltea Pillow. Más rápida; no detecta 'pixelada'.",
                "values": {"--no-measure": True},
            },
        ],
        "flags": [
            _flag("--px", "Umbral de píxeles 'pequeña'",
                  "Una portada con menos de estos píxeles se marca pixelada. "
                  "Default 90000 (≈300×300).",
                  type="int", default=90000, advanced=True),
            _flag("--examples", "Ejemplos por categoría (stdout)",
                  "Cuántos ejemplos imprimir en el log de cada alerta.",
                  type="int", default=6, advanced=True),
            _flag("--no-measure", "No medir píxeles (rápido)",
                  "Saltea abrir cada imagen con Pillow. Pierde la detección "
                  "de 'pixelada' pero corre mucho más rápido.",
                  type="bool", default=False),
            _flag("--no-json", "No escribir el JSON",
                  "Solo imprime el reporte humano, sin actualizar "
                  "data/quality_report.json.",
                  type="bool", default=False, advanced=True),
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
