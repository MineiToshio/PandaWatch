"""Durable full-before-delta, partial-run recovery and official catalog replay."""
import json
import sys
from types import SimpleNamespace
import pytest
import requests
from bs4 import BeautifulSoup
from scripts import ingestion_policy as policy
from scripts import manga_watch as mw
from scripts.wikis import prhcomics as prh


def test_changed_source_requires_new_baseline(tmp_path):
    spec={'enabled':True,'full_from':'2000-01'}
    assert policy.needs_full('delta',tmp_path,'wiki:test',spec)
    policy.commit_baseline(tmp_path,'wiki:test',spec,evidence={'pages':2})
    assert not policy.needs_full('delta',tmp_path,'wiki:test',spec)
    assert policy.needs_full('delta',tmp_path,'wiki:test',{**spec,'revision':2})
    assert policy.needs_full('full',tmp_path,'wiki:test',spec)
    policy.receipt_path(tmp_path,'wiki:test').write_text('{broken')
    with pytest.raises(json.JSONDecodeError): policy.has_baseline(tmp_path,'wiki:test',spec)


@pytest.mark.parametrize('workers', [1,2])
def test_full_receipt_requires_all_pages_but_not_other_sources(tmp_path,monkeypatch,workers):
    source=mw.Source(name='Good',url='https://example.test/catalog',max_pages=1)
    bad=mw.Source(name='Bad',url='https://broken.test/catalog')
    monkeypatch.setattr(mw,'load_sources',lambda _: [source,bad])
    calls=[]
    def fetch(session,url,timeout,**kwargs):
        calls.append(url)
        if 'broken' in url: raise requests.ConnectionError('unavailable')
        return '<html><body>catalog</body></html>',{'http_status':200,'final_url':url}
    monkeypatch.setattr(mw,'fetch_with_metadata',fetch)
    monkeypatch.setattr(mw,'detect_empty_or_js',lambda *a:None)
    monkeypatch.setattr(mw,'find_next_page_url',lambda soup,url,visited:None if 'page=2' in url else url+'?page=2')
    monkeypatch.setattr(mw,'extract_generic_html',lambda source,text,**kw:[mw.candidate_from_source(source,'Berserk Deluxe 1',source.url+'/product','')])
    argv=['scraper','--skip-image-download','--sleep-seconds','0','--ingestion-mode','delta','--workers',str(workers),'--data-dir',str(tmp_path),'--reports-dir',str(tmp_path)]
    monkeypatch.setattr(sys,'argv',argv)
    assert mw.run(mw.parse_args())==1
    assert source.url+'?page=2' in calls
    assert policy.has_baseline(tmp_path,'yaml:Good',source)
    assert not policy.has_baseline(tmp_path,'yaml:Bad',bad)


def test_retired_wiki_never_fetches(tmp_path,monkeypatch):
    monkeypatch.setattr(sys,'argv',['scraper','--bootstrap-wiki','spp-tw','--ingestion-mode','delta','--skip-image-download'])
    assert mw._run_wiki_bootstrap(mw.parse_args(),SimpleNamespace(),{},tmp_path/'state.json',tmp_path/'items.jsonl',tmp_path/'report.md')==0
    assert not (tmp_path/"items.jsonl").exists()
    assert not (tmp_path/".source-baselines").exists()


def test_prh_partial_fetch_preserves_good_page_and_marks_failure():
    class Session:
        def get(self,url,**kw):
            if url==prh.PRH_CATALOG_URLS[1]:raise requests.ConnectionError('blocked')
            return SimpleNamespace(text='<li class="toast-anchor">book</li>',raise_for_status=lambda:None)
    s=Session()
    assert len(prh.fetch_manga_page(s))==1
    assert s._ingestion_issues


def test_prh_delta_keeps_newly_listed_old_editions(monkeypatch):
    candidate=mw.candidate_from_source(mw.Source(name='PRH',url=prh.PRH_MANGA_URL),'Berserk Deluxe 1','https://prh.test/book','')
    candidate.isbn='9781506711980';candidate.release_date='2019-01-01';candidate.score=90
    monkeypatch.setattr(prh,'fetch_manga_page',lambda *a,**kw:[object(),object()])
    monkeypatch.setattr(prh,'parse_item',lambda _:candidate)
    assert prh.bootstrap(2026,9,2026,12,SimpleNamespace())==[candidate]


def test_kingstone_pagination_is_catalog_navigation():
    url='https://www.kingstone.com.tw/bookpublish/publist/14395/?page=1'
    soup=BeautifulSoup('<li class="pageNext"><a href="?page=2"></a></li>','html.parser')
    assert mw.find_next_page_url(soup,url,{url})==url.replace('page=1','page=2')


@pytest.mark.parametrize('different', ['isbn','country','cover'])
def test_final_consolidation_preserves_conflicting_products(tmp_path,different):
    a=dict(url='https://a.test/1',title='Berserk Deluxe 1',edition_key='berserk-deluxe-us',volume='1',country='Estados Unidos',isbn='9781506711980')
    b={**a,'url':'https://b.test/1'}
    if different=='isbn':b['isbn']='9781506711997'
    if different=='country':b['country']='España'
    if different=='cover':a['title']+=' Cover A';b['title']+=' Cover B'
    result=mw.consolidate_by_cluster([a,b])
    assert len(result)==2
    assert all(r['identity_review_required'] for r in result)
    assert len({r['cluster_key'] for r in result})==2
    assert mw.consolidate_by_cluster(result)==result
    path=tmp_path/'items.jsonl';mw.write_items_atomic(path,result)
    mw.append_jsonl(path,[dict(a,title=a['title']+' updated')])
    assert len(mw.read_jsonl_strict(path))==2
    assert all(r['cluster_key']==mw.derive_cluster_key(r) for r in mw.read_jsonl_strict(path))


