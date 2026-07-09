"""Tests para los 5 fixes de ingestión en manga_watch (work order 2026-07-07).

Cubre:
  1. Bloque de keywords portugués (PT-BR) + "Edição" en los patrones X-Edition
     + stoplist de genéricos PT + keywords tailandesas nuevas.
  2. Guard en _strip_korean_retailer_tail (no colapsar al marcador desnudo).
  3. fsync en append_jsonl (durabilidad del write atómico).
  4. Fill-if-empty para isbn/author/release_date en items RAW del upsert.
  5. Clave fuzzy de cluster por PAÍS (no idioma) + guard de country vacío.
"""

from __future__ import annotations

import json
from pathlib import Path

from scripts import manga_watch as mw


# ---------------------------------------------------------------------------
# Fix 1 — Portugués (PT-BR) en KEYWORD_RULES + Edição + stoplist + TH
# ---------------------------------------------------------------------------

def test_pt_edicao_limitada_detecta_limited():
    _, phrases, types = mw.detect_signals("Berserk Edição Limitada")
    assert "limited" in types


def test_pt_edicao_especial_detecta_special():
    _, _, types = mw.detect_signals("Naruto Edição Especial")
    assert "special_edition" in types


def test_pt_edicao_colecionador_detecta_collector():
    _, _, types = mw.detect_signals("One Piece Edição de Colecionador")
    assert "collector" in types


def test_pt_capa_dura_detecta_hardcover():
    _, _, types = mw.detect_signals("Vagabond capa dura")
    assert "hardcover" in types


def test_pt_box_detecta_box_set():
    _, _, types = mw.detect_signals("Naruto Box Completo")
    assert "box_set" in types


def test_pt_luva_detecta_box_set():
    _, _, types = mw.detect_signals("Berserk edição com luva")
    assert "box_set" in types


def test_pt_estojo_caixa_detecta_box_set():
    _, _, t1 = mw.detect_signals("Death Note estojo especial")
    _, _, t2 = mw.detect_signals("Bleach caixa de colecionador")
    assert "box_set" in t1
    assert "box_set" in t2


def test_pt_sobrecapa_detecta_bonus():
    _, _, types = mw.detect_signals("Dragon Ball com sobrecapa reversível")
    assert "bonus" in types


def test_pt_brindes_sigue_siendo_bonus():
    # "brindes" (portugués) se movió/duplicó a la sección PT pero la regla
    # sigue existiendo en el ruleset.
    _, _, types = mw.detect_signals("Slam Dunk com brindes")
    assert "bonus" in types


def test_box_word_boundary_no_falso_positivo():
    # "box" con word-boundary NO debe matchear dentro de "sandbox"/"boxing".
    _, _, types = mw.detect_signals("Sandbox Chronicles boxing legends")
    assert "box_set" not in types


def test_pt_word_no_generico_no_dispara_collectible():
    # "Primeira Edição" = reimpresión estándar, NO coleccionable.
    ok, reason = mw.is_collectible_edition(
        "One Piece Primeira Edição", "", [], "book", isbn="", url="")
    assert ok is False


def test_pt_nova_edicao_no_dispara_collectible():
    ok, _ = mw.is_collectible_edition(
        "Naruto Nova Edição", "", [], "book", isbn="", url="")
    assert ok is False


def test_edicao_pasa_patron_x_edition():
    # Un lore-word + "Edição" dispara el patrón generalista X-Edition.
    m = mw._GENERIC_X_EDITION_PATTERN.search("Vinland Saga Tribute Edição")
    assert m is not None
    assert m.group(1).lower() == "tribute"


def test_edicao_x_edition_es_collectible():
    ok, reason = mw.is_collectible_edition(
        "Vinland Saga Tribute Edição", "", [], "book", isbn="", url="")
    assert ok is True
    assert reason.startswith("x_edition:")


def test_edicao_en_patron_strong_manga():
    # El patrón STRONG (manga-hint) también acepta "<word> Edição": un título
    # PT con lore-word + Edição, sin vol/tomo ni kanji, cuenta como manga.
    assert any(p.search("Zoro Tarot Edição") for p in mw._STRONG_MANGA_PATTERNS)


def test_edicao_strong_hace_manga_a_titulo_pt():
    # Integración: is_likely_manga acepta el título PT vía el STRONG hint.
    ok, _reason = mw.is_likely_manga("Zoro Tarot Edição", source_purity="manga_only")
    assert ok is True


def test_th_edicion_limitada_detecta_limited():
    _, _, types = mw.detect_signals("การ์ตูน ฉบับจำกัด")
    assert "limited" in types


def test_th_box_set_detecta_box_set():
    _, _, types = mw.detect_signals("มังงะ บ็อกซ์เซ็ต")
    assert "box_set" in types


# ---------------------------------------------------------------------------
# Fix 2 — Guard en _strip_korean_retailer_tail
# ---------------------------------------------------------------------------

def test_kr_guard_conserva_titulo_cuando_colapsaria_al_marcador():
    # Título con marcador al inicio + cola de tienda: el recorte dejaría solo
    # "한정판" (3 chars → luego title_too_short). El guard conserva el original.
    title = "한정판 홍길동 (지은이) | 학산문화사 15,000원"
    out = mw._strip_korean_retailer_tail(title)
    assert out != "한정판"
    assert len(out) > len("한정판")


def test_kr_guard_recorte_normal_sigue_funcionando():
    # Serie ANTES del marcador: el recorte legítimo debe seguir ocurriendo.
    title = "블루록 5 (한정판) - 홍길동 (지은이) 15,000원"
    out = mw._strip_korean_retailer_tail(title)
    assert "블루록" in out
    assert "한정판" in out
    assert "지은이" not in out  # la cola de tienda sí se recortó


