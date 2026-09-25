"""Regression contracts for ingestion loss and false-success failures."""
import json
from pathlib import Path
from types import SimpleNamespace
import pytest
import scripts.manga_watch as mw
from scripts.audit import source_health as health


def put(path, rows):
    path.write_text(''.join(json.dumps(r) + '\n' for r in rows))


def test_secondary_source_updates_curated_product_without_duplicate(tmp_path):
    p = tmp_path / 'items.jsonl'
    old = dict(url='https://a.test/book', title='Berserk Deluxe 1',
               source='A', standardized_at='2026-01-01', edition_key='berserk-darkhorse-deluxe-us',
               series_key='berserk', volume='1', detected_at='2026-01-01',
               isbn='9781506711980', author='Kentaro Miura',
               sources=[{'url': 'https://a.test/book'}, {'url': 'https://b.test/book'}])
    old['cluster_key'] = mw.derive_cluster_key(old)
    put(p, [old])
    mw.append_jsonl(p, [dict(url='https://b.test/book', source='B', title='scraped',
                            detected_at='2026-09-24', author='', isbn='')])
    rows = mw.read_jsonl_strict(p)
    assert len(rows) == 1
    assert rows[0]['title'] == old['title']
    assert rows[0]['author'] == old['author']
    assert rows[0]['isbn'] == old['isbn']
    assert rows[0]['url'] == old['url']
    assert mw.item_urls(rows[0]) == mw.item_urls(old)


def test_ambiguous_secondary_url_refuses_destructive_merge(tmp_path):
    p = tmp_path / 'items.jsonl'
    put(p, [dict(url=f'https://a.test/{i}', sources=[{'url':'https://b.test/shared'}]) for i in (1,2)])
    before = p.read_bytes()
    with pytest.raises(ValueError, match='Ambiguous'):
        mw.append_jsonl(p, [{'url':'https://b.test/shared'}])
    assert p.read_bytes() == before


@pytest.mark.parametrize('target', ['items.jsonl', 'items.jsonl.spool'])
@pytest.mark.parametrize('bad', ['{broken', 'null', '[]'])
def test_corrupt_durable_input_never_disappears(tmp_path, target, bad):
    p = tmp_path / 'items.jsonl'
    put(p, [{'url':'https://a.test/old'}])
    broken = tmp_path / target
    with broken.open('a') as f:
        f.write(bad+'\n')
    before = {x: x.read_bytes() for x in (p, broken)}
    with pytest.raises(ValueError, match='input preserved'):
        mw.append_jsonl(p, [{'url':'https://a.test/new'}])
    assert all(x.read_bytes() == b for x,b in before.items())


def test_raw_reingestion_preserves_first_detection_and_review_attempts(tmp_path):
    p = tmp_path/'items.jsonl'
    put(p, [dict(url='https://a.test/book', detected_at='2026-01-01', standardize_attempts=3)])
    mw.append_jsonl(p, [dict(url='https://a.test/book', detected_at='2026-09-24')])
    row = mw.read_jsonl_strict(p)[0]
    assert row['detected_at']=='2026-01-01'
    assert row['standardize_attempts']==3


def test_state_recovery_considers_secondary_sources_and_rejections(tmp_path):
    p = tmp_path/'items.jsonl'
    put(p, [dict(url='https://a.test/a', sources=[{'url':'https://b.test/b'}])])
    put(tmp_path/'non_manga_blacklist.jsonl', [{'url':'https://a.test/rejected'}])
    state = {'url:'+url: {'content_hash':'hash'} for url in
             ['https://a.test/a','https://b.test/b','https://a.test/rejected','https://a.test/missing']}
    result = mw.reconcile_ingestion_state(state, p)
    assert set(state)-set(result)=={'url:https://a.test/missing'}


def test_image_and_extra_only_changes_change_hash():
    c = mw.candidate_from_source(mw.Source(name='X',url='https://a.test'), 'Berserk Deluxe 1','https://a.test/book','')
    mw.score_candidate(c)
    original = c.content_hash
    c.image_url='https://a.test/new.jpg'
    mw._recompute_content_hash(c)
    assert c.content_hash != original
    original=c.content_hash
    c.extras=[{'description':'Art card'}]
    mw._recompute_content_hash(c)
    assert c.content_hash != original


def test_queue_it_redirect_is_a_challenge():
    assert mw.detect_challenge('<html>wait</html>',200,'https://panini.queue-it.net/?x=1')=='queue-it'
    assert mw.detect_challenge('queue-it customer',200,'https://shop.example/product') is None


def test_search_skip_keeps_full_source_name(tmp_path):
    name='ES - Panini España (search) [search: deluxe]'
    (tmp_path/'01-scrape.log').write_text(f'[SKIP-empty] {name}: HTML muy corto (2000 chars).\n')
    assert list(health.parse_run_log(tmp_path)) == [name]


