"""Adversarial contracts: same illustration is not the same published cover."""
import io
import json
from pathlib import Path
import pytest
from PIL import Image, ImageDraw, ImageEnhance
from scripts.cover_identity import visual_identity, same_asset_url, automatic_upgrade
from scripts.retrofit import maintain_covers as mc


def artwork():
    im = Image.new('RGB', (240, 360), 'white')
    d = ImageDraw.Draw(im)
    for x in range(0, 240, 15):
        d.rectangle((x, 0, x+9, 359), fill=(x, 255-x, (x*7)%255))
    d.rectangle((0, 300, 239, 359), fill='white')
    d.text((15, 312), 'IVREA ARGENTINA 1', fill='black', stroke_width=1)
    return im


def png(im):
    f = io.BytesIO(); im.save(f, format='PNG'); return f.getvalue()


def test_same_asset_resampling_is_allowed():
    a = artwork(); b = a.resize((720, 1080), Image.Resampling.LANCZOS)
    assert automatic_upgrade('https://cdn.test/book-240x360.png', 'https://cdn.test/book.png', png(a), png(b))['ok']


@pytest.mark.parametrize('change', ['publisher_logo', 'colour', 'crop', 'illustration', 'volume'])
def test_regional_and_art_only_changes_are_rejected(change):
    a = artwork(); b = a.copy(); d = ImageDraw.Draw(b)
    if change == 'publisher_logo':
        d.rectangle((0, 300, 239, 359), fill='red'); d.text((10, 310), 'PANINI MEXICO', fill='white')
    elif change == 'volume':
        d.rectangle((180, 0, 239, 70), fill='black'); d.text((190, 15), '10', fill='white')
    elif change == 'colour': b = ImageEnhance.Color(b).enhance(0)
    elif change == 'crop': b = b.crop((20, 0, 220, 360))
    else: b = b.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    assert not visual_identity(png(a), png(b))['ok']


def test_identical_art_from_another_source_never_auto_applies():
    data = png(artwork())
    assert not automatic_upgrade('https://ivrea.test/one-piece.jpg', 'https://panini.test/one-piece.jpg', data, data)['ok']


@pytest.mark.parametrize('url', ['https://cdn.test/image?isbn=9781234567890&width=200',
                                 'https://cdn.test/media/catalog/product/cache/abcdef123456/book.jpg'])
def test_url_transform_cannot_drop_product_identity(url):
    from scripts.retrofit.upgrade_image_resolution import derive_original_url
    assert not same_asset_url(url, 'https://cdn.test/image')


def test_missing_corrupt_and_tiny_reference_fail_closed():
    for data in [b'', b'broken', png(artwork().resize((60, 90)))]:
        assert not visual_identity(data, png(artwork()))['ok']


def test_apply_rechecks_bytes_and_preserves_unrelated_edits(tmp_path):
    images = tmp_path / 'images'; images.mkdir()
    a = png(artwork()); b = png(artwork().resize((720, 1080)))
    (images/'old.png').write_bytes(a); (images/'new.png').write_bytes(b)
    path = tmp_path/'items.jsonl'
    row = {'url':'https://publisher.test/product', 'title':'user edited title',
           'images':[{'url':'https://cdn.test/book-240x360.png','local':'old.png'}]}
    mc.m.write_items_atomic(path,[row])
    result = {'item_url':row['url'],'old_url':row['images'][0]['url'],'old_local':'old.png',
              'item_identity':mc.item_identity(row),'old_sha256':mc.sha(a),'new_url':'https://cdn.test/book.png',
              'new_local':'new.png','new_sha256':mc.sha(b),'status':'ready'}
    (images/'old.png').write_bytes(b)
    assert mc.apply_result(path,images,result)=='bytes_drift'
    (images/'old.png').write_bytes(a)
    assert mc.apply_result(path,images,result)=='applied'
    got=mc.m.read_jsonl_strict(path)[0]
    assert got['title']=='user edited title' and got['cover_history'][0]['old_url']==result['old_url']
    assert mc.apply_result(path,images,result)=='reference_drift'


def test_dry_run_does_not_download_or_write_catalog(tmp_path, monkeypatch):
    images=tmp_path/'images';images.mkdir();(images/'a.png').write_bytes(png(artwork()))
    p=tmp_path/'items.jsonl'
    mc.m.write_items_atomic(p,[{'url':'https://publisher.test/book','images':[{'url':'https://cdn.test/book-240x360.png','local':'a.png'}]}])
    before=p.read_bytes()
    monkeypatch.setattr(mc.image_store,'download_image',lambda *a,**k:pytest.fail('network in dry run'))
    assert mc.run(tmp_path,apply=False)['scheduled']==1
    assert before==p.read_bytes() and not (tmp_path/'cover_maintenance.jsonl').exists()


def test_maintenance_gc_preserves_original_bytes(tmp_path):
    from scripts.retrofit import mirror_images
    images=tmp_path/'images'; images.mkdir()
    (images/'original.png').write_bytes(png(artwork()))
    (images/'current.png').write_bytes(png(artwork()))
    rows=[{'images':[{'local':'current.png'}], 'cover_history':[{'old_local':'original.png','new_local':'current.png'}]}]
    assert mirror_images._run_gc(rows,images,delete=True,dry_run=False)==0
    assert (images/'original.png').exists()