def test_kr_guard_marcador_desnudo_no_vacio():
    out = mw._strip_korean_retailer_tail("한정판")
    assert out  # no vacío
    assert "한정판" in out


# ---------------------------------------------------------------------------
# Fix 3 — fsync en append_jsonl (durabilidad)
# ---------------------------------------------------------------------------

def test_append_jsonl_escribe_atomicamente(tmp_path, monkeypatch):
    # Verificamos que fsync se invoca durante el write atómico.
    calls: list[int] = []
    real_fsync = mw.os.fsync
    monkeypatch.setattr(mw.os, "fsync", lambda fd: calls.append(fd) or real_fsync(fd))
    path = tmp_path / "items.jsonl"
    mw.append_jsonl(path, [{"url": "https://ex/a", "title": "Berserk 1"}])
    assert path.exists()
    assert calls, "os.fsync no fue invocado en append_jsonl"


# ---------------------------------------------------------------------------
# Fix 4 — Fill-if-empty para isbn/author/release_date en items RAW
# ---------------------------------------------------------------------------

def _read_rows(path: Path) -> list[dict]:
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _row_by_url(rows: list[dict], url: str) -> dict:
    key = mw.normalize_url_for_dedup(url)
    for r in rows:
        srcs = r.get("sources") or []
        urls = [s.get("url", "") for s in srcs] + [r.get("url", "")]
        if any(mw.normalize_url_for_dedup(u) == key for u in urls if u):
            return r
    raise AssertionError(f"no row for {url}")


def test_fill_if_empty_conserva_viejo(tmp_path):
    url = "https://ex/raw1"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "Berserk 1", "country": "Japan",
           "isbn": "9781234567897", "author": "Kentaro Miura",
           "release_date": "2020-01-01"}
    mw.append_jsonl(path, [old])
    # Re-scrape SIN isbn/author/release_date.
    new = {"url": url, "title": "Berserk 1", "country": "Japan",
           "price": "€10", "stock_type": "in_stock"}
    mw.append_jsonl(path, [new])
    row = _row_by_url(_read_rows(path), url)
    assert row["isbn"] == "9781234567897"
    assert row["author"] == "Kentaro Miura"
    assert row["release_date"] == "2020-01-01"


def test_fill_if_empty_gana_nuevo(tmp_path):
    url = "https://ex/raw2"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "Naruto 1", "country": "Japan",
           "isbn": "9780000000001", "author": "Old Author"}
    mw.append_jsonl(path, [old])
    new = {"url": url, "title": "Naruto 1", "country": "Japan",
           "isbn": "9789999999999", "author": "Masashi Kishimoto"}
    mw.append_jsonl(path, [new])
    row = _row_by_url(_read_rows(path), url)
    assert row["isbn"] == "9789999999999"
    assert row["author"] == "Masashi Kishimoto"


def test_fill_if_empty_no_toca_item_estandarizado(tmp_path):
    # Un item con standardized_at pasa por la rama sticky (elif), no por el
    # else de fill-if-empty. Los campos curados se preservan y el re-scrape
    # RAW no los degrada.
    url = "https://ex/std1"
    path = tmp_path / "items.jsonl"
    old = {"url": url, "title": "One Piece Kanzenban", "country": "Japan",
           "standardized_at": "2026-06-01", "edition_key": "op-kanzenban-jp",
           "volume": "1", "series_display": "One Piece",
           "isbn": "9788899999999", "author": "Eiichiro Oda"}
    mw.append_jsonl(path, [old])
    new = {"url": url, "title": "One Piece 1", "country": "Japan"}  # RAW, sin nada
    mw.append_jsonl(path, [new])
    row = _row_by_url(_read_rows(path), url)
    assert row.get("standardized_at") == "2026-06-01"
    assert row.get("edition_key") == "op-kanzenban-jp"
    assert row.get("series_display") == "One Piece"


# ---------------------------------------------------------------------------
# Fix 5 — Clave fuzzy por PAÍS + guard de country vacío
# ---------------------------------------------------------------------------

def test_fuzzy_usa_country_no_language():
    key = mw.derive_cluster_key({
        "title": "Berserk 5", "country": "España", "language": "es",
        "publisher": "Norma"})
    assert key.startswith("fuzzy:")
    assert "espana" in key or "españa" in key
    # NO debe usar el código de idioma "es" como primer campo.
    assert not key.startswith("fuzzy:es|")


def test_fuzzy_country_distingue_ediciones_mismo_idioma():
    # ES-España y ES-México comparten idioma pero son ediciones distintas
    # (regla dura país=edición): deben caer en claves DISTINTAS.
    a = mw.derive_cluster_key({
        "title": "Berserk 5", "country": "España", "language": "es",
        "publisher": "Norma"})
    b = mw.derive_cluster_key({
        "title": "Berserk 5", "country": "México", "language": "es",
        "publisher": "Norma"})
    assert a != b


def test_fuzzy_country_vacio_cae_a_url():
    key = mw.derive_cluster_key({
        "title": "Berserk 5", "country": "", "language": "es",
        "publisher": "Norma", "url": "https://ex/berserk-5"})
    assert key.startswith("url:")


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (bis) — Anti-bot mínimo sistemático (item 1)
# ---------------------------------------------------------------------------