def test_wiki_network_warning_does_not_report_healthy(tmp_path):
    (tmp_path/'02-social.log').write_text('[BOOTSTRAP-WIKI] fuente: socialanime\n[socialanime] WARN type=box: 403 Client Error\n  candidates totales: 0\n')
    stats=health.parse_run_log(tmp_path)['wiki:socialanime']
    assert stats['error']
    assert health.classify(health._single_run_agg(stats))=='broken_http'


@pytest.mark.parametrize('title',['Blue Lock Vol. 15 - Capa Variante','Wotakoi 10 Capa Alternativa'])
def test_portuguese_variants_survive_gate(title):
    score,signals,types=mw.detect_signals(title)
    assert score>0 and 'variant_cover' in types
    assert mw.is_collectible_edition(title,'',types,'manga')[0]


def test_meian_is_automatically_ingested_in_both_modes():
    for mode in ['full','delta']:
        script=Path(f'scripts/scrape_{mode}.sh').read_text()
        assert '--bootstrap-wiki meian ' in script
        assert 'exit 1\nfi' in script[script.rfind('# Partial runs'):]


def test_recent_updates_are_not_starved_by_old_missing_urls():
    from wikis import mangavariant as mv
    entries=[('https://mangavariant.com/variant/a/old/','2020-01-01'),
             ('https://mangavariant.com/variant/b/updated/','2026-09-24')]
    selected,stats=mv._select_incremental_urls(entries,{'/variant/b/updated'},since='2026-09-20',max_new=1)
    assert selected==[entries[1][0]]
    assert stats['capped']


def test_panini_short_date_requires_italian_source_label():
    assert mw.extract_release_date('Fumetti 17/09/26')=='2026-09-17'
    assert mw.extract_release_date('Fumetti 31/02/26')==''
    assert mw.extract_release_date('17/09/26')==''


def test_incomplete_bootstrap_cannot_be_healthy(tmp_path):
    (tmp_path/'02.log').write_text('[BOOTSTRAP-WIKI] fuente: socialanime\n')
    stats=health.parse_run_log(tmp_path)['wiki:socialanime']
    assert health.classify(health._single_run_agg(stats))=='broken_skip'


def test_sevenseas_failure_is_not_empty_success(monkeypatch):
    from wikis import sevenseas as ss
    import requests
    class Session:
        def get(self,*a,**k):
            raise requests.ConnectionError('offline')
    session=Session()
    monkeypatch.setattr(ss.time,'sleep',lambda _:None)
    assert ss.fetch_books(session)==[]
    assert session._ingestion_issues


def test_storefront_failure_is_reported(monkeypatch):
    from wikis import storefront_json as sf
    import requests
    class Session:
        def get(self,*a,**k):
            raise requests.ConnectionError('offline')
    session=Session()
    monkeypatch.setattr(sf.time,'sleep',lambda _:None)
    assert sf._get_json(session,'https://store.example/api') is None
    assert session._ingestion_issues


def test_explicit_rejection_survives_hash_changes_and_empty_state(tmp_path):
    p=tmp_path/'items.jsonl'
    c=mw.candidate_from_source(mw.Source(name='X',url='https://a.test'), 'Berserk Deluxe 1','https://a.test/book','')
    mw.score_candidate(c)
    put(tmp_path/'non_manga_blacklist.jsonl',[{'url':c.url}])
    state=mw.reconcile_ingestion_state({},p)
    assert mw.flush_source_candidates([c],state,p,min_score=0)==0
    assert mw.process_state([c],state,min_score=0,include_seen=True)[0]==[]
    assert not p.exists()


def test_selector_results_cannot_bypass_non_manga_gate(tmp_path):
    from bs4 import BeautifulSoup
    source=mw.Source(name='BR - Panini', url='https://panini.com.br/',purity='mixed',selectors={'item_selector':'li','title_selector':'a'})
    html='<ul><li><a href="/batman">Absolute Batman 1 Capa Variante</a></li><li><a href="/wotakoi">Wotakoi Vol. 10 Capa Variante</a></li></ul>'
    candidates=[mw.score_candidate(c) for c in mw.extract_with_selectors(source,BeautifulSoup(html,'html.parser'),10)]
    assert len(candidates)==2
    assert mw.flush_source_candidates(candidates,{},tmp_path/'items.jsonl',0)==1
    reportable,_=mw.process_state(candidates,{},0,False)
    assert [c.title for c in reportable]==['Wotakoi Vol. 10 Capa Variante']


def test_marketing_bestseller_does_not_prove_a_product_is_a_novel():
    assert not mw.is_pure_novel('The One - Coffret Partie 1','Le best-seller de Nicky Lee')[0]
    assert mw.is_pure_novel('Western novel','Saga literaria romántica bestseller')[0]


