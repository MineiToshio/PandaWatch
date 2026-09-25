"""Calendar and linked-volume traversal must expose incomplete coverage."""
import requests
from scripts.wikis import animeclick as ac, shueisha_books as sb

INITIAL = '<div id="calendario-pagination-div" data-current-day="7" data-current-month="9" data-current-year="2026"></div><div id="calendario-days-thumbs">initial</div>'


def run_calendar(monkeypatch, responses, max_weeks=2000):
    session = requests.Session()
    pages = []
    monkeypatch.setattr(ac, 'fetch_html', lambda *a, **k: INITIAL)
    it = iter(responses)
    monkeypatch.setattr(ac, 'fetch_week_ajax', lambda *a, **k: next(it))
    monkeypatch.setattr(ac, 'MAX_WEEKS', max_weeks)
    monkeypatch.setattr(ac, 'parse_calendar_html', lambda html: pages.append(html) or [])
    ac.bootstrap(2026, 9, 2026, 9, session, sleep_seconds=0, fetch_details=False)
    return pages, getattr(session, '_ingestion_issues', [])


def test_calendar_keeps_week_crossing_month_start(monkeypatch):
    pages, issues = run_calendar(monkeypatch, [('overlap', 31, 8, 2026), ('older', 24, 8, 2026)])
    assert 'overlap' in pages
    assert 'older' not in pages
    assert not issues


def test_calendar_repeated_week_fails_without_repeating_requests(monkeypatch):
    pages, issues = run_calendar(monkeypatch, [('repeat', 7, 9, 2026)])
    assert len(pages) == 1
    assert any('did not move backwards' in issue for issue in issues)


def test_calendar_limit_is_not_success(monkeypatch):
    _, issues = run_calendar(monkeypatch, [('overlap', 31, 8, 2026)], max_weeks=1)
    assert any('pagination limit' in issue for issue in issues)


def test_calendar_failed_ajax_preserves_initial_week(monkeypatch):
    pages, issues = run_calendar(monkeypatch, [(None, 7, 9, 2026)])
    assert len(pages) == 1
    assert issues


def test_calendar_rejects_unexpected_json_schema():
    class Response:
        def raise_for_status(self): pass
        def json(self): return []
    session = requests.Session()
    session.get = lambda *a, **k: Response()
    assert ac.fetch_week_ajax(session, 7, 9, 2026)[0] is None
    assert session._ingestion_issues


def test_shueisha_limit_keeps_acquired_volumes_and_reports_gap(monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(sb, 'fetch_book_page', lambda *a, **k: 'book')
    monkeypatch.setattr(sb, 'parse_book_page', lambda html, isbn: {'title': 'Book', 'isbn': isbn, 'release_date': '', 'next_isbn': '9784081234568'})
    rows = sb.walk_series('9784081234567', session, sleep_seconds=0, max_vols=1)
    assert len(rows) == 1
    assert any('pagination limit' in issue for issue in session._ingestion_issues)


def test_shueisha_unparseable_page_is_not_success(monkeypatch):
    session = requests.Session()
    monkeypatch.setattr(sb, 'fetch_book_page', lambda *a, **k: 'changed markup')
    monkeypatch.setattr(sb, 'parse_book_page', lambda *a, **k: None)
    assert sb.walk_series('9784081234567', session, sleep_seconds=0) == []
    assert session._ingestion_issues


def test_viz_product_schema_change_is_reported(monkeypatch):
    from scripts.wikis import viz_artbooks as viz
    from types import SimpleNamespace
    session=requests.Session()
    monkeypatch.setattr(session,'get',lambda *a,**k:SimpleNamespace(status_code=200,text='<html>New layout without book data</html>',raise_for_status=lambda:None))
    assert viz.fetch_product('/manga-books/product/1',session) is None
    assert any('could not parse' in issue for issue in session._ingestion_issues)


def test_shueisha_broken_link_does_not_look_like_end_of_series(monkeypatch):
    session=requests.Session()
    monkeypatch.setattr(sb,'fetch_book_page',lambda *a,**k:None)
    assert sb.walk_series('9784081234567',session,sleep_seconds=0)==[]
    assert any('unavailable linked book' in issue for issue in session._ingestion_issues)


def test_viz_preview_title_preserves_book_name():
    from scripts.wikis import viz_artbooks as viz
    for prefix in ('VIZ: See ', 'VIZ: Read a Free Preview of ', ''):
        book = viz.parse_product_page(f'<meta property="og:title" content="{prefix}Sunny, Vol. 1"><p>9781421555256</p>')
        assert book['title'] == 'Sunny, Vol. 1'


def test_viz_missing_linked_product_is_reported(monkeypatch):
    from scripts.wikis import viz_artbooks as viz
    from types import SimpleNamespace
    session=requests.Session()
    monkeypatch.setattr(session,'get',lambda *a,**k:SimpleNamespace(status_code=404))
    assert viz.fetch_product('/manga-books/product/1',session) is None
    assert any('unavailable linked product' in issue for issue in session._ingestion_issues)
