import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os
import sys
from pathlib import Path
from types import SimpleNamespace as N


import cloud_queue as m

q=m.CloudQueue.__new__(m.CloudQueue)
q.remote_cache_seconds=0
q.full_cache_seconds=0
q.pb=N(OFFLINE_INIT=0,OFFLINE_DOWNLOADING=1,OFFLINE_UNKNOWN=4,OFFLINE_FINISHED=2)
q.state={'tasks':{},'skipped':{}};q.catalog=[]
q.quota=lambda:N(left=0,total=1500);q.all_tasks=lambda:{};q.report=lambda msg='':None
q.exhausted=lambda msg:q.state.update(status='quota_exhausted')
assert q.tick() is False and q.state['status']=='quota_exhausted'

q.quota=lambda:N(left=1,total=1500);q.all_tasks=lambda:{'a':N(status=2)}
q.catalog=[{'id':1,'name_cn':'测试动画','name':'test'}]
m.candidates=lambda catalog:iter([(catalog[0],{'title':'测试动画','url':'unused'},'a')])
m.local_coverage=lambda:(set(),set())
q.stub=N(GetSpaceInfo=lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Duplicate must not submit')))
assert q.tick() is True and q.state['skipped']['1:a']['reason']=='already_in_115'

q.state={'tasks':{str(i):{'status':'uncertain'} for i in range(10)},'skipped':{}}
q.all_tasks=lambda:{}
assert q.tick() is True and q.state['status']=='waiting_for_cloud_slots'

a={'id':10380,'name_cn':'命运石之门','name':'STEINS;GATE'}
b={'id':1,'name_cn':'命运石之门0','name':'STEINS;GATE 0'}
assert m.identity_conflict(a,{'title':'[命运石之门0][1080P]'},[a,b])!=''
assert m.identity_conflict(a,{'title':'[命运石之门0][1080P]'},[a])!=''
assert m.identity_conflict(a,{'title':'[命运石之门][01-24全集][1080P]'},[a,b])==''
assert m.identity_conflict({'id':2,'name_cn':'攻壳机动队','name':'攻殻機動隊'}, {'title':'[LoliHouse] 攻壳机动队 SAC_2045 S2 / Ghost in the Shell SAC_2045 Season2 [1080p]'},[])!=''
q.state={'tasks':{},'skipped':{}};q.save=lambda:None
q.catalog=[{'id':1,'name_cn':'测试动画','name':'test','mikan_id':'1'}]
m.candidates=lambda catalog:iter([(catalog[0],{'title':'测试动画','url':'mock'},'a')])
m.batch.fetch=lambda url:b'metadata'
m.batch.torrent_info=lambda data:('wrong-hash',[{'name':'test.mkv','size':10}])
assert q.tick() is True and q.state['skipped']['1:a']['reason']=='torrent_metadata_hash_mismatch'
print('PASS: quota stop, deduplication, uncertain submission reservation, sequel mismatch')
print('PASS: one mismatched torrent is held without blocking the queue')

import tempfile
from pathlib import Path
with tempfile.TemporaryDirectory() as directory:
    m.STOP=Path(directory)/'STOP'
    q=m.CloudQueue.__new__(m.CloudQueue);q.remote_cache_seconds=20;q.md=()
    q.state={'tasks':{},'skipped':{}};q.catalog=[{'id':1,'name_cn':'测试动画','name':'test'}]
    calls=[];snapshots=[]
    q.pb=N(OFFLINE_INIT=0,OFFLINE_DOWNLOADING=1,OFFLINE_UNKNOWN=4,OFFLINE_FINISHED=2,
           FileRequest=lambda **kw:N(**kw),AddOfflineFileRequest=lambda **kw:N(**kw))
    q.quota=lambda:N(left=100,total=1500)
    q.all_tasks=lambda:(snapshots.append(1) or {})
    q.ensure_dir=lambda path:None;q.save=lambda:None;q.report=lambda message='':None
    q.stub=N(GetSpaceInfo=lambda *a,**kw:N(freeSpace=2**50),AddOfflineFiles=lambda request,**kw:(calls.append(request.urls) or N(success=True)))
    sources=[(q.catalog[0],{'title':'测试动画','page':'https://share.dmhy.org/','url':'','manual_verified':True,'magnet_only':True,'declared_size':1000},f'{i:040x}') for i in range(1,12)]
    m.candidates=lambda catalog:iter(sources)
    m.batch.fetch=lambda url:(_ for _ in ()).throw(AssertionError('Reviewed magnet must not fetch video/torrent payload'))
    for _ in range(11):assert q.tick() is True
    assert len(calls)==10 and len(snapshots)==1
    assert q.state['status']=='waiting_for_cloud_slots'
    assert all(t['file_count'] is None and t['metadata_checked'] is False for t in q.state['tasks'].values())
print('PASS: cached task history still enforces ten slots; reviewed external magnets preserve quota gating')

q=m.CloudQueue.__new__(m.CloudQueue);q.md=();q.remote_cache_seconds=0
q._full_snapshot_at=m.time.monotonic();old=N(infoHash='old',status=1);recent=N(infoHash='recent',status=2)
q._task_snapshot=(0,{'old':old})
q.pb=N(OfflineFileListAllRequest=lambda **kw:N(**kw))
q.stub=N(ListAllOfflineFiles=lambda *a,**kw:N(offlineFiles=[recent]))
q.all_tasks=lambda:(_ for _ in ()).throw(AssertionError('Incremental poll must not read full history'))
snapshot=q.task_snapshot();assert snapshot['old'].status==1 and snapshot['recent'].status==2
print('PASS: latest-page polling preserves old active jobs without repeated full-history requests')
