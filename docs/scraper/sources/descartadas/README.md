# Registro de fuentes descartadas / deshabilitadas

> **Propósito**: que `sources/` sea el catálogo COMPLETO de fuentes conocidas —
> las activas tienen su ficha en `docs/scraper/sources/`, y las que NO están
> activas viven acá con su razón exacta y las condiciones para re-evaluarlas.
> Así nunca re-investigamos desde cero ni re-implementamos algo ya descartado.
>
> Mantenimiento: cada vez que se deshabilita una fuente en `sources.yml` o se
> descarta una candidata en una evaluación, se registra acá EN EL MISMO TURN
> (regla dura de FUENTES, CLAUDE.md). Última revisión: 2026-06-12.

Tres categorías:

1. **§1 Evaluadas y DESCARTADAS (nunca implementadas)** — auditadas con
   /watch-evaluate-sources o investigación dirigida; no entraron al pipeline.
2. **§2 Implementadas y DESHABILITADAS** — están en `sources.yml` con
   `enabled: false`; la razón vive en el comentario del YAML y se replica acá.
3. **§3 Watchlist** — no viables HOY por una condición externa que puede
   cambiar; re-evaluar cuando se cumpla la condición indicada.

---

## §1 Evaluadas y descartadas (nunca implementadas)

| Fuente | País | Fecha | Razón | ¿Re-evaluar si…? |
|---|---|---|---|---|
| Waneko (sklepwaneko.pl) | PL | 2026-06-12 | Sus "exclusivos" son tomos regulares + postal promocional SIN foto del extra (lección BooksPrivilege); ~15-20 coleccionables reales en todo el sitio | lanzan línea coleccionista real |
| Crunchyroll Store US | US | 2026-06-12 | Contenido único (box sets exclusivos) pero React SPA + SCAPI OAuth + robots.txt bloqueando Search-UpdateGrid → inviable sin Playwright+token | exponen feed/API pública |
| Panini Argentina (tiendapanini.com.ar) | AR | 2026-06-12 | Vende las ediciones LATAM de Panini México (ISBN 978-607, SKU sufijo LAT) — NO ediciones argentinas propias; ~6 especiales, todos agotados y sin ISBN → crearían clusters fuzzy duplicados de ediciones MX | Panini AR lanza ediciones con ISBN argentino (978-987) |
| Forbidden Planet (UK) | UK | 2026-06-12 | Cloudflare challenge activo (403 con cf-mitigated incluso en /sitemap.xml) | baja el challenge o se invierte en Playwright+solving |
| Utopia Editorial | AR | 2026-06-12 | El servidor falla el TLS handshake (sslv3 alert) con curl Y requests — inconectable. Catálogo disponible solo vía retailers AR terceros | arreglan su TLS |
| Yes24 (Corea) | KR | 2026-06-12 | ~776 resultados 한정판 pero curl recibe 302→home (cookies/headers especiales); Aladin cubre el mismo mercado sin fricción | Aladin deja de funcionar |
| Kyobobook (Corea) | KR | 2026-06-12 | Productos renderizados por JS (solo metadata en HTML crudo) → requeriría --enable-js | se justifica el costo Playwright |
| Moztros | AR/ES | 2026-06-12 | Es la tienda de ESPAÑA (EUR; país=edición → serían items ES, mercado cubierto); solo 53 productos manga y sus únicos "Deluxe" son cómics Energon | abren tienda AR con catálogo manga propio |
| edition-limitee.fr | FR | 2026-06-12 (eval. sesión 2) | ~550 manga reales pero 45% ruido BD/comics, sin ISBN, alto overlap de serie con Manga-Sanctuary; valor solo en coffrets de nicho (Noeve Grafx) | se necesita cobertura extra de coffrets FR de nicho |
| Gildia (sklep.gildia.pl) | PL | 2026-06-12 | DNS muerto en sklep.gildia.pl; gildia.pl responde 403 a fetch simple | reactivan la tienda |
| Egmont Polska (egmont.pl) | PL | 2026-06-12 | Timeout en 443 desde IPs no polacas (geo-block probable); catálogo manga chico, sin evidencia de especiales (su línea es cómic occidental) | — (baja prioridad permanente) |
| Wydawnictwo Dango (sklep-dango.pl) | PL | 2026-06-12 | Sitio accesible pero CERO señales de ediciones especiales (BL/yuri en tankobon regular) | lanzan línea especial |
| Studio JG / Kotori (directas) | PL | 2026-06-12 | Sin tienda propia rastreable — se cubren vía yatta.pl y Mangastore.pl respectivamente | abren e-commerce propio |
| yatta.pl | PL | 2026-06-12 | Viable técnicamente (~20-40 SKUs vía búsqueda) pero volumen chico y stock vivo (lo agotado desaparece); Mangastore cubre Studio JG/Kotori con fichas persistentes | Mangastore deja de cubrir Studio JG |
| Nautiljon (FR) | FR | 2026-06 (eval. previa) | 403 a bots; existe scraper no-oficial (github.com/barthofu/nautiljon-scraper) como referencia | se decide invertir en bypass |
| BDfugue (FR) | FR | 2026-06 (eval. previa) | Magento con 403; quizá endpoints JSON internos | se encuentran endpoints |
| Barnes & Noble exclusives (US) | US | 2026-06 (eval. previa) | Cloudflare | — |
| Waterstones (UK) | UK | 2026-06 (eval. previa) | 403 | — |
| eslite 誠品 (TW) | TW | 2026-06-12 | 403 a fetch simple (SPA Nuxt + anti-bot challenge); 4 fuentes TW viables lo hacen innecesario | se prioriza TW y se invierte en --enable-js |
| 天下出版 Tin Ha (HK) | HK | 2026-06-12 | Sin catálogo online propio; sus 珍藏版/復刻版 (風雲) solo en marketplaces de segunda mano | abren tienda online |
| cp1897.com.hk 商務印書館 (HK) | HK | 2026-06-12 | Certificado SSL expirado en su cadena (error TLS real); mybookone.com.hk del mismo grupo es JS SPA | arreglan TLS |
| BiliBili 会员购 (CN) | CN | 2026-06-12 | SPA JS de 10KB; APIs orientadas a app con login/csrf | exponen web pública |
| Taobao/JD/天猫 (CN) | CN | 2026-06-12 | El mercado físico de manhua continental vive detrás de anti-bot fuerte + login; no vale el esfuerzo al scale actual | — |
| Dangdang 当当 (CN) | CN | 2026-06-12 | Técnicamente accesible (HTML GBK, 60/pág) pero purity muy mixed (domina literatura infantil), señal 典藏版 abunda fuera de manhua, y captcha al paginar agresivo | se decide abrir China con filtros de categoría 动漫 estrictos |
| Fahasa (VN) | VN | 2026-06-12 | 403 Cloudflare "Just a moment" incluso con UA browser; Kim Đồng + IPM cubren VN | baja el challenge |
| naiin.com (TH) | TH | 2026-06-12 | Búsqueda thai 403 sin cookies y resultados por AJAX (0 links en HTML); yaakz cubre Siam Inter/NED | se descubre el endpoint AJAX |
| siamintercomics.com (TH) | TH | 2026-06-12 | Shell vacío de create-react-app (2.5KB); su tienda real es yaakz.com — usar esa | — |
| NED Comics (TH) | TH | 2026-06-12 | nedcomics.com no resuelve (DNS); sin tienda propia, solo Facebook; sus Big Books llegan vía yaakz/naiin | montan tienda |
| gramedia.com (ID) | ID | 2026-06-12 | Next.js full client-side (0 links de producto en HTML); API gateway Kong sin rutas públicas | se descubren rutas API desde browser |
| m&c! / mncgramedia.id (ID) | ID | 2026-06-12 | Catálogo institucional sin e-commerce, libros por JS, sin señales de especiales | lanzan tienda |
| Elex Media (ID) | ID | 2026-06-12 | Escrapeable por categoría (Next.js SSR parcial, 53 productos) pero 0 señales de especiales en lo muestreado; búsqueda client-side | se confirma que existe línea premium ID (re-test con --enable-js) |
| Mangafan (HU) | HU | 2026-06-12 | Connection refused puertos 80/443 desde fuera de HU (o caído); reportes de webshop cerrado | re-test con proxy HU |
| Vad Virágok (HU) | HU | 2026-06-12 | Shop UNAS funcional pero sin limitált/gyűjtői en manga (sus limitadas son Tintín/western) | — |
| Fumax (HU) | HU | 2026-06-12 | ~48 productos manga/manhwa; "RITKASÁG" = escasez de stock, no ediciones especiales | el mercado HU produce limitadas |
| Képregénymarket (HU) | HU | 2026-06-12 | Agregador HU sin señales de especiales ni precios en listado | el mercado HU madura |
| Marmara Çizgi (TR) | TR | 2026-06-12 | Sección "Özel Ürünler" excelente (74 items, dukkan.marmaracizgi.com.tr) pero ~95% Marvel/DC, 0 manga | lanzan especiales manga |
| İthaki (TR) | TR | 2026-06-12 | 26 mangas regulares (Dorohedoro, Mob Psycho), 0 marcadores özel/varyant/kutulu. OJO: ithaki.com.tr no resuelve; el sitio es ithakiyayingrubu.com | publican especiales |
| Sangatsu Manga (FI) | FI | 2026-06-12 | 403 Cloudflare (cf_bm); mercado FI chico | baja CF o se prioriza FI |
| Países Bajos (mercado) | NL | 2026-06-12 | No existe editorial NL con línea de especiales; special-edition.nl es una tienda física que vende imports EN (redundante) | aparece editorial NL |
| Anubis (GR) | GR | 2026-06-12 | WooCommerce con categoría manga escrapeable pero sin συλλεκτική έκδοση en manga (solo en novelas) | re-evaluar en 6-12 meses |
| SF-Bokhandeln (SE) / Escandinavia | SE/NO/DK | 2026-06-12 | Tag "samlarutgåva manga" (~30) pero todos imports EN → redundante; no hay editorial nórdica con manga local especial | aparece editorial local |
| Editora Devir (PT-PT) | PT | 2026-06-12 | Viable técnicamente (WooCommerce, 200 con UA browser) pero señales de especiales ~0 (solo packs/bundles); el publisher manga PT es chico | lanzan línea especial/colecionador |
| Istari Comics + Азбука (RU) | RU | 2026-06-12 | Técnicamente viables (istari.ru y azbooka.ru responden 200, HTML plano; el mercado RU SÍ tiene лимитированное издание) — **descartadas por decisión de producto pendiente**: implica idioma RU nuevo en el stack y mercado bajo sanciones | el owner decide abrir RU |
| Rumania / Ucrania | RO/UA | 2026-06-12 | Sin candidatos sólidos en esta pasada (RO sin editorial manga activa; UA: Nasha Idea anotada para una segunda ronda) | segunda ronda de discovery |