def test_detect_challenge_cloudflare_structural():
    for h in (
        '<meta name="cf-chl-bypass" content="x">',
        '<script>window.__cf_chl_rt_tk="abc"</script>',
        '<script src="/cdn-cgi/challenge-platform/h/g/orchestrate/chl_page/v1"></script>',
    ):
        assert mw.detect_challenge(h) == "cloudflare", h


def test_detect_challenge_text_markers_short_page():
    assert mw.detect_challenge("<html><body>Just a moment...</body></html>") == "challenge"
    assert mw.detect_challenge("<html>Checking your browser before accessing</html>") == "challenge"
    assert mw.detect_challenge("<title>Access Denied</title>") == "challenge"


def test_detect_challenge_none_for_legit_and_big():
    assert mw.detect_challenge("<html><body>contenido real</body></html>") is None
    assert mw.detect_challenge("") is None
    # El JSD bot-detection (/scripts/, no /h/) NO es un challenge.
    assert mw.detect_challenge(
        '<script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script>'
    ) is None
    # Página grande (>50KB) con la frase en el body → contenido real, no challenge.
    big = "<html>" + ("x" * 60000) + " just a moment </html>"
    assert mw.detect_challenge(big) is None


def test_detect_challenge_accepts_status_arg():
    # `status` se acepta (para futuros WAFs) sin alterar la decisión hoy.
    assert mw.detect_challenge("<html>Access denied</html>", status=403) == "challenge"


def test_blocked_403_error_is_exception():
    assert issubclass(mw.Blocked403Error, Exception)


def test_problem_categories_include_antibot():
    # El resumen/reporte distingue challenge y 403 (no se confunden con vacías).
    assert "challenge" in mw.PROBLEM_CATEGORY_LABELS
    assert "blocked-403" in mw.PROBLEM_CATEGORY_LABELS
    assert "challenge" in mw.PROBLEM_CATEGORY_ORDER
    assert "blocked-403" in mw.PROBLEM_CATEGORY_ORDER


class _FakeResp:
    def __init__(self, status=200, text="<html>ok</html>", headers=None, url="http://x"):
        self.status_code = status
        self.text = text
        self.headers = headers or {"Content-Type": "text/html"}
        self.url = url
        self.encoding = "utf-8"
        self.apparent_encoding = "utf-8"

    def raise_for_status(self):
        if self.status_code >= 400:
            err = mw.requests.HTTPError(f"HTTP {self.status_code}")
            err.response = self
            raise err


class _FakeSession:
    def __init__(self, resp):
        self.resp = resp
        self.calls: list[dict] = []

    def get(self, url, timeout=None, headers=None):
        self.calls.append({"url": url, "headers": headers})
        return self.resp


def test_fetch_with_metadata_applies_per_source_user_agent():
    sess = _FakeSession(_FakeResp())
    _text, meta = mw.fetch_with_metadata(sess, "http://x", (5, 5), user_agent="MyUA/1.0")
    assert sess.calls[0]["headers"] == {"User-Agent": "MyUA/1.0"}
    assert meta["http_status"] == 200


def test_fetch_with_metadata_no_ua_passes_none_headers():
    sess = _FakeSession(_FakeResp())
    mw.fetch_with_metadata(sess, "http://x", (5, 5))
    # Sin UA per-source: no se fuerza header (usa el UA de la sesión).
    assert sess.calls[0]["headers"] is None


def test_source_user_agent_default_empty():
    s = mw.Source(name="x", url="y")
    assert s.user_agent == ""


