import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os,sys,json,tempfile
from pathlib import Path
from unittest.mock import patch

import organize_cloud_batch as m

with tempfile.TemporaryDirectory() as td,patch.object(m,'FOLDER',Path(td)),patch.object(m,'TV_FOLDERS',{}),patch.object(m,'TV_NAMES',{}),patch.object(m,'TV_START_YEARS',{}):
    source='/待整理/批量收藏/999 repair'
    files=[dict(id='video',name='Show [12].mkv',path=source+'/Show [12].mkv',dir=False,size=100,sha1='A'*40),dict(id='sub',name='Show [12].chs.ass',path=source+'/Show [12].chs.ass',dir=False,size=10,sha1='B'*40)]
    (Path(td)/'999.before.json').write_text(json.dumps(files),encoding='utf8')
    subject=dict(id=999,name_cn='Show',name='Show',date='2021-01-01',tmdb='tv/1/season/1/episode/12',eps=12,_review_episode_offset=11,_review_allow_gaps=True)
    plan=m.build([{'subject':subject,'tasks':[{'hash':'x','destination':source}]}],persist=False)[0]
    assert len(plan['transfers'])==2
    assert all('S01E23.' in x['destination'] for x in plan['transfers'])
    assert plan['missing_numbers']==list(range(12,23))
print('PASS: selectively downloading source episode 12 of a split season maps to library episode 23, including subtitles; it cannot overwrite library episode 12')

subject={'id':425587,'name_cn':'我的英雄学院 第七季','tmdb':'tv/65930/season/7','eps':21,'date':'2024-05-04'}
video={'id':'recap','name':'[DBD-Raws][Boku no Hero Academia Memories][01][1080P].mkv','path':'/source/root/[DBD-Raws][Boku no Hero Academia Memories][01][1080P].mkv'}
target,kind=m.classify(subject,video,'/source')
assert '/Season 00/' in target and 'S00E13' in target
video=dict(video,name='[DBD-Raws][Boku no Hero Academia S7][01][1080P].mkv')
target,kind=m.classify(subject,video,'/source')
assert '/Season 07/' in target and 'S07E01' in target
print('PASS: MHA recap 1 maps to special 13; season-seven episode 1 remains S07E01')
