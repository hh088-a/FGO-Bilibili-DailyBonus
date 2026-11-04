import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os,sys
from pathlib import Path

import organize_cloud_batch as m
original={'video':(100,'A'*40),'sub':(10,'B'*40)}
after=[{'id':'metadata','dir':False,'name':'show.nfo','sha1':'C'*40}]
assert m.verify_originals(original,dict(original,metadata=(50,'C'*40)),after)==1
for bad,archive in [({'video':original['video']},[]),(dict(original,video=(100,'D'*40)),[]),(dict(original,unknown=(100,'E'*40)),[{'id':'unknown','dir':False,'name':'other.mkv','sha1':'E'*40}])]:
    try:m.verify_originals(original,bad,archive)
    except AssertionError:pass
    else:raise AssertionError('Incomplete or changed originals unexpectedly accepted')
print('PASS: every original ID, size and SHA1 must survive; additional NFO is accepted separately; missing/changed originals and unexpected video files are rejected')
