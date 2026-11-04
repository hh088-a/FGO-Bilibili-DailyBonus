import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'archive/runtime'))
import os,sys
from pathlib import Path
from types import SimpleNamespace as N
from unittest.mock import patch

import batch

state={'tasks':{'slow':{'status':'waiting_for_peers','selected_bytes':100*batch.GIB,'progress':0.01}}}
assert batch.storage_committed(state)==batch.GIB
with patch.object(batch.shutil,'disk_usage',return_value=N(free=50*batch.GIB)):
    assert batch.storage_ready(state,5*batch.GIB)
    assert not batch.storage_ready(state,99*batch.GIB)
    state['tasks']['slow']['status']='downloading'
    state['tasks']['slow']['selected_bytes']=(batch.STAGING_GIB+1)*batch.GIB
    assert not batch.storage_ready(state,0)
with patch.object(batch.shutil,'disk_usage',return_value=N(free=34*batch.GIB)):
    state['tasks']['slow']['status']='waiting_for_peers'
    assert not batch.storage_ready(state,5*batch.GIB)
print('PASS: paused partial data stays counted, active tasks reserve their entire selection, and retries cannot exceed staging or free-space guards')