@pytest.mark.parametrize('title,publisher', [('Akira — Vol.1 - Graphitti limited','Marvel Comics'),('One-Punch Man — Vol.23 - Avengers variant',''),('Chihayafuru — Mickey Mouse 90 years - variant','')])
def test_structured_manga_variant_identity_survives_western_brand_keywords(title,publisher):
    tags=['variant-catalog','mv-series:akira']
    assert mw.is_likely_manga(title,tags=tags,publisher=publisher,url='https://mangavariant.com/variant/akira/special/')[0]
    assert not mw.is_likely_manga(title,tags=tags,publisher=publisher,url='https://shop.test/item')[0]


@pytest.mark.parametrize('blocked,full',[(True,False),(False,True)])
def test_listing_partial_pages_survive_and_full_overrides_source_cap(tmp_path,monkeypatch,capsys,blocked,full):
    import sys
    argv=['scraper','--dry-run','--skip-image-download','--sleep-seconds','0',
          '--data-dir',str(tmp_path),'--reports-dir',str(tmp_path),'--max-pages','2','--min-score','0']
    if full:argv+=['--full-catalog']
    monkeypatch.setattr(sys,'argv',argv)
    args=mw.parse_args()
    source=mw.Source(name='Test',url='https://example.test/1',max_pages=1 if full else 0)
    monkeypatch.setattr(mw,'load_sources',lambda _: [source])
    fetched=[]
    def fetch(session,url,timeout,**kwargs):
        fetched.append(url)
        return ('blocked' if blocked and url.endswith('/2') else url), {'http_status':200,'final_url':url}
    monkeypatch.setattr(mw,'fetch_with_metadata',fetch)
    monkeypatch.setattr(mw,'detect_empty_or_js',lambda *a:None)
    monkeypatch.setattr(mw,'detect_challenge',lambda text,*a:'queue-it' if text=='blocked' else None)
    monkeypatch.setattr(mw,'find_next_page_url',lambda soup,url,visited:'https://example.test/2' if url.endswith('/1') else None)
    monkeypatch.setattr(mw,'extract_generic_html',lambda source,text,**k:[mw.candidate_from_source(source,'Berserk Deluxe '+text[-1],text,'')])
    assert mw.run(args)==(1 if blocked else 0)
    assert fetched==['https://example.test/1','https://example.test/2']
    assert f'reportables: {1 if blocked else 2}' in capsys.readouterr().out


def test_cleanup_matches_ingestion_for_raw_curated_variants():
    from scripts.retrofit.filter_collectible import should_reject
    raw={'title':'One Piece — Celebration cover (100M copies)','tags':['variant-catalog'],'product_type':'manga'}
    assert not should_reject(raw,False,'regular_tomo')
    assert should_reject(raw,False,'no_title')
    assert should_reject({'title':'One Piece 1','tags':[]},False,'regular_tomo')


def test_spp_keyword_overlap_does_not_truncate_later_pages(monkeypatch):
    from scripts.wikis import storefront_json as sf
    monkeypatch.setattr(sf, '_SPP_KEYWORDS', ['first', 'second'])
    def get(session, url, params):
        start = params['startIndex']
        if start == 0:
            return [{'Id': i} for i in range(1, 151)]
        if params['keyword'] == 'second' and start == 150:
            return [{'Id': 151}]
        return []
    monkeypatch.setattr(sf, '_get_json', get)
    assert len(list(sf._spp_list(SimpleNamespace(), 0))) == 151


def test_spp_repeated_page_is_failure_not_success(monkeypatch):
    from scripts.wikis import storefront_json as sf
    monkeypatch.setattr(sf, '_SPP_KEYWORDS', ['first'])
    monkeypatch.setattr(sf, '_get_json', lambda *a: [{'Id': i} for i in range(1,151)])
    session = SimpleNamespace()
    assert len(list(sf._spp_list(session, 0))) == 150
    assert 'repeated page' in session._ingestion_issues[0]


def test_shopify_limit_and_invalid_schema_are_reported(monkeypatch):
    from scripts.wikis import storefront_json as sf
    for data in ({'products': [{'id': 1}]}, {'error': 'maintenance'}):
        monkeypatch.setattr(sf, '_get_json', lambda *a: data)
        session = SimpleNamespace()
        list(sf._shopify_like_list('https://shop.test', session, 0, max_pages=1))
        assert session._ingestion_issues


def test_sevenseas_delta_uses_modification_date_and_reports_cap():
    from scripts.wikis import sevenseas as ss
    calls = []
    class Session:
        def get(self, url, **kwargs):
            calls.append(kwargs['params'])
            return SimpleNamespace(status_code=200, headers={'X-WP-TotalPages':'2'},
                                   raise_for_status=lambda:None, json=lambda:[{'id':1}]*100)
    session = Session()
    assert len(ss.fetch_books(session, after='2026-01-01T00:00:00', max_pages=1, sleep_seconds=0)) == 100
    assert calls[0]['modified_after'] == '2026-01-01T00:00:00'
    assert 'after' not in calls[0]
    assert session._ingestion_issues


