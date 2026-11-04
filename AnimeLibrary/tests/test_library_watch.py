import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import json
import os
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace as N


import library_watch as watcher
import organize_cloud_batch as organizer

pb=N(OFFLINE_FINISHED=2)
record={'tasks':[{'hash':'a'},{'hash':'b'}]}
assert not watcher.eligible(record,{'a':N(status=2),'b':N(status=1)},pb,{'a','b'})
assert not watcher.eligible(record,{'a':N(status=2),'b':N(status=2)},pb,{'a','b','c'})
assert watcher.eligible(record,{'a':N(status=2),'b':N(status=2)},pb,{'a','b'})

with tempfile.TemporaryDirectory() as temporary:
    organizer.FOLDER=Path(temporary)
    organizer.TV_FOLDERS={'94664':'无职转生 (2021) [tmdbid-94664]'}
    folder='/待整理/云端下载/999 测试'
    files=[{'name':name,'path':folder+'/'+name,'id':str(i),'dir':False,'size':100,'sha1':str(i)*40} for i,name in enumerate(['test [01].mkv','test [02].mkv','test [01].chs.ass'],1)]
    (organizer.FOLDER/'999.before.json').write_text(json.dumps(files),encoding='utf8')
    plans=organizer.build([{'subject':{'id':999,'name_cn':'测试 第2部分','name':'test','tmdb':'tv/94664/season/1/episode/12','eps':2,'date':'2021-10-01'},'tasks':[{'hash':'c','destination':folder}]}],persist=False)
    paths=[x['destination'] for x in plans[0]['transfers']]
    assert all(x.startswith('/剧集/无职转生 (2021) [tmdbid-94664]/Season 01/') for x in paths)
    assert any('S01E12.mkv' in x for x in paths) and any('S01E13.mkv' in x for x in paths)
    assert any('S01E12.zh-Hans.default.ass' in x for x in paths)
    partial=[dict(x,name=name,path=folder+'/'+name) for x,name in zip(files[:2],['test [02].mkv','test [04].mkv'])]
    (organizer.FOLDER/'999.backup.before.json').write_text(json.dumps(partial),encoding='utf8')
    supplement=organizer.build([{'subject':{'id':999,'name_cn':'测试','name':'test','tmdb':'tv/94664','eps':4,'date':'2021-01-01','_batch_key':'999.backup','_review_allow_gaps':True},'tasks':[{'hash':'d','destination':folder}]}],persist=False)[0]
    assert supplement['state_key']=='999.backup' and supplement['missing_numbers']==[1,3]
    assert any('E02.mkv' in x['destination'] for x in supplement['transfers'])
    assert any('E04.mkv' in x['destination'] for x in supplement['transfers'])
print('PASS: waits for complete source set; unfinished download retained; mapped part numbering and subtitles; existing series folder reused')
print('PASS: supplement manifests are separate; missing episode numbers are preserved explicitly')
