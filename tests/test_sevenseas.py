"""Tests del parser de Seven Seas (wikis/sevenseas.py) — ver ficha
docs/scraper/sources/us-sevenseas.md y evaluación 2026-06-12."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wikis.sevenseas import (  # noqa: E402
    _ISBN_RE,
    _RELEASE_RE,
    _STAFF_RE,
    _parse_release_date,
    is_special_title,
    parse_book,
)


def test_is_special_title_qualifiers():
    # califican
    assert is_special_title("Monster Musume: Deluxe Edition 2 (Vol. 4-6 Hardcover Omnibus)")
    assert is_special_title("Orange Complete Series Box Set")
    assert is_special_title("Rozen Maiden Collector's Edition Vol. 7")
    assert is_special_title("Panguan: The Twelfth Gate (Novel) Vol. 1 (Special Edition)")
    assert is_special_title("Grandmaster of Demonic Cultivation (Deluxe Hardcover Novel) Vol. 1")
    # NO califican: tomo regular y omnibus a secas (gotcha #18)
    assert not is_special_title("A Man and His Cat Vol. 12")
    assert not is_special_title("Ichi the Killer (Omnibus) Vol. 5")
    assert not is_special_title("Don't Call it Mystery (Omnibus) Vol. 15-16")
    # NO califica: Mature Hardcover sin otro qualifier (variante sin censura)
    assert not is_special_title("ENNEAD Vol. 6 [Mature Hardcover]")
    # SÍ califica: mature + qualifier real
    assert is_special_title("ENNEAD Box Set [Mature Hardcover]")


def test_parse_book_builds_candidate():
    book = {
        "id": 26328,
        "date": "2025-06-02T11:05:29",
        "link": "https://sevenseasentertainment.com/books/svsss-deluxe-box-set/",
        "title": {"rendered": "The Scum Villain&#8217;s Self-Saving System (Deluxe Hardcover Novel) Box Set"},
        "content": {"rendered": "<p><strong>Limited edition box set</strong> of deluxe hardcovers with slipcase, mini artbook and two mini posters. Numbered printing.</p>"},
    }
    cand = parse_book(book)
    assert cand is not None
    assert "Scum Villain" in cand.title and "&#8217;" not in cand.title
    assert cand.url.endswith("/svsss-deluxe-box-set/")
    assert cand.country == "Estados Unidos"
    assert cand.publisher == "Seven Seas"
    assert "box set" in cand.description.lower()
    assert cand.score > 0
    sigs = set(cand.signal_types or [])
    assert sigs & {"box_set", "deluxe", "limited"}


def test_parse_book_regular_returns_none():
    book = {
        "id": 1, "date": "2026-01-01T00:00:00",
        "link": "https://sevenseasentertainment.com/books/regular-vol-3/",
        "title": {"rendered": "A Man and His Cat Vol. 3"},
        "content": {"rendered": "<p>regular tome</p>"},
    }
    assert parse_book(book) is None


def test_detail_page_regexes():
    html = ('<p><b>Release Date:</b> February 17, 2026</p><p><b>Price:</b> $139.99</p>'
            '<p><b>Format:</b> Novel</p><p><b>ISBN:</b> 979-8-89765-142-9</p>'
            '<p class="bookcrew"><p><strong>Story &amp; Art by</strong>: Okayado<br /></p>')
    m = _ISBN_RE.search(html)
    assert m and m.group(1).replace("-", "") == "9798897651429"
    m = _RELEASE_RE.search(html)
    assert m and _parse_release_date(m.group(1)) == "2026-02-17"
    m = _STAFF_RE.search(html)
    assert m and m.group(1).strip() == "Okayado"


def test_parse_release_date_garbage():
    assert _parse_release_date("TBD") == ""
    assert _parse_release_date("") == ""


def test_is_special_title_color_edition():
    """'(Full) Color Edition' es premium real (Tokyo Revengers Brilliant Full
    Color); 'Complete Collection' (omnibus rústica) NO (gotcha #18)."""
    assert is_special_title("Tokyo Revengers: Brilliant Full Color Edition (Omnibus) Vol. 1-2")
    assert is_special_title("Hollow Fields (Color Edition) Vol. 1")
    assert not is_special_title("orange: The Complete Collection 1")
    assert not is_special_title("Witches: The Complete Collection (Omnibus)")
