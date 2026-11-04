"""Local API helper. Credentials remain encrypted on disk and are never logged."""
import os,sys,subprocess,json,urllib.request,urllib.parse,contextlib
from pathlib import Path

import batch

@contextlib.contextmanager
def session():
    path=batch.ROOT/'config/admin.credential.xml'
    script="$c=Import-Clixml -LiteralPath '"+str(path).replace("'","''")+"';@{Username=$c.UserName;Pw=$c.GetNetworkCredential().Password}|ConvertTo-Json -Compress"
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,check=True,creationflags=batch.NO_WINDOW)
    credential=json.loads(r.stdout.decode('utf-8-sig'))
    header='MediaBrowser Client="AnimeLibrary Audit", Device="Windows PC", DeviceId="anime-library-audit", Version="1.0"'
    def call(route,data=None,method=None):
        url='http://127.0.0.1:8097'+route
        raw=json.dumps(data).encode() if data is not None else None
        req=urllib.request.Request(url,data=raw,headers={'Authorization':header,'Content-Type':'application/json'},method=method)
        with urllib.request.urlopen(req,timeout=45) as response:body=response.read()
        return json.loads(body) if body else None
    auth=call('/Users/AuthenticateByName',credential)
    header+=', Token="'+auth['AccessToken']+'"'
    try:yield call,auth['User']['Id']
    finally:
        try:call('/Sessions/Logout',method='POST')
        except Exception:pass

if __name__=='__main__':
    with session() as (call,user):
        for term,kind in [('轻音','Movie'),('我的英雄学院','Series')]:
            params=urllib.parse.urlencode(dict(SearchTerm=term,IncludeItemTypes=kind,Recursive='true',Fields='Path,MediaStreams,ProviderIds',Limit=30))
            data=call('/Items?'+params)
            print(json.dumps([{'id':x['Id'],'name':x['Name'],'path':x.get('Path'),'providers':x.get('ProviderIds'),'streams':[{k:s.get(k) for k in ('Type','Language','Codec','IsExternal','DisplayTitle','IsDefault')} for s in x.get('MediaStreams',[])]} for x in data['Items']],ensure_ascii=False),flush=True)
        print('scan',[(t['Name'],t['State'],t.get('CurrentProgressPercentage')) for t in call('/ScheduledTasks') if t['Key']=='RefreshLibrary'])
