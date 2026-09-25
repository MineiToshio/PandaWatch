# Fuente: Gerekli Şeyler (Turquía)

> Ficha del catálogo de fuentes de PandaWatch. Última revisión: 2026-08-29 (read timeout del host).

| Campo | Valor |
|---|---|
| **Nombre** | TR - Gerekli Şeyler (varyant) |
| **Entrada** | `gerekliseyler.com.tr/arama/varyant` (~13 hits) |
| **kind / class** | `html` / `retailer` · País Turquía · **publisher VACÍO** (gotcha #44; la editorial real es Komik Şeyler, sale de la ficha) |
| **Aporte** | ~10-13 especiales (Solo Leveling Kuşe Kağıt Varyant, Madoka ×3, ORV) — micro-fuente que abre Turquía de 0 |

- Selectores `div.showcase` + `.showcase-title a`. Ficha estructurada label:value
  con Barkod=ISBN-13, editorial, año (señales turcas: varyant kapak, özel edisyon,
  kuşe kağıt — en KEYWORD_RULES desde 2026-06-12).
- Los ~3 hits western (Venomized, Spider-Man) los filtra la comics blacklist /
  filter_non_manga downstream — verificar tras la 1ª ingesta; si "Venomized"
  se cuela (no matchea \bVenom\b por boundary), agregarlo a la blacklist.
- NO scrapear /arama/özel (todo Batman/Marvel) ni /kategori/manga (8714 regulares).
- Dry-run de alta: 13 candidatos / 13 reportables.
- Curación LLM non-manga 2026-08-23: 1 item expulsado — "What If? İç Savaş -
  Silvestri Varyant" (Marvel); se agregó "What If?" a `data/comics_blacklist.yml`.

## 2026-08-29 — read timeout del host: la fuente cae en 🔴 Broken (HTTP errors)

En el delta del 2026-08-29 la fuente falló entera con **0 candidatos**:

```
[ERROR] TR - Gerekli Şeyler (varyant): request error HTTPSConnectionPool(
  host='www.gerekliseyler.com.tr', port=443): Max retries exceeded with url:
  /arama/varyant (Caused by ReadTimeoutError("... Read timed out. (read timeout=30)"))
```

`source_health --baseline-alert` la clasificó como **🔴 Broken (HTTP errors)** —
la única fuente en esa categoría en toda la corrida (1 run, 0 candidatos, 1 error).

**Qué se sabe y qué no.** Es un **read timeout**, no un 404 ni un challenge
anti-bot: el TLS conecta y el servidor no responde el cuerpo dentro de los 30s.
Con una sola corrida **no se puede distinguir** entre (a) lentitud puntual del
host turco (la más probable — es una micro-fuente de ~13 hits, y el timeout de
30s es el default global, nunca se ajustó para ella), (b) el sitio caído ese día,
o (c) geo/rate-limit incipiente. **No se tocó nada**: `enabled` sigue en ✓.

**Qué mirar en la próxima corrida.** Si vuelve a salir 🔴 con el mismo
`ReadTimeoutError`, ya es patrón y no ruido; ahí la decisión (del owner) es entre
subirle el timeout a esta fuente o deshabilitarla como se hizo con ES/MX MangaLine
(host caído desde 2026-07-07). Precedente útil: el aporte de esta fuente es de
~10-13 items de un país que ninguna otra cubre, así que la asimetría favorece
esperar y subir el timeout antes que podarla.