def test_socialanime_full_page_at_limit_is_incomplete():
    from scripts.wikis import socialanime as sa
    session = SimpleNamespace(get=lambda *a,**k:SimpleNamespace(
        raise_for_status=lambda:None, json=lambda:[{'id':i} for i in range(25)]))
    assert len(sa.fetch_feed_pages(session, 'variant', max_pages=1)) == 25
    assert session._ingestion_issues


def test_shared_secondary_url_can_resolve_unique_isbn(tmp_path):
    p = tmp_path / 'items.jsonl'
    shared = 'https://shop.test/shared'
    put(p, [dict(url='https://a.test/1', isbn='9782344048078', title='Other', sources=[{'url':shared}]),
            dict(url='https://a.test/2', isbn='9782344069158', title='Artbook', sources=[{'url':shared}])])
    mw.append_jsonl(p, [dict(url=shared, isbn='9782344069158', title='Artbook updated')])
    rows = mw.read_jsonl_strict(p)
    assert len(rows) == 2
    assert next(r for r in rows if r['url'].endswith('/1'))['title'] == 'Other'
    assert next(r for r in rows if r['url'].endswith('/2'))['title'] == 'Artbook updated'


def test_secondary_url_with_conflicting_isbn_does_not_absorb_new_edition(tmp_path):
    p = tmp_path / 'items.jsonl'
    shared = 'https://shop.test/shared'
    put(p, [dict(url='https://a.test/1', isbn='9782344048078', title='Other', sources=[{'url':shared}])])
    mw.append_jsonl(p, [dict(url=shared, isbn='9782344069158', title='Artbook')])
    assert {r['isbn'] for r in mw.read_jsonl_strict(p)} == {'9782344048078','9782344069158'}


def test_checkpoint_replays_downtime_and_is_scoped_to_data_dir(tmp_path):
    import datetime as dt
    from scripts.wikis.checkpoints import read_checkpoint, resume_month, write_checkpoint
    assert resume_month((2026,9), None) == (2026,9)
    started = dt.datetime(2026,5,3,tzinfo=dt.timezone.utc)
    write_checkpoint(tmp_path, 'sevenseas', started)
    assert read_checkpoint(tmp_path,'sevenseas') == started
    assert read_checkpoint(tmp_path,'meian') is None
    assert resume_month((2026,9), started) == (2026,4)
    assert resume_month((2000,1), started) == (2000,1)


@pytest.mark.parametrize('bad', ['2026-13','2026-00','0000-01'])
def test_wiki_rejects_impossible_months(bad):
    with pytest.raises(SystemExit):
        mw._parse_wiki_month(bad,2024,1)


def test_kodansha_missing_total_does_not_truncate_search():
    from scripts.wikis import kodansha_us as kd
    calls=[]
    class Session:
        def get(self, url, **kwargs):
            page=kwargs['params']['page'];calls.append(page)
            return SimpleNamespace(ok=True,json=lambda:{'data':[{'slug':str(page)}] if page<3 else []})
    assert len(kd.search_series(Session(),'deluxe')) == 2
    assert calls == [1,2,3]


def test_kodansha_http_failure_is_reported():
    from scripts.wikis import kodansha_us as kd
    session=SimpleNamespace(get=lambda *a,**k:SimpleNamespace(ok=False,status_code=403))
    assert kd.search_series(session,'deluxe') == []
    assert session._ingestion_issues


@pytest.mark.parametrize('module,function,args',[
    ('blogbbm','fetch_post',('https://example.test',)),
    ('booksprivilege','fetch_html',('https://example.test',)),
    ('sumikko','fetch_html',('https://example.test',)),
])
def test_additional_wiki_fetch_failures_are_not_empty_success(module,function,args):
    import importlib,requests
    mod=importlib.import_module('scripts.wikis.'+module)
    class Session:
        def get(self,*a,**k):raise requests.ConnectionError('offline')
    session=Session()
    getattr(mod,function)(session,*args)
    assert session._ingestion_issues


