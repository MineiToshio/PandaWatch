#!/usr/bin/env python3
"""curate_llm_non_manga_20260823.py — cierra la curación manual de los 265 items
que el LLM de `/watch-standardize-catalog` marcó `is_manga=false` el 2026-08-23.

CONTEXTO. Por la regla del repo (gotcha #122) el veredicto del LLM NO expulsa:
los 265 quedaron PENDIENTES (sin `standardized_at`) y registrados en
`data/unmapped_series.jsonl` (reason `llm_non_manga`) para que un humano
decidiera. Esta corrida es esa decisión, tomada item por item con verificación
web de autor/editorial de origen.

RESULTADO DE LA REVISIÓN (2026-08-23):
  - KEEP  94  — light novels JP/DE/PL/VN/TW, novelas danmei CN de Seven Seas
            (Otaku Calendar / Manga-Sanctuary), artbooks y 1 manga de Gou Tanabe
            mal clasificado. 7 de ellos quedan como INCIERTOS y siguen
            flageados en `unmapped_series.jsonl`.
  - EXPEL 171 — cómic occidental (Marvel/DC/Disney IT/Bonelli/Image/IDW/
            Valiant), artbooks de videojuego, merchandising JP/TW/KR, DVD/Blu-ray,
            libros de texto/historia VN, novela literaria general JP y 2 páginas de
            noticias capturadas como producto.

CAUSA RAÍZ del bloque más grande de falsos negativos (83 items): la regla
"Light novels → `false`" en `.claude/skills/watch-standardize-catalog/
prompt-rules.md` contradecía CLAUDE.md, `is_likely_manga()` y el enum de
`product_type` (que incluye `novel`). Se corrigió en el mismo turn (gotcha #146)
— este script sólo limpia el corpus, la prevención vive allá.

REPARTO DE LA EXPULSIÓN (dos mecanismos, en este orden):
  1. `filter_non_manga.py` — gate DETERMINISTA. Con las keywords nuevas de
     `data/comics_blacklist.yml` + 2 patrones HARD (【日本進口精品】,
     ファミ通DXパック) rechaza 93 de los 171. Es el camino preferente:
     además previene la re-ingesta en el próximo scrape.
  2. Este script — los 78 restantes, que NO se pueden expresar como
     patrón sin falsos positivos: series indie italianas de un solo item,
     merchandising sin marcador estructural, y sobre todo los ~35 items de
     `IT - Funside Variant` cuyo `title` es una FECHA ("USCITA: 28/10/26") por un
     bug del parser (ver gotcha #147) — sin título no hay patrón posible.
  Embebemos las 171 URLs completas (no sólo las 78) para que el
  script sea idempotente y auditable corra antes o después del filtro.

También limpia `data/unmapped_series.jsonl` (única cola de registros inciertos,
nunca archivos paralelos): borra las filas `llm_non_manga` de los items
expulsados y las de los KEEP ya resueltos. Las 7 filas INCIERTAS se
CONSERVAN a propósito.

Idempotente. Guard `approved_at` (golden records) + `--include-approved`.
Backup vía `backup_and_rotate` antes de escribir. Escritura atómica.

Uso:
  .venv/bin/python scripts/retrofit/curate_llm_non_manga_20260823.py            # dry-run
  .venv/bin/python scripts/retrofit/curate_llm_non_manga_20260823.py --apply
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_SCRIPTS = Path(__file__).resolve().parent.parent  # scripts/retrofit → scripts
if str(_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS))

# El wrapper manga_watch.py de la RAÍZ puede estar ya cacheado en sys.modules
# bajo pytest (no expone estos símbolos) → fallback al módulo real (mismo
# patrón que fetch_better_covers.py / backfill_series_aliases.py).
try:
    from manga_watch import (  # type: ignore
        backup_and_rotate, is_approved, write_items_atomic, write_lines_atomic,
    )
except ImportError:  # pragma: no cover
    from scripts.manga_watch import (  # type: ignore
        backup_and_rotate, is_approved, write_items_atomic, write_lines_atomic,
    )

ITEMS = _SCRIPTS.parent / "data" / "items.jsonl"
UNMAPPED = _SCRIPTS.parent / "data" / "unmapped_series.jsonl"
DIAG = _SCRIPTS.parent / "data" / "diagnostics" / "items.llm_non_manga_curated.jsonl"

# --- Veredicto EXPEL: no-manga confirmado (verificado uno por uno) ----------
EXPEL_URLS: frozenset[str] = frozenset([
    # BR - Panini Brasil (search) [search: edicao definitiva]
    "https://panini.com.br/tom-strong-edicao-definitiva-vol-2",  # Tom Strong: Edição Definitiva Vol. 2
    # ES - Milky Way (search) [search: tapa dura]
    "https://www.milkywayediciones.com/blogs/news/nuevas-licencias-given-10th-mix-pink-heart-jam-beat-oyasumi-shinkai-summer-time-render-2026-strand-boichi-original-sf-tapenshu-omori-y-atelier-of-witch-hat-ed-deluxe?_pos=9&_sid=729a3016b&_ss=r",  # Nuevas licencias: “Given 10th Mix”, “Pink Heart Jam Beat”, “Oy
    # ES - Panini España (search) [search: deluxe]
    "https://www.panini.es/shp_esp_es/marvel-now-deluxe-secret-wars-integral-smlux034y-es01.html",  # Marvel Now! Deluxe. Secret Wars: Integral
    # ES - Panini Manga España
    "https://www.panini.es/shp_esp_es/marvel-treasury-edition-shola030-es01.html",  # Marvel Treasury Edition
    # ES - Pika Ediciones
    "https://www.pika.fr/",  # Una alianza estratégica para el manga en español Pika Édition 
    # IT - Dynit
    "https://www.dynit.it/prodotto/harmagedon-limited-edition-blu-raydvdbookletsettei-book-blu-ray/",  # Harmagedon Limited Edition (Blu-Ray+Dvd+Booklet+Settei Book)
    "https://www.dynit.it/prodotto/madoka-magica-the-complete-series-eps-01-12-3-dvd-dvd/",  # Sconto 10%
    # IT - Edizioni BD (search) [search: cofanetto]
    "https://www.edizionibd.it/archie-box-con-cofanetto-e-poster-omaggio.html",  # Archie Box - Con Cofanetto E Poster Omaggio
    # IT - Edizioni BD (search) [search: edizione limitata]
    "https://www.edizionibd.it/house-of-slaughter-6-ed-variant-sketchata-da-letizia-cadonici.html",  # House of Slaughter 6 - Ed. Variant Sketchata da Letizia Cadoni
    # IT - Edizioni BD (search) [search: variant]
    "https://www.edizionibd.it/critical-role-vox-machina-001-le-origini-variant.html",  # Critical Role Vox Machina 001 - Le Origini Variant
    "https://www.edizionibd.it/dark-ark-001-quaranta-notti-variant-blue.html",  # Dark Ark 001 - Quaranta Notti Variant Blue
    # IT - Funside Variant
    "https://funside.it/products/a-twisted-tale-once-upon-a-dream-vol-1-variant",  # A TWISTED TALE ONCE UPON A DREAM VOL.1 - VARIANT
    "https://funside.it/products/anyaman-vol-1-variant",  # ANYMAN VOL.1 - VARIANT
    "https://funside.it/products/barbascura-spiega-gli-animali-e-sio-li-disegna-variant-che-puzza",  # BARBASCURA SPIEGA GLI ANIMALI (E SIO LI DISEGNA) - VARIANT CHE
    "https://funside.it/products/capitan-america-3-2025-capitan-america-190-stitch-variant",  # CAPITAN AMERICA 3 (2025) - CAPITAN AMERICA 190 - STITCH VARIAN
    "https://funside.it/products/dark-shots-variant-mack",  # DARK SHOTS - VARIANT MACK
    "https://funside.it/products/dead-eyes-variant",  # DEAD EYES - VARIANT
    "https://funside.it/products/diablo-lalba-dellodio-ed-variant-funside",  # DIABLO - L'ALBA DELL'ODIO - ED. VARIANT
    "https://funside.it/products/geist-maschine-vol-2-variant-fumetterie",  # GEIST MASCHINE VOL.2 - VARIANT FUMETTERIE
    "https://funside.it/products/godzilla-hic-sunt-dracones-iii-variant",  # GODZILLA - HIC SUNT DRACONES III - VARIANT CON COFANETTO
    "https://funside.it/products/godzilla-il-colpo-variant",  # GODZILLA - IL COLPO - VARIANT
    "https://funside.it/products/helen-di-wyndhorn-variant",  # HELEN DI WYNDHORN - VARIANT
    "https://funside.it/products/hoka-hey-variant",  # HOKA HEY! - VARIANT
    "https://funside.it/products/hyde-street-vol-1-variant",  # HYDE STREET VOL. 1 VARIANT
    "https://funside.it/products/cronache-di-arda-il-ritorno-dei-draghi-variant",  # LE CRONACHE DI ARDA: IL RITORNO DEI DRAGHI VARIANT
    "https://funside.it/products/le-cronache-di-florens-vol-1-elisia-variant",  # LE CRONACHE DI FLORENS VOL.1 - ELISIA VARIANT
    "https://funside.it/products/l-inferno-di-dante-illustrato-da-paolo-barbieri-variant",  # L’INFERNO DI DANTE - ILLUSTRATO DA PAOLO BARBIERI - VARIANT
    "https://funside.it/products/marvel-miniserie-298-i-dungeon-di-destino-2-variant-londra-di-alan-davis",  # MARVEL MINISERIE 298 - I DUNGEON DI DESTINO 2 - VARIANT LONDRA
    "https://funside.it/products/mondo-oscuro-vol-37-dragonero-150-la-fine-di-tutto-variant",  # MONDO OSCURO VOL.37 - DRAGONERO 150 - LA FINE DI TUTTO - VARIA
    "https://funside.it/products/nero-9-aspettando-lospite-donore-variant",  # NERO 9 - ASPETTANDO L'OSPITE D'ONORE - VARIANT
    "https://funside.it/products/norse-miti-e-dei-vichinghi-variant",  # NORSE: MITI E DEI VICHINGHI - VARIANT
    "https://funside.it/products/outcast-il-reietto-5-variant-colore",  # OUTCAST: IL REIETTO 5 - VARIANT COLORE
    "https://funside.it/products/paperino-549-variant-con-statuina-sport-invernali",  # PAPERINO 549 - VARIANT CON STATUINA SPORT INVERNALI
    "https://funside.it/products/scegli-la-tua-avventura-the-classic-collection-box-vol-1-4-ed-variant-funside",  # SCEGLI LA TUA AVVENTURA: THE CLASSIC COLLECTION BOX VOL. 1-4 -
    "https://funside.it/products/scheletri-zerocalcare-tascabile-variant",  # SCHELETRI - ZEROCALCARE - TASCABILE - VARIANT
    "https://funside.it/products/scottecs-gigazine-1-variant-fumetterie",  # SCOTTECS GIGAZINE 1 - VARIANT FUMETTERIE
    "https://funside.it/products/scottecs-gigazine-11-variant-fumetterie",  # SCOTTECS GIGAZINE 11 - VARIANT FUMETTERIE
    "https://funside.it/products/scottecs-gigazine-16-variant-fumetterie",  # SCOTTECS GIGAZINE 16 - VARIANT FUMETTERIE
    "https://funside.it/products/scottecs-gigazine-17-variant-one-pizz",  # SCOTTECS GIGAZINE 17 - VARIANT ONE PIZZ
    "https://funside.it/products/scottecs-gigazine-23-variant",  # SCOTTECS GIGAZINE 23 - VARIANT
    "https://funside.it/products/scottecs-gigazine-27-variant-limitata-esclusiva-fumetterie-1-di-3",  # SCOTTECS GIGAZINE 27 - VARIANT LIMITATA ESCLUSIVA FUMETTERIE -
    "https://funside.it/products/scottecs-gigazine-28-variant-limitata-esclusiva-fumetterie-2-di-3",  # SCOTTECS GIGAZINE 28 - VARIANT LIMITATA ESCLUSIVA FUMETTERIE -
    "https://funside.it/products/scottecs-gigazine-29-variant-limitata-esclusiva-fumetterie-3-di-3",  # SCOTTECS GIGAZINE 29 - VARIANT LIMITATA ESCLUSIVA FUMETTERIE -
    "https://funside.it/products/scottecs-gigazine-30-variant-oro-limitata",  # SCOTTECS GIGAZINE 30 - VARIANT ORO LIMITATA
    "https://funside.it/products/scottecs-gigazine-34-variant-one-pizz",  # SCOTTECS GIGAZINE 34 - VARIANT ONE PIZZ
    "https://funside.it/products/scottecs-gigazine-35-variant",  # SCOTTECS GIGAZINE 35 - VARIANT
    "https://funside.it/products/scottecs-grosso-100-fumetti-a-colori-di-sio-variant",  # SCOTTECS GROSSO - 100% FUMETTI A COLORI DI SIO - VARIANT FUMET
    "https://funside.it/products/senzanima-17-tradimento-variant-orda-flipbook",  # SENZANIMA 17 - TRADIMENTO - VARIANT ORDA FLIPBOOK
    "https://funside.it/products/senzanima-18-vendetta-variant",  # SENZANIMA 18 - VENDETTA - VARIANT MANICOMIX
    "https://funside.it/products/sinisters-six-2025-1-x-force-64-variant-di-rickie-yagawa",  # SINISTER'S SIX (2025) 1 - X-FORCE 64 - VARIANT DI RICKIE YAGAW
    "https://funside.it/products/sonic-the-hedgehog-vol-1-leco-della-guerra-variant",  # SONIC THE HEDGEHOG VOL.1 - L'ECO DELLA GUERRA - VARIANT
    "https://funside.it/products/starhenge-variant",  # STARHENGE VARIANT
    "https://funside.it/products/stray-dogs-cani-randagi-variant-la-cosa",  # STRAY DOGS - CANI RANDAGI - VARIANT LA COSA
    "https://funside.it/products/stray-dogs-cani-randagi-variant-limitata-the-blair-witch-project",  # STRAY DOGS - CANI RANDAGI - VARIANT LIMITATA THE BLAIR WITCH P
    "https://funside.it/products/stray-dogs-cani-randagi-variant-super-limitata-bram-strokers-dracula",  # STRAY DOGS - CANI RANDAGI - VARIANT SUPER LIMITATA BRAM STROKE
    "https://funside.it/products/stray-dogs-giorni-da-cani-variant-squid-game",  # STRAY DOGS - GIORNI DA CANI - VARIANT SQUID GAME
    "https://funside.it/products/stray-dogs-giorni-da-cani-variant-super-limitata-alien",  # STRAY DOGS - GIORNI DA CANI - VARIANT SUPER LIMITATA ALIEN
    "https://funside.it/products/street-fighter-legends-chun-li-cover-variant-d",  # STREET FIGHTER LEGENDS: CHUN-LI - COVER VARIANT D
    "https://funside.it/products/topolino-3656-variant-natale",  # TOPOLINO 3656 VARIANT NATALE
    "https://funside.it/products/topolino-3679-variant-etna-comics-2026",  # TOPOLINO 3679 VARIANT ETNA COMICS 2026
    "https://funside.it/products/tutto-un-altro-lupo-alberto-variant-silver-laminata-argento",  # TUTTO UN ALTRO LUPO ALBERTO - VARIANT SILVER LAMINATA ARGENTO
    "https://funside.it/products/ultimate-endgame-vol-1-variant-di-simone-meo",  # ULTIMATE ENDGAME VOL.1 - VARIANT DI SIMONE DI MEO
    "https://funside.it/products/topolino-3702-variant-lucca-comics-2",  # USCITA: 04/11/26
    "https://funside.it/products/topolino-3694-variant-palermo-comics",  # USCITA: 09/09/26
    "https://funside.it/products/sin-city-star-variant-vol-7",  # USCITA: 10/11/26
    "https://funside.it/products/batman-hush-2-variant-di-corrado-roi",  # USCITA: 19/09/26
    "https://funside.it/products/venom-111-connecting-variant-7",  # USCITA: 24/08/26
    "https://funside.it/products/spider-man-898-connecting-variant-9",  # USCITA: 24/08/26
    "https://funside.it/products/disney-special-events-pk-2-tutta-unaltra-storia-variant-di-fabio-celoni",  # USCITA: 26/08/26
    "https://funside.it/products/ultimate-universe-finale-variant",  # USCITA: 27/08/26
    "https://funside.it/products/amazing-spider-man-divisi-3-spider-man-897-variant-amazing-visions-di-lee-bermejo",  # USCITA: 27/08/26
    "https://funside.it/products/absolute-freccia-verde-vol-1-variant-esclusiva",  # USCITA: 28/10/26
    "https://funside.it/products/disney-special-events-pk-3-un-passo-ancora-variant-di-simone-meo",  # USCITA: 28/10/26
    "https://funside.it/products/absolute-freccia-verde-vol-1-variant-di-tyler-kirkham",  # USCITA: 28/10/26
    "https://funside.it/products/dc-crossover-52-dc-ko-vol-5-variant-di-ian-bertam",  # USCITA: 28/10/26
    "https://funside.it/products/dc-crossover-52-dc-ko-vol-5-variant-di-daniel-warren-johnson",  # USCITA: 28/10/26
    "https://funside.it/products/spectacular-spider-man-brand-new-day-1-spider-man-900-variant-amazing-visions-di-lee-bermejo",  # USCITA: 28/10/26
    "https://funside.it/products/amazing-spider-man-21-spider-man-901-variant-amazing-visions-di-lee-bermejo",  # USCITA: 28/10/26
    "https://funside.it/products/teenage-mutant-ninja-turtles-2024-vol-21-variant-di-frank-miller",  # USCITA: 28/10/26
    "https://funside.it/products/topolino-3701-variant-lucca-comics-1",  # USCITA: 28/10/26
    "https://funside.it/products/dc-facsimile-edition-jla-avengers-2-variant-wraparound-di-dan-mora",  # USCITA: 28/10/26
    "https://funside.it/products/dc-facsimile-edition-batman-il-ritorno-del-cavaliere-oscuro-1-variant",  # USCITA: 28/10/26
    "https://funside.it/products/justice-league-unlimited-19-justice-league-50-variant-di-claudio-castellini",  # USCITA: 28/10/26
    "https://funside.it/products/spectacular-spider-man-brand-new-day-1-spider-man-900-variant",  # USCITA: 28/10/26
    "https://funside.it/products/spider-man-shadow-warrior-1-variant",  # USCITA: 28/10/26
    "https://funside.it/products/raven-cycle-vol-2-the-dream-thieves-graphic-novel-variant",  # USCITA: 28/10/26
    "https://funside.it/products/vertigo-presenta-1-variant",  # USCITA: 28/10/26
    "https://funside.it/products/a-twisted-tale-unbirthday-1-variant",  # USCITA: 28/10/26
    "https://funside.it/products/zio-paperone-100-variant",  # USCITA: 28/10/26
    "https://funside.it/products/american-caper-vol-1-il-blues-del-redpillato-variant",  # USCITA: 28/10/26
    "https://funside.it/products/check-please-hockey-vol-1-variant",  # USCITA: 28/10/26
    "https://funside.it/products/sin-city-star-variant-vol-6",  # USCITA: 29/09/26
    "https://funside.it/products/ultimate-impact-reborn-vol-1-variant",  # USCITA: 30/09/26
    "https://funside.it/products/amazing-spider-man-20-spider-man-899-variant-amazing-visions-di-lee-bermejo-19",  # USCITA: 30/09/26
    "https://funside.it/products/amazing-spider-man-20-spider-man-899-variant-amazing-visions-di-lee-bermejo-18",  # USCITA: 30/09/26
    "https://funside.it/products/amazing-spider-man-19-spider-man-898-variant-amazing-visions-di-lee-bermejo",  # USCITA: 30/09/26
    "https://funside.it/products/marvel-miniserie-299-i-dungeon-di-destino-3-doomination-variant-venezia-di-federico-vicentini",  # USCITA: 30/09/26
    "https://funside.it/products/dc-crossover-52-dc-ko-vol-4-variant-di-mike-del-mundo",  # USCITA: 30/09/26
    "https://funside.it/products/dc-crossover-52-dc-ko-vol-4-variant-di-daniel-warren",  # USCITA: 30/09/26
    "https://funside.it/products/dc-facsimile-edition-jla-avengers-1-variant-di-ryan-stegman",  # USCITA: 30/09/26
    "https://funside.it/products/void-rivals-vol-4-variant",  # VOID RIVALS VOL.4 - VARIANT
    "https://funside.it/products/zagor-700-zenith-gigante-751-la-foresta-dei-destini-incrociati-variant",  # ZAGOR 700 (ZENITH GIGANTE 751) - LA FORESTA DEI DESTINI INCROC
    "https://funside.it/products/zagor-indian-circus-variant-giapponese",  # ZAGOR INDIAN CIRCUS - VARIANT GIAPPONESE
    "https://funside.it/products/zodiaco-leo-ortolani-variant-autografata",  # ZODIACO - LEO ORTOLANI - VARIANT AUTOGRAFATA
    # IT - Manga Dreams
    "https://mangadreams.it/products/cthulhu-death-may-die-una-porta-per-yog-sothoth-variant-manicomix",  # CTHULHU - DEATH MAY DIE/ UNA PORTA PER YOG-SOTHOTH - VARIANT M
    # IT - SocialAnime Cofanetti
    "https://www.amazon.it/dp/8869615723?tag=socianim0c-21&linkCode=ogi&th=1&psc=1",  # Box Tutto Attica: Vol. 1-6
    # IT - SocialAnime Variant
    "https://www.amazon.it/dp/8828795204?tag=socianim0c-21&linkCode=ogi&th=1&psc=1",  # Wayne Family Adventures 1 Variant Cover di Simone Di Meo
    # IT - Star Comics (search) [search: collector]
    "https://www.starcomics.com/fumetto/la-casta-dei-meta-baroni-1-collector-edition",  # LA CASTA DEI META-BARONI n. 1 COLLECTOR EDITION
    "https://www.starcomics.com/fumetto/the-plot-holes-collector-edition",  # THE PLOT HOLES COLLECTOR EDITION
    # IT - Star Comics (search) [search: variant]
    "https://www.starcomics.com/fumetto/300-variant-edition",  # 300 VARIANT EDITION
    "https://www.starcomics.com/fumetto/barnstormers-a-ballad-of-love-and-murder-variant-cover-edition",  # BARNSTORMERS: A BALLAD OF LOVE AND MURDER VARIANT COVER EDITIO
    "https://www.starcomics.com/fumetto/valiant-variant-cover-7-bloodshot-4",  # BLOODSHOT n. 4 BLOODSHOT - H.A.R.D. CORPS - VARIANT COVER
    "https://www.starcomics.com/fumetto/valiant-variant-cover-58-britannia-1",  # BRITANNIA n. 1 BRITANNIA - VARIANT COVER DI THEO
    "https://www.starcomics.com/fumetto/valiant-variant-cover-29-faith-1",  # FAITH n. 1 HOLLYWOOD E LA VIGNA - VARIANT COVER
    "https://www.starcomics.com/fumetto/valiant-variant-cover-11-harbinger-6",  # HARBINGER n. 6 HARBINGER - OMEGA - VARIANT COVER
    "https://www.starcomics.com/fumetto/rabbids-1-limited-edition",  # RABBIDS n. 1 BWAAAAAAAAAAH - VARIANT COVER SIO
    "https://www.starcomics.com/fumetto/rabbids-4-variant-cover",  # RABBIDS n. 4 SCARABOCCHI - VARIANT COVER EDITION
    "https://www.starcomics.com/fumetto/valiant-variant-cover-91-x-o-manowar-nuova-serie-4",  # X-O MANOWAR NUOVA SERIE n. 4 VISIGOTO - VARIANT COVER
    # JP - KADOKAWA Store
    "https://store.kadokawa.co.jp/shop/g/g302605000094/",  # アニメ「斉木楠雄のΨ難」きらきら缶バッジコレクション 花ver. BOX
    "https://store.kadokawa.co.jp/shop/g/g302605000134/",  # アニメ「斉木楠雄のΨ難」アクリルカード 花ver. vol.2 BOX
    "https://store.kadokawa.co.jp/shop/g/g7015026102902/",  # アノマリス／ANOMALITH 数量限定 危険区画対策室BOX ファミ通DXパック PS5版
    "https://store.kadokawa.co.jp/shop/g/g7015027029904/",  # ペルソナ4 リバイバル アトラスDショップ限定版 ファミ通DXパック（先着購入特典付き）
    "https://store.kadokawa.co.jp/shop/g/g7015027031803/",  # 悠久幻想曲 2nd Album リバイバル 特装版 ファミ通DXパック オリジナルステッカー特典つき
    # JP - KADOKAWA Store Artbooks Fanbooks
    "https://store.kadokawa.co.jp/shop/g/g302608000771/",  # 『くまのプーさん 100エーカーの森の不思議な物語』 カドスト限定版
    # JP - Rakuten Books (search) [search: 初回限定]
    "https://books.rakuten.co.jp/rb/18526105/?l-id=search-c-item-img-27",  # 吉高由里子 『 しらふ 』【初回限定版】(吉高由里子 イラスト＆メッセージプリント入り栞)
    # JP - Rakuten Books (search) [search: 数量限定]
    "https://books.rakuten.co.jp/rb/16491097/?l-id=search-c-item-img-08",  # 【楽天ブックス限定カバー：サイン付き（数量限定）】ゲッターズ飯田の五星三心占い2021完全版
    # JP - Rakuten Books (search) [search: 特装版]
    "https://books.rakuten.co.jp/rb/18761453/?l-id=search-c-item-img-27",  # コーヒーが冷めないうちに(特装版)
    # JP - Sumikko (限定版・特装版)
    "https://comic.sumikko.info/item-select/1869850009",  # Rakuten×ONE PIECE もこもこポーチ&ハンドタオル セット(お買いものパンダ・小パンダ・ルフィ・チョッパー オ
    "https://comic.sumikko.info/item-select/4797380284",  # いちばん基本の初音ミクV3 マスター ~Piapro Studioで、ボカロPになろう! ~ ショートカット集付き【Amaz
    "https://comic.sumikko.info/item-select/4331252884",  # ガルパンの奇跡 ~"美少女と戦車アニメ"大ヒットの裏側~ 【先行初回限定版】
    "https://comic.sumikko.info/item-select/4777098990",  # ポストカード付き 鉄おも!しんかんせん大集合!【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4062184710",  # 化物語 PremiumアイテムBOX
    "https://comic.sumikko.info/item-select/4845622971",  # 十人の憂鬱な容疑者 素敵なパーティ、死体がふたつ
    "https://comic.sumikko.info/item-select/4065194679",  # 完結記念!期間限定受注製造 五等分の花嫁 A4クリアファイル2枚セット
    "https://comic.sumikko.info/item-select/4862552021",  # 春秋戦国完全ビジュアルガイド 【The Quest For History】【amazon.co.jp限定 ポストカード付き
    # KR - Aladin (만화 한정판)
    "https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=303533024",  # 블랙팬서 히든 젬 패키지 세트 (블랙 팬서 : 둠 워 + 블랙 팬서 : 우리 발아래의 국가 + 한정판
    "https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=188276105",  # 시빌 워 2 스페셜 에디션 (한정판)
    "https://www.aladin.co.kr/shop/wproduct.aspx?ItemId=44114024",  # 열혈강호 피규어 한비광 한정판
    # MX - Panini México (search) [search: portada variante]
    "https://tiendapanini.com.mx/one-world-under-doom-6-portada-variante",  # One World Under Doom #6 (portada Variante)
    "https://tiendapanini.com.mx/one-world-under-doom-7-portada-variante",  # One World Under Doom #7 (Portada Variante)
    "https://tiendapanini.com.mx/one-world-under-doom-8-portada-variante",  # One World Under Doom #8 (Portada Variante)
    # TR - Gerekli Şeyler (varyant)
    "https://www.gerekliseyler.com.tr/urun/what-if-ic-savas-silvestri-varyant",  # What If? İç Savaş - Silvestri Varyant
    # TW - Kadokawa Taiwan (特裝/限定) [search: 典藏]
    "https://www.kadokawa.com.tw/products/4942330216286",  # 預購-《迷宮飯》 壓克力Q版收藏組 BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4942330283165",  # 預購-「TYPE-MOON Ace」迷你小卡收藏組 BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4550687139976",  # 預購-「文豪Stray dogs」貼紙收藏組 BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4550687092998",  # 預購-咒術迴戰 小卡收藏組 回憶篇ver.BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4942330258958",  # 預購-怪獸8號 Pose Pose收藏組 BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4942330214657",  # 預購-怪獸8號 徽章收藏組＋５６ BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4942330214442",  # 預購-怪獸8號 透明夾徽章收藏組 BOX販售【日本進口精品】
    "https://www.kadokawa.com.tw/products/4935228637416",  # 預購-鏈鋸人 迷你File夾收藏組 BOX販售【日本進口精品】
    # TW - Kadokawa Taiwan (特裝/限定) [search: 限定]
    "https://www.kadokawa.com.tw/products/4711289633303",  # 不時輕聲地以俄語遮羞的鄰座艾莉同學(原作) 壓克力色紙 D (台灣角川官網限定)
    "https://www.kadokawa.com.tw/products/4711289633372",  # 預購-不時輕聲地以俄語遮羞的鄰座艾莉同學(原作) 大掛軸 J (會場+官網限定)
    "https://www.kadokawa.com.tw/products/4711289633389",  # 預購-不時輕聲地以俄語遮羞的鄰座艾莉同學(原作) 複製原畫 I (會場+官網限定)
    # TW - Sharp Point 尖端 (especiales)
    "https://www.spp.com.tw/SalePage/Index/10053140",  # 【首刷限量特裝版】這次不遲到！有感筆電超激推100款ROBLOX絕讚遊戲
    # US - Dark Horse Direct (search) [search: deluxe]
    "https://www.darkhorsedirect.com/products/world-of-warcraft-chronicle-hardcover-volumes?_pos=70&_sid=a3db19c5f&_ss=r",  # World of Warcraft: Chronicle Hardcover Volumes
    # US - Dark Horse Direct (search) [search: exclusive]
    "https://www.darkhorsedirect.com/products/critical-role-the-chronicles-of-exandria-the-mighty-nein-part-two-hc-deluxe-edition?_pos=52&_sid=4f443eb6d&_ss=r",  # Critical Role: The Chronicles of Exandria--The Mighty Nein Par
    "https://www.darkhorsedirect.com/products/critical-role-vox-machina-origins-series-i-and-ii-library-edition-hc?_pos=103&_sid=4f443eb6d&_ss=r",  # Critical Role: Vox Machina Origins Series I and II Library Edi
    "https://www.darkhorsedirect.com/products/h-p-lovecrafts-the-dunwich-horror-deluxe-edition-hc?_pos=70&_sid=4f443eb6d&_ss=r",  # H.P. Lovecraft's The Dunwich Horror Deluxe Edition HC
    # US - Dark Horse Direct (search) [search: hardcover]
    "https://www.darkhorsedirect.com/products/critical-role-tales-of-exandria-volume-2-artagan-hc-deluxe-edition?_pos=111&_sid=280db101f&_ss=r",  # Critical Role: Tales of Exandria Volume 2--Artagan HC (Deluxe 
    # US - Dark Horse Direct (search) [search: limited edition]
    "https://www.darkhorsedirect.com/products/art-of-over-the-garden-wall-expanded-edition-hc?_pos=80&_sid=e11deaf78&_ss=r",  # Art of Over the Garden Wall: Expanded Edition HC
    "https://www.darkhorsedirect.com/products/helldivers-2-b-01-tactical-helmet-1-1-scale-replica-battle-damaged-edition?_pos=22&_sid=e11deaf78&_ss=r",  # Helldivers 2: B-01 Tactical Helmet 1:1 Scale Replica - Battle 
    # US - Dark Horse Direct (search) [search: slipcase]
    "https://www.darkhorsedirect.com/products/the-art-of-horizon-forbidden-west-hc-deluxe-edition?_pos=28&_sid=4afc479e7&_ss=r",  # The Art of Horizon Forbidden West HC (Deluxe Edition)
    "https://www.darkhorsedirect.com/products/the-art-of-masters-of-the-universe-origins-and-masterverse-hc-deluxe-edition?_pos=17&_sid=4afc479e7&_ss=r",  # The Art of Masters of the Universe: Origins and Masterverse HC
    "https://www.darkhorsedirect.com/products/the-art-of-the-legend-of-vox-machina-hc-deluxe-edition?_pos=10&_sid=4afc479e7&_ss=r",  # The Art of The Legend of Vox Machina HC (Deluxe Edition)
    "https://www.darkhorsedirect.com/products/the-world-of-cyberpunk-2077-hc-deluxe-edition?_pos=20&_sid=4afc479e7&_ss=r",  # The World of Cyberpunk 2077 HC (Deluxe Edition)
    # US - Dark Horse Direct (search) [search: variant]
    "https://www.darkhorsedirect.com/products/strayed-1-exclusive-variant-comic-bundle?_pos=21&_sid=9925ae96c&_ss=r",  # Strayed #1 Exclusive Variant Comic Bundle
    "https://www.darkhorsedirect.com/products/the-witcher-witchs-lament-1-variant-comic-bundle?_pos=31&_sid=9925ae96c&_ss=r",  # The Witcher: Witch's Lament #1 Exclusive Variant Comic Bundle
    # US - Dark Horse Direct Manga
    "https://www.darkhorsedirect.com/collections/comics/products/the-witcher-library-edition-hardcover-volumes",  # The Witcher Library Edition Hardcover Volumes
    # VN - NXB Kim Đồng (bản đặc biệt)
    "https://nxbkimdong.com.vn/products/boxset-viet-nam-tieu-hoc-tung-thu-4-cuon",  # Boxset Việt Nam tiểu học tùng thư (4 cuốn)
    "https://nxbkimdong.com.vn/products/de-men-phieu-luu-ky-ban-dac-biet",  # Dế Mèn phiêu lưu ký (Bản đặc biệt)
    "https://nxbkimdong.com.vn/products/viet-nam-su-luoc-ban-dac-biet",  # Việt Nam sử lược - Bản đặc biệt
])

# --- Veredicto KEEP resuelto: manga/LN/artbook válido ----------------------
# Se les borra la fila `llm_non_manga` de unmapped_series.jsonl; el item queda
# PENDIENTE (sin `standardized_at`), así la próxima corrida de
# `/watch-standardize-catalog` lo vuelve a proyectar a Tier 2/3 y lo estandariza.
KEEP_RESOLVED_URLS: frozenset[str] = frozenset([
    # DE - Manga-Passion Sonderausgaben
    "https://api.manga-passion.de/volumes/23706",  # Arifureta – Der Kampf zurück in meine Welt (Light Novel, 2-in-
    "https://api.manga-passion.de/volumes/23707",  # Arifureta – Der Kampf zurück in meine Welt (Light Novel, 2-in-
    "https://api.manga-passion.de/volumes/23708",  # Arifureta – Der Kampf zurück in meine Welt (Light Novel, 2-in-
    "https://api.manga-passion.de/volumes/25420",  # The Holy Grail of Eris – Light Novel (2-in-1) Band 1 – Limited
    "https://api.manga-passion.de/volumes/25421",  # The Holy Grail of Eris – Light Novel (2-in-1) Band 1 – Ultra L
    "https://api.manga-passion.de/volumes/26832",  # I'm in Love with the Villainess (Light Novel, 2-in-1) Band 1 –
    "https://api.manga-passion.de/volumes/28882",  # Vom Yakuza zur Villainess: Wiedergeboren in einem Otome Game (
    "https://api.manga-passion.de/volumes/29349",  # Makeine: Too Many Losing Heroines! – (Light Novel, 2-in-1) Ban
    "https://api.manga-passion.de/volumes/29364",  # 7th Time Loop: The Villainess Enjoys a Carefree Life Married t
    "https://api.manga-passion.de/volumes/33288",  # I'm in Love with the Villainess (Light Novel, 2-in-1) Band 2 –
    # JP - Rakuten Books (search) [search: グッズ付き]
    "https://books.rakuten.co.jp/rb/17580887/?l-id=search-c-item-img-13",  # ＃コンパス ヒーロー観察記録 グッズ付き特装版 （角川ビーンズ文庫）
    "https://books.rakuten.co.jp/rb/18607548/?l-id=search-c-item-img-03",  # 魔導具師ダリヤはうつむかない 〜今日から自由な職人ライフ〜15 グッズ付き特装版 （MFブックス）
    # JP - Rakuten Books (search) [search: 特装版]
    "https://books.rakuten.co.jp/rb/18659086/?l-id=search-c-item-img-14",  # オルクセン王国史〜野蛮なオークの国は、如何にして平和なエルフの国を焼き払うに至ったか〜7 小冊子付き特装版 （サーガフォレス
    "https://books.rakuten.co.jp/rb/18698362/?l-id=search-c-item-img-29",  # 異世界はスマートフォンとともに。32 ドラマCD付き特装版 （HJ NOVELS）
    "https://books.rakuten.co.jp/rb/18703361/?l-id=search-c-item-img-19",  # 無職転生 〜蛇足編〜4 グッズ付き特装版 （MFブックス）
    # JP - Sumikko (限定版・特装版)
    "https://comic.sumikko.info/item-select/2100011938014",  # 小説 きみは面倒な婚約者
    "https://comic.sumikko.info/item-select/4040701712",  # 棺姫のチャイカXII Blu-ray付き限定版
    "https://comic.sumikko.info/item-select/4041006856",  # 問題児たちが異世界から来るそうですよ? 暴虐の三頭龍 オリジナルアニメ ブルーレイ同梱版 (角川スニーカー文庫)
    "https://comic.sumikko.info/item-select/4041007739",  # 首の姫と首なし騎士 裏切りの婚約者
    "https://comic.sumikko.info/item-select/4041010535",  # 俺の脳内選択肢が、学園ラブコメを全力で邪魔している 8 ブルーレイ付き同梱版
    "https://comic.sumikko.info/item-select/4041010721",  # タクミくんシリーズ Station 小冊子付き特装版 (角川ルビー文庫)
    "https://comic.sumikko.info/item-select/4047289736",  # 特装版 犬とハサミは使いよう7 (ファミ通文庫)
    "https://comic.sumikko.info/item-select/4047291765",  # ログ・ホライズン7 供贄の黄金 【ドラマCD付特装版】
    "https://comic.sumikko.info/item-select/4063584372",  # アーク9 2 セフィロトの魔導士(上) オリジナルBlu-rayアニメーション付き特装版 (講談社ラノベ文庫 や 2-1-2
    "https://comic.sumikko.info/item-select/4063584585",  # おジャ魔女どれみ17 ドラマCD付き限定版 (講談社ラノベ文庫 と 1-2-1)
    "https://comic.sumikko.info/item-select/4063584925",  # CD付き 彼女がフラグをおられたら 今までこの初詣のお守りのお陰で何回も命拾いしたんだ、これ貸してやるよ 限定版 (講談社キ
    "https://comic.sumikko.info/item-select/4065193141",  # CD付き ヒプノシスマイク -Before The Battle- The Dirty Dawg(3)限定版
    "https://comic.sumikko.info/item-select/4065194253",  # CD付き ヒプノシスマイク -Division Rap Battle- side B.B & M.T.C(3)限定版
    "https://comic.sumikko.info/item-select/4072901857",  # 竜殺しの過ごす日々 1-6巻セット
    "https://comic.sumikko.info/item-select/4072901911",  # 異世界迷宮でハー◯ムを 1-2巻セット
    "https://comic.sumikko.info/item-select/4072902004",  # 理想のヒモ生活 1-3巻セット
    "https://comic.sumikko.info/item-select/4086149052",  # 『贅沢な身の上』書きおろしSSつき1~5巻セット (コバルト文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4086149060",  # 『鬼舞』イラストカードつき1~5巻セット (コバルト文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4086149079",  # 『ひみつの陰陽師』書きおろしSSつき全8巻セット (コバルト文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4086149087",  # 『悪魔のような花婿』イラストカードつき全10巻セット (コバルト文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4086309416",  # 『カンピオーネ! 』イラストカード付き1~5巻セット (スーパーダッシュ文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4089070457",  # パパのいうことを聞きなさい! 16 ドラマCD付予約限定版 (集英社スーパーダッシュ文庫 ま)
    "https://comic.sumikko.info/item-select/4094514538",  # やはり俺の青春ラブコメはまちがっている。8 イラスト集付き限定特装版 (ガガガ文庫)
    "https://comic.sumikko.info/item-select/4199007296",  # FLESH&BLOOD21 (キャラ文庫)【Amazon co.jp限定 書きおろしショートストーリー付き】
    "https://comic.sumikko.info/item-select/4199007539",  # 暴君竜を飼いならせ 書き下ろしショートストーリー付き (キャラ文庫)【Amazon co.jp限定】
    "https://comic.sumikko.info/item-select/4199007547",  # 制服と王子 書き下ろしショートストーリー付き (キャラ文庫)【Amazon co.jp限定】
    "https://comic.sumikko.info/item-select/4199007555",  # 予言者は眠らない 書き下ろしショートストーリー付き (キャラ文庫)【Amazon co.jp限定】
    "https://comic.sumikko.info/item-select/4199007628",  # FLESH&BLOOD 22 書き下ろしショートストーリー付き (キャラ文庫)【Amazon co.jp限定】
    "https://comic.sumikko.info/item-select/4199007636",  # 不響和音 二重螺旋9 書き下ろしショートストーリー付き (キャラ文庫)【Amazon co.jp限定】
    "https://comic.sumikko.info/item-select/4758044643",  # 俺がお嬢様学校に「庶民サンプル」として拉致られた件7 ドラマCD付特装版 (一迅社文庫)
    "https://comic.sumikko.info/item-select/4758045518",  # 10歳の保健体育7 特装版 (一迅社文庫)
    "https://comic.sumikko.info/item-select/4797373601",  # ダンジョンに出会いを求めるのは間違っているだろうか3 書き下ろし短編小説&ゲストイラスト集付き限定版 (GA文庫)
    "https://comic.sumikko.info/item-select/4797373644",  # うちの居候が世界を掌握している! 4
    "https://comic.sumikko.info/item-select/4797375159",  # ダンジョンに出会いを求めるのは間違っているだろうか4 小冊子付き限定版 (GA文庫)
    "https://comic.sumikko.info/item-select/4797375213",  # のうりん 7
    "https://comic.sumikko.info/item-select/4797375515",  # 最弱無敗の神装機竜《バハムート》2 書き下ろし小冊子付き (GA文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4797375574",  # 聖剣使いの禁呪詠唱<ワールドブレイク> 6 ドラマCD付き限定特装版 (GA文庫)
    "https://comic.sumikko.info/item-select/4797375582",  # のうりん8 ドラマCD付き限定特装版 (GA文庫)
    "https://comic.sumikko.info/item-select/4797375590",  # 這いよれ! ニャル子さん 12 ドラマCD付き限定特装版 (GA文庫)
    "https://comic.sumikko.info/item-select/4797376813",  # 神楽剣舞のエアリアル 書き下ろし4PリーフレットSS付き (GA文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4797377348",  # 俺の彼女と幼なじみが修羅場すぎる8 ドラマCD付き限定特装版+書き下ろし4PリーフレットSS付き (GA文庫)【Amazon
    "https://comic.sumikko.info/item-select/4797377534",  # のうりん 9 書き下ろし4PリーフレットSS付き (GA文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4797377909",  # 異能バトルは日常系のなかで 7 書き下ろし4PリーフレットSS付き (GA文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4797377925",  # 落第騎士の英雄譚(キャバルリィ)5 書き下ろし4PリーフレットSS付き (GA文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4797380160",  # 聖剣使いの禁呪詠唱<ワールドブレイク>8 書き下ろし4PリーフレットSS付き (GA文庫)【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4797380500",  # ファタモルガーナの館-The house in Fata morgana- あなたの原典に至る物語I 書き下ろし4Pリーフレ
    "https://comic.sumikko.info/item-select/4799711946",  # アマゾン限定特典付 小説 ファインダーの烙印
    "https://comic.sumikko.info/item-select/4829197692",  # 生徒会の祝日 Blu-ray付き限定版 碧陽学園生徒会黙示録8 (単行本)
    "https://comic.sumikko.info/item-select/4829679255",  # 美少女文庫 みかづき紅月3点セット 美少女カレンダー4枚組付き【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4829679263",  # 美少女文庫 山口陽3点セット 美少女カレンダー4枚組付き【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4829679271",  # 美少女文庫 遠野渚3点セット 美少女カレンダー4枚組付き【Amazon.co.jp限定】
    "https://comic.sumikko.info/item-select/4864721815",  # 魔術士オーフェンはぐれ旅 女神未来(上)【ドラマCD付 初回限定版】
    # IT - Funside Variant
    "https://funside.it/products/il-richiamo-di-cthulhu-lovecraft-edizione-deluxe-ed-variant-funside",  # IL RICHIAMO DI CTHULHU - LOVECRAFT - EDIZIONE DELUXE - ED.VARI
    # PL - Mangastore (twarda)
    "https://mangastore.pl/twoje-imie-ln-twarda-oprawa-p-8024.html",  # twoje imię. (LN) twarda oprawa
    # VN - NXB Kim Đồng (bản đặc biệt)
    "https://nxbkimdong.com.vn/products/chua-te-bong-toi-light-novel-tap-1-ban-gioi-han-tang-kem-the-nhan-vat-mini-clearfile",  # Chúa tể bóng tối (Light-novel) - Tập 1 - Bản giới hạn (Tặng kè
    # EN - Otaku Calendar
    "https://otakucalendar.com/Release/22858/grandmaster-of-demonic-cultivation-mo-dao-zu-shi-deluxe-hardcover-novel-volume-5",  # Grandmaster of Demonic Cultivation: Mo Dao Zu Shi (Deluxe Hard
    "https://otakucalendar.com/Release/24491/little-mushroom-deluxe-hardcover-novel-volume-1-manga-us",  # Little Mushroom (Deluxe Hardcover Novel) Volume 1
    "https://otakucalendar.com/Release/24519/ballad-of-sword-and-wine-qiang-jin-jiu-novel-volume-8-special-edition-manga-us",  # Ballad of Sword and Wine: Qiang Jin Jiu (Novel) Volume 8 (Spec
    "https://otakucalendar.com/Release/24879/panguan-the-twelfth-gate-novel-volume-1-special-edition-manga-us",  # Panguan: The Twelfth Gate (Novel) Volume 1 (Special Edition)
    # US - Seven Seas (ediciones especiales)
    "https://sevenseasentertainment.com/books/case-file-compendium-bing-an-ben-novel-vol-10-special-edition/",  # Case File Compendium: Bing An Ben (Novel) Vol. 10 (Special Edi
    # IT - SocialAnime Cofanetti
    "https://www.amazon.it/dp/8834915445?tag=socianim0c-21&linkCode=ogi&th=1&psc=1",  # Death stranding. Collection box (Vol. 1-2)
    # IT - SocialAnime Variant
    "https://www.amazon.it/dp/B0FT86NZK2?tag=socianim0c-21",  # no game no life - cofanetto limited edition
    # TW - Kadokawa Taiwan (特裝/限定) [search: 典藏]
    "https://www.kadokawa.com.tw/products/4711289626787",  # 歡迎來到實力至上主義的教室 2年級篇 (12.5) （全套收納BOX典藏版）
    # TW - Kadokawa Taiwan (特裝/限定) [search: 限定]
    "https://www.kadokawa.com.tw/products/4711289631231",  # 86─不存在的戰區─(Ep.14) ─Paint it black─（限定版）【7月下旬出貨】
    # Manga-Sanctuary (planning)
    "https://www.manga-sanctuary.com/light-novel-the-husky-and-his-white-cat-shizun-vol-1-collector-s76663-p434348.html",  # The Husky and His White Cat Shizun 1
    "https://www.manga-sanctuary.com/light-novel-the-husky-and-his-white-cat-shizun-vol-2-collector-s76663-p434451.html",  # The Husky and His White Cat Shizun 2
    "https://www.manga-sanctuary.com/light-novel-the-husky-and-his-white-cat-shizun-vol-3-collector-s76663-p444715.html",  # The Husky and His White Cat Shizun 3
    "https://www.manga-sanctuary.com/light-novel-une-fleur-venue-d-ailleurs-vol-1-coffret-s77230-p436208.html",  # Une fleur venue d'ailleurs
    # JP - Sanyodo Comic Limited Editions
    "https://www.sanyodo.co.jp/?s=978-4-04-660537-5",  # 無職転生 ～蛇足編～４ 特装版
    "https://www.sanyodo.co.jp/?s=978-4-7580-9802-1",  # ふつつかな悪女ではございますが１２ ～雛宮蝶鼠とりかえ伝～ 特装版
    "https://www.sanyodo.co.jp/?s=978-4-8156-4011-8",  # お隣の天使様にいつの間にか駄目人間にされていた件１２ 特装版
    "https://www.sanyodo.co.jp/?s=978-4-8156-4012-5",  # お隣の天使様にいつの間にか駄目人間にされていた件１２ 特装版
])

# --- KEEP pero INCIERTO: se conservan Y siguen flageados -------------------
# (no se tocan ni en items.jsonl ni en unmapped_series.jsonl)
KEEP_UNCERTAIN_URLS: frozenset[str] = frozenset([
    # IT - Funside Variant
    "https://funside.it/products/dark-souls-cofanetto-variant-funside-voll-1-5",  # DARK SOULS - COFANETTO VARIANT FUNSIDE (VOLL.1-5)
    "https://funside.it/products/jagua-tales-vol-2-ita-italian-variant",  # JAGUA TALES VOL.2 ITA - ITALIAN VARIANT
    "https://funside.it/products/jagua-tales-vol-2-ita-nsfw-variant",  # JAGUA TALES VOL.2 ITA - NSFW VARIANT
    "https://funside.it/products/nine-stones-3-deluxe-variant-con-cofanetto-vuoto",  # NINE STONES 3 DELUXE VARIANT - CON COFANETTO VUOTO
    # VN - NXB Kim Đồng (bản đặc biệt)
    "https://nxbkimdong.com.vn/products/kamishibai-ke-chuyen-bang-tranh-de-den-dung-cam-ban-dac-biet",  # Kamishibai - Kể chuyện bằng tranh - Dê Đen dũng cảm (Bản đặc b
    "https://nxbkimdong.com.vn/products/kamishibai-ke-chuyen-bang-tranh-to-to-to-len-ban-dac-biet",  # Kamishibai - Kể chuyện bằng tranh - To, to, to lên! (Bản đặc b
    # TH - Siam Inter / yaakz (box sets)
    "https://www.yaakz.com/product/yaakz-collector-box-ขนาด-กว้าง-16-x-ยาว-42-x-สูง-22",  # YAAKZ Collector Box (ขนาด กว้าง 16 x ยาว 42 x สูง 22)
])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--apply", action="store_true",
                    help="Escribe los cambios (por defecto: dry-run).")
    ap.add_argument("--include-approved", action="store_true",
                    help="Procesar también items aprobados (golden records).")
    args = ap.parse_args()

    rows = [json.loads(l) for l in ITEMS.read_text(encoding="utf-8").splitlines() if l.strip()]
    kept: list[dict] = []
    removed: list[dict] = []
    skipped_approved = 0
    for it in rows:
        if it.get("url") in EXPEL_URLS:
            if is_approved(it) and not args.include_approved:
                skipped_approved += 1
                kept.append(it)
                continue
            removed.append(it)
            continue
        kept.append(it)

    # Cola de inciertos: se limpian las filas llm_non_manga de TODOS los
    # curados como EXPEL (incluidos los que `filter_non_manga.py` ya expulsó en
    # el paso anterior — si sólo miráramos las filas que borra ESTE script, las
    # ~90 del gate determinista quedarían huérfanas en la cola) y las de los
    # KEEP ya resueltos. Todo lo demás (otras reasons, inciertos, y un EXPEL
    # salteado por `approved_at`) se conserva.
    kept_urls = {it.get("url") for it in kept}
    drop_from_queue = (set(EXPEL_URLS) - kept_urls) | set(KEEP_RESOLVED_URLS)
    q_lines = [l for l in UNMAPPED.read_text(encoding="utf-8").splitlines() if l.strip()]
    q_keep: list[str] = []
    q_dropped = 0
    for line in q_lines:
        try:
            d = json.loads(line)
        except Exception:
            q_keep.append(line)
            continue
        if d.get("reason") == "llm_non_manga" and d.get("sample_url") in drop_from_queue:
            q_dropped += 1
            continue
        q_keep.append(line)

    print(f"[INFO] items.jsonl: {len(rows)} → {len(kept)} ({len(removed)} expulsados)")
    if skipped_approved:
        print(f"[INFO] {skipped_approved} aprobados saltados (usa --include-approved)")
    print(f"[INFO] unmapped_series.jsonl: {len(q_lines)} → {len(q_keep)} ({q_dropped} filas resueltas)")
    print(f"[INFO] KEEP inciertos que siguen flageados: {len(KEEP_UNCERTAIN_URLS)}")

    if not args.apply:
        print("[DRY-RUN] No se escribió nada. Usá --apply.")
        return 0
    if not removed and not q_dropped:
        print("[OK] Nada que hacer (idempotente).")
        return 0

    if removed:
        backup_and_rotate(ITEMS, "curate-llm-nonmanga")
        DIAG.parent.mkdir(parents=True, exist_ok=True)
        if DIAG.exists():
            backup_and_rotate(DIAG, "curate-llm-nonmanga-rejected")
        write_lines_atomic(DIAG, [json.dumps(it, ensure_ascii=False) for it in removed])
        print(f"[OK] Evidencia de los expulsados en {DIAG}")
        write_items_atomic(ITEMS, kept)
        print(f"[OK] items.jsonl reescrito con {len(kept)} filas.")
    if q_dropped:
        backup_and_rotate(UNMAPPED, "curate-llm-nonmanga-queue")
        write_lines_atomic(UNMAPPED, q_keep)
        print(f"[OK] unmapped_series.jsonl reescrito con {len(q_keep)} filas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