---

## §2 Implementadas y deshabilitadas (`enabled: false` en sources.yml)

> La razón canónica vive en el comentario `enabled: false # …` del YAML; esta
> tabla se regenera de ahí. Grupos grandes: las 15 Bluesky (audit 2026-05-25,
> 0 items), los feeds de noticias US (0 productos), y la **poda 2026-06-12**
> de fuentes con 0 items netos en todo el histórico (el gate descartaba el
> 100% de sus candidatos — requests desperdiciados).

| País | Fuente | kind | Razón |
|---|---|---|---|
| Argentina | AR - Ivreality | html | disabled 2026-06-12 (poda de fuentes muertas): 0 items netos en todo el histórico (25 candidatos/run, el gate descarta todo — blog de noticias). Ivrea AR cubierta por la fuente de catálogo. |
| Argentina | AR - La Comiquería | js | audit 2026-05-25: 0 items |
| Argentina | AR - Ovni Press Manga | html | audit 2026-05-25: 0 items |
| Brasil | BR - Devir Brasil | html | audit 2026-05-25: 0 items |
| Brasil | BR - Editora JBC Títulos | html | disabled 2026-06-12 (poda de fuentes muertas): 80 candidatos/run → 1 neto; JBC Checklist (9 items) cubre la editorial mejor. |
| Brasil | BR - NewPOP Catálogo | html | tags: ["manga", "official"] |
| Brasil | BR - NewPOP Mangas | html | disabled 2026-06-12 (poda de fuentes muertas): 400 candidatos/run → 0 items netos (catálogo de tankobon regulares, el gate descarta todo). Lançamentos queda como fuente delta de NewPOP. |
| Brasil | BR - NewPOP One-shots | html | disabled 2026-06-12 (poda de fuentes muertas): 240 candidatos/run → 0 items netos (one-shots regulares). |
| Brasil | BR - NewPOP Pacotes | html | disabled 2026-06-12 (poda de fuentes muertas): 80 candidatos/run → 0-1 items netos (pacotes = bundles de tomos regulares, no box sets premium). |
| Brasil | BR - Panini Brasil Planet Manga | html | disabled 2026-06-12 (poda de fuentes muertas): 39 candidatos/run → 0 netos; las búsquedas Panini BR (search) aportan 21 items — el catálogo es redundante. |
| España | ES - Distrito Manga | html | disabled 2026-06-12 (poda de fuentes muertas): 0 items netos en todo el histórico (61 candidatos tras el fix de selectores 2026-06-12, todo gateado: integrales/regulares sin línea coleccionista). List |
| España | ES - ECC Manga | html | tags: ["manga", "official", "store"] |
| España | ES - Fnac España exclusivos | js | 403 desde Python/Playwright vanilla; necesita stealth + proxies |
| España | ES - Ivrea España Noticias | html | audit 2026-05-25: 0 items |
| España | ES - Kibook Novedades | js | disabled 2026-06-01: 0 items en corpus, fuente JS (Playwright caro), sin yield. Ver auditoría de fuentes. |
| España | ES - Listado Manga Blog RSS | rss | Decisión 2026-05-23: deshabilitado. Son posts de noticias, |
| España | ES - Listado Manga Calendario | html | autodetect falla (anchors con imagen sin texto); usar --bootstrap-wiki listadomanga |
| España | ES - Listado Manga Novedades | html | autodetect falla; el wiki parser cubre /calendario.php que es equivalente |
| España | ES - Misión Tokyo lanzamientos | js | sitio caído (connection timeout 30s+); reactivar si vuelve |
| España | ES - Misión Tokyo novedades manga | js | sitio caído (connection timeout 30s+); reactivar si vuelve |
| España | ES - Norma (search) | html | disabled 2026-06-12 (poda de fuentes muertas): 7 búsquedas/run → 0 items netos; Norma está íntegramente cubierta por ListadoManga (colecciones) y la fuente de catálogo Norma (3 items). |
| España | ES - Ramen Para Dos Manga | html | audit 2026-05-25: 0 items |
| España | ES - Ramen Para Dos RSS | rss | audit 2026-05-25: 0 items |
| España | SOCIAL - Arechi Manga Bluesky | bluesky | audit 2026-05-25: 0 items |
| España | SOCIAL - Milky Way Ediciones Bluesky | bluesky | audit 2026-05-25: 0 items |
| España | SOCIAL - Norma Editorial Bluesky | bluesky | audit 2026-05-25: 0 items |
| España | SOCIAL - Norma Editorial Manga Bluesky | bluesky | audit 2026-05-25: 0 items |
| España | SOCIAL - Planeta Cómic Bluesky | bluesky | audit 2026-05-25: 0 items |
| España / LatAm | ES - Crunchyroll Noticias | js | audit 2026-05-25: 0 items |
| España / LatAm | ES/LatAm - Whakoom Novedades | html | disabled 2026-06-12 (poda de fuentes muertas): kind js (costo Playwright) → 1 item neto histórico. El spider whakoom opt-in sigue disponible para corridas dedicadas. |
| Estados Unidos | SOCIAL - Dark Horse Bluesky | bluesky | audit 2026-05-25: 0 items |
| Estados Unidos | SOCIAL - Kodansha USA Bluesky | bluesky | audit 2026-05-25: 0 items |
| Estados Unidos | SOCIAL - Seven Seas Bluesky | bluesky | audit 2026-05-25: 0 items |
| Estados Unidos | SOCIAL - VIZ Media Bluesky | bluesky | audit 2026-05-25: 0 items |
| Estados Unidos | SOCIAL - Yen Press Bluesky | bluesky | audit 2026-05-25: 0 items |
| Estados Unidos | US - Anime News Network News | html | tags: ["news", "anime", "manga", "fallback"] |
| Estados Unidos | US - Anime News Network News RSS | rss | audit 2026-05-25: 0 items |
| Estados Unidos | US - Barnes & Noble Manga Exclusives | js | tags: ["retailer", "exclusive", "variant"] |
| Estados Unidos | US - ComicBook.com Anime | html | audit 2026-05-25: 0 items |
| Estados Unidos | US - Crunchyroll Store Manga | html | audit 2026-05-25: 0 items |
| Estados Unidos | US - Kinokuniya Exclusives | html | notes: "Reemplazado por wiki parser scripts/wikis/kinokuniya.py (Squarespace dynamic class names rompían el selector). El wiki parser extrae ISBNs directamente del patrón de URL de producto /bw/{isbn1 |
| Estados Unidos | US - Kodansha USA (search) | html | tags: ["manga", "official"] |
| Estados Unidos | US - Kodansha USA News | html | audit 2026-05-25: 0 items |
| Estados Unidos | US - Seven Seas Box Sets | js | disabled 2026-06-01: 0 items en corpus, fuente JS (Playwright caro), sin yield. Box sets de Seven Seas ya llegan vía PRH Comics. Ver auditoría de fuentes. |
| Estados Unidos | US - Seven Seas News | html | disabled 2026-06-01: feed de noticias, 0 items coleccionables en corpus. Ver auditoría de fuentes. |
| Estados Unidos | US - Seven Seas RSS | rss | disabled 2026-06-01: RSS de noticias, 0 items coleccionables en corpus. Ver auditoría de fuentes. |
| Estados Unidos | US - VIZ Blog | html | disabled 2026-06-01: feed de noticias, 0 items coleccionables en corpus. Los exclusivos VIZ llegan vía US - VIZ Collector's Guide. Ver auditoría de fuentes. |
| Estados Unidos | US - Yen Press (search) | html | tags: ["manga", "official"] |
| Estados Unidos | US - Yen Press News | html | disabled 2026-06-01: feed de noticias, 0 items coleccionables. Yen Press llega vía wiki yenpress (calendario). Ver auditoría de fuentes. |
| Francia | FR - ActuaLitté Mangas RSS | rss | audit 2026-05-25: 0 items |
| Francia | FR - Akata | html | disabled 2026-06-12 (poda de fuentes muertas): 0 items netos en todo el histórico; FR cubierta por Manga-Sanctuary + fuentes Pika/Glénat/Kurokawa/Meian. |
| Francia | FR - Glénat (search) | html | tags: ["manga", "official"] |
| Francia | FR - Kana Actualités | html | audit 2026-05-25: 0 items |
| Francia | FR - Ki-oon | html | disabled 2026-06-12 (poda de fuentes muertas): 0 items netos en todo el histórico (catálogo sin señales de edición en listing; Manga-Sanctuary captura las collector de Ki-oon). |
| Francia | FR - Kurokawa | js | tags: ["manga", "official"] |
| Francia | FR - Manga-News Actus | html | audit 2026-05-25: 0 items |
| Francia | FR - Manga-News Home | html | audit 2026-05-25: 0 items |
| Francia | FR - Meian Plus Boutique | js | disabled 2026-06-01: 0 items en corpus, fuente JS (Playwright caro), sin yield. Ver auditoría de fuentes. |
| Francia | FR - Pika (search) | html | tags: ["manga", "official"] |
| Francia | FR - Pika Planning | html | disabled 2026-06-12 (poda de fuentes muertas): 2 items, 0 únicos (Pika Édition y Pika Livres/Artbooks cubren lo mismo). |
| Francia | FR - Vega Dupuis | js | disabled 2026-06-01: 0 items en corpus, fuente JS (Playwright caro), sin yield. Ver auditoría de fuentes. |
| Francia | SOCIAL - Glénat Manga Bluesky | bluesky | audit 2026-05-25: 0 items |
| Francia | SOCIAL - Ki-oon Bluesky | bluesky | audit 2026-05-25: 0 items |
| Francia | SOCIAL - Kurokawa Bluesky | bluesky | audit 2026-05-25: 0 items |
| Francia | SOCIAL - Pika Édition Bluesky | bluesky | audit 2026-05-25: 0 items |
| Italia | IT - Edizioni BD | html | audit 2026-05-25: 0 items |
| Italia | IT - GOEN / RW Edizioni | html | audit 2026-05-25: 0 items |
| Italia | IT - J-Pop Manga | js | audit 2026-05-25: 0 items |
| Italia | IT - Magic Press | html | audit 2026-05-25: 0 items |
| Italia | IT - Magic Press Uscite | html | audit 2026-05-25: 0 items |
| Italia | IT - MangaYo Esclusive | js | tags: ["retailer", "exclusive", "variant", "italy"] |
| Italia | IT - Star Comics Home | html | audit 2026-05-25: 0 items |
| Japón | JP - Akita Shoten Comics | html | audit 2026-05-25: 0 items |
| Japón | JP - Animate Online Books | html | tags: ["retailer", "bonus", "manga", "japan"] |
| Japón | JP - Hakusensha | html | audit 2026-05-25: 0 items |
| Japón | JP - Honto (search) | html | disabled 2026-06-12 (poda de fuentes muertas): 9 búsquedas/run → 0 items netos (resultados dominados por ebooks, ver gotcha de honto.jp/ebook/). Rakuten Books (search) cubre JP retail con 179 items. |
| Japón | JP - Jump Characters Store | html | audit 2026-05-25: 0 items |
| Japón | JP - KADOKAWA Comics | html | disabled 2026-06-12 (poda de fuentes muertas): 1 item compartido, 0 únicos; KADOKAWA Store (6) + Store Artbooks/Fanbooks (89) cubren la editorial. |
| Japón | JP - Kodansha Comic Calendar | html | audit 2026-05-25: 0 items |
| Japón | JP - Kodansha Comic Limited Editions | html | audit 2026-05-25: 0 items |
| Japón | JP - S-MANGA Shueisha | html | audit 2026-05-25: 0 items |
| Japón | JP - Shogakukan Comic | html | audit 2026-05-25: 0 items |
| Japón | JP - Shogakukan Comics Calendar | js | audit 2026-05-25: 0 items |
| Japón | JP - Shueisha Comics Paper Releases | js | audit 2026-05-25: 0 items |
| Japón | JP - Square Enix Comics | html | disabled 2026-06-12 (poda de fuentes muertas): 1 item compartido, 0 únicos; el catálogo JP de SQEX no expone especiales scrapeables (las 限定版 llegan vía Sumikko/Rakuten). |
| Japón / Global | SOCIAL - Manga Mogura Bluesky | bluesky | audit 2026-05-25: 0 items |
| Japón / Global | SOCIAL - Manga Mogura RE X | html | tags: ["social", "x", "twitter", "news", "manga"] |
| México | MX - Panini Manga México | html | disabled 2026-06-12 (poda de fuentes muertas): 2 candidatos/run → 0 netos; Panini México Boxsets (31) + búsquedas (36+4) cubren la editorial. |