@pytest.mark.parametrize('mode', ['success','failed_source','failed_sink','dry_run','future_only'])
def test_wiki_watermark_requires_successful_durable_commit(tmp_path,monkeypatch,mode):
    import sys
    from wikis import meian
    from scripts.wikis.checkpoints import read_checkpoint
    monkeypatch.setattr(sys,'argv',['scraper','--bootstrap-wiki','meian','--skip-image-download'])
    args=mw.parse_args()
    args.dry_run = mode == 'dry_run'
    if mode == 'future_only':
        future_year=mw.dt.datetime.now(mw.dt.timezone.utc).year+1
        args.wiki_from=f'{future_year}-01'
        args.wiki_to=f'{future_year}-12'
    def bootstrap(*a,**kwargs):
        if mode == 'failed_source':
            kwargs['session']._ingestion_issues.append('connection failed')
        return []
    monkeypatch.setattr(meian,'bootstrap',bootstrap)
    if mode == 'failed_sink':
        def fail(*a,**k):raise OSError('disk full')
        monkeypatch.setattr(mw,'append_jsonl',fail)
    session=SimpleNamespace()
    if mode == 'failed_sink':
        with pytest.raises(OSError):
            mw._run_wiki_bootstrap(args,session,{},tmp_path/'state.json',tmp_path/'items.jsonl',tmp_path/'report.md')
    else:
        rc=mw._run_wiki_bootstrap(args,session,{},tmp_path/'state.json',tmp_path/'items.jsonl',tmp_path/'report.md')
        assert rc == (1 if mode == 'failed_source' else 0)
    assert (read_checkpoint(tmp_path,'meian') is not None) == (mode == 'success')


def test_sitemap_http_gzip_is_not_decompressed_twice():
    from scripts.sitemap_miner import _fetch_text
    xml = '<urlset><url><loc>https://shop.test/book</loc></url></urlset>'
    response = SimpleNamespace(status_code=200,headers={'Content-Encoding':'gzip'},
                               content=xml.encode(),text=xml,encoding='utf-8',raise_for_status=lambda:None)
    session=SimpleNamespace(get=lambda *a,**k:response)
    assert _fetch_text('https://shop.test/sitemap.xml.gz',session) == xml


def test_root_entrypoint_can_serialize_real_candidates_in_fresh_interpreter():
    import subprocess,sys
    root=Path(__file__).resolve().parents[1]
    code="""
import runpy
runpy.run_path('manga_watch.py', run_name='entrypoint_test')
from scripts.manga_watch import Source, candidate_from_source, candidate_to_json
c=candidate_from_source(Source(name='X',url='https://shop.test'), 'Berserk Deluxe Vol. 1', 'https://shop.test/book', '')
assert candidate_to_json(c)['title'] == c.title
"""
    result=subprocess.run([sys.executable,'-c',code],cwd=root,capture_output=True,text=True,timeout=30)
    assert result.returncode == 0,result.stderr


def test_wiki_html_challenge_cannot_become_successful_empty_catalog():
    import requests
    from scripts.wikis.health import install_response_guard
    session=requests.Session()
    install_response_guard(session)
    install_response_guard(session)
    assert len(session.hooks['response']) == 1
    response=requests.Response()
    response.status_code=200
    response.url='https://shop.test/catalog'
    response.headers['Content-Type']='text/html'
    response._content=b'<html><title>Just a moment...</title><script src="/cdn-cgi/challenge-platform/scripts/jsd/main.js"></script></html>'
    with pytest.raises(requests.HTTPError):
        session.hooks['response'][0](response)
    assert session._ingestion_issues
    response.headers['Content-Type']='application/json'
    response._content=b'[]'
    assert session.hooks['response'][0](response) is response


@pytest.mark.parametrize('title,volume',[('3×3 EYES 完全版 第22期','22'),('作品 第２３卷','23'),('作品 第4冊','4')])
def test_chinese_numbered_volumes_are_distinct(title,volume):
    assert mw._extract_volume(title) == volume


def test_unresolved_raw_volume_cannot_merge_distinct_products():
    source=mw.Source(name='X',url='https://a.test',country='Hong Kong',publisher='X')
    rows=[mw.candidate_to_json(mw.candidate_from_source(source,title,'https://a.test/'+str(i),''))
          for i,title in enumerate(['Berserk Artbook Sunrise','Berserk Artbook Sunset'])]
    assert all(r['cluster_key'].startswith('url:') for r in rows)
    assert len(mw.consolidate_by_cluster(rows)) == 2


def test_historical_shared_link_cannot_absorb_another_numbered_volume(tmp_path):
    p=tmp_path/'items.jsonl'
    shared='https://jd-intl.com/product/22'
    put(p,[dict(url=f'https://jd-intl.com/product/{n}',title=f'3×3 EYES 完全版 第{n}期',
                sources=[{'url':shared}]) for n in (23,24)])
    mw.append_jsonl(p,[dict(url=shared,title='3×3 EYES 完全版 第22期',volume='22')])
    rows = mw.read_jsonl_strict(p)
    assert len(rows) == 3
    assert all(shared not in mw.item_urls(r) for r in rows if r['url'] != shared)


def test_next_article_is_not_catalog_pagination():
    from bs4 import BeautifulSoup
    soup=BeautifulSoup('<a class="next" href="/news/serialstories_02_you23">Next</a>','html.parser')
    assert mw.find_next_page_url(soup,'https://www.sanyodo.co.jp/news/bks_new_comic_limited-edition',set()) is None


