# Fuente: Gerekli Şeyler (Turquía)

> Ficha del catálogo de fuentes de PandaWatch. Última revisión: 2026-06-12 (alta).

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
