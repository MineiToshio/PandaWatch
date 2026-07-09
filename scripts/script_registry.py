"""script_registry.py — fuente de verdad para el Panel de Control web.

Describe cada script que se puede ejecutar desde web/control.html con:
- una explicación "para dummies" de qué hace y cuándo se usa
- todos sus flags clasificados como básicos (siempre visibles) o avanzados
- presets pre-armados (combinaciones de flags recomendadas)

scripts/serve.py expone este registry vía GET /api/scripts y valida que
cualquier run venga de un id conocido + flags conocidas.

Convenciones de tipos de flag:
- "bool"      → toggle. Solo agrega el flag si está en True (acción 'store_true').
- "int"       → input numérico. Si vacío, no se agrega el flag. Soporta
                choices (lista de ints) para action="store" con choices=[...].
- "float"     → input numérico decimal. Idem "int" sin choices.
- "str"       → input texto libre. Si vacío, no se agrega el flag.
- "choice"    → select desplegable. choices: lista de strings.
- "csv"       → input texto que el usuario separa con comas. Mismo tratamiento
                que "str" (UN solo `--flag "a,b,c"`) pero con placeholder
                distinto. Para el argparse real: default="" con split interno.
- "csv_multi" → mismo input que "csv", pero el CLI emite el flag UNA VEZ POR
                cada valor separado por coma (`--flag a --flag b`). Usar
                cuando el argparse real es action="append" y NO hace split
                interno de comas (si el script sí splitea internamente, usar
                "csv" — más simple, un solo --flag).

Mantener este registry en sync con los argparse reales — si rompís uno y no
el otro, el panel ejecutará comandos inválidos. tests/test_script_registry.py
lo valida por AST contra cada script real.

Política deliberada de flags NO expuestos (2026-07-08, hallazgo 3.1 de la
auditoría Fable): varios scripts tienen --include-approved en su argparse
real pero NO en este registry a propósito — protege golden records
(items con approved_at) de mutaciones accidentales lanzadas desde el panel.
`rescore.py --include-standardized` tampoco se expone: es el guard de la
gotcha #61 (no rescorear items ya estandarizados). Si encontrás uno de estos
flags "faltante", es DELIBERADO — no lo agregues sin levantar el guard
correspondiente en el código primero.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


# Ejecutable Python a usar. Se resuelve en serve.py al path absoluto del venv.
PYTHON = ".venv/bin/python"


# ---------------------------------------------------------------------------
# Helpers para construir flags sin repetir kwargs.
# ---------------------------------------------------------------------------

def _flag(arg: str, label: str, help: str, *, type: str = "bool",
          default: Any = None, choices: list[Any] | None = None,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
            # El argparse real es action="append" (repetible: --only-source A
            # --only-source B), sin split interno de comas — encontrado por
            # el test AST (4.3, 2026-07-08) al escribirlo, no estaba en el
            # reporte de auditoría original. "csv_multi" también cubre el
            # caso de un solo nombre (comportamiento previo intacto).
            _flag("--only-source", "Solo esta(s) fuente(s) (CSV)",
                  "Nombre(s) EXACTO(s) de fuente, separados por coma si son "
                  "varias (ej. 'ES - Norma'). Útil para depurar una fuente "
                  "específica.",
                  type="csv_multi", default="",
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
                  "Solo items con score ≥ N se reportan. Default 20 — "
                  "coincide con el umbral real del script y con "
                  "scrape_delta/scrape_full; ya incluye artbooks.",
                  type="int", default=20, advanced=True),
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
        "mutates_items": True,
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
                "id": "sevenseas_delta",
                "label": "🇺🇸 Seven Seas - especiales recientes (3 meses)",
                "desc": (
                    "Anuncios nuevos de Seven Seas vía su API de WordPress: deluxe "
                    "hardcovers, box sets, collector's y special editions (manga, "
                    "manhwa y light novels EN). Enriquece cada uno con ISBN, fecha "
                    "y portada desde la ficha del libro."
                ),
                "values": {
                    "--bootstrap-wiki": "sevenseas",
                    "--wiki-from": "2026-04",
                },
            },
            {
                "id": "sevenseas_full",
                "label": "🇺🇸 Seven Seas - catálogo completo de especiales",
                "desc": (
                    "Recorre el catálogo completo (~6150 libros) de Seven Seas y "
                    "captura todas las ediciones especiales: deluxe hardcover "
                    "omnibus, box sets con extras, collector's editions, danmei "
                    "deluxe (Mo Dao Zu Shi…). ~150-250 items, el mayor gap de "
                    "cobertura de EEUU."
                ),
                "values": {
                    "--bootstrap-wiki": "sevenseas",
                    "--wiki-from": "2000-01",
                },
            },
            {
                "id": "kodansha_us_delta",
                "label": "🇺🇸 Kodansha USA - especiales recientes (3 meses)",
                "desc": (
                    "Ediciones especiales de Kodansha USA (deluxe hardcovers, omnibus, "
                    "collector's, box sets) desde su API propia. Modo delta: solo "
                    "volúmenes publicados en los últimos 3 meses (Vinland Saga Deluxe, "
                    "Battle Angel Alita Deluxe, Ghost in the Shell Deluxe, Attack on "
                    "Titan Omnibus…). Incluye ISBN y portada por volumen."
                ),
                "values": {
                    "--bootstrap-wiki": "kodansha-us",
                    "--wiki-from": "2026-04",
                },
            },
            {
                "id": "kodansha_us_full",
                "label": "🇺🇸 Kodansha USA - catálogo completo de especiales",
                "desc": (
                    "Descarga todo el catálogo de ediciones especiales de Kodansha USA "
                    "(~45 series, ~200-300 volúmenes): deluxe, omnibus, collector's, "
                    "hardcover y box sets. Enriquece cada volumen con ISBN, fecha y "
                    "portada desde las páginas individuales."
                ),
                "values": {
                    "--bootstrap-wiki": "kodansha-us",
                    "--wiki-from": "2000-01",
                },
            },
            {
                "id": "storefronts_api",
                "label": "🌏 Storefronts API - HK/TW/VN/TH (los 5 perfiles)",
                "desc": (
                    "Catálogos completos de las 5 tiendas editoriales con API JSON "
                    "(storefront_json.py): Jade Dynasty HK (珍藏版/愛藏版, ~340), "
                    "Sharp Point TW (特裝版, ~340+), Kim Đồng VN (bản đặc biệt, ~119), "
                    "IPM VN (bản sưu tầm, ~110) y yaakz TH (box sets, ~47). "
                    "Correr cada perfil por separado con --bootstrap-wiki "
                    "jd-intl|spp-tw|kimdong|ipm|yaakz."
                ),
                "values": {
                    "--bootstrap-wiki": "jd-intl",
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
            # Sincronizado con manga_watch.py:9727 (choices reales del argparse).
            # Si agregás una wiki nueva, agregala en AMBOS lados o el test AST
            # de tests/test_script_registry.py va a fallar (1.3, 2026-07-08).
            _flag("--bootstrap-wiki", "Wiki a importar",
                  "Elegí qué wiki recorrer. Cada una cubre un país/idioma.",
                  type="choice", default="listadomanga",
                  choices=["listadomanga", "listadomanga-blog", "whakoom",
                           "manga-sanctuary", "otaku-calendar", "manga-mexico",
                           "mangavariant", "socialanime", "blogbbm",
                           "booksprivilege", "sumikko",
                           "listadomanga-collections", "mangapassion",
                           "animeclick", "prhcomics", "kinokuniya", "yenpress",
                           "shueisha", "viz", "sevenseas", "kodansha-us",
                           "jd-intl", "spp-tw", "kimdong", "ipm", "yaakz"]),
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
            # Excepción tácita (2.4): la mayoría de los bool arrancan en False
            # (opt-in explícito); --fetch-details default=True a propósito —
            # sin detalle un bootstrap deja items sin portada/autor/ISBN, así
            # que el toggle nace pre-marcado como "Normal" en scrape (arriba).
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
        "mutates_items": True,
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
        "mutates_items": False,
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
                "values": {"--embed": True},
            },
            {
                "id": "clear",
                "label": "🧹 Vaciar (volver a fetch dinámico)",
                "desc": "Quita los datos embebidos. El HTML vuelve a leer via fetch.",
                "values": {"--clear": True},
            },
        ],
        "flags": [
            # Bug encontrado durante 6/2026-07-08: este preset mandaba
            # "values": {} — el bug 1.1 (flags→values) lo hacía invisible,
            # pero el flag --embed tampoco existía en el registry. Sin
            # --embed el script deja el embed vacío (comportamiento default),
            # así que el preset "Embeber" no embebía nada. Corregido junto
            # con la exposición del flag.
            _flag("--embed", "Embeber catálogo completo en el HTML",
                  "Mete todos los items dentro de web/index.html para que "
                  "funcione con doble-click (file://) sin server. Por "
                  "defecto el embed queda vacío y la página usa fetch() en "
                  "vivo (decisión #5, ver docs/reference/dashboard.md).",
                  type="bool", default=False),
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
            _flag("--force", "Saltar el gate de validate_corpus",
                  "Construye igual aunque --input tenga violaciones "
                  "estructurales DURAS. Override consciente — el pipeline "
                  "canónico (scrape_delta/full) NO usa este flag, tiene su "
                  "propio gate + cuarentena/restore. Solo para invocación "
                  "manual deliberada.",
                  type="bool", default=False, advanced=True),
        ],
    },

    # =====================================================================
    # MANTENIMIENTO (retrofits)
    # =====================================================================
    {
        "id": "filter_non_manga",
        "mutates_items": True,
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
        "mutates_items": True,
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
        "id": "restore_official_titles",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "📛",
        "name": "Restaurar títulos oficiales",
        "tagline": "title = nombre oficial scrapeado (migración one-shot).",
        "what": (
            "Migración de la política de títulos 2026-06-12: restaura el "
            "título oficial (title_original limpio) en items que el skill de "
            "standardize había renombrado/traducido, y retira el campo "
            "title_standardized. Marca cada item procesado "
            "(title_restored_at) y nunca lo re-procesa, así que re-correrla "
            "es seguro y normalmente no hace nada. Después de aplicar, "
            "correr el enforcer de listadomanga."
        ),
        "when": (
            "Ya se corrió sobre todo el corpus (2026-06-12). Solo volver a "
            "correrla si aparecen items viejos restaurados de un backup."
        ),
        "command": [PYTHON, "scripts/retrofit/restore_official_titles.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Cuenta cuántos restauraría sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Restaurar",
                "desc": "Aplica con backup y marca los items.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Cuenta cuántos títulos restauraría sin guardar nada.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "extract_store_bonus",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🎁",
        "name": "Separar bonus de tienda",
        "tagline": "Mueve el 店舗特典 del título al campo store_bonus.",
        "what": (
            "Los retailers japoneses pegan su bonus de compra en el título "
            "oficial — '(…ポストカード)【楽天ブックス限定特典】'. Eso no es el nombre "
            "del producto: lo separa al campo store_bonus (visible solo en el "
            "detalle, no en el grid). Conserva intacta la edición real "
            "(特装版/限定版) y el volumen. El scraper ya lo aplica a items nuevos; "
            "este script es para el corpus histórico. Idempotente."
        ),
        "when": (
            "Ya se corrió (2026-06-12, 221 separados). Solo re-correr si "
            "cambia el helper split_store_bonus."
        ),
        "command": [PYTHON, "scripts/retrofit/extract_store_bonus.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Muestra qué separaría sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Separar",
                "desc": "Aplica con backup.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Muestra los títulos que separaría sin guardar nada.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "fix_corrupted_lm_special_titles",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🩹",
        "name": "Arreglar títulos LM corruptos (edición duplicada)",
        "tagline": "Reconstruye desde description los títulos con edición EN+ES duplicada.",
        "what": (
            "Gotcha #93: el skill viejo de standardize tradujo la edición a "
            "inglés y perdió el volumen en algunos tomos de listadomanga "
            "('Pájaro que trina no vuela no Special Edition Edición Especial'). "
            "Reconstruye el título desde el description (collection_title "
            "scrapeado con su nº y la edición en español) reusando "
            "normalize_display_title — restaura el volumen y deja un solo "
            "marcador. Idempotente (tras correrlo el título ya no matchea)."
        ),
        "when": (
            "Ya se corrió sobre todo el corpus (2026-06-13, 18 items). Solo "
            "volver a correrla si reaparecen items con edición en inglés en el "
            "título (ej. restaurados de un backup viejo)."
        ),
        "command": [PYTHON, "scripts/retrofit/fix_corrupted_lm_special_titles.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Muestra los títulos que reconstruiría sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Reconstruir",
                "desc": "Aplica con backup y consolida.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Muestra los cambios sin guardar nada.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "restore_mistranslated_especial",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🌐",
        "name": "Restaurar edición mal traducida",
        "tagline": "Deshace 'Special Edition'→'Edición Especial' en títulos no españoles.",
        "what": (
            "Gotcha #94: el viejo format_especial_title traducía la edición "
            "inglesa a español sobre títulos no españoles, dejándolos mezclados "
            "('葬送のフリーレン 15 Edición Especial'). Restaura title = "
            "clean_title(title_original) — el nombre oficial scrapeado. Excluye "
            "listadomanga (title_original corrupto, se arregla aparte) y la firma "
            "de corrupción 'no Special/Fanbook'. Idempotente."
        ),
        "when": (
            "Ya se corrió sobre todo el corpus (2026-06-13, 85 items). El fix de "
            "mecanismo (la regex sólo matchea español) evita reincidencia."
        ),
        "command": [PYTHON, "scripts/retrofit/restore_mistranslated_especial.py"],
        "presets": [
            {"id": "dryrun", "label": "🧪 Prueba",
             "desc": "Muestra los títulos que restauraría sin escribir.",
             "values": {"--dry-run": True}},
            {"id": "apply", "label": "✅ Restaurar",
             "desc": "Aplica con backup y consolida.", "values": {}},
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba", "Muestra los cambios sin guardar.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "remove_phantom_calendar_editions",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "👻",
        "name": "Borrar ediciones fantasma del calendario",
        "tagline": "Quita especiales inventados + fotos del bonus de otro tomo.",
        "what": (
            "Gotcha #99: el módulo plano del calendario + la estandarización (LLM) "
            "inventaban una Edición Especial/Artbook que NO existe en la página real "
            "de ListadoManga y le pegaban la foto de un extra (cofre/posavasos/"
            "miniartbook) de OTRO volumen — caso 'Edens Zero Especial 23'. Borra los "
            "fantasmas verificados (guarda: sólo fuente única 'ListadoManga (calendario)' "
            "y no aprobados) y quita las fotos robadas. Listas EXPLÍCITAS verificadas a "
            "mano contra la página viva (el cruce calendario-vs-colecciones tiene falsos "
            "positivos). Con backup, idempotente."
        ),
        "when": (
            "Ya se corrió (2026-06-14: 5 fantasmas + 2 fotos). La guarda durable es el "
            "invariante STOLENIMG de validate_corpus.py."
        ),
        "command": [PYTHON, "scripts/retrofit/remove_phantom_calendar_editions.py"],
        "presets": [
            {"id": "dryrun", "label": "🧪 Prueba",
             "desc": "Muestra qué borraría/arreglaría sin escribir.",
             "values": {"--dry-run": True}},
            {"id": "apply", "label": "✅ Limpiar",
             "desc": "Aplica con backup.", "values": {}},
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba", "Muestra los cambios sin guardar.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "remove_free_preview_editions",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🎟️",
        "name": "Borrar folletos promocionales gratuitos",
        "tagline": "Quita los 'Número Gratuito' de ListadoManga colados como especial.",
        "what": (
            "Gotcha #103: ListadoManga titula '(Especial)' a folletos que la editorial "
            "REGALA (preview del 1er capítulo, mini-artbook, avance bundleado con un "
            "videojuego). No son ediciones comprables. La señal viva es la línea de precio "
            "'Número Gratuito' (vs '9,98 €'). Borra (a) los que tienen 'Número Gratuito' en "
            "la description (parser de colecciones) y (b) los legacy del calendario en "
            "colecciones free-preview verificadas por fetch. Guarda: nunca borra aprobados. "
            "Con backup, idempotente."
        ),
        "when": (
            "Ya se corrió (2026-06-14: 13 borrados). La prevención durable es "
            "FREE_PRICE_PATTERN en listadomanga_collections.py (delta + full)."
        ),
        "command": [PYTHON, "scripts/retrofit/remove_free_preview_editions.py"],
        "presets": [
            {"id": "dryrun", "label": "🧪 Prueba",
             "desc": "Muestra qué borraría sin escribir.",
             "values": {"--dry-run": True}},
            {"id": "apply", "label": "✅ Limpiar",
             "desc": "Aplica con backup.", "values": {}},
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba", "Muestra los cambios sin guardar.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "clean_titles",
        "mutates_items": True,
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
        "id": "normalize_release_dates",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "📅",
        "name": "Normalizar fechas de lanzamiento",
        "tagline": "Convierte release_date legacy (DD/MM/YYYY) a ISO.",
        "what": (
            "Normaliza release_date a formato ISO (YYYY-MM-DD). Por defecto "
            "convierte solo la familia DD/MM/YYYY (día primero, rangos "
            "validados); YYYY y YYYY-MM se respetan como granularidad parcial "
            "legítima. Los demás formatos se reportan sin tocar. Es seguro "
            "correrlo varias veces."
        ),
        "when": (
            "Si el reporte de formatos muestra fechas legacy en el corpus "
            "(p.ej. tras restaurar un backup viejo). Los scrapes nuevos ya "
            "entran normalizados."
        ),
        "command": [PYTHON, "scripts/retrofit/normalize_release_dates.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Reporta qué cambiaría sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Normalizar",
                "desc": "Aplica la normalización con backup.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Reporta qué fechas cambiarían sin guardar nada.",
                  type="bool", default=False),
            _flag("--all-formats", "Todos los formatos",
                  "Además de DD/MM/YYYY normaliza fechas japonesas (年月日), "
                  "datetime de tienda (YYYY/MM/DD hh:mm:ss) y mes textual.",
                  type="bool", default=False, advanced=True),
            _flag("--include-approved", "Incluir aprobados",
                  "Procesa también los items aprobados (golden records).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "fix_product_types",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🏷️",
        "name": "Re-derivar product_type fuera de enum",
        "tagline": "Arregla product_type='special'/'deluxe'/'variant' (eso va en edition_key, no acá).",
        "what": (
            "Re-deriva product_type con derive_product_type() (título + "
            "descripción + signal_types) para items cuyo valor no pertenece "
            "al enum manga/artbook/fanbook/guidebook/boxset/novel/magazine/"
            "audiobook — resabio de la estandarización vieja que confundía "
            "el TIPO de edición con el TIPO de producto. Si la re-derivación "
            "también cae fuera del enum, usa 'manga' como fallback. Es "
            "seguro correrlo varias veces."
        ),
        "when": (
            "Si validate_corpus.py reporta violaciones PTYPE_ENUM (product_type "
            "fuera del enum). Los scrapes/estandarizaciones nuevas ya validan "
            "contra el enum (standardize_apply.py) y no lo generan de nuevo."
        ),
        "command": [PYTHON, "scripts/retrofit/fix_product_types.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Cuenta cuántos cambiarían sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Arreglar",
                "desc": "Aplica la re-derivación con backup.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Cuenta cuántos product_type cambiarían sin guardar nada.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Procesa también los items aprobados (golden records).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "normalize_languages",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🌐",
        "name": "Normalizar idioma al canon español",
        "tagline": "'Deutsch'/'English'/'ja'/'en'/… → 'Alemán'/'Inglés'/'Japonés'/…",
        "what": (
            "Normaliza el campo language al set canónico en ESPAÑOL del "
            "proyecto (los 14 idiomas) usando un mapa de sinónimos explícito "
            "(nombres en inglés, códigos ISO-639-1 sueltos, y 'Deutsch' de "
            "mangapassion). Valores sin mapeo conocido quedan intactos y se "
            "reportan agrupados — nunca inventa un idioma. Es seguro "
            "correrlo varias veces."
        ),
        "when": (
            "Si validate_corpus.py reporta violaciones LANG_ENUM (language "
            "fuera del canon). Los scrapes nuevos de mangapassion ya entran "
            "con 'Alemán' desde el fix de _virtual_source()."
        ),
        "command": [PYTHON, "scripts/retrofit/normalize_languages.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Reporta qué cambiaría sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Normalizar",
                "desc": "Aplica la normalización con backup.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Reporta qué language cambiarían sin guardar nada.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Procesa también los items aprobados (golden records).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "queue_regular_shielded",
        "mutates_items": False,
        "category": "Mantenimiento",
        "icon": "🚩",
        "name": "Encolar tomos regulares sospechosos",
        "tagline": "Items estandarizados con pinta de tomo regular sin bonus → cola de revisión.",
        "what": (
            "Detecta items ya estandarizados (standardized_at) cuyo "
            "edition_key/edition_display tiene pinta de tomo REGULAR ('-regular-' "
            "o 'Regular') pero SIN ninguna señal de bonus/extra (sin "
            "store_bonus, sin signal_types='bonus') — posible mala "
            "clasificación aguas arriba. NO borra ni reclasifica nada: solo "
            "encola a data/unmapped_series.jsonl (reason "
            "'regular_shielded_review') para revisión manual o del skill de "
            "standardize. Por defecto solo LISTA/cuenta; --apply escribe la cola."
        ),
        "when": (
            "Después de una estandarización grande, para chequear que no se "
            "colaron tomos sin extras reales al catálogo de coleccionables."
        ),
        "command": [PYTHON, "scripts/retrofit/queue_regular_shielded.py"],
        "presets": [
            {
                "id": "list",
                "label": "🧪 Listar",
                "desc": "Cuenta y lista los candidatos sin escribir la cola.",
                "values": {},
            },
            {
                "id": "apply",
                "label": "✅ Encolar",
                "desc": "Escribe los candidatos a unmapped_series.jsonl.",
                "values": {"--apply": True},
            },
        ],
        "flags": [
            _flag("--apply", "Encolar de verdad",
                  "Escribe a data/unmapped_series.jsonl. Sin este flag solo lista.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Encola también items aprobados (golden records).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "normalize_isbn",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🔢",
        "name": "Normalizar ISBN",
        "tagline": "Limpia prefijos basura del ISBN (ej. '： ' fullwidth en fuentes JP).",
        "what": (
            "Aplica normalize_isbn() sobre el campo isbn de todos los items: "
            "conserva solo dígitos y X (x→X) y descarta prefijos/sufijos basura "
            "—el más común es el '： ' (dos puntos fullwidth) que las fuentes JP "
            "dejan pegado. Ese prefijo degrada el dedup por ISBN. Los scrapes "
            "nuevos ya entran normalizados; esto limpia el corpus histórico. Es "
            "seguro correrlo varias veces (idempotente)."
        ),
        "when": (
            "Una vez, sobre el corpus histórico. Los items ingresados después "
            "del fix de ingestión ya vienen limpios."
        ),
        "command": [PYTHON, "scripts/retrofit/normalize_isbn.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Prueba",
                "desc": "Cuenta cuántos ISBN cambiarían sin escribir.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Normalizar",
                "desc": "Aplica la normalización con backup.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Modo prueba",
                  "Cuenta cuántos ISBN cambiarían sin guardar nada.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Procesa también los items aprobados (golden records).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "clean_descriptions",
        "mutates_items": True,
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
        "mutates_items": True,
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
            # --include-approved e --include-standardized existen en el argparse
            # real pero se dejan AFUERA del registry a propósito (3.1, 2026-07-08):
            # --include-standardized es el guard-rail de la gotcha #61 (rescorear
            # un item ya estandarizado pisa señales curadas por el skill/LLM);
            # --include-approved protege golden records. Exponerlos en el panel
            # facilitaría saltear ambos guards sin querer.
        ],
    },

    {
        "id": "backfill_metadata",
        "mutates_items": True,
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
            # choices SIN "" a propósito: "" == default="" del script real
            # (rellena TODOS los campos); build_command ya omite el flag
            # cuando el valor es "" (elif t == "choice": if not sval: continue),
            # así que agregar "" a choices no es necesario y no matchea el
            # argparse real (choices=BACKFILL_FIELDS, sin la cadena vacía).
            _flag("--only", "Solo este campo",
                  "Si querés rellenar solo uno: image_url, author, isbn, "
                  "release_date, o images (carrusel multi-imagen). Vacío = "
                  "todos los campos.",
                  type="choice", default="",
                  choices=["image_url", "author", "isbn", "release_date", "images"]),
            _flag("--limit", "Máx items a procesar",
                  "0 = sin límite. Útil para probar con --limit 50.",
                  type="int", default=0, placeholder="50"),
            _flag("--max-per-source", "Máx items por fuente",
                  "0 = sin límite. Evita martillar a una sola tienda.",
                  type="int", default=0, advanced=True),
            _flag("--sleep", "Pausa entre requests (seg)",
                  "Default 0.3.",
                  type="float", default=0.3, advanced=True),
            # El argparse real es action="append" SIN split interno de comas
            # (2.4, 2026-07-08) — "csv_multi" emite un --skip-domain por
            # cada dominio, ahora sí soporta varios desde el panel.
            _flag("--skip-domain", "Saltar estos dominios (CSV)",
                  "Match por substring contra la URL del item. Podés poner "
                  "varios separados por coma.",
                  type="csv_multi", default="", advanced=True,
                  placeholder="darkhorse.com,otrodominio.com"),
            _flag("--dry-run", "Modo prueba (no fetchea)",
                  "Solo cuenta cuántos serían candidatos.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "backfill_animeclick_details",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🇮🇹",
        "name": "Backfill AnimeClick (fecha, descripción)",
        "tagline": "Rellena release_date / description en items AnimeClick que quedaron vacíos.",
        "what": (
            "Cuando se ingestaron los items de AnimeClick sin buscar el "
            "detalle de cada edición, los campos release_date y "
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
                "id": "dryrun",
                "label": "🔬 Dry-run (ver cuántas hay)",
                "desc": "Cuenta cuántas imágenes calificarían sin upscalear nada.",
                "values": {"--dry-run": True},
            },
            {
                "id": "test",
                "label": "🔬 Test rápido (20 imágenes)",
                "desc": "Upscalea sólo 20 imágenes para validar el resultado.",
                "values": {"--limit": 20},
            },
            {
                "id": "todo",
                "label": "🔬 Todo (< 200 000 px)",
                "desc": "Upscalea todas las imágenes por debajo del umbral.",
                "values": {"--max-pixels": 200000},
            },
        ],
        "flags": [
            _flag("--max-pixels", "Umbral de píxeles",
                  "Solo procesa imágenes con menos de N píxeles totales. "
                  "200 000 ≈ 450×445 px. Subir para procesar más imágenes.",
                  type="int", default=200000, placeholder="200000"),
            # --scale es type=int con choices=[2, 4] en el argparse real (no
            # strings) — 2.4, 2026-07-08. Usa el flag "int" con choices para
            # que build_command valide y castee coherente con el script.
            _flag("--scale", "Factor de escala",
                  "Multiplicar las dimensiones por este factor (2 o 4). "
                  "Default 2: una imagen de 150×220 pasa a ~300×440 px.",
                  type="int", default=2, choices=[2, 4]),
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
        "mutates_items": True,
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
            _flag("--retry-empty", "Reintentar traducciones vacías fallidas",
                  "Reprocesa SOLO los campos con description_es='' cuya "
                  "description NO detecta como español — recupera fallos de "
                  "API marcados por error como 'ya está en español'. Nunca "
                  "toca items aprobados (golden records); no re-traduce lo "
                  "ya traducido.",
                  type="bool", default=False, advanced=True),
            _flag("--dry-run", "Modo prueba",
                  "Solo muestra qué se traduciría. No llama a la API.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "fetch_better_covers",
        "mutates_items": True,
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
            "Verificación (endurecida 2026-07-08): identidad AND-gate — aHash Hamming ≤ "
            "--max-hash-dist (default 6/64) + dHash≤8 + pHash≤8 + NCC≥0.90 — y un gate de "
            "entropía/detalle que descarta candidatas 'blandas' (escaneos sobre-comprimidos "
            "o upscales que ganan píxeles pero pierden nitidez). "
            "SEGURO POR DEFECTO (2026-06-03): NO reemplaza ninguna portada automáticamente — todas las "
            "candidatas van a cover-preview.html para tu aprobación manual; el item conserva su portada "
            "vieja hasta que apruebes. Solo busca imágenes que realmente lo necesitan (debajo de --min-pixels). "
            "Con --apply, las de ALTA confianza (CDN/ISBN hash-verificadas) se aplican directo; la baja "
            "confianza NUNCA se auto-aplica. Aprobás en la página → corrés con --apply-preview."
        ),
        "when": (
            "Después de upgrade_image_resolution.py. Cuando hay items con imagen < 90 000 px "
            "sin versión hi-res en el servidor origen (típico: AnimeClick IT, ListadoManga ES). "
            "Correr primero con --dry-run para estimar. "
            "Requiere: pip install Pillow. "
            "APIs opcionales en .env: SERPER_API_KEY (2 500 gratis, sin tarjeta) o TAVILY_API_KEY (1 000/mes)."
        ),
        "command": [PYTHON, "scripts/retrofit/fetch_better_covers.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🔍 Dry-run (ver candidatos)",
                "desc": "Lista candidatas sin descargar ni escribir preview. NO consume cuota API.",
                "values": {"--dry-run": True, "--limit": 30, "--verbose": True},
            },
            {
                "id": "cdn_only",
                "label": "🔍 Solo CDN + OpenLibrary (sin web search)",
                "desc": "Sólo lookups determinísticos por ISBN, sin gastar cuota de Serper/Tavily.",
                "values": {"--no-search": True},
            },
            {
                "id": "buscar",
                "label": "🔍 Buscar y mandar a preview (no aplica nada)",
                "desc": "Corrida real: busca candidatas y las manda a cover-preview.html para tu aprobación.",
                "values": {},
            },
            {
                "id": "apply_preview",
                "label": "✅ Aplicar aprobadas del preview",
                "desc": "Aplica a items.jsonl las candidatas que ya aprobaste en cover-preview.html.",
                "values": {"--apply-preview": True},
            },
        ],
        "flags": [
            # min-pixels/max-hash-dist DEBEN coincidir con LOW_QUALITY_PX /
            # DEFAULT_MAX_HASH_DIST de fetch_better_covers.py (2.1/2.2,
            # 2026-07-08): un default más laxo acá DEBILITA el gate de
            # covers recién endurecido en cada corrida desde el panel.
            _flag("--min-pixels", "Umbral de calidad baja (px)",
                  "Items con imagen de menos de N píxeles totales son candidatos. "
                  "Default 90 000 ≈ 300×300 px (mismo umbral que el Panel de Calidad).",
                  type="int", default=90000, placeholder="90000"),
            _flag("--min-gain", "Ganancia mínima requerida (×)",
                  "La candidata debe tener al menos N× más píxeles que la imagen actual. "
                  "Default 1.5: si la actual tiene 30 000 px, la candidata debe tener ≥ 45 000 px.",
                  type="float", default=1.5, placeholder="1.5"),
            _flag("--max-hash-dist", "Distancia hash máxima del aHash (0-64)",
                  "Cota Hamming del aHash para aceptar la candidata como 'misma portada'. "
                  "0 = imagen idéntica, 64 = completamente diferente. dHash≤8, pHash≤8, "
                  "NCC≥0.90 y el gate de entropía aplican SIEMPRE además de esta cota. "
                  "Default 6 (endurecido 2026-07-08 — eval: old=14 falsos positivos → "
                  "new=0). Valores >6 se honran pero suben el riesgo de falso positivo.",
                  type="int", default=6, placeholder="6"),
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
            # action="append" en el argparse real (script splitea comas por
            # chunk Y soporta --slugs repetido) — "csv_multi" cubre ambos.
            _flag("--slugs", "Acotar a estos slugs (CSV)",
                  "Corre SOLO sobre estos slugs exactos, además de los filtros "
                  "normales de candidatura (un slug sin candidatura real igual "
                  "se saltea). Vacío = todos los candidatos.",
                  type="csv_multi", default="", advanced=True,
                  placeholder="berserk-darkhorse-deluxe-1,naruto-viz-3in1-1"),
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Solo muestra qué se encontraría. No descarga ni modifica archivos.",
                  type="bool", default=False),
            _flag("--verbose", "Mostrar detalle de cada item",
                  "Imprime URL candidata, píxeles y resultado de verificación por item.",
                  type="bool", default=False),
            # --include-approved existe en el argparse real pero se deja
            # AFUERA del registry a propósito (3.1, 2026-07-08): por defecto
            # protege golden records de --apply/--apply-preview; exponerlo en
            # el panel facilitaría pisar una portada aprobada por error.
        ],
    },

    {
        "id": "dedup_carousel_images",
        "mutates_items": True,
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
            {"id": "dryrun", "label": "🖼️ Dry-run (ver qué se quitaría)",
             "desc": "Lista los duplicados que se quitarían sin tocar items.jsonl.",
             "values": {"--dry-run": True}},
            {"id": "apply_lm", "label": "🖼️ Aplicar (solo items con imagen de listadomanga)",
             "desc": "Dedupea sólo items que tienen alguna imagen de listadomanga.",
             "values": {}},
            {"id": "apply_all", "label": "🖼️ Aplicar a TODOS los items",
             "desc": "Revisa el carrusel de TODOS los items con ≥2 imágenes.",
             "values": {"--all": True}},
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
        "id": "purge_placeholder_images",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🚫",
        "name": "Purgar imágenes placeholder / 1×1 / rotas",
        "tagline": "Quita de images[] las fotos que no son portadas reales para que la card muestre el 📚.",
        "what": (
            "Algunas fuentes sirven una imagen genérica cuando NO tienen la carátula: Amazon "
            "devuelve un GIF 1×1, listadomanga/otros CDNs un blanco, Penguin Random House un "
            "'Cover Coming Soon', Funside un 'Immagine non disponibile', SocialAnime un 'Image "
            "coming soon'. Todas terminan espejadas y mostradas como si fueran la portada. Este "
            "retrofit las detecta vía image_store.placeholder_reason() —estructural (1×1, "
            "casi-sólido std<3, archivo roto) + firmas de contenido en "
            "data/placeholder_signatures.json para los placeholders con texto— y las quita de "
            "TODAS las filas. Limpia también sources[].image_local/image_url al mismo archivo, "
            "re-marca la portada por posición y manda los archivos huérfanos a cuarentena "
            "data/images/_orphans/ (reversible). NUNCA inventa imágenes: un item sin fotos muestra "
            "el 📚. Corre como paso [4i] del pipeline (después de dedup_carousel_images)."
        ),
        "when": (
            "Cuando aparecen cards con un placeholder de la fuente (1×1, blanco, 'no disponible') "
            "en vez del 📚. Automático en el pipeline (delta y full); manual con --dry-run primero. "
            "Sin red — lee el espejo local. Requiere: pip install Pillow."
        ),
        "command": [PYTHON, "scripts/retrofit/purge_placeholder_images.py"],
        "presets": [
            {"id": "dryrun", "label": "🚫 Dry-run (ver qué se quitaría)",
             "desc": "Reporta placeholders detectados sin tocar items.jsonl ni mover archivos.",
             "values": {"--dry-run": True}},
            {"id": "apply", "label": "🚫 Aplicar (mueve huérfanos a cuarentena)",
             "desc": "Quita los placeholders y manda los archivos huérfanos a data/images/_orphans/.",
             "values": {}},
            {"id": "apply_keep", "label": "🚫 Aplicar sin mover archivos",
             "desc": "Quita las entries de images[] pero deja los archivos placeholder en disco.",
             "values": {"--keep-files": True}},
        ],
        "flags": [
            _flag("--dry-run", "Solo mostrar, no escribir",
                  "Reporta qué entries se quitarían y cuántos items quedarían sin imagen, "
                  "sin tocar items.jsonl ni mover archivos.",
                  type="bool", default=False),
            _flag("--keep-files", "No mover huérfanos a cuarentena",
                  "Quita las entries de images[] pero deja los archivos placeholder en "
                  "data/images/ en vez de moverlos a _orphans/.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "prune_soft_cover_candidates",
        "mutates_items": False,
        "category": "Mantenimiento",
        "icon": "🩹",
        "name": "Podar candidatas de portada chicas + blandas",
        "tagline": "Quita de la cola de aprobación las portadas con más px pero poco detalle, que se verían pixeladas.",
        "what": (
            "El px count engaña: una candidata con MÁS píxeles que la portada actual puede verse "
            "PEOR (un escaneo sobre-comprimido o upscale tiene más px pero menos detalle real). "
            "Mostrada agrandada en el modal/tarjeta se ve fea y pixelada. Este retrofit re-aplica a "
            "data/cover_preview.json el MISMO gate que ahora bloquea estas candidatas upstream "
            "(fetch_better_covers._is_soft_image: chica < 150k px Y blanda _detail_ratio < 0.115). "
            "Si una entry se queda sin candidatas, la elimina. NUNCA toca items.jsonl —la portada "
            "actual se conserva. Idempotente; backup .bak-prune-soft. Gotcha #94."
        ),
        "when": (
            "1× para limpiar la cola ya armada antes de que existiera el gate. Después de cada "
            "corrida del skill watch-search-covers ya no hace falta (el gate corre inline en la "
            "validación). Sin red — lee el espejo local. Requiere: pip install Pillow."
        ),
        "command": [PYTHON, "scripts/retrofit/prune_soft_cover_candidates.py"],
        "presets": [
            {"id": "dryrun", "label": "🩹 Dry-run (ver qué se quitaría)",
             "desc": "Reporta candidatas chicas+blandas sin tocar cover_preview.json.",
             "values": {"--dry-run": True}},
            {"id": "apply", "label": "🩹 Aplicar",
             "desc": "Poda las candidatas chicas+blandas de la cola de aprobación.",
             "values": {}},
        ],
        "flags": [
            _flag("--dry-run", "Solo mostrar, no escribir",
                  "Reporta qué candidatas chicas+blandas se quitarían y cuántas entries quedarían "
                  "sin candidatas, sin tocar cover_preview.json.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "promote_hires_cover",
        "mutates_items": True,
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
        "id": "sync_cover_preview",
        "mutates_items": False,
        "category": "Mantenimiento",
        "icon": "🔄",
        "name": "Sincronizar cola de portadas candidatas",
        "tagline": "Poda sugerencias obsoletas de cover_preview.json contra el catálogo actual.",
        "what": (
            "La cola cover_preview.json guarda una foto congelada del item al momento "
            "de encolar. El catálogo evoluciona (upgrades, mirror, applies) y la cola "
            "queda desincronizada: sugiere candidatas para portadas que ya están en alta "
            "calidad, o muestra botones de borrar para fotos que ya no existen en el item. "
            "Este script sincroniza: refresca old_url/old_image/old_pixels/current_images "
            "de cada entry, poda candidatas pending cuya premisa ya no existe (portada "
            "ya ≥ 90 000 px, foto target desaparecida/ok, new_url = portada actual), y "
            "elimina entries cuyo slug ya no existe o que quedaron sin candidatas. "
            "Las candidatas approved/rejected nunca se tocan."
        ),
        "when": (
            "El panel /cover-preview.html llama GET /api/cover-preview que lo hace "
            "automáticamente al cargar. Manual: cuando querés auditar la cola sin "
            "abrir el panel, o para correr en --dry-run y ver qué se podaría."
        ),
        "command": [PYTHON, "scripts/retrofit/sync_cover_preview.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🔍 Dry-run (ver qué se podaría sin escribir)",
                "desc": "Muestra los stats sin tocar cover_preview.json.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "🔄 Aplicar",
                "desc": "Sincroniza y persiste la cola limpia.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Solo mostrar, no escribir",
                  "Reporta los stats sin modificar cover_preview.json.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "revalidate_cover_preview",
        "mutates_items": False,
        "category": "Mantenimiento",
        "icon": "🔎",
        "name": "Re-validar candidatas de portada contra el gate endurecido",
        "tagline": "Re-corre el gate _same_cover/_is_soft_image OFFLINE sobre la cola pendiente.",
        "what": (
            "La mayoría de las candidatas PENDING de cover_preview.json vienen de una "
            "versión vieja del skill watch-search-covers que nunca pasó por el gate "
            "endurecido (_same_cover AND-gate + _is_soft_image, overhaul 2026-07-08). "
            "Este script re-valida cada candidata pending SIN red — old_image y "
            "new_image ya están espejados en data/images/ — reusando las funciones "
            "REALES del motor (fetch_better_covers, delegación pura, cero lógica "
            "copiada). Las que pasan quedan 'verified: true' con match_dist poblado "
            "(las decide igual el owner); las que fallan pasan a 'rejected' con "
            "reject_reason='auto_revalidation'. Sin referencia o candidata en disco "
            "→ 'verified: false' (no auto-rechaza, sólo flaggea para revisión humana). "
            "Idempotente: una candidata ya procesada no se reprocesa."
        ),
        "when": (
            "1× para limpiar el backlog de candidatas sin verificar heredado del "
            "skill viejo. Después de cada corrida del skill watch-search-covers ya no "
            "hace falta — valida inline. Sin red, requiere Pillow."
        ),
        "command": [PYTHON, "scripts/retrofit/revalidate_cover_preview.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🔎 Dry-run (default del script)",
                "desc": "Reporta qué cambiaría sin escribir cover_preview.json.",
                "values": {},
            },
            {
                "id": "apply",
                "label": "✅ Aplicar",
                "desc": "Escribe los resultados de la re-validación (backup + atomic).",
                "values": {"--apply": True},
            },
        ],
        "flags": [
            _flag("--apply", "Aplicar de verdad",
                  "El script es dry-run por DEFAULT (mutuamente excluyente con este "
                  "flag en el argparse real) — sin --apply sólo reporta. Con --apply "
                  "escribe cover_preview.json con backup y rotación.",
                  type="bool", default=False),
        ],
    },

    {
        "id": "wayback_recover",
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
        "mutates_items": True,
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
    {
        "id": "backfill_series_aliases",
        "mutates_items": True,
        "category": "Retrofit",
        "icon": "🔗",
        "name": "Backfill de aliases de serie (scope acotado)",
        "tagline": "Remapea series_key/series_display a su canónica según series_aliases.yml.",
        "what": (
            "Aplica data/series_aliases.yml sobre los items indicados vía "
            "canonical_series_key() (fuente única de la resolución de aliases): "
            "remapea series_key/series_display a la forma canónica, re-alinea el "
            "prefijo del edition_key (rebuild_edition_key_prefix), re-deriva "
            "cluster_key y re-consolida con consolidate_by_cluster (la MISMA "
            "primitiva del merge de la ingesta — decisión #1, nada reimplementado). "
            "Salta items aprobados (golden records) por defecto. Idempotente; "
            "backupea items.jsonl antes de escribir."
        ),
        "when": (
            "Lo corre el skill /watch-enrich-series-aliases tras editar el YAML "
            "de aliases. 'Series a remapear' (--only-keys) es OBLIGATORIO: son "
            "EXACTAMENTE los series_key que la corrida del skill procesó. "
            "Correrlo sobre todo el corpus puede colapsar series ajenas — regla "
            "dura de la auditoría post-scrape 2026-07-07 ('backfill de aliases "
            "NUNCA sobre todo el corpus'). Sin ese campo, el script aborta."
        ),
        "command": [PYTHON, "scripts/retrofit/backfill_series_aliases.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra qué cambiaría. Requiere completar 'Series a remapear'.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--only-keys", "Series a remapear (CSV) — OBLIGATORIO",
                  "Lista separada por comas de los series_key EXACTOS a "
                  "remapear (los que la corrida del skill acaba de procesar). "
                  "Sin este campo el script aborta — es el guard contra "
                  "colapsos colaterales de series ajenas.",
                  type="csv", default="",
                  placeholder="atelier-des-sorciers,apothicaire"),
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los remapeos que haría sin modificar items.jsonl.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Remapea también items aprobados (golden records). Por "
                  "defecto se saltean.",
                  type="bool", default=False, advanced=True),
            # --all / --yes-i-know-collateral existen en el argparse real pero
            # NO se exponen en el panel a propósito: son el caso excepcional
            # de CLI para remapear TODO el corpus (doble confirmación textual).
            # Exponerlos como toggles trivializaría un footgun con historial
            # real de colapsos colaterales (regla dura 2026-07-07) — quien lo
            # necesite, que lo escriba a mano en una terminal.
        ],
    },

    {
        "id": "sc_plan",
        "mutates_items": False,
        "category": "Retrofit",
        "icon": "🖼️",
        "name": "Plan de búsqueda de portadas (search-covers, Step 1)",
        "tagline": "Arma la lista de imágenes a buscar + variantes de query. No escribe items.jsonl.",
        "what": (
            "Compila a script el planificador determinista del skill "
            "/watch-search-covers (Step 1, auditoría Fable 2026-07-08, "
            "hallazgo F9): identifica portadas/galería de baja calidad o "
            "ausentes, arma las variantes de query ordenadas (whakoom/yandex/"
            "texto según idioma) y aplica los guards (ya adjudicado en "
            "cover_preview.json, memoria de intentos de 30 días, referencia "
            "degenerada). Escribe SOLO .tmp_sc_plan.json/.tmp_sc_acc.json "
            "(archivos de trabajo del skill) — nunca toca items.jsonl. Correr "
            "desde acá sirve para inspeccionar el plan; el loop de Chrome del "
            "Step 3 sigue siendo del skill (no automatizable)."
        ),
        "when": "Lo invoca el skill /watch-search-covers en su Step 1. Correrlo "
                "manual solo para ver cuántos targets hay sin lanzar el skill.",
        "command": [PYTHON, "scripts/retrofit/sc_plan.py"],
        "presets": [
            {
                "id": "default",
                "label": "🟢 Todas las imágenes pendientes",
                "desc": "Portadas de baja calidad o ausentes (sin galería).",
                "values": {},
            },
            {
                "id": "gallery",
                "label": "🖼️ Solo galería",
                "desc": "Salta portadas; procesa solo fotos de galería (img_idx >= 1).",
                "values": {"--gallery-only": True},
            },
        ],
        "flags": [
            _flag("--limit", "Máximo de targets",
                  "0 = TODAS las imágenes pendientes (default).",
                  type="int", default=0),
            _flag("--slug", "Solo este slug",
                  "Procesa únicamente el item con este slug exacto.",
                  type="str", default="", placeholder="berserk-darkhorse-deluxe-1"),
            _flag("--include-no-image", "Incluir items sin imagen",
                  "Candidatas quedan verified:false (sin referencia para comparar).",
                  type="bool", default=False, advanced=True),
            _flag("--gallery-only", "Solo galería",
                  "Salta portadas (img_idx 0); procesa solo galería.",
                  type="bool", default=False, advanced=True),
            _flag("--include-gallery", "Portadas + galería",
                  "Sin este flag ni --gallery-only, solo se procesan portadas.",
                  type="bool", default=False, advanced=True),
            _flag("--retry-failed", "Ignorar exclusión de 30 días",
                  "Reintenta targets con 0 matches en el último mes.",
                  type="bool", default=False, advanced=True),
            _flag("--query-extra", "Texto extra en cada query",
                  "Se agrega al final de cada variante de búsqueda en Google.",
                  type="str", default="", placeholder="portada oficial",
                  advanced=True),
        ],
    },

    {
        "id": "apply_rarity_verdicts",
        "mutates_items": True,
        "category": "Retrofit",
        "icon": "🟪",
        "name": "Aplicar veredictos de rareza (validate-rarity, Step 3)",
        "tagline": "Aplica los veredictos web (Step 2 del skill) a items.jsonl.",
        "what": (
            "Compila a script el Step 3 del skill /watch-validate-rarity "
            "(auditoría Fable 2026-07-08, hallazgo F5): lee "
            "data/diagnostics/rarity_validation_results.json (veredicto por "
            "group_id), escribe stock_status/stock_checked_at como EVIDENCIA "
            "y re-deriva rarity con derive_rarity_tier() — nunca asigna un "
            "tier a mano. inconclusive no toca nada. Re-selecciona candidatos "
            "con la MISMA rarity_uncertainty_reason() del Step 0/1 (scripts/"
            "audit/rarity_candidates.py) por si el universo cambió entre "
            "selección y aplicación."
        ),
        "when": "Lo invoca el skill /watch-validate-rarity tras la verificación "
                "web (Step 2). Requiere el JSON de resultados ya escrito.",
        "command": [PYTHON, "scripts/retrofit/apply_rarity_verdicts.py"],
        "presets": [
            {
                "id": "apply",
                "label": "✅ Aplicar veredictos",
                "desc": "Lee data/diagnostics/rarity_validation_results.json y actualiza items.jsonl.",
                "values": {},
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
        ],
    },

    {
        "id": "fix_item_fields",
        "mutates_items": True,
        "category": "Retrofit",
        "icon": "✏️",
        "name": "Corregir campos puntuales de un item",
        "tagline": "Mini-helper --url X --set campo=valor. Reemplaza ediciones a mano de review-feedback.",
        "what": (
            "Corrige campos puntuales de UN item (identificado por --url o "
            "--slug) contra una allowlist (series_key/series_display/"
            "edition_key/edition_display/volume/product_type/rarity/country/"
            "publisher/language/isbn/stock_status/description) más el campo "
            "sintético cover_url (delega en image_store.set_cover, categoría "
            "K wrong_image). 'title' está BLOQUEADO salvo --allow-title explícito (política de títulos, "
            "gotcha #92 — el title es el nombre OFICIAL, nunca se renombra a "
            "mano). Re-deriva cluster_key si el cambio tocó uno de sus "
            "insumos (edition_key/volume/country/publisher/title/url, gotcha "
            "#55). Reemplaza los snippets K/M embebidos del skill "
            "/watch-review-feedback (auditoría Fable 2026-07-08, hallazgo F12)."
        ),
        "when": "Al aplicar una corrección puntual de review-feedback (categorías "
                "K/L/M/N) o cualquier fix manual de un item específico.",
        "command": [PYTHON, "scripts/retrofit/fix_item_fields.py"],
        "presets": [
            {
                "id": "dryrun",
                "label": "🧪 Preview (no escribe)",
                "desc": "Muestra qué cambiaría. Completá URL y al menos un campo.",
                "values": {"--dry-run": True},
            },
        ],
        "flags": [
            _flag("--url", "URL exacta del item",
                  "Identifica el item a editar por su URL.",
                  type="str", default="", placeholder="https://tienda.com/producto"),
            _flag("--slug", "slug exacto del item (alternativa a URL)",
                  "Identifica el item a editar por su slug.",
                  type="str", default="", placeholder="berserk-darkhorse-deluxe-1"),
            _flag("--set", "Campo a corregir (field=value)",
                  "Repetible: agregá una fila por cada campo a cambiar.",
                  type="csv_multi", default="",
                  placeholder="series_key=berserk"),
            _flag("--allow-title", "Permitir editar 'title'",
                  "Bloqueado por default (política de títulos, gotcha #92). "
                  "Solo para basura real de scraping, nunca para renombrar.",
                  type="bool", default=False, advanced=True),
            _flag("--dry-run", "Modo prueba (no escribe)",
                  "Muestra los cambios que aplicaría sin modificar items.jsonl.",
                  type="bool", default=False),
            # --include-approved existe en el argparse real pero NO se expone
            # acá a propósito (protege golden records de ediciones puntuales
            # lanzadas desde el panel — mismo criterio que backfill_series_aliases).
        ],
    },

    # =====================================================================
    # AUDITORÍA
    # =====================================================================
    {
        "id": "source_health",
        "mutates_items": False,
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
            _flag("--mode", "Modo del run (para el baseline)",
                  "delta o full — compara el yield contra la mediana "
                  "histórica del MISMO modo (delta-vs-delta, full-vs-full). "
                  "Vacío = se infiere del run más reciente. Sólo tiene "
                  "efecto junto con 'Alertar regresión de yield'.",
                  type="choice", default="", choices=["delta", "full", "other"],
                  advanced=True),
            _flag("--baseline-alert", "Alertar regresión de yield",
                  "Compara el yield del run actual contra la mediana "
                  "histórica del mismo modo (ver logs/metrics.jsonl) y "
                  "reporta fuentes que cayeron a menos de la mitad.",
                  type="bool", default=False, advanced=True),
        ],
    },
    {
        "id": "data_quality",
        "mutates_items": False,
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
    {
        "id": "split_edition_buckets",
        "mutates_items": False,
        "category": "Auditoría",
        "icon": "🔀",
        "name": "Ediciones sospechosas de partirse solo por el tipo",
        "tagline": "Reporte de candidatas a duplicado por slug de tipo inconsistente. Solo lectura.",
        "what": (
            "Agrupa filas fuera de listadomanga por (serie, país, volumen) y "
            "aísla los casos donde 2+ edition_keys tienen EXACTAMENTE el mismo "
            "prefijo serie+editorial+país y sólo difieren en el slug de TIPO "
            "(special/limited/collector/deluxe/ultimate/perfect/master/boxset/"
            "variant/cofanetto…). Por cada caso muestra los edition_keys, sus "
            "fuentes, si comparten ISBN (señal fuerte de duplicado real) y un "
            "título de muestra. NO fusiona nada — el auto-merge fue vetado "
            "(deluxe y regular, por ejemplo, NO son el mismo producto); esto "
            "es evidencia para revisión humana."
        ),
        "when": (
            "Cuando quieras revisar candidatas a duplicado que "
            "consolidate_sources no agarra (cluster_key ya distinto a "
            "propósito). Los buckets con ISBN compartido son la señal más "
            "confiable — priorizalos."
        ),
        "command": [PYTHON, "scripts/audit/split_edition_buckets.py"],
        "presets": [
            {
                "id": "resumen",
                "label": "📋 Resumen (stdout)",
                "desc": "Imprime el resumen; los buckets con ISBN compartido siempre completos.",
                "values": {},
            },
            {
                "id": "json",
                "label": "🧾 Reporte JSON completo",
                "desc": "Guarda TODOS los buckets a un archivo para revisión offline.",
                "values": {"--json": "data/diagnostics/split-edition-buckets.json"},
            },
        ],
        "flags": [
            _flag("--examples", "Buckets sin ISBN a mostrar (stdout)",
                  "Cuántos buckets SIN isbn compartido imprimir en pantalla. "
                  "Los que SÍ comparten ISBN siempre se listan todos.",
                  type="int", default=20, advanced=True),
            _flag("--json", "Guardar reporte completo a archivo",
                  "Si lo dejás vacío, sólo imprime en pantalla. Si ponés una "
                  "ruta, guarda ahí el JSON con TODOS los buckets.",
                  type="str", default="",
                  placeholder="data/diagnostics/split-edition-buckets.json",
                  advanced=True),
        ],
    },

    {
        "id": "rarity_candidates",
        "mutates_items": False,
        "category": "Auditoría",
        "icon": "🟪",
        "name": "Candidatos de rareza por incertidumbre (validate-rarity, Step 0/1)",
        "tagline": "Selecciona y prioriza los 'rare' que necesitan verificación web. Solo lectura.",
        "what": (
            "Compila a script el Step 0/1 del skill /watch-validate-rarity "
            "(auditoría Fable 2026-07-08, hallazgo F5): selecciona items "
            "rarity='rare' cuya rareza viene de INCERTIDUMBRE (retailer_"
            "exclusive sin stock verificado, o fuente de referencia sin otra "
            "evidencia) — no los que tienen evidencia estructural. "
            "rarity_uncertainty_reason() es la ÚNICA implementación del "
            "tracer (antes duplicado 2 veces en el SKILL.md); un test de "
            "coherencia fija que replica el orden real de "
            "derive_rarity_tier(). Agrupa por edition_key, prioriza "
            "retailer_exclusive + mercados occidentales, y escribe el JSON a "
            "data/diagnostics/rarity_validation_candidates.json."
        ),
        "when": "Lo invoca el skill /watch-validate-rarity en su Step 0/1. "
                "Correrlo manual solo para ver cuántos candidatos hay.",
        "command": [PYTHON, "scripts/audit/rarity_candidates.py"],
        "presets": [
            {
                "id": "text",
                "label": "📋 Texto (default)",
                "desc": "Lista legible en pantalla + escribe el JSON de candidatos.",
                "values": {},
            },
            {
                "id": "json",
                "label": "🧾 JSON puro (stdout)",
                "desc": "Para procesamiento programático.",
                "values": {"--output": "json"},
            },
        ],
        "flags": [
            _flag("--limit", "Tope de ediciones a priorizar",
                  "Default 40. 0 = sin tope.",
                  type="int", default=40),
            _flag("--output", "Formato de stdout",
                  "text = legible; json = para máquina.",
                  type="choice", default="text", choices=["text", "json"]),
        ],
    },

    {
        "id": "purge_false_artbook_residuals",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🖼️",
        "name": "Desblindar falsos artbook (calendario legacy)",
        "tagline": "Tomos regulares marcados artbook/boxset por el bug viejo de 'category' inyectada.",
        "what": (
            "Detecta residuos del bug (pre-2026-05-23) del calendario legacy de "
            "ListadoManga que inyectaba la 'category' del día ('Artbook'...) en la "
            "description de items cercanos, marcando tomos REGULARES como "
            "product_type=artbook/boxset (Chainsaw Man 1, Black Butler 27, Fire "
            "Force 9, Tokyo Ghoul:re 14, etc.). Blast radius acotado: "
            "product_type∈{artbook,boxset} + standardized_at + edition_key/display "
            "con pinta de Regular + signal_types==['artbook'] SOLO + título SIN "
            "keyword real de artbook. NO borra ni reclasifica: sólo remueve "
            "standardized_at (desblindar) para que rescore.py + filter_collectible.py "
            "los reevalúen y expulsen en la próxima corrida. Por defecto solo "
            "LISTA/cuenta; sin --dry-run escribe de verdad."
        ),
        "when": (
            "One-shot, tras la auditoría post-scrape 2026-07-07 (GRUPO 2). Correr "
            "también si reaparecen residuos similares de una fuente que inyecta "
            "'category' como signal."
        ),
        "command": [PYTHON, "scripts/retrofit/purge_false_artbook_residuals.py"],
        "presets": [
            {
                "id": "dry-run",
                "label": "🧪 Dry-run",
                "desc": "Cuenta y lista los candidatos sin escribir nada.",
                "values": {"--dry-run": True},
            },
            {
                "id": "apply",
                "label": "✅ Desblindar",
                "desc": "Remueve standardized_at de los candidatos.",
                "values": {},
            },
        ],
        "flags": [
            _flag("--dry-run", "Solo listar",
                  "No escribe nada, sólo reporta los candidatos.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Desblinda también items aprobados (golden records).",
                  type="bool", default=False, advanced=True),
        ],
    },

    {
        "id": "purge_op_import_foreign",
        "mutates_items": True,
        "category": "Mantenimiento",
        "icon": "🏴‍☠️",
        "name": "Purgar residuos ajenos del import de One Piece",
        "tagline": "Series ajenas coladas por ISBN mal resuelto en el import manual de One Piece.",
        "what": (
            "Detecta items con source 'Research import (One Piece ...)' (import "
            "manual one-shot, scripts/import_op_remix.py / fix_op_special_vols.py) "
            "cuyo título/title_original NO referencia a One Piece (keywords: 'one "
            "piece', 'ワンピース', '尾田') — ~11 series ajenas coladas por un ISBN mal "
            "resuelto (地獄楽, RURIDRAGON, 青の祓魔師, etc.). Con --apply: remueve "
            "standardized_at (desblindar, mismo mecanismo que GRUPO 2) Y encola a "
            "data/unmapped_series.jsonl (reason 'op_import_foreign') para curación "
            "manual — dato corrompido (título/ISBN no coinciden entre sí), así que "
            "la expulsión determinista es best-effort y un humano debe confirmar. "
            "Por defecto solo LISTA/cuenta."
        ),
        "when": (
            "One-shot, tras la auditoría post-scrape 2026-07-07 (GRUPO 3). La "
            "prevención estructural (op_series_guard.py) ya evita que un re-run de "
            "los scripts de import vuelva a colar series ajenas."
        ),
        "command": [PYTHON, "scripts/retrofit/purge_op_import_foreign.py"],
        "presets": [
            {
                "id": "list",
                "label": "🧪 Listar",
                "desc": "Cuenta y lista los candidatos sin escribir nada.",
                "values": {},
            },
            {
                "id": "apply",
                "label": "✅ Desblindar + encolar",
                "desc": "Remueve standardized_at y encola a unmapped_series.jsonl.",
                "values": {"--apply": True},
            },
        ],
        "flags": [
            _flag("--apply", "Aplicar de verdad",
                  "Desblinda + encola. Sin este flag solo lista.",
                  type="bool", default=False),
            _flag("--include-approved", "Incluir aprobados",
                  "Procesa también items aprobados (golden records).",
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


def mutates_items(script_id: str) -> bool:
    """True si el script puede escribir data/items.jsonl.

    Lo usan serve.py/admin_serve.py para el 409 de S10 (dos mutadores del
    Panel corriendo a la vez se pisan sin lock de archivo, gotcha A12/S10)."""
    s = SCRIPTS_BY_ID.get(script_id)
    return bool(s and s.get("mutates_items"))


# ---------------------------------------------------------------------------
# Construcción del comando desde flags — FUENTE ÚNICA (4.1, 2026-07-08).
#
# Vivía duplicado byte-a-byte en serve.py y admin_serve.py (60 líneas, ya
# habían divergido: sólo la copia de admin_serve.py sabía castear "choice").
# Ambos servers ahora importan build_command/resolve_preset_env de acá.
# ---------------------------------------------------------------------------

def build_command(
    script_id: str, flag_values: dict[str, Any]
) -> tuple[list[str], str] | tuple[None, str]:
    """Valida flags y devuelve (argv, label) o (None, mensaje_error)."""
    spec = get_script(script_id)
    if not spec:
        return None, f"script_id desconocido: {script_id}"

    valid = known_flags(script_id)
    cmd = list(spec["command"])
    used_labels: list[str] = []
    by_arg = {f["arg"]: f for f in spec["flags"]}

    for arg, value in flag_values.items():
        if arg not in valid:
            return None, f"flag desconocido para {script_id}: {arg}"
        f = by_arg[arg]
        t = f["type"]

        if t == "bool":
            if bool(value):
                cmd.append(arg)
                used_labels.append(arg)
        elif t == "int":
            if value in (None, "", "null"):
                continue
            try:
                ival = int(value)
            except (TypeError, ValueError):
                return None, f"valor int inválido para {arg}: {value!r}"
            if f.get("choices") and ival not in [int(c) for c in f["choices"]]:
                return None, f"choice inválido para {arg}: {ival!r}"
            cmd.extend([arg, str(ival)])
            used_labels.append(f"{arg}={ival}")
        elif t == "float":
            if value in (None, "", "null"):
                continue
            try:
                fval = float(value)
            except (TypeError, ValueError):
                return None, f"valor float inválido para {arg}: {value!r}"
            cmd.extend([arg, str(fval)])
            used_labels.append(f"{arg}={fval}")
        elif t == "csv_multi":
            # action="append" del argparse real, sin split interno de comas:
            # una toma por cada valor separado por coma que mandó el panel.
            sval = "" if value is None else str(value)
            tokens = [tok.strip() for tok in sval.split(",") if tok.strip()]
            for tok in tokens:
                cmd.extend([arg, tok])
            if tokens:
                used_labels.append(f"{arg}={','.join(tokens)}")
        elif t in ("str", "csv"):
            sval = "" if value is None else str(value).strip()
            if not sval:
                continue
            cmd.extend([arg, sval])
            used_labels.append(f"{arg}={sval}")
        elif t == "choice":
            sval = "" if value is None else str(value).strip()
            if not sval:
                continue
            if f.get("choices") and sval not in f["choices"]:
                return None, f"choice inválido para {arg}: {sval!r}"
            cmd.extend([arg, sval])
            used_labels.append(f"{arg}={sval}")
        else:
            return None, f"tipo de flag no soportado: {t}"

    label = spec["name"]
    if used_labels:
        label += "  ·  " + " ".join(used_labels)
    return cmd, label


# ---------------------------------------------------------------------------
# Resolución server-side del env de un preset (1.2 / S5, 2026-07-08).
#
# Los presets "+ Whakoom spider" / "+ Whakoom + Wayback" corren scrape_delta/
# full con INCLUDE_WHAKOOM_SPIDER=1 / INCLUDE_WAYBACK_RECOVERY=1 — variables
# que los .sh leen para activar fases opt-in. El CLIENTE NUNCA manda env
# arbitrario (sería inyección de proceso); sólo manda un preset_id conocido
# y el servidor resuelve el env DESDE ACÁ, validado contra la allowlist.
# ---------------------------------------------------------------------------

# Prefijos de env var que los .sh del pipeline efectivamente leen
# (scrape_delta.sh / scrape_full.sh: INCLUDE_WHAKOOM_SPIDER, SKIP_*, etc.).
ALLOWED_ENV_PREFIXES: tuple[str, ...] = ("INCLUDE_", "SKIP_")


def resolve_preset_env(script_id: str, preset_id: str | None) -> dict[str, str]:
    """Devuelve el env dict de un preset conocido, filtrado por la allowlist.

    preset_id ausente/desconocido, o un preset sin "env" → {} (sin efecto).
    Claves fuera de ALLOWED_ENV_PREFIXES se descartan silenciosamente (nunca
    deberían estar en el registry — 4.2 lo valida con un assert al importar)."""
    if not preset_id:
        return {}
    spec = get_script(script_id)
    if not spec:
        return {}
    for preset in spec.get("presets", []):
        if preset.get("id") == preset_id:
            env = preset.get("env") or {}
            return {
                k: str(v) for k, v in env.items()
                if isinstance(k, str) and k.startswith(ALLOWED_ENV_PREFIXES)
            }
    return {}


# ---------------------------------------------------------------------------
# Validación estructural del registry (4.2, 2026-07-08).
#
# Corre al IMPORTAR el módulo — un registry roto tumba serve.py/admin_serve.py
# al arrancar en vez de fallar en silencio en producción (el bug 1.1 —
# presets con "flags" en vez de "values" — pasó desapercibido meses porque
# nada validaba el schema). tests/test_script_registry.py ejercita lo mismo
# más las comparaciones por-AST contra los argparse reales.
# ---------------------------------------------------------------------------

_KNOWN_FLAG_TYPES = {"bool", "int", "float", "str", "choice", "csv", "csv_multi"}
_ROOT = Path(__file__).resolve().parent.parent


def _validate_registry() -> None:
    ids_seen: set[str] = set()
    for spec in SCRIPTS:
        sid = spec.get("id")
        assert isinstance(sid, str) and sid, f"entrada sin id válido: {spec!r}"
        assert sid not in ids_seen, f"id duplicado en SCRIPTS: {sid!r}"
        ids_seen.add(sid)

        assert isinstance(spec.get("mutates_items"), bool), (
            f"{sid}: falta 'mutates_items' (bool) — marcá si el script "
            f"puede escribir data/items.jsonl (usado por el 409 de S10)."
        )

        command = spec.get("command")
        assert isinstance(command, list) and command, f"{sid}: 'command' inválido"
        # El último elemento del command es el path al script (los previos son
        # el intérprete/subcomando, ej. [PYTHON, "scripts/x.py"] o ["bash", "x.sh"]).
        script_path = command[-1]
        if isinstance(script_path, str) and script_path.endswith((".py", ".sh")):
            full_path = _ROOT / script_path
            assert full_path.exists(), (
                f"{sid}: 'command' apunta a un path que no existe: {script_path}"
            )

        arg_names: set[str] = set()
        for f in spec.get("flags", []):
            arg = f.get("arg")
            assert isinstance(arg, str) and arg.startswith("--"), (
                f"{sid}: flag con 'arg' inválido: {f!r}"
            )
            assert arg not in arg_names, f"{sid}: flag duplicado {arg!r}"
            arg_names.add(arg)
            ftype = f.get("type")
            assert ftype in _KNOWN_FLAG_TYPES, (
                f"{sid}.{arg}: type desconocido {ftype!r} (válidos: {_KNOWN_FLAG_TYPES})"
            )
            if ftype == "choice":
                assert f.get("choices"), f"{sid}.{arg}: type=choice sin 'choices'"

        for preset in spec.get("presets", []):
            assert "flags" not in preset, (
                f"{sid}: preset con clave 'flags' (schema viejo, el panel usa "
                f"'values') — {preset.get('label', preset)!r}. Este es "
                f"EXACTAMENTE el bug 1.1 (2026-07-08): renombrá a 'values'."
            )
            assert isinstance(preset.get("id"), str) and preset["id"], (
                f"{sid}: preset sin 'id' — {preset.get('label', preset)!r}"
            )
            assert isinstance(preset.get("label"), str) and preset["label"], (
                f"{sid}: preset {preset.get('id')!r} sin 'label'"
            )
            assert isinstance(preset.get("desc"), str) and preset["desc"], (
                f"{sid}: preset {preset.get('id')!r} sin 'desc'"
            )
            assert isinstance(preset.get("values"), dict), (
                f"{sid}: preset {preset.get('id')!r} sin 'values' (dict)"
            )
            for preset_arg in preset["values"]:
                assert preset_arg in arg_names, (
                    f"{sid}: preset {preset['id']!r} referencia el flag "
                    f"desconocido {preset_arg!r} (no está en 'flags')"
                )
            env = preset.get("env")
            if env is not None:
                assert isinstance(env, dict), f"{sid}: preset 'env' debe ser dict"
                for k in env:
                    assert isinstance(k, str) and k.startswith(ALLOWED_ENV_PREFIXES), (
                        f"{sid}: preset {preset['id']!r} tiene la env var "
                        f"{k!r} fuera de la allowlist {ALLOWED_ENV_PREFIXES} "
                        f"— resolve_preset_env() la descartaría en silencio."
                    )

    assert len(SCRIPTS) == len(SCRIPTS_BY_ID), (
        "hay ids duplicados en SCRIPTS (SCRIPTS_BY_ID los dedupeó en silencio)"
    )


_validate_registry()