def test_ecbeing_next_catalog_page_is_supported():
    from bs4 import BeautifulSoup
    soup=BeautifulSoup('<a rel="next" href="/shop/c/c109050_p2/">次</a>','html.parser')
    assert mw.find_next_page_url(soup,'https://store.kadokawa.co.jp/shop/c/c109050/',set()).endswith('_p2/')


@pytest.mark.parametrize('title,volume',[
 ('Atak Tytanów - Before the Fall tom 06 (oprawa twarda) - OSTATNIE','6'),
 ('Aufgeweckt mit einem Kuss, Band 08 mit Schuber','8'),
 ('GACHIAKUTA, Band 01-05 im Schuber','1-5'),
 ('FLASHLIGHT 2 【特裝版】','2'),
 ('고깔모자의 아틀리에 16 (한정판)','16'),
 ('메리 마블링 9~10 세트 - 전2권 (한정판)','9-10'),
])
def test_multilingual_volume_identity_preserves_numbers_and_ranges(title,volume):
    assert mw._extract_volume(title) == volume


def test_ambiguous_input_is_durable_without_blocking_unrelated_products(tmp_path):
    p=tmp_path/'items.jsonl';shared='https://b.test/shared'
    put(p,[dict(url=f'https://a.test/{i}',isbn=isbn,sources=[{'url':shared}])
           for i,isbn in [(1,'9782344048078'),(2,'9782344069158')]])
    conflict={'url':shared,'title':'Unknown Artbook'}
    mw._append_spool(p,[conflict,{'url':'https://a.test/new','title':'New book'}])
    state={'url:'+shared:{'content_hash':'cached'}}
    deferred=mw.persist_ingestion_rows(p,[],state)
    assert deferred == [conflict]
    assert 'url:'+shared not in state
    assert len(mw.read_jsonl_strict(p)) == 3
    assert not mw._items_spool_path(p).exists()
    ledger=p.with_name(p.name+'.conflicts')
    assert mw.read_jsonl_strict(ledger) == [conflict]
    assert mw.persist_ingestion_rows(p,[dict(conflict,isbn='9782344069158')],state) == []
    assert mw.read_jsonl_strict(ledger) == []
    assert len(mw.read_jsonl_strict(p)) == 3


def test_deferred_rows_survive_failure_of_corpus_write(tmp_path,monkeypatch):
    p=tmp_path/'items.jsonl';shared='https://b.test/shared'
    put(p,[dict(url=f'https://a.test/{i}',sources=[{'url':shared}]) for i in (1,2)])
    before=p.read_bytes()
    real_write=mw.write_items_atomic
    def fail_corpus(path,rows):
        if path == p:raise OSError('disk full')
        real_write(path,rows)
    monkeypatch.setattr(mw,'write_items_atomic',fail_corpus)
    with pytest.raises(OSError):mw.append_jsonl(p,[{'url':shared}],defer_conflicts=True)
    assert p.read_bytes() == before
    assert mw.read_jsonl_strict(p.with_name(p.name+'.conflicts')) == [{'url':shared}]


def test_distinct_raw_variant_covers_of_same_volume_do_not_collapse():
    source=mw.Source(name='X',url='https://a.test',country='Italia',publisher='Panini')
    rows=[]
    for label in ['A','B']:
        c=mw.candidate_from_source(source,f'Berserk Vol. 1 Variant {label}','https://a.test/'+label,'')
        mw.score_candidate(c)
        rows.append(mw.candidate_to_json(c))
    assert len(mw.consolidate_by_cluster(rows)) == 2
    assert all(r['cluster_key'].startswith('url:') for r in rows)


@pytest.mark.parametrize('title',[
 'One Piece OP11 Display Box 24 Booster ENG - Case 12 Box',
 "MTG - The Lord of the Rings: Middle-earth Collector's Booster Display (12 Packs) - ENG",
 'Maxi Mystery Box con Booster Box One Piece',
])
def test_card_displays_are_not_manga_box_sets(title):
    assert mw.is_likely_manga(title)[0] is False


def test_numbered_manga_can_include_a_booster_bonus():
    assert mw.is_likely_manga('One Piece Vol. 1 with booster pack')[0]