def test_marked_avif_is_still_synthetic(tmp_path):
    from scripts.retrofit import fetch_better_covers as fbc
    assert fbc._is_upscaled({'images':[{'url':'https://cdn.test/book','local':'cover.avif','upscaled':True}]},tmp_path)


def test_mirror_patch_does_not_overwrite_user_edits(tmp_path):
    from scripts.retrofit import mirror_images as mi
    p=tmp_path/'items.jsonl'
    latest={'url':'https://a/book','title':'Edited while downloading','images':[{'url':'https://a/cover','local':''}]}
    mc.m.write_items_atomic(p,[latest,{'url':'https://a/new'}])
    mi._write_items(p,[{'url':latest['url'],'title':'Old title','images':[{'url':'https://a/cover','local':'downloaded.avif'}]}])
    rows=mc.m.read_jsonl_strict(p)
    assert len(rows)==2 and rows[0]['title']==latest['title']
    assert rows[0]['images'][0]['local']=='downloaded.avif'


def test_ingestion_preserves_cover_history(tmp_path):
    p=tmp_path/'items.jsonl';history=[{'old_url':'https://cdn/a','new_url':'https://cdn/b'}]
    mc.m.write_items_atomic(p,[{'url':'https://publisher/book','cover_history':history}])
    mc.m.append_jsonl(p,[{'url':'https://publisher/book','title':'Fresh metadata'}])
    assert mc.m.read_jsonl_strict(p)[0]['cover_history']==history


def test_blocked_image_host_is_not_refetched_and_cools_down(tmp_path, monkeypatch):
    from scripts.retrofit import mirror_images as mi
    images=tmp_path/'images';images.mkdir()
    calls=[]
    def blocked(url, images_dir, session=None, **kwargs):
        calls.append(url)
        session._image_download_failures={url:'http_403'}
        return ''
    monkeypatch.setattr(mi.image_store,'download_image',blocked)
    monkeypatch.setattr(mi,'_classify_failure',lambda *a,**k:pytest.fail('duplicate diagnostic fetch'))
    rows=[{'slug':str(i),'images':[{'url':f'https://blocked.test/{i}.jpg','local':''}]} for i in range(3)]
    opts=dict(workers=1,per_host_limit=1,timeout=(1,1),limit=0,user_agent='test',dry_run=False)
    assert mi._run_backfill(rows,images,**opts)==0
    assert len(calls)==1
    assert mi._run_backfill(rows,images,**opts)==0
    assert len(calls)==1


def test_corrupt_mirror_is_not_published(tmp_path, monkeypatch):
    from scripts.retrofit import mirror_images as mi
    images=tmp_path/'images';images.mkdir();(images/'bad.jpg').write_bytes(b'not an image')
    monkeypatch.setattr(mi.image_store,'download_image',lambda *a,**k:'bad.jpg')
    monkeypatch.setattr(mi.image_store,'placeholder_reason',lambda *a:'')
    rows=[{'slug':'a','images':[{'url':'https://a.test/a.jpg','local':''}]}]
    assert mi._run_backfill(rows,images,workers=1,per_host_limit=1,timeout=(1,1),limit=0,user_agent='test',dry_run=False)==0
    assert not rows[0]['images'][0]['local']


def test_gallery_identity_preserves_product_queries_and_case():
    from scripts import manga_watch as m
    assert m._img_stem('https://cdn.test/image?id=1')!=m._img_stem('https://cdn.test/image?id=2')
    assert m._img_stem('https://cdn.test/image?q=onepiece')!=m._img_stem('https://cdn.test/image?q=berserk')
    assert m._img_stem('https://cdn.test/Cover.jpg')!=m._img_stem('https://cdn.test/cover.jpg')
    assert m._img_stem('https://cdn.test/cover.jpg?v=1')!=m._img_stem('https://cdn.test/cover.jpg?v=2')


def test_legacy_snapshot_writer_refuses_concurrent_metadata_loss(tmp_path):
    from scripts.image_snapshot import read_snapshot,write_snapshot
    p=tmp_path/'items.jsonl'
    mc.m.write_items_atomic(p,[{'url':'https://a/book','title':'Old'}])
    old=read_snapshot(p)
    mc.m.write_items_atomic(p,[{'url':'https://a/book','title':'New user edit'}])
    with pytest.raises(RuntimeError,match='Corpus changed'):
        write_snapshot(p,old)
    assert mc.m.read_jsonl_strict(p)[0]['title']=='New user edit'


def test_preview_cleanup_preserves_maintenance_history():
    from scripts.retrofit import fetch_better_covers as fbc
    row = {'images': [{'local': 'current.avif'}],
           'cover_history': [{'old_local': 'original.avif', 'new_local': 'upgrade.avif'}]}
    assert fbc._collect_referenced_locals([row]) == {'current.avif', 'original.avif', 'upgrade.avif'}
