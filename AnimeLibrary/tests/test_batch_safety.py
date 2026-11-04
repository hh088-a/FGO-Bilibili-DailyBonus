import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import importlib.util,tempfile
from pathlib import Path
from unittest.mock import patch

base=Path(__file__).resolve().parents[1]/'archive/runtime'
spec=importlib.util.spec_from_file_location('batch',base/'batch.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.log=lambda message:None
class Q:
    def __init__(self,folder):self.calls=[];self.folder=folder
    def call(self,route,data=None):
        self.calls.append((route,data))
        if route=='torrents/info':return [{'hash':'a'*40,'progress':1,'state':'stoppedUP','category':'anime-batch','save_path':str(self.folder)}]

with tempfile.TemporaryDirectory() as tmp:
    root=Path(tmp);downloads=root/'downloads';folder=downloads/('a'*40);folder.mkdir(parents=True)
    source=folder/'show.mkv';source.write_bytes(b'test-data')
    mount=root/'mount';dest=mount/'待整理/批量收藏/1 Test/show.mkv';dest.parent.mkdir(parents=True);dest.write_bytes(source.read_bytes())
    m.DOWNLOADS=downloads;m.CLOUD_MOUNT=mount;m.DATA=root
    state={'subjects':{},'tasks':{'a'*40:{'subject_id':1,'title':'Test','selected_bytes':9,'local_folder':str(folder),'status':'downloading','files':[{'name':'show.mkv','size':9,'index':0}],'verified':[]}}}
    qb=Q(folder)
    with patch.object(m,'cloud_verified',return_value=False):m.publish(qb,state,object())
    assert source.exists() and not any(r=='torrents/delete' for r,d in qb.calls)
    with patch.object(m,'cloud_verified',return_value=True):m.publish(qb,state,object())
    assert any(r=='torrents/delete' and d=={'hashes':'a'*40,'deleteFiles':'true'} for r,d in qb.calls)
    assert state['tasks']['a'*40]['status']=='cloud_verified'
    for bad in ['../private.txt','C:/outside.mkv','/absolute.mkv','show.mkv:ads']:
        try:m.safe_relative(bad)
        except ValueError:pass
        else:raise AssertionError('unsafe path accepted: '+bad)
print('PASS: unverified cloud retains local data; verified cloud permits only managed torrent cleanup; path traversal rejected')