@pytest.mark.parametrize('enabled',[True,False])
def test_queue_it_can_render_normally_when_browser_is_enabled(tmp_path,monkeypatch,enabled):
    import sys
    argv=['scraper','--dry-run','--skip-image-download','--data-dir',str(tmp_path)]
    if enabled:argv+=['--enable-js']
    monkeypatch.setattr(sys,'argv',argv);args=mw.parse_args()
    source=mw.Source(name='Panini',url='https://www.panini.it/catalog')
    monkeypatch.setattr(mw,'load_sources',lambda _: [source])
    monkeypatch.setattr(mw,'fetch_with_metadata',lambda *a,**k:('<html>Queue</html>',{'http_status':200,'final_url':'https://panini.queue-it.net/?q=123'}))
    rendered=[]
    def browser(**kwargs):
        rendered.append(kwargs['url'])
        return '<html><h1>Berserk Deluxe Vol. 1</h1></html>',{'http_status':200,'final_url':source.url}
    monkeypatch.setattr(mw,'fetch_with_playwright',browser)
    monkeypatch.setattr(mw,'detect_empty_or_js',lambda *a:None)
    monkeypatch.setattr(mw,'extract_generic_html',lambda *a,**k:[mw.candidate_from_source(source,'Berserk Deluxe Vol. 1',source.url+'/book','')])
    monkeypatch.setattr(mw,'find_next_page_url',lambda *a:None)
    assert mw.run(args) == (0 if enabled else 1)
    assert bool(rendered) == enabled


def test_secondary_link_cannot_merge_distinct_covers_even_with_same_isbn(tmp_path):
    p=tmp_path/'items.jsonl';shared='https://shop.test/variant-b'
    put(p,[dict(url='https://shop.test/variant-a',title='Berserk Vol. 1 Variant A',
                isbn='9782344048078',sources=[{'url':shared}])])
    mw.append_jsonl(p,[dict(url=shared,title='Berserk Vol. 1 Variant B',isbn='9782344048078')])
    rows=mw.read_jsonl_strict(p)
    assert len(rows) == 2
    assert shared not in mw.item_urls(next(r for r in rows if r['url'].endswith('variant-a')))


def test_secondary_url_with_distinct_valid_isbns_is_a_separate_product(tmp_path):
    p=tmp_path/'items.jsonl'; shared='https://store.test/shared'
    put(p,[dict(url=f'https://publisher.test/{i}',isbn=isbn,sources=[{'url':shared}])
           for i,isbn in [(1,'9784065288894'),(2,'9784065226513')]])
    deferred=mw.append_jsonl(p,[{'url':shared,'isbn':'9784065194256','title':'Separate edition'}],defer_conflicts=True)
    rows=mw.read_jsonl_strict(p)
    assert not deferred
    assert len(rows)==3
    assert all(shared not in mw.item_urls(r) for r in rows if r['url']!=shared)


def test_isbn_conflict_removes_wrong_owner_but_preserves_unknown_owner(tmp_path):
    p=tmp_path/'items.jsonl'; shared='https://store.test/shared'
    put(p,[dict(url='https://publisher.test/correct',sources=[{'url':shared}]),
           dict(url='https://publisher.test/other',isbn='9784758025089',sources=[{'url':shared}])])
    assert not mw.append_jsonl(p,[{'url':shared,'isbn':'9784758020886','title':'Correct edition'}],defer_conflicts=True)
    rows=mw.read_jsonl_strict(p)
    assert len(rows)==2
    correct=next(r for r in rows if r['url'].endswith('/correct'))
    assert correct['isbn']=='9784758020886'
    assert shared not in mw.item_urls(next(r for r in rows if r['url'].endswith('/other')))


def test_invalid_isbn_tokens_cannot_disambiguate_multiple_owners(tmp_path):
    p=tmp_path/'items.jsonl';shared='https://shop.test/shared'
    put(p,[dict(url=f'https://publisher.test/{i}',isbn=code,sources=[{'url':shared}])
           for i,code in [(1,'2100013335255'),(2,'2100013335262')]])
    pending=mw.append_jsonl(p,[{'url':shared,'isbn':'2100013335286'}],defer_conflicts=True)
    assert len(pending)==1
    assert len(mw.read_jsonl_strict(p))==2


def test_listing_page_is_durable_before_process_interruption(tmp_path, monkeypatch):
    import sys
    monkeypatch.setattr(sys, 'argv', ['scraper', '--skip-image-download', '--sleep-seconds', '0',
                        '--data-dir', str(tmp_path), '--reports-dir', str(tmp_path), '--full-catalog'])
    source=mw.Source(name='Test',url='https://example.test/catalog')
    monkeypatch.setattr(mw,'load_sources',lambda _: [source])
    def fetch(session,url,timeout,**kwargs):
        if 'page=2' in url:
            raise KeyboardInterrupt('simulated process interruption')
        return 'catalog', {'http_status':200,'final_url':url}
    monkeypatch.setattr(mw,'fetch_with_metadata',fetch)
    monkeypatch.setattr(mw,'detect_empty_or_js',lambda *a:None)
    monkeypatch.setattr(mw,'find_next_page_url',lambda *a:'https://example.test/catalog?page=2')
    monkeypatch.setattr(mw,'extract_generic_html',lambda *a,**k:[mw.candidate_from_source(source,'Berserk Deluxe 1','https://example.test/product','')])
    with pytest.raises(KeyboardInterrupt): mw.run(mw.parse_args())
    pending=mw._read_spool(tmp_path/'items.jsonl')
    assert [r['url'] for r in pending]==['https://example.test/product']
    assert not (tmp_path/'state.json').exists()


