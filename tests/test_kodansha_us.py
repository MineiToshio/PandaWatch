"""Tests del wiki kodansha-us (scripts/wikis/kodansha_us.py).

Cubre: is_special_series, _image_url, get_volume_data (JSON-LD mock).
"""
import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from wikis.kodansha_us import (  # noqa: E402
    _image_url,
    get_volume_data,
    is_special_series,
)

# ---------------------------------------------------------------------------
# is_special_series
# ---------------------------------------------------------------------------


def test_is_special_series_positives():
    assert is_special_series("Vinland Saga Deluxe")
    assert is_special_series("Attack on Titan Omnibus")
    assert is_special_series("Battle Angel Alita Deluxe")
    assert is_special_series("The Ghost in the Shell Deluxe Complete Box Set")
    assert is_special_series("Mushishi Collector's Edition")
    assert is_special_series("AKIRA Hardcover Collection")
    assert is_special_series("Princess Jellyfish Complete Manga Box Set")
    assert is_special_series("No Longer Human Complete Edition")


def test_is_special_series_negatives():
    # Series regulares: no deben calificar.
    assert not is_special_series("Attack on Titan")
    assert not is_special_series("Fairy Tail")
    assert not is_special_series("Fire Force Vol. 3")
    assert not is_special_series("Blue Lock")


# ---------------------------------------------------------------------------
# _image_url
# ---------------------------------------------------------------------------


def test_image_url_from_dict():
    img = {"uuid": "abc-123", "aspect_ratio_decimal": 0.8}
    url = _image_url(img)
    assert url == "https://production.image.azuki.co/abc-123/800.webp"


def test_image_url_from_string():
    assert _image_url("https://example.com/cover.jpg") == "https://example.com/cover.jpg"


def test_image_url_empty():
    assert _image_url({}) == ""
    assert _image_url("") == ""


# ---------------------------------------------------------------------------
# get_volume_data (JSON-LD parsing)
# ---------------------------------------------------------------------------

_VOLUME_HTML = """
<html><head></head><body>
<script type="application/ld+json">
{
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "Book",
      "name": "Vinland Saga Deluxe Volume 1",
      "url": "https://kodansha.us/series/vinland-saga-deluxe/volume-1/",
      "image": "https://production.image.azuki.co/abc-uuid/800.webp",
      "author": {"@type": "Person", "name": "Makoto Yukimura"},
      "numberOfPages": 688,
      "workExample": [
        {
          "@type": "Book",
          "bookFormat": "https://schema.org/Paperback",
          "isbn": "9781646519781",
          "datePublished": "2024-02-06",
          "offers": {
            "@type": "Offer",
            "price": 54.99,
            "priceCurrency": "USD"
          }
        }
      ]
    }
  ]
}
</script>
</body></html>
"""


def test_get_volume_data_extracts_json_ld():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = _VOLUME_HTML
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    data = get_volume_data(mock_session, "https://kodansha.us/series/vinland-saga-deluxe/volume-1/")

    assert data is not None
    assert data["title"] == "Vinland Saga Deluxe Volume 1"
    assert data["isbn"] == "9781646519781"
    assert data["published_at"] == "2024-02-06"
    assert data["author"] == "Makoto Yukimura"
    assert "azuki.co" in data["image"]


def test_get_volume_data_returns_none_on_error():
    mock_session = MagicMock()
    mock_session.get.side_effect = Exception("Connection error")
    result = get_volume_data(mock_session, "https://kodansha.us/series/test/volume-1/")
    assert result is None


def test_get_volume_data_no_book_type():
    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.text = "<html><body><script type='application/ld+json'>{\"@type\":\"WebPage\"}</script></body></html>"
    mock_session = MagicMock()
    mock_session.get.return_value = mock_resp

    result = get_volume_data(mock_session, "https://kodansha.us/series/test/volume-1/")
    assert result is None
