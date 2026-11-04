import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os,sys
from pathlib import Path

import organize_cloud_batch as m,library_watch as w
assert m.episode('[LoliHouse] Aparida - 09.5 [1080p].mkv',1) is None
assert m.episode('Example - 09.mkv',1)==(1,9)
assert m.episode('Example - 09v2 [1080p].mkv',1)==(1,9)
s=dict(id=487630,name_cn='我独自升级 第二季',tmdb='tv/127532/season/1/episode/13',eps=13,date='2025-01-04')
v=dict(dir=False,name='[Dont be a simp] Ore dake Level Up na Ken Season 2 - 12 [1080p].mkv',path='/stage/release/file.mkv')
corrected=w.reviewed_subject(s,[v]);dest,_=m.classify(corrected,v,'/stage')
assert 'S01E24' in dest and s.get('_review_episode_offset') is None
print('PASS: decimal specials cannot overwrite integer episode slots; reviewed partial sequel keeps its proper library episode number')