def test_panini_browser_session_reuses_context_but_isolates_hosts():
    from types import SimpleNamespace
    contexts=[]
    class Context:
        def __init__(self):self.closed=False
        def add_init_script(self,*a):pass
        def new_page(self):
            return SimpleNamespace(goto=lambda *a,**k:SimpleNamespace(status=200),
                title=lambda:'Catalog',wait_for_timeout=lambda *a:None,
                wait_for_function=lambda *a,**k:None,evaluate=lambda *a:None,
                content=lambda:'<html>catalog</html>',url='https://www.panini.it/catalog',
                close=lambda:None)
        def close(self):self.closed=True
    class Browser:
        def new_context(self,**kw):
            ctx=Context();contexts.append(ctx);return ctx
    browser=Browser()
    for url in ['https://www.panini.it/catalog?p=1','https://www.panini.it/catalog?p=2']:
        mw._fetch_with_playwright_impl(browser,url,1000,'domcontentloaded')
    assert len(contexts)==1 and not contexts[0].closed
    mw._fetch_with_playwright_impl(browser,'https://www.panini.es/catalog',1000,'domcontentloaded')
    assert len(contexts)==2
    mw._fetch_with_playwright_impl(browser,'https://other.test/catalog',1000,'domcontentloaded')
    assert len(contexts)==3 and contexts[-1].closed


def test_verified_collector_category_keeps_bare_title_without_inventing_type(tmp_path):
    from scripts.retrofit.filter_collectible import should_reject
    source=mw.Source(name='Curated official category',url='https://example.test/category',source_class='official',tags=['manga','collector-catalog','search:variant esclusiva'])
    candidates=[mw.score_candidate(mw.candidate_from_source(source,'Sakamoto Days 25',f'https://example.test/edition/{n}','')) for n in [1,2]]
    assert all(c.score>=20 and 'box_set' not in c.signal_types for c in candidates)
    accepted,_=mw.process_state(candidates,{},20,False)
    assert len(accepted)==2
    rows=[mw.candidate_to_json(c) for c in accepted]
    assert all(not r.get('edition_key') and r['cluster_key'].startswith('url:') for r in rows)
    assert all(not should_reject(r,False,'regular_tomo') for r in rows)
    assert len({r['cluster_key'] for r in rows})==2


def test_ordinary_search_is_not_curated_category():
    source=mw.Source(name='Search',url='https://example.test/search',tags=['search:variant'])
    c=mw.score_candidate(mw.candidate_from_source(source,'Sakamoto Days 25','https://example.test/product',''))
    assert not mw.is_curated_collectible_source(c)
    assert mw.process_state([c],{},20,False)[0]==[]


@pytest.mark.parametrize('title,expected', [
    ('Kaiju No. 8 Limited Edition 1','1'),
    ('Kaiju No. 8 Limited Edition',''),
    ('Kaiju Nº8 nº16','16'),
    ('Kaiju No. 8 Vol. 8','8'),
])
def test_series_number_is_not_a_special_edition_volume(title,expected):
    assert mw._extract_volume(title)==expected


def test_invalid_isbn10_cannot_detach_secondary_owners(tmp_path):
    p=tmp_path/'items.jsonl';shared='https://shop.test/shared'
    put(p,[dict(url=f'https://publisher.test/{i}',isbn=code,sources=[{'url':shared}])
           for i,code in [(1,'1234567890'),(2,'1234567891')]])
    pending=mw.append_jsonl(p,[{'url':shared,'isbn':'1234567892'}],defer_conflicts=True)
    assert len(pending)==1
    assert all(shared in mw.item_urls(r) for r in mw.read_jsonl_strict(p))


def test_secondary_refresh_keeps_protected_canonical_url_key(tmp_path):
    p = tmp_path / 'items.jsonl'
    old = dict(url='https://publisher.test/book', title='Berserk Artbook',
               isbn='9782344073124', identity_review_required=True,
               sources=[{'url': 'https://publisher.test/book'},
                        {'url': 'https://catalog.test/book'}])
    old['cluster_key'] = mw.derive_cluster_key(old)
    put(p, [old])
    mw.append_jsonl(p, [dict(url='https://catalog.test/book', title='Berserk Artbook',
                            isbn=old['isbn'])])
    rows = mw.read_jsonl_strict(p)
    assert len(rows) == 1
    assert rows[0]['url'] == old['url']
    assert rows[0]['cluster_key'] == mw.derive_cluster_key(rows[0])
    assert mw.item_urls(rows[0]) == mw.item_urls(old)
