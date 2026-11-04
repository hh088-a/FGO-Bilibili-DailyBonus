import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

import batch,library_watch as w,organize_cloud_batch as m
def item(name,path=None):return dict(name=name,path=path or '/stage/wrapper/'+name,dir=False,id=name,size=1,sha1='a'*40)
assert m.extra(item('show - 01 Preview.mkv'),'/stage')
assert m.extra(item('show - 01.mkv','/stage/wrapper/Preview/show - 01.mkv'),'/stage')
assert m.extra(item('[DBD-Raws][Mayonaka Punch][SP Anime][01].mkv'),'/stage')
assert not m.extra(item('show - 01.mkv','/stage/wrapper/show - 01.mkv'),'/stage')
s=dict(id=457326,tmdb='tv/30984/season/2/episode/27',eps=14,name_cn='死神',date='2024-10-05',_review_allow_gaps=True)
v=item('[Fyy Raws] Bleach Sennen Kessenhen-Soukokutan - 03 [1080p].mkv')
corrected=w.reviewed_subject(s,[v]);dest,_=m.classify(corrected,v,'/stage')
assert 'S02E29' in dest
with tempfile.TemporaryDirectory() as td:
    p=Path(td)
    with patch.object(batch,'DATA',p):
        (p/'catalog.json').write_text(json.dumps([dict(id=517532,tmdb='tv/261135/season/1/episode/7',eps=6)]),encoding='utf8')
        v=item('[heibaisub] Kankin Kuiki Level X [08][CHS].mp4')
        corrected=w.reviewed_subject(dict(id=507433,_batch_key='original',eps=6),[v])
        assert corrected['id']==517532 and corrected['_batch_key']=='original'
    with patch.object(m,'FOLDER',p):
        s=dict(id=492352,tmdb='movie/1287324',eps=2,name_cn='五等分的新娘＊',date='2024-12-23',_batch_key='parts')
        videos=[item(f'[XKsub&LoliHouse] 5Hanayome SP2 - {n:02d} [1080p].mkv') for n in (1,2)]
        corrected=w.reviewed_subject(s,videos)
        (p/'parts.before.json').write_text(json.dumps(videos),encoding='utf8')
        plan=m.build([dict(subject=corrected,tasks=[dict(hash='x',destination='/stage')])],persist=False)[0]
        assert len(plan['transfers'])==2
        assert all(f' - part{n}.mkv' in plan['transfers'][n-1]['destination'] for n in (1,2))
        s=dict(id=453140,tmdb=None,eps=5,name_cn='好想告诉你 第三季',date='2024-08-01',_batch_key='kimi',_review_allow_gaps=True)
        videos=[item(f'[LoliHouse] Kimi ni Todoke S3 - {n:02d} [1080p].mkv') for n in range(6)]
        corrected=w.reviewed_subject(s,videos)
        (p/'kimi.before.json').write_text(json.dumps(videos),encoding='utf8')
        plan=m.build([dict(subject=corrected,tasks=[dict(hash='x',destination='/stage')])],persist=False)[0]
        assert len(plan['transfers'])==5 and all('/Season 03/' in x['destination'] for x in plan['transfers'])
print('PASS: previews and bonus videos archived, sequel episode mapping preserved, both film parts retained, recap excluded from regular season')
