# Fuente: Crew (Chequia)

> Ficha del catálogo de fuentes de PandaWatch. Última revisión: 2026-06-12 (alta).

| Campo | Valor |
|---|---|
| **Nombre** | CZ - Crew Manga |
| **Entrada** | `obchod.crew.cz/kategorie-21646/komiks/crew-manga?page=1` (27 págs, ~440 productos) |
| **kind / class** | `html` / `official` · País Chequia · purity manga_only |
| **Aporte** | ~4-5 especiales vivos (~1% del catálogo) — fuente MIXTA de bajo costo que abre Chequia de 0 |

- Editorial #1 checa (tienda propia). Selectores `article.item` + `h3.item__tit a`.
- Qualifiers SIEMPRE en el título: limitovaná verze/edice, Sběratelský box,
  Speciální balíček → el gate filtra el ~99% regular determinísticamente
  (señales checas en KEYWORD_RULES desde 2026-06-12).
- EAN checo 859… en boxes (no ISBN). Señal de rareza: Vyprodáno (Kagurabači
  limitovaná ya agotada al darla de alta).
- Speciální balíček = bundle de tomos regulares sin cofre → gateado (regla
  "pack 1ª ed. = regular").
- Dry-run de alta: 1074 candidatos / 4 reportables (correcto — esos 4 son los
  especiales reales).
