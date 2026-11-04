import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import json,os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

import batch,library_watch as watch,organize_cloud_batch as organizer

def items(names):
    return [dict(name=n,dir=False) for n in names]
demon=dict(id=441939,tmdb='tv/85937/season/5',eps=8)
result=watch.reviewed_subject(demon,items([f'[BeanSub&FZSD&LoliHouse] Kimetsu no Yaiba - {n} [1080p].mkv' for n in range(56,64)]))
assert result['_review_episode_offset']==-55
assert demon.get('_review_episode_offset') is None
unchanged=watch.reviewed_subject(demon,items(['Kimetsu no Yaiba - 55 [1080p].mkv']))
assert unchanged==demon
with tempfile.TemporaryDirectory() as td,patch.object(batch,'DATA',Path(td)):
    sequel=dict(id=486676,tmdb='tv/236385/season/2',eps=12,name_cn='时光巡逻队 第二季')
    (Path(td)/'catalog.json').write_text(json.dumps([sequel]),encoding='utf8')
    first=dict(id=457956,tmdb='tv/236385',eps=12,_batch_key='457956.qb.test')
    result=watch.reviewed_subject(first,items(['[SweetSub&LoliHouse] TP Bon - 15 [1080p].mkv']))
    assert result['id']==486676 and result['_batch_key']==first['_batch_key']
    dest,kind=organizer.classify(result,dict(name='[SweetSub&LoliHouse] TP Bon - 15 [1080p].mkv',path='/stage/TP Bon - 15.mkv'),'/stage')
    assert '/Season 02/' in dest and 'S02E03' in dest and kind=='episode'
    # A mixed-season source requires a separate review rather than a blanket offset.
    unchanged=watch.reviewed_subject(first,items(['TP Bon - 12 [1080p].mkv','TP Bon - 13 [1080p].mkv']))
    assert unchanged==first
print('PASS: absolute release numbering maps to the reviewed seasons, preserving original subject keys; out-of-range and mixed releases unchanged')