def test_same_product_keeps_multi_source_provenance():
    rows=[dict(url=u,title='Berserk Deluxe 1',edition_key='berserk-deluxe-us',volume='1',isbn=isbn) for u,isbn in [('https://a.test/1','9781506711980'),('https://b.test/1','1506711987')]]
    result=mw.consolidate_by_cluster(rows)
    assert len(result)==1
    assert len(result[0]['sources'])==2

@pytest.mark.parametrize('title', ['【電子書】潮與虎 完全版(10)', '[eBook] Berserk Deluxe 1', 'Berserk Deluxe 1 (eBook)'])
def test_digital_format_cannot_masquerade_as_collectible(title):
    assert mw.is_likely_manga(title)[0] is False

@pytest.mark.parametrize('title', ['Berserk Deluxe 1 with ebook bonus', 'NANA新裝版(03)+(04)合購特裝版', 'Heaven Official’s Blessing (Novel) Deluxe Edition'])
def test_physical_premium_books_and_asian_novels_remain(title):
    assert mw.is_likely_manga(title)[0] is True

@pytest.mark.parametrize('title', ['Wayne Family Adventures Cofanetto', 'SPAWN 100 METALIZADO', 'DYLAN DOG - MORTE IN SEDICI NONI - VARIANT MANICOMIX'])
def test_western_comics_do_not_pass_premium_gate(title):
    assert mw.is_likely_manga(title)[0] is False


def test_japanese_spawn_adaptation_survives_franchise_filter():
    assert mw.is_likely_manga('Shadows of Spawn Deluxe Edition')[0] is True


def test_changed_acceptance_threshold_invalidates_baseline(tmp_path):
    spec={'enabled':True,'full_from':'2000-01'}
    policy.commit_baseline(tmp_path,'wiki:test',spec,evidence={},min_score=30)
    assert policy.needs_full('delta',tmp_path,'wiki:test',spec,min_score=20)
    assert not policy.needs_full('delta',tmp_path,'wiki:test',spec,min_score=30)


def test_every_wiki_has_an_explicit_runtime_decision():
    assert set(policy.load_policy()['wikis'])==set(mw.WIKI_BOOTSTRAP_IDS)


def test_health_report_respects_wiki_retirement():
    from scripts.audit import source_health
    result=source_health.aggregate_health([],[])
    assert result['wiki:spp-tw']['enabled'] is False
    assert result['wiki:prhcomics']['enabled'] is True


def test_kingstone_tracking_does_not_create_duplicate_products():
    base='https://www.kingstone.com.tw/basic/2019462240846/'
    assert mw.normalize_url_for_dedup(base+'?lid=one&actid=two')==mw.normalize_url_for_dedup(base)
    assert mw.normalize_url_for_dedup('https://other.test/basic/1/?lid=one')!='https://other.test/basic/1'

@pytest.mark.parametrize('title', ['Médaka-Box T22', 'Elfen Lied Double Edition T06', "Tough Edition double - L’aube d’une légende T02"])
def test_series_box_and_regular_double_volumes_are_not_premium(title):
    c=mw.score_candidate(mw.candidate_from_source(mw.Source(name='Delcourt',url='https://www.editions-delcourt.fr/mangas/liste-mangas'),'','https://www.editions-delcourt.fr/mangas/series/serie-test/album-test',''))
    c.title=title;c.description=title;mw.score_candidate(c)
    assert not mw.is_collectible_edition(c.title,c.description,c.signal_types,product_type=c.product_type,url=c.url)[0]

@pytest.mark.parametrize('title', ['Médaka-Box Coffret T01-T06', 'Elfen Lied Double Edition T06 Hardcover', 'Tough Edition double Collector T02'])
def test_real_premium_qualifier_survives_double_or_series_box(title):
    c=mw.score_candidate(mw.candidate_from_source(mw.Source(name='Delcourt',url='https://test'),'x','https://test/product',''))
    c.title=title;mw.score_candidate(c)
    assert mw.is_collectible_edition(c.title,c.description,c.signal_types,product_type=c.product_type,url=c.url)[0]


def test_boxset_and_last_volume_cannot_share_one_product():
    a=dict(url='https://shop.test/box',title='Series Deluxe Box Set 1-8',cluster_key='fuzzy:collision',product_type='boxset')
    b=dict(url='https://shop.test/vol8',title='Series Deluxe 8',cluster_key='fuzzy:collision',product_type='manga')
    rows=mw.consolidate_by_cluster([a,b])
    assert len(rows)==2 and all(r['identity_review_required'] for r in rows)


def test_chinese_parts_with_same_volume_are_separate_products():
    rows=[dict(url=f'https://shop.test/{p}',title=f'愛情白皮書典藏版 第{p}部(2)',cluster_key='fuzzy:collision',product_type='manga') for p in [1,2]]
    assert len(mw.consolidate_by_cluster(rows))==2

@pytest.mark.parametrize('title', ['短篇漫畫集', '短編漫画集'])
def test_manga_anthology_is_not_an_artbook(title):
    assert 'artbook' not in mw.detect_signals(title)[2]
    assert mw.derive_product_type(title,'',[])=='manga'


def test_traditional_chinese_artbook_and_book_set_are_recognized():
    assert 'artbook' in mw.detect_signals('井上雄彥畫冊')[2]
    assert 'box_set' in mw.detect_signals('20週年紀念套書(全20冊)')[2]
