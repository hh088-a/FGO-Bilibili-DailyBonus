import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os,sys,tempfile
from pathlib import Path
from unittest.mock import patch

import batch

def task(status='downloading',**extra):return dict(subject_id=1,title='Test',source_hash='a'*40,status=status,selected_bytes=1,files=[],verified=[],**extra)
def torrent(**extra):
    d=dict(hash='a'*40,state='stalledDL',progress=0,added_on=1000,category='anime-batch',dlspeed=0,availability=0,num_seeds=0);d.update(extra);return d
class QB:
    def __init__(self,torrents):self.torrents=torrents;self.calls=[]
    def call(self,route,data=None):
        self.calls.append((route,data))
        if route=='torrents/info':return self.torrents

with tempfile.TemporaryDirectory() as td,patch.object(batch,'DATA',Path(td)):
    state={'tasks':{'a'*40:task()},'subjects':{}};q=QB([torrent()])
    batch.maintain_downloads(q,state,now=2000)
    assert state['tasks']['a'*40]['status']=='waiting_for_peers'
    assert batch.active_downloads(state)==0 and state['tasks']['a'*40]['selected_bytes']==1
    assert ('torrents/stop',{'hashes':'a'*40}) in q.calls
    assert not any(r=='torrents/delete' for r,_ in q.calls)
    batch.maintain_downloads(q,state,now=3000)
    assert state['tasks']['a'*40]['status']=='waiting_for_peers'
    batch.maintain_downloads(q,state,now=3900)
    assert state['tasks']['a'*40]['status']=='downloading'
    # Data flowing without a complete seed still counts as real progress.
    state['tasks']['a'*40]=task();q=QB([torrent(dlspeed=1024)])
    batch.maintain_downloads(q,state,now=5000)
    assert state['tasks']['a'*40]['status']=='downloading'
    assert not any(r=='torrents/stop' for r,_ in q.calls)
    # Paused replaced releases never resume, even after their retry deadline.
    state['tasks']['a'*40]=task('source_replaced',retry_after=0);q=QB([torrent(state='stoppedDL')])
    batch.maintain_downloads(q,state,now=10000)
    assert not any(r=='torrents/start' for r,_ in q.calls)
    state['tasks']['a'*40]=task('waiting_for_peers',retry_after=0)
    for i in range(batch.MAX_ACTIVE):state['tasks'][str(i)]=task()
    q=QB([torrent()]);batch.maintain_downloads(q,state,now=10000)
    assert state['tasks']['a'*40]['status']=='waiting_for_peers'
    assert not any(r=='torrents/start' for r,_ in q.calls)
    # Error/missing-file tasks release download slots without discarding data.
    state={'subjects':{},'tasks':{'a'*40:task()}};q=QB([torrent(state='missingFiles')])
    batch.maintain_downloads(q,state,now=2000)
    assert state['tasks']['a'*40]['status']=='needs_attention'
    assert batch.active_downloads(state)==0
    # Connected seeds and a protocol/data trickle do not keep a slow source
    # active forever. A nearly finished selection is allowed to finish.
    state={'subjects':{},'tasks':{'a'*40:task()}}
    q=QB([torrent(state='downloading',num_seeds=3,dlspeed=1024,time_active=1000,downloaded=2*1024**2,amount_left=500*1024**2)])
    batch.maintain_downloads(q,state,now=3000)
    assert state['tasks']['a'*40]['status']=='waiting_for_peers'
    # A retried slow source gets time to find peers rather than being parked
    # immediately by its old lifetime average.
    batch.maintain_downloads(q,state,now=4801)
    assert state['tasks']['a'*40]['status']=='downloading'
    batch.maintain_downloads(q,state,now=4804)
    assert state['tasks']['a'*40]['status']=='downloading'
    batch.maintain_downloads(q,state,now=4982)
    assert state['tasks']['a'*40]['status']=='waiting_for_peers'
    state={'subjects':{},'tasks':{'a'*40:task()}}
    q=QB([torrent(state='downloading',num_seeds=3,dlspeed=1024,time_active=1000,downloaded=2*1024**2,amount_left=50*1024**2)])
    batch.maintain_downloads(q,state,now=3000)
    assert state['tasks']['a'*40]['status']=='downloading'
print('PASS: peerless tasks yield slots, retries get a connection grace period and respect configured concurrency, partial data and healthy sources retained')

with tempfile.TemporaryDirectory() as td:
    root=Path(td);downloads=root/'downloads';downloads.mkdir();tasks={};torrents=[]
    for h in ('a'*40,'b'*40):
        local=downloads/h;local.mkdir();(local/'file.mkv').write_bytes(b'data')
        tasks[h]=dict(subject_id=1,title='Test',source_hash=h,status='upload_pending',selected_bytes=4,files=[{'name':'file.mkv','size':4,'index':0}],verified=['file.mkv'],local_folder=str(local))
        torrents.append(dict(hash=h,state='stalledUP',progress=1,category='anime-batch',save_path=str(local)))
    state={'subjects':{},'tasks':tasks};q=QB(torrents)
    def verify(remote,local,connection):
        if local.parent.name=='a'*40:raise OSError('simulated unavailable first file')
        return True
    with patch.object(batch,'DATA',root),patch.object(batch,'DOWNLOADS',downloads),patch.object(batch,'ROOT',root),patch.object(batch,'cloud_verified',side_effect=verify),patch.object(batch,'log'):
        batch.publish(q,state,object())
    assert tasks['a'*40]['status']=='upload_pending' and (downloads/('a'*40)/'file.mkv').exists()
    assert tasks['b'*40]['status']=='cloud_verified'
    assert ('torrents/delete',{'hashes':'b'*40,'deleteFiles':'true'}) in q.calls
    assert not any(r=='torrents/delete' and d['hashes']=='a'*40 for r,d in q.calls)
print('PASS: one inaccessible upload preserves its local data while another verified torrent completes cleanup')
