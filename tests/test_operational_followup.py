import json
import sys
from bs4 import BeautifulSoup
from scripts import manga_watch as m, ingestion_policy as policy
from scripts.audit import source_health as health


def test_magento_search_controller_index_is_pagination():
    url='https://tiendapanini.com.mx/catalogsearch/result/?q=especial&skip_default_filters=true'
    target='/catalogsearch/result/index/?p=2&q=especial&skip_default_filters=true'
    soup=BeautifulSoup(f'<a class="action next" href="{target}">Página Siguiente</a>','html.parser')
    assert m.find_next_page_url(soup,url,{url})=='https://tiendapanini.com.mx'+target
    soup=BeautifulSoup('<a class="next" href="/another-product">Next</a>','html.parser')
    assert m.find_next_page_url(soup,url,{url}) is None


def test_paper_grade_is_not_artbook_but_real_artbook_still_is():
    for text in ['畫冊等級的高階美術紙','畫冊級紙張','画集等级用纸']:
        assert 'artbook' not in m.detect_signals(text)[2]
    assert 'artbook' in m.detect_signals('公式畫冊 特別版')[2]
    assert 'artbook' in m.detect_signals('公式畫冊。畫冊等級用紙')[2]


def test_daily_delta_defers_uninitialized_sources_without_network(tmp_path,monkeypatch,capsys):
    src=m.Source(name='Pending',url='https://example.test/catalog')
    monkeypatch.setattr(m,'load_sources',lambda _: [src])
    monkeypatch.setattr(m,'_fetch_source_html',lambda *a,**k:None,raising=False)
    monkeypatch.setattr(m,'fetch_with_metadata',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')))
    monkeypatch.setattr(sys,'argv',['scraper','--ingestion-mode','delta','--data-dir',str(tmp_path),'--reports-dir',str(tmp_path)])
    assert m.run(m.parse_args())==0
    assert '[SOURCE-DEFERRED] Pending' in capsys.readouterr().out
    assert not policy.has_baseline(tmp_path,'yaml:Pending',src)


def test_initialization_batches_rotate_failed_attempts(tmp_path):
    a=m.Source(name='A',url='https://a.test'); b=m.Source(name='B',url='https://b.test')
    assert policy.pending_batch(tmp_path,[a,b],1)==[a]
    policy.record_attempt(tmp_path,'yaml:A')
    assert policy.pending_batch(tmp_path,[a,b],1)==[b]
    policy.commit_baseline(tmp_path,'yaml:B',b,evidence={})
    assert policy.pending_batch(tmp_path,[a,b],1)==[a]


def test_health_compares_actual_scan_mode_not_run_folder(tmp_path):
    run=tmp_path/'scrape-delta-2026-09-27';run.mkdir()
    (run/'02-wiki.log').write_text('[SOURCE-MODE] full wiki:viz\n[BOOTSTRAP-WIKI] fuente: viz\n  candidates totales: 500\n')
    stats=health.parse_run_log(run)
    assert stats['wiki:viz']['scan_mode']=='full'
    metrics=tmp_path/'metrics.jsonl'
    health.append_metrics(metrics,run,stats)
    record=json.loads(metrics.read_text().splitlines()[0]);assert record['mode']=='full' and record['mode_explicit']
    history=[{'run':f'old-{i}','source':'wiki:viz','mode':'delta','candidates':500} for i in range(3)]
    metrics.write_text('\n'.join(map(json.dumps,history))+'\n')
    current={'wiki:viz':{'candidates':50,'scan_mode':'delta'}}
    assert health.compute_yield_regressions(metrics,'current',current,'delta')==[]


def test_serialization_uses_canonical_language_and_preserves_chinese_variant(monkeypatch):
    from scripts import series_aliases
    monkeypatch.setattr(series_aliases,'log_unmapped_series',lambda *a,**k:None)
    for original, canonical in [('English','Inglés'),('Japanese','Japonés'),('Chino tradicional','Chino')]:
        candidate=m.Candidate(title='Manga Deluxe',url='https://test/book',source='test',source_url='https://test',source_class='official',country='Taiwán',language=original,publisher='test',tags=[],description='')
        row=m.candidate_to_json(m.score_candidate(candidate))
        assert row['language']==canonical
        if original=='Chino tradicional': assert row['language_variant']=='tradicional'


def test_daily_wiki_without_receipt_is_deferred(tmp_path,monkeypatch,capsys):
    monkeypatch.setattr(sys,'argv',['scraper','--ingestion-mode','delta','--bootstrap-wiki','viz','--data-dir',str(tmp_path),'--reports-dir',str(tmp_path)])
    monkeypatch.setattr(m,'fetch_with_metadata',lambda *a,**k: (_ for _ in ()).throw(AssertionError('network')))
    assert m.run(m.parse_args())==0
    assert '[SOURCE-DEFERRED] wiki:viz' in capsys.readouterr().out


def test_deferred_is_not_a_broken_source(tmp_path):
    run=tmp_path/'scrape-delta-2026-09-27';run.mkdir()
    (run/'01-scrape.log').write_text('[SOURCE-DEFERRED] Pending\n')
    stats=health.parse_run_log(run)['Pending']
    assert health.classify(health._single_run_agg(stats))=='pending_baseline'