def test_load_sources_reads_user_agent(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(
        "sources:\n"
        "  - name: Test\n"
        "    url: https://ex.test/\n"
        "    user_agent: 'Mozilla/5.0 custom'\n",
        encoding="utf-8",
    )
    srcs = mw.load_sources(p)
    assert len(srcs) == 1
    assert srcs[0].user_agent == "Mozilla/5.0 custom"


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (bis) — Persistir original_title (item 2)
# ---------------------------------------------------------------------------

def _min_candidate(**over):
    base = dict(
        title="ワンピース 100", url="x", source="JP - Rakuten", source_url="y",
        country="Japón", language="Japonés", publisher="Shueisha",
        source_class="retailer", tags=[], description="",
    )
    base.update(over)
    return mw.Candidate(**base)


def test_candidate_to_json_persists_original_title():
    c = _min_candidate()
    c.original_title = "ONE PIECE 100"   # atributo dinámico (como edition_display)
    row = mw.candidate_to_json(c)
    assert row.get("original_title") == "ONE PIECE 100"


def test_candidate_to_json_omits_empty_original_title():
    c = _min_candidate()
    row = mw.candidate_to_json(c)
    assert "original_title" not in row
    # No confundir con title_original (gotcha #93), que SÍ está siempre.
    assert "title_original" in row


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (bis) — Normalización de ISBN (item 3)
# ---------------------------------------------------------------------------

def test_normalize_isbn_strips_fullwidth_colon():
    # "： " (U+FF1A + espacio) es el prefijo basura típico de fuentes JP.
    # (ISBN-13 real y válido; el normalizador real exige checksum, 2026-07-08.)
    assert mw.normalize_isbn("： 9781506711980") == "9781506711980"


def test_normalize_isbn_strips_hyphens_and_spaces():
    assert mw.normalize_isbn("978-1-5067-1198-0") == "9781506711980"
    assert mw.normalize_isbn("  9781506711980  ") == "9781506711980"


def test_normalize_isbn_uppercases_x_and_converts_10():
    # X solo válida como dígito de control de ISBN-10; x→X y 10→13.
    assert mw.normalize_isbn("0-8044-2957-x") == "9780804429573"


def test_normalize_isbn_idempotent():
    assert mw.normalize_isbn("9781506711980") == "9781506711980"


def test_normalize_isbn_empty_and_only_junk():
    assert mw.normalize_isbn("") == ""
    assert mw.normalize_isbn("： ") == ""


def test_normalize_isbn_anomaly_returns_cleaned(capsys):
    # Longitud != 10/13: NO se descarta (puede ser parcial útil), se devuelve
    # limpio y se loguea ISBN_ANOMALY a stderr (B5: no contaminar stdout, que
    # es salida parseable — función de librería llamada por ítem).
    assert mw.normalize_isbn("： 12345") == "12345"
    assert "ISBN_ANOMALY" in capsys.readouterr().err


def test_candidate_to_json_normalizes_isbn():
    c = _min_candidate(title="Berserk 1", isbn="： 9784592143741")
    row = mw.candidate_to_json(c)
    assert row["isbn"] == "9784592143741"


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (run delta) — Fix 1: "box" en nombre propio NO es box_set
# ---------------------------------------------------------------------------

# --- POSITIVOS: construcción de producto DEBE seguir señalando box_set ---

def test_box_construction_box_de_manga():
    _, _, types = mw.detect_signals("Box de Mangá One Piece")
    assert "box_set" in types


def test_box_construction_box_completo_sigue_detectando():
    # Test existente reforzado: "Naruto Box Completo" = construcción → box_set.
    _, _, types = mw.detect_signals("Naruto Box Completo")
    assert "box_set" in types


def test_box_construction_one_piece_box_ep():
    _, _, types = mw.detect_signals("One Piece BOX EP.1")
    assert "box_set" in types


def test_box_construction_con_box_preposicion():
    _, _, types = mw.detect_signals("Berserk edición con box")
    assert "box_set" in types


def test_box_set_keyword_propia_sigue_funcionando():
    _, _, types = mw.detect_signals("Naruto Box Set 1")
    assert "box_set" in types


def test_coffret_keyword_no_afectada():
    _, _, types = mw.detect_signals("Demon Slayer Coffret Collector")
    assert "box_set" in types


def test_cofanetto_keyword_no_afectada():
    _, _, types = mw.detect_signals("Lone Wolf & Cub Omnibus – Cofanetto 3")
    assert "box_set" in types


def test_cofre_listadomanga_no_se_rompe():
    # El formato "en cofre" de ListadoManga (keyword "cofre" propia) sigue intacto.
    _, _, types = mw.detect_signals("One Piece edición en cofre")
    assert "box_set" in types


# --- NEGATIVOS: nombre propio con "box" NO debe señalar box_set ---

def test_blue_box_serie_regular_no_box_set():
    # "Blue Box" es una SERIE; un tomo regular no es un box set.
    _, _, types = mw.detect_signals("Blue Box vol 14")
    assert "box_set" not in types


def test_blue_box_sin_volumen_no_box_set():
    _, _, types = mw.detect_signals("Blue Box")
    assert "box_set" not in types


def test_editorial_black_box_no_box_set():
    # "Black Box" es una EDITORIAL francesa; su nombre en la descripción no debe
    # convertir un tomo regular en box set (caso Manga-Sanctuary, 76 tomos).
    _, _, types = mw.detect_signals("Sugar Vol. 4 · Black Box · Manga")
    assert "box_set" not in types


def test_tokyo_black_box_no_box_set():
    _, _, types = mw.detect_signals("Tokyo Black Box")
    assert "box_set" not in types


def test_box_seguido_de_volumen_no_box_set():
    # "box" seguido de un marcador de tomo (vol/tomo/N) = título de serie, no caja.
    for t in ("Blue Box tomo 3", "Blue Box 5", "Black Box Vol. 2"):
        _, _, types = mw.detect_signals(t)
        assert "box_set" not in types, t


def test_box_construction_no_matchea_sandbox_boxing():
    # Refuerza el word-boundary: sandbox/boxing no son construcción "box".
    _, _, types = mw.detect_signals("Sandbox Chronicles boxing legends")
    assert "box_set" not in types


# --- CJK: el "BOX" pegado a ideograma NO es nombre propio latino → se conserva ---
# (regresión evitada: la regla no debe tirar los boxes japoneses/chinos/coreanos
#  que usaban el token "box" desnudo como ÚNICA señal.)

def test_cjk_box_tw_tokusou_se_conserva():
    _, _, types = mw.detect_signals("沉月之鑰 第一部 特裝BOX")
    assert "box_set" in types


def test_cjk_box_zh_almacenaje_se_conserva():
    _, _, types = mw.detect_signals("青春豬頭少年 (15)（全套收納BOX典藏版）")
    assert "box_set" in types


def test_cjk_box_kr_multiuso_se_conserva():
    _, _, types = mw.detect_signals("노다메 칸타빌레 15 (다용도BOX 포함) 박스 한정판")
    assert "box_set" in types


def test_box_pegado_a_puntuacion_se_conserva():
    # "Re：BOX" (colon de ancho completo japonés) → BOX de producto, no bigrama latino.
    _, _, types = mw.detect_signals("Re：BOX 2nd Art Works")
    assert "box_set" in types


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (run delta) — Fix 2: throttle_group (Shopify 429)
# ---------------------------------------------------------------------------

import threading  # noqa: E402
import time  # noqa: E402


def test_load_sources_reads_throttle_group(tmp_path):
    p = tmp_path / "sources.yml"
    p.write_text(
        "sources:\n"
        "  - name: A\n"
        "    url: https://a.test/\n"
        "    throttle_group: 'shopify'\n"
        "  - name: B\n"
        "    url: https://b.test/\n",
        encoding="utf-8",
    )
    srcs = mw.load_sources(p)
    by_name = {s.name: s for s in srcs}
    assert by_name["A"].throttle_group == "shopify"
    assert by_name["B"].throttle_group == ""  # sin grupo por defecto


def test_source_throttle_group_default_empty():
    s = mw.Source(name="x", url="y")
    assert s.throttle_group == ""


def test_throttle_group_shares_one_semaphore():
    # Dos hosts del mismo grupo → el MISMO semáforo (serializan con limit 1).
    reg = mw.ThrottleRegistry(
        per_host_limit=8,
        host_to_group={"darkhorsedirect.com": "shopify", "funside.it": "shopify"},
        group_delay=0.0,
    )
    k1, g1 = reg._key_for("https://darkhorsedirect.com/collections/x")
    k2, g2 = reg._key_for("https://funside.it/collections/y")
    assert g1 and g2
    assert k1 == k2 == "group:shopify"
    assert reg._sem(k1, True) is reg._sem(k2, True)


def test_throttle_group_serializes_requests():
    # Dos requests del mismo grupo NO pueden solaparse (limit 1).
    reg = mw.ThrottleRegistry(
        per_host_limit=8,
        host_to_group={"a.test": "grp", "b.test": "grp"},
        group_delay=0.0,
    )
    active = 0
    max_active = 0
    lock = threading.Lock()

    def worker(url):
        nonlocal active, max_active
        with reg.acquire(url):
            with lock:
                active += 1
                max_active = max(max_active, active)
            time.sleep(0.02)
            with lock:
                active -= 1

    threads = [
        threading.Thread(target=worker, args=(u,))
        for u in ("https://a.test/1", "https://b.test/2", "https://a.test/3")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert max_active == 1  # nunca dos a la vez dentro del grupo


def test_throttle_group_enforces_min_delay():
    reg = mw.ThrottleRegistry(
        per_host_limit=8,
        host_to_group={"a.test": "grp"},
        group_delay=0.05,
    )
    start = time.monotonic()
    for _ in range(3):
        with reg.acquire("https://a.test/x"):
            pass
    elapsed = time.monotonic() - start
    # 3 inicios espaciados ≥ 0.05s → al menos 2 intervalos.
    assert elapsed >= 0.09


def test_throttle_no_group_uses_per_host_limit():
    # Fuentes sin grupo: se agrupan por host y NO comparten con otros hosts.
    reg = mw.ThrottleRegistry(per_host_limit=3, host_to_group={}, group_delay=2.0)
    ka, ga = reg._key_for("https://a.test/x")
    kb, gb = reg._key_for("https://b.test/y")
    assert not ga and not gb
    assert ka != kb
    # límite = per_host_limit (3), sin delay (no es grupo).
    sem = reg._sem(ka, False)
    assert sem._value == 3


def test_throttle_no_group_no_delay():
    # Sin grupo, aunque group_delay>0, un host suelto no duerme.
    reg = mw.ThrottleRegistry(per_host_limit=2, host_to_group={}, group_delay=5.0)
    start = time.monotonic()
    for _ in range(3):
        with reg.acquire("https://solo.test/x"):
            pass
    assert (time.monotonic() - start) < 1.0


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (run delta) — Fix 3: título = badge de descuento (Dynit)
# ---------------------------------------------------------------------------

from bs4 import BeautifulSoup  # noqa: E402


def test_is_sale_badge_detecta_sconto():
    assert mw._is_sale_badge("Sconto 10%")
    assert mw._is_sale_badge("Sconto 5%")
    assert mw._is_sale_badge("-10%")
    assert mw._is_sale_badge("10% off")
    assert mw._is_sale_badge("Sale")
    assert mw._is_sale_badge("Offerta")
    assert mw._is_sale_badge("Descuento 15%")


def test_is_sale_badge_no_toca_titulos_reales():
    for t in (
        "One Piece Vol. 105",
        "Berserk Deluxe Edition 1",
        "Naruto 10",           # número que NO es porcentaje
        "Sconto Speciale One Piece",  # "Sconto" + producto, no badge puro
        "5 Centimeters per Second",
    ):
        assert not mw._is_sale_badge(t), t


def _dynit_card(badge_text, title_text):
    html = f"""
    <div class="sc_extended_products_content">
      <a class="onsale" href="/products/x">{badge_text}</a>
      <h2 class="woocommerce-loop-product__title">{title_text}</h2>
      <a href="/products/one-piece-105">continua</a>
    </div>
    """
    return BeautifulSoup(html, "html.parser").select_one("div.sc_extended_products_content")


def test_first_non_badge_title_salta_sconto():
    card = _dynit_card("Sconto 10%", "One Piece Vol. 105")
    sel = ".woocommerce-loop-product__title, h2, h3, a"
    assert mw._first_non_badge_title(card, sel) == "One Piece Vol. 105"


def test_first_non_badge_title_sin_badge_devuelve_primero():
    # Sin badge de descuento previo: el primer match es el título (comportamiento
    # intacto). El texto "Novità" NO está en la lista de badges de descuento, así
    # que un título que empiece así no se salta.
    html = """
    <div class="card">
      <h2 class="woocommerce-loop-product__title">Berserk Deluxe 1</h2>
      <a href="/products/berserk">continua</a>
    </div>
    """
    card = BeautifulSoup(html, "html.parser").select_one("div.card")
    sel = ".woocommerce-loop-product__title, h2, h3, a"
    assert mw._first_non_badge_title(card, sel) == "Berserk Deluxe 1"


def test_first_non_badge_title_todos_badges_cae_al_primero():
    # Si (raro) todos los matches son badges, devuelve el primero (no vacío).
    html = '<div class="card"><a href="/x">Sconto 10%</a><a href="/y">-5%</a></div>'
    card = BeautifulSoup(html, "html.parser").select_one("div.card")
    assert mw._first_non_badge_title(card, "a") == "Sconto 10%"


def test_extract_with_selectors_dynit_no_devuelve_badge():
    # Integración: la card de Dynit con "Sconto 10%" antes del título produce un
    # candidate con el NOMBRE real, no el badge.
    source = mw.Source(
        name="IT - Dynit", url="https://www.dynit.it/",
        country="Italia", language="Italiano", publisher="Dynit Manga",
        selectors={
            "item_selector": "div.sc_extended_products_content",
            "title_selector": ".woocommerce-loop-product__title, h2, h3, a",
        },
    )
    html = """
    <html><body>
    <div class="sc_extended_products_content">
      <a class="onsale" href="/products/op105">Sconto 10%</a>
      <h2 class="woocommerce-loop-product__title">One Piece 105</h2>
    </div>
    </body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    cands = mw.extract_with_selectors(source, soup, max_items=10)
    assert len(cands) == 1
    assert "One Piece" in cands[0].title
    assert "Sconto" not in cands[0].title


# ---------------------------------------------------------------------------
# Work order 2026-07-07 (IT - Funside) — badges "desnudos" sin porcentaje
#
# 7 items de Funside quedaron con título literal "Sconto" (la palabra sola, sin
# %). El regex sólo cubría "Sconto <n>%". Se extiende para saltar el badge cuando
# el texto ENTERO es la palabra desnuda (fullmatch), sin sobre-matchear títulos
# reales que la contengan en contexto ("Garage Sale Vol 1").
# ---------------------------------------------------------------------------


def test_is_sale_badge_detecta_badges_desnudos():
    # Palabra sola (con espacios alrededor tolerados), case-insensitive.
    for t in ("Sconto", "sconto", "  Sconto  ", "SALE", "Offerta",
              "Descuento", "Rebaja", "Réduction", "Reduction"):
        assert mw._is_sale_badge(t), t


def test_is_sale_badge_no_toca_titulos_con_la_palabra_en_contexto():
    # La palabra dentro de un título real (no es el texto completo) NO se salta.
    for t in ("Garage Sale Vol 1", "Summer Sale Special Edition",
              "Sconto Speciale One Piece", "Rebaja de Otoño 3"):
        assert not mw._is_sale_badge(t), t


def test_first_non_badge_title_salta_sconto_desnudo():
    # Badge desnudo "Sconto" antes del título real → devuelve el título real.
    card = _dynit_card("Sconto", "Berserk Deluxe 1")
    sel = ".woocommerce-loop-product__title, h2, h3, a"
    assert mw._first_non_badge_title(card, sel) == "Berserk Deluxe 1"


def test_first_non_badge_title_no_salta_garage_sale():
    # "Garage Sale Vol 1" es un título legítimo: NO debe saltarse aunque el
    # primer match empiece con una palabra de badge en contexto.
    html = """
    <div class="card">
      <h2 class="woocommerce-loop-product__title">Garage Sale Vol 1</h2>
      <a href="/products/x">continua</a>
    </div>
    """
    card = BeautifulSoup(html, "html.parser").select_one("div.card")
    sel = ".woocommerce-loop-product__title, h2, h3, a"
    assert mw._first_non_badge_title(card, sel) == "Garage Sale Vol 1"


# ---------------------------------------------------------------------------
# Bug 2026-07-07 — carrusel de 'productos relacionados' contamina images[]
#
# Star Comics (search) [variant cover] adjuntaba a la galería de un item los
# thumbnails de OTRAS series que viven en el carrusel "ti potrebbe interessare"
# del detail page. Cuando la cover del propio producto también es un thumbnail
# (mismo subdir /thumbnail/ que los relacionados), el filtro de mismo-directorio
# (gotcha #31) no puede separarlos. El fix es estructural: excluir del harvest de
# galería los <img> que viven dentro de una GRILLA de product-cards que enlazan a
# páginas de producto DISTINTAS (una galería legítima no enlaza a N productos).
# ---------------------------------------------------------------------------


def _star_comics_detail_with_grid(cover_url: str) -> BeautifulSoup:
    """Detail page al estilo Star Comics: producto principal + una grilla
    `div.fumetto-card` de 'otri volumi' con thumbnails de OTRAS series, todos en
    el subdir /thumbnail/ (mismo que la cover del reproductor del bug)."""
    grid = "\n".join(
        f'<div class="card fumetto-card border-0"><a href="/fumetto/{slug}">'
        f'<figure class="mb-0"><img src="https://www.starcomics.com/files/'
        f'immagini/fumetti-cover/thumbnail/{img}-1200px"></figure></a></div>'
        for slug, img in [
            ("ranking-of-kings-16", "rankingofkings-16"),
            ("astro-royale-5", "astroroyale-5"),
            ("solo-leveling-2", "sololeveling-romanzo-2"),
            ("one-piece-campus-5", "onepiece-campus-5"),
        ]
    )
    html = f"""
    <html><body><main class="flex-shrink-0">
      <article itemtype="https://schema.org/Product">
        <meta property="og:image" content="{cover_url}">
        <div class="product-gallery"><img src="{cover_url}" alt="cover"></div>
      </article>
      <div class="swiper">{grid}</div>
    </main></body></html>
    """
    return BeautifulSoup(html, "html.parser")


def test_related_grid_thumbs_dropped_when_cover_is_thumbnail():
    """La cover propia es un /thumbnail/ (folder filter inútil) + grilla de
    relacionados en el MISMO folder → solo sobrevive la cover del producto."""
    cover = ("https://www.starcomics.com/files/immagini/fumetti-cover/"
             "thumbnail/nue-sexorcist-1-1200px")
    soup = _star_comics_detail_with_grid(cover)
    images = mw._extract_images_from_detail_soup(
        soup, "https://www.starcomics.com/fumetto/nue-s-exorcist-1-variant-cover-edition"
    )
    urls = [im["url"] for im in images]
    assert cover in urls
    for foreign in ("rankingofkings", "astroroyale", "sololeveling", "onepiece-campus"):
        assert not any(foreign in u for u in urls), urls
    assert len(images) == 1, urls


def test_related_grid_thumbs_dropped_when_cover_is_fullres():
    """Aunque el filtro de path ya cubría este caso (cover en /fumetti-cover/,
    relacionados en /fumetti-cover/thumbnail/), la exclusión estructural también
    lo resuelve — y de forma independiente al layout de carpetas."""
    cover = ("https://www.starcomics.com/files/immagini/fumetti-cover/"
             "sweetpaprika-3-variant-1200px")
    soup = _star_comics_detail_with_grid(cover)
    images = mw._extract_images_from_detail_soup(
        soup, "https://www.starcomics.com/fumetto/sweet-paprika-variant-fumetterie-3"
    )
    urls = [im["url"] for im in images]
    assert cover in urls
    assert not any("/thumbnail/" in u for u in urls), urls
    assert len(images) == 1, urls


def test_multi_card_grid_each_gets_only_its_own_image():
    """Contrato del bug: al procesar una lista con varios cards, la galería de
    CADA item queda con SOLO su propia imagen, no la unión de la página. Se
    modela con el detail de dos productos distintos: ninguna galería absorbe los
    thumbnails de la grilla de relacionados (que son de terceras series)."""
    for cover_slug, cover in [
        ("nue-sexorcist-1", "https://www.starcomics.com/files/immagini/fumetti-cover/thumbnail/nue-sexorcist-1-1200px"),
        ("gachiakuta-2", "https://www.starcomics.com/files/immagini/fumetti-cover/gachiakuta-variant-2-gadget-1200px"),
    ]:
        soup = _star_comics_detail_with_grid(cover)
        images = mw._extract_images_from_detail_soup(
            soup, f"https://www.starcomics.com/fumetto/{cover_slug}"
        )
        urls = [im["url"] for im in images]
        assert urls == [cover], urls


def test_legit_lightbox_gallery_not_treated_as_related_grid():
    """Regresión: una galería REAL del mismo producto donde cada slide enlaza a
    un ARCHIVO de imagen distinto (patrón lightbox Magento/Fotorama) NO debe
    detectarse como grilla de relacionados — sus fotos se conservan."""
    base = "https://cdn.shop.com/p/berserk-1"
    html = f"""
    <html><body><main>
      <article itemtype="https://schema.org/Product">
        <meta property="og:image" content="{base}/cover.jpg">
        <div class="product-gallery">
          <a href="{base}/cover.jpg"><img src="{base}/cover_thumb.jpg"></a>
          <a href="{base}/back.jpg"><img src="{base}/back_thumb.jpg"></a>
          <a href="{base}/spine.jpg"><img src="{base}/spine_thumb.jpg"></a>
          <a href="{base}/interior.jpg"><img src="{base}/interior_thumb.jpg"></a>
        </div>
      </article>
    </main></body></html>
    """
    images = mw._extract_images_from_detail_soup(BeautifulSoup(html, "html.parser"), base)
    urls = {mw._gallery_url_normalize(im["url"]) for im in images}
    for part in ("cover", "back", "spine", "interior"):
        assert any(part in u for u in urls), (part, urls)


def test_related_grid_ids_empty_without_grid():
    """Sin grilla de relacionados (galería simple), el helper no marca nada:
    no debe alterar el harvest normal de una sola cover."""
    html = """
    <html><body><main>
      <article itemtype="https://schema.org/Product">
        <meta property="og:image" content="https://cdn.example.com/p/1/cover.jpg">
        <div class="product-gallery"><img src="https://cdn.example.com/p/1/cover.jpg"></div>
      </article>
    </main></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    scope = mw._find_product_scope(soup) or soup
    assert mw._related_grid_card_ids(scope, "https://cdn.example.com/p/1") == set()


# ---------------------------------------------------------------------------
# Bug 2026-07-07 — "FR - Glénat Art Books": artbooks perdidos en el gate de
# coleccionable + vocabulario FR de artbook.
#
# La fuente (tag "artbook", kind:js) cataloga artbooks reales ("L'Art de Berserk",
# "One Piece Color Walk", "Rumiko Takahashi Colors") pero sus títulos rara vez
# traen la keyword "art book"/"画集". detect_signals daba score=0 → morían en el
# gate de señal; y aun con señal, derive_product_type caía en "manga" y el gate
# is_collectible_edition los rechazaba como regular_tomo. Fix: (1) bypass por tag
# "artbook" en el gate de coleccionable (fuerza product_type=artbook), análogo a
# variant-catalog; (2) vocabulario FR de artbook en KEYWORD_RULES.
# ---------------------------------------------------------------------------


def _artbook_source_candidate(title, tags=("artbook", "official", "france"),
                              product_type="manga", signal_types=None):
    """Candidate al estilo de un card de 'FR - Glénat Art Books' (tag artbook)."""
    c = mw.Candidate(
        title=title, url="https://www.glenat.com/art-de-x",
        source="FR - Glénat Art Books",
        source_url="https://www.glenat.com/livres-keywords-art-book/",
        country="Francia", language="Francés", publisher="Glénat Manga",
        source_class="official", tags=list(tags), description="",
    )
    c.product_type = product_type
    c.signal_types = list(signal_types or [])
    return c


# --- (c) Vocabulario FR de artbook dispara la señal artbook ---

def test_fr_lart_de_dispara_artbook():
    _, _, types = mw.detect_signals("L'Art de Berserk")
    assert "artbook" in types


def test_fr_lart_de_apostrofo_curvo_dispara_artbook():
    # El apóstrofo tipográfico (U+2019) lo normaliza normalize_text a ASCII.
    _, _, types = mw.detect_signals("L’Art de Studio Ghibli")
    assert "artbook" in types


def test_fr_super_art_book_dispara_artbook():
    _, _, types = mw.detect_signals("Dragon Ball Le super art book")
    assert "artbook" in types


def test_fr_color_walk_dispara_artbook():
    _, _, types = mw.detect_signals("One Piece Color Walk")
    assert "artbook" in types


def test_colors_al_final_dispara_artbook():
    _, _, types = mw.detect_signals("Rumiko Takahashi Colors")
    assert "artbook" in types


def test_colors_mid_title_no_dispara_artbook():
    # "colors" en medio (título termina en el número de tomo) NO debe marcar
    # artbook: son tomos regulares, no artbooks. Ancla a fin de texto.
    for t in ("True Colors 3", "Colorful vol 2", "Blue Colors 10"):
        _, _, types = mw.detect_signals(t)
        assert "artbook" not in types, t


# --- (a) Bypass por tag artbook: fuerza product_type y pasa is_collectible ---

def test_bypass_artbook_lart_de_berserk_es_collectible():
    c = _artbook_source_candidate("L'Art de Berserk")
    assert mw.is_curated_collectible_source(c) is True
    assert c.product_type == "artbook"
    ok, reason = mw.is_collectible_edition(
        c.title, c.description, c.signal_types, c.product_type,
        tags=c.tags, isbn=c.isbn, url=c.url)
    assert ok is True
    assert reason.startswith("product_type:artbook")


def test_bypass_artbook_one_piece_color_walk_es_collectible():
    c = _artbook_source_candidate("One Piece Color Walk")
    assert mw.is_curated_collectible_source(c) is True
    assert c.product_type == "artbook"
    ok, _ = mw.is_collectible_edition(
        c.title, c.description, c.signal_types, c.product_type,
        tags=c.tags, isbn=c.isbn, url=c.url)
    assert ok is True


def test_bypass_artbook_sin_keyword_igual_pasa():
    # El corazón del mecanismo: aunque el título NO matchee NINGUNA keyword de
    # artbook (product_type quedaría "manga"), la fuente curada (tag artbook) lo
    # fuerza a artbook y lo deja pasar el gate. Independiente de KEYWORD_RULES.
    c = _artbook_source_candidate("Berserk", product_type="manga", signal_types=[])
    assert mw.is_curated_collectible_source(c) is True
    assert c.product_type == "artbook"


def test_bypass_artbook_no_clobbea_tipo_coleccionable_previo():
    # Si el título YA resolvió a un tipo coleccionable (boxset), el bypass NO lo
    # degrada a artbook.
    c = _artbook_source_candidate(
        "Berserk Deluxe Box", product_type="boxset", signal_types=["box_set"])
    assert mw.is_curated_collectible_source(c) is True
    assert c.product_type == "boxset"


# --- (b) Un item de BD occidental (Cromwell) NO se cuela ---

def test_bd_occidental_sin_senal_artbook_muere_en_gate_de_signal():
    # "Cromwell" / "Druillet" (BD occidental) no traen keyword de artbook: score=0
    # → mueren en el gate `if score <= 0: continue` (extract_generic_html), antes
    # de llegar al bypass. El bypass NO puede rescatarlos.
    for t in ("Cromwell", "Druillet"):
        score, _, types = mw.detect_signals(t)
        assert score == 0, t
        assert "artbook" not in types, t


def test_bd_occidental_falla_is_likely_manga_en_mixed():
    # Defensa de relevancia-manga: con purity mixta, un título sin STRONG hint de
    # manga se rechaza aunque la fuente tenga el tag artbook. El bypass se aplica
    # DESPUÉS de is_likely_manga, así que un no-manga nunca llega al gate.
    ok, _reason = mw.is_likely_manga(
        "Cromwell", source_purity="mixed", tags=["artbook", "official", "france"])
    assert ok is False


# --- (d) Regresión: fuente SIN tag artbook no cambia comportamiento ---

def test_sin_tag_artbook_no_bypassa_ni_muta_product_type():
    c = _artbook_source_candidate(
        "Naruto 12", tags=("official", "france"), product_type="manga")
    assert mw.is_curated_collectible_source(c) is False
    assert c.product_type == "manga"  # no mutado
    # y el gate normal lo rechaza como tomo regular.
    ok, reason = mw.is_collectible_edition(
        c.title, c.description, c.signal_types, c.product_type,
        tags=c.tags, isbn=c.isbn, url=c.url)
    assert ok is False


def test_variant_catalog_sigue_bypasseando():
    # Regresión del bypass previo (Mangavariant): variant-catalog sigue pasando
    # sin mutar product_type.
    c = _artbook_source_candidate(
        "Vol.1 - Cover A", tags=("variant-catalog",), product_type="manga")
    assert mw.is_curated_collectible_source(c) is True
    assert c.product_type == "manga"
