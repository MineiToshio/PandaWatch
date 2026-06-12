"""Tests del módulo storefront_json (5 perfiles API, 2026-06-12)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wikis.storefront_json import (  # noqa: E402
    _JD_SPECIAL_RE,
    _PROFILES,
    _VN_FALSE_POSITIVE_RE,
    _VN_SPECIAL_RE,
    _jd_intl_map,
    _make_source,
    _spp_map,
    _vn_map,
    _yaakz_map,
)


def test_profiles_registered():
    assert set(_PROFILES) == {"jd-intl", "spp-tw", "kimdong", "ipm", "yaakz"}
    for prof in _PROFILES:
        src = _make_source(prof)
        assert src.purity == "manga_only"
        assert src.country


def test_jd_special_filter():
    src = _make_source("jd-intl")
    ok = _jd_intl_map({"name": "壬生義士傳 珍藏版 第3期",
                       "permalink": "https://jd-intl.com/product/x/",
                       "short_description": "ISBN978-988-8965-38-0"}, src)
    assert ok is not None and ok.isbn == "9789888965380"
    # 新裝版 = re-edición regular → fuera
    assert _jd_intl_map({"name": "城市獵人 新裝版 第1期",
                         "permalink": "https://jd-intl.com/product/y/"}, src) is None
    # tomo regular → fuera
    assert _jd_intl_map({"name": "幼稚園WARS 第11期",
                         "permalink": "https://jd-intl.com/product/z/"}, src) is None


def test_spp_map_filters_noise():
    src = _make_source("spp-tw")
    ok = _spp_map({"Title": "超人Ｘ(10)特裝版", "Id": 11501236, "PicUrl": "//img/x.jpg"}, src)
    assert ok is not None and ok.image_url.startswith("https://")
    # full-text match sin qualifier en título → fuera
    assert _spp_map({"Title": "普通漫畫 第3集", "Id": 1}, src) is None
    # photobook/merch → fuera
    assert _spp_map({"Title": "偶像寫真 限定版", "Id": 2}, src) is None


def test_vn_map_and_false_positives():
    src = _make_source("kimdong")
    ok = _vn_map({"name": "One Piece - Tập 110 (Bản đặc biệt)",
                  "alias": "one-piece-tap-110-ban-dac-biet"}, src,
                 "https://nxbkimdong.com.vn")
    assert ok is not None
    # nombre de serie con la señal — NO es edición especial
    assert _vn_map({"name": "Pokémon Đặc Biệt - Tập 5", "alias": "p5"}, src,
                   "https://nxbkimdong.com.vn") is None
    # IPM: barcode EAN-13 (con sufijo de letra a limpiar) + published_at
    src2 = _make_source("ipm")
    ok2 = _vn_map({"title": "Bakemonogatari - 3 (Bản Giới Hạn)",
                   "handle": "bakemonogatari-3",
                   "variants": [{"barcode": "8935250709668A"}],
                   "published_at": "2026-06-09T10:00:00+07:00"}, src2,
                  "https://ipm.vn")
    assert ok2 is not None
    assert ok2.isbn == "8935250709668"
    assert ok2.release_date == "2026-06-09"


def test_yaakz_map_excludes_empty_boxes_and_subscriptions():
    src = _make_source("yaakz")
    ok = _yaakz_map({"name": "HAIKYU!! เล่ม 45 (ชุดพิเศษ boxset)", "id": 44555,
                     "slug": "haikyu-45"}, src)
    assert ok is not None
    assert _yaakz_map({"name": "กล่องเปล่า Never Gone", "id": 9847}, src) is None
    assert _yaakz_map({"name": "[Subscription Order] TOKYO GHOUL boxset", "id": 1}, src) is None


def test_vn_regexes():
    assert _VN_SPECIAL_RE.search("Bluelock - Tập 27 (Bản đặc biệt)")
    assert _VN_SPECIAL_RE.search("Thiên Quan Tứ Phúc - 6 (Bản Sưu Tầm)")
    assert _VN_FALSE_POSITIVE_RE.search("Pokémon Đặc Biệt - Tập 5")
    assert not _VN_FALSE_POSITIVE_RE.search("One Piece (Bản đặc biệt)")
    assert _JD_SPECIAL_RE.search("帶子雄狼愛藏版 第1至20期")
