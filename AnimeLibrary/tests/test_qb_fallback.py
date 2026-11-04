import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os,sys,json,tempfile
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace

import batch,cloud_queue,library_watch

inspected=[{'index':0,'name':'Show/01.mkv','size':10},{'index':2,'name':'Show/02.mkv','size':20}]
qbfiles=[{'index':0,'name':'Show/01.mkv','size':10},{'index':1,'name':'Show/02.mkv','size':20},{'index':2,'name':'Show/03.mkv','size':30}]
assert [x['index'] for x in batch.map_selected_files(inspected,qbfiles)]==[0,1]
try:batch.map_selected_files(inspected,[dict(qbfiles[0],size=999),qbfiles[1]])
except RuntimeError:pass
else:raise AssertionError('different file sizes must not pass selection mapping')

with tempfile.TemporaryDirectory() as td:
    root=Path(td);data=root/'data';data.mkdir()
    h='a'*40;urlhash='b'*40;folder=root/'downloads'/h;folder.mkdir(parents=True)
    incomplete=root/'downloads/incomplete';incomplete.mkdir();source=incomplete/'episode.mkv';source.write_bytes(b'verified-data')
    state={'subjects':{},'tasks':{h:{'source_hash':h,'subject_id':999,'title':'Test','status':'upload_pending','selected_bytes':13,'fallback':True,'local_folder':str(folder),'files':[{'name':'episode.mkv','size':13,'index':0}],'verified':['episode.mkv']}}}
    plan={'entries':[{'hash':h,'url_hash':urlhash,'status':'reserved','subject':{'id':999,'name_cn':'Test'},'candidate':{'qb_fallback':True}}]}
    batch.atomic(data/'qb-fallback-plan.json',plan);batch.atomic(data/'cloud-queue.json',{'tasks':{h:{'status':'OFFLINE_DOWNLOADING'}}})
    with patch.object(batch,'DATA',data),patch.object(batch,'HERE',root),patch.object(batch,'load_state',return_value=state):
        hashes,sids=cloud_queue.local_coverage()
        assert {h,urlhash}<=hashes and 999 not in sids
        with patch.object(batch,'add_task') as add:
            batch.fallback_tick(None,{'tasks':{}})
            assert not add.called
        assert json.loads((data/'qb-fallback-plan.json').read_text())['entries'][0]['status']=='covered_by_115'
    assert batch.cloud_staging_name(state['tasks'][h],h)=='999 Test [qB-aaaaaaaa]'
    assert batch.completed_local({'save_path':str(folder),'download_path':str(incomplete)},Path('episode.mkv'))==source
    class QB:
        def __init__(self):self.calls=[]
        def call(self,route,arg=None):
            self.calls.append((route,arg))
            if route=='torrents/info':return [{'hash':h,'state':'stalledUP','progress':1,'category':'anime-batch','save_path':str(folder),'download_path':str(incomplete)}]
    q=QB()
    with patch.object(batch,'ROOT',root),patch.object(batch,'DOWNLOADS',root/'downloads'),patch.object(batch,'DATA',data),patch.object(batch,'log'),patch.object(batch,'cloud_verified',return_value=False):
        batch.publish(q,state,object())
        assert 'Final cloud recheck failed' in state['tasks'][h]['last_error']
        assert not any(r=='torrents/delete' for r,_ in q.calls)
    with patch.object(batch,'ROOT',root),patch.object(batch,'DOWNLOADS',root/'downloads'),patch.object(batch,'DATA',data),patch.object(batch,'log'),patch.object(batch,'cloud_verified',return_value=True):
        batch.publish(q,state,object())
        assert state['tasks'][h]['status']=='cloud_verified'
        assert any(r=='torrents/delete' for r,_ in q.calls)
    # A completed qB release is imported under its own key, even if another
    # release of the subject was previously organized. An unfinished chunk blocks it.
    class CQ:
        catalog=[{'id':999,'name_cn':'Test','tmdb':'tv/1','eps':2}]
        def all_tasks(self):return {}
    with patch.object(cloud_queue,'load',return_value={'tasks':{}}),patch.object(batch,'load_state',return_value=state),patch.object(library_watch,'read',return_value={'999':{'status':'verified','task_hashes':['c'*40]}}):
        result=library_watch.available(CQ());assert len(result)==1
        assert result[0]['subject']['_batch_key']=='999.qb.'+h[:12]
        state['chunk_queue']=[{'subject':{'id':999},'candidate':{'task_key':h+':1'}}]
        assert library_watch.available(CQ())==[]
print('PASS: cloud reservations deduplicate both hashes; cloud-active sources never enter qB; incomplete-path cleanup requires fresh proof; release-specific import waits for every chunk')

with tempfile.TemporaryDirectory() as td:
    root=Path(td);state={'tasks':{},'subjects':{}}
    class FailedAdd:
        def call(self,route):return []
        def add(self,*args):raise RuntimeError('simulated interrupted submission')
    source={'title':'Test','url':'https://example.invalid/source.torrent','page':'https://example.invalid','qb_fallback':True,'verified_hash':'a'*40}
    files=[{'name':'Show/01.mkv','size':3*batch.GIB,'index':0},{'name':'Show/02.mkv','size':3*batch.GIB,'index':2}]
    with patch.object(batch,'DATA',root),patch.object(batch,'DOWNLOADS',root),patch.object(batch,'fetch',return_value=b''),patch.object(batch,'torrent_info',return_value=('a'*40,files)),patch.object(batch.shutil,'disk_usage',return_value=SimpleNamespace(free=2**40)):
        try:batch.add_task(FailedAdd(),{'id':999,'name':'Test'},source,state)
        except RuntimeError:pass
        else:raise AssertionError('simulated interrupted add must raise')
    assert {x['candidate']['task_key'] for x in state['chunk_queue']}=={'a'*40+':0','a'*40+':1'}
print('PASS: interruption while adding first chunk retains every chunk prerequisite; padding-file index changes cannot select different episodes')