---

## §3 Watchlist (re-evaluar cuando cambie la condición)

| Fuente | País | Condición de re-evaluación |
|---|---|---|
| Kazé / Pegasus Manga (HarperCollins DE) | DE | La marca Kazé relanza en abril 2026 bajo HarperCollins; hoy kaze-online.de es un portal B2B. Re-evaluar post-relanzamiento. |
| Panini DE (panini.de) | DE | Viable (Magento, igual que Panini ES/IT/BR/MX) pero con waiting-room Queue-it en el primer hit — necesita cookie jar persistente en el fetcher. Implementar si se agrega soporte de sesión con cookies. |
| Aladin OpenAPI (TTB key) | KR | Upgrade de la fuente HTML actual: API oficial gratuita con ISBN/portada en JSON. Pedir TTB key si la fuente escala o el HTML cambia. |
| Crunchyroll Store US | US | Ver §1 — si exponen feed. Contenido único real (Frieren box set exclusivo, etc.). |
| BooksPrivilege (JP) | JP | Deshabilitada 2026-05-26 (11k items de tomo regular + bonus de tienda SIN foto del extra). Re-evaluar SOLO si empiezan a fotografiar los extras. Módulo `wikis/booksprivilege.py` sigue disponible. |
| Censored covers ListadoManga | ES | Portadas adultas detrás de modal "aceptar contenido adulto" — requeriría Playwright o cookie injection per-source (diferido explícito en CLAUDE.md). |
