"""Resumable Japanese-anime acquisition. Delete local data only after remote SHA1 verification."""
import argparse, collections, csv, hashlib, html, http.cookiejar, json, os, re, shutil, sqlite3, subprocess, sys, time, urllib.parse, urllib.request, uuid
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from xml.etree import ElementTree as ET

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
OUT=ROOT/'reports'; OUT.mkdir(exist_ok=True)
CACHE=HERE/'cache'; CACHE.mkdir(exist_ok=True)
DATA=HERE/'data'; DATA.mkdir(exist_ok=True)
DOWNLOADS=HERE/'downloads'; DOWNLOADS.mkdir(exist_ok=True)
CLOUD_MOUNT=Path('X:/动漫')
QB='http://127.0.0.1:8098'
GIB=2**30
MAX_ACTIVE=100
STAGING_GIB=160
CHUNK_GIB=5
TODAY='2026-11-03'
UA='AnimeLibrary/1.0 (personal catalog)'
NO_WINDOW=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0

def atomic(path,obj):
    p=path.with_suffix('.tmp');p.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf8');p.replace(path)

def log(message):
    text=datetime.now().isoformat(timespec='seconds')+' '+str(message)
    with (HERE/'batch.log').open('a',encoding='utf8') as f:f.write(text+'\n')
    print(text,flush=True)

def fetch(url,body=None,cache=True):
    key=hashlib.sha256((url+json.dumps(body,sort_keys=True,ensure_ascii=False)).encode()).hexdigest()
    dest=CACHE/(key+'.response')
    if cache and dest.exists():return dest.read_bytes()
    args=['powershell.exe','-NoProfile','-NonInteractive','-File',str(HERE/'http.ps1'),'-Url',url,'-OutputPath',str(dest)+'.part']
    if body is not None:
        request=CACHE/(key+'.request.json');atomic(request,body);args+=['-BodyPath',str(request)]
    for attempt in range(3):
        r=subprocess.run(args,capture_output=True,timeout=50,creationflags=NO_WINDOW)
        if not r.returncode and Path(str(dest)+'.part').exists():
            Path(str(dest)+'.part').replace(dest);time.sleep(1);return dest.read_bytes()
        time.sleep(2*(attempt+1))
    raise RuntimeError('HTTP failed: '+urllib.parse.urlparse(url).netloc)

def api_search(filters,sort,limit=100,offset=0):
    return json.loads(fetch(f'https://api.bgm.tv/v0/search/subjects?limit={limit}&offset={offset}',{'keyword':'','sort':sort,'filter':filters}))

def build_catalog():
    catalog={}
    ranked={}
    offset=0
    while len(ranked)<100:
        ranks=api_search({'type':[2],'meta_tags':['日本'],'rank':['>0'],'nsfw':False},'rank',20,offset)
        for s in ranks['data']:ranked[s['id']]=s
        if not ranks['data']:break
        offset+=len(ranks['data'])
        if offset>300:raise RuntimeError('Top100 pagination is not advancing')
    top=sorted(ranked.values(),key=lambda x:x['rating']['rank'])[:100]
    if len(top)!=100:raise RuntimeError('Top100 response incomplete')
    for i,s in enumerate(top,1):s['top_japan_order']=i;s['reasons']=['日本动画Top100'];catalog[s['id']]=s
    for year in range(2022,2027):
        offset=0; count=0
        while True:
            filters={'type':[2],'meta_tags':['日本'],'air_date':[f'>={year}-01-01',f'<={min(TODAY,str(year)+"-12-31")}'],'nsfw':False}
            page=api_search(filters,'heat',100,offset)
            for s in page['data']:
                if s.get('platform') not in ('TV','WEB'):continue
                old=catalog.setdefault(s['id'],s)
                old.setdefault('reasons',[])
                if '近五年新番' not in old['reasons']:old['reasons'].append('近五年新番')
                count+=1
            offset+=len(page['data'])
            if not page['data'] or offset>=page['total']:break
            if offset>=1000:raise RuntimeError(f'{year}: API search cap reached; catalog cannot be declared complete')
        log(f'catalog {year}: {count} TV/WEB entries')
        atomic(DATA/'catalog.partial.json',list(catalog.values()))
    mapping_path=DATA/'mapping.json'
    if not mapping_path.exists():mapping_path.write_bytes(fetch('https://unpkg.com/bangumi-data/dist/data.json'))
    mapping={}
    for x in json.loads(mapping_path.read_text(encoding='utf-8-sig'))['items']:
        ids={a['site']:a['id'] for a in x.get('sites',[]) if a.get('site') and a.get('id')}
        if 'bangumi' in ids:mapping[int(ids['bangumi'])]=(x,ids)
    for s in catalog.values():
        if s['id'] in mapping:
            x,ids=mapping[s['id']];s['mikan_id']=ids.get('mikan');s['tmdb']=ids.get('tmdb');s['aliases']=x.get('titleTranslate',{}).get('zh-Hans',[])
    values=sorted(catalog.values(),key=lambda s:(0,s['top_japan_order']) if 'top_japan_order' in s else (1,s.get('date') or '',s['id']))
    atomic(DATA/'catalog.json',values)
    atomic(OUT/'批量收藏清单.json',values)
    with (OUT/'批量收藏清单.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['Bangumi ID','中文名','原名','日期','类型','日本榜顺位','全站排名','评分','入选原因','来源'])
        for s in values:w.writerow([s['id'],s.get('name_cn'),s['name'],s.get('date'),s.get('platform'),s.get('top_japan_order'),s.get('rating',{}).get('rank'),s.get('rating',{}).get('score'),';'.join(s['reasons']),f'https://bgm.tv/subject/{s["id"]}'])
    log(f'catalog complete: {len(values)} unique subjects; Japan top100 verified')
    return values

def text(data):return data.decode('utf-8-sig')

def find_mikan(s):
    possible=[]
    if s.get('mikan_id'):possible.append(str(s['mikan_id']))
    if not possible:
        queries=list(dict.fromkeys([s.get('name_cn') or '',s['name']]+s.get('aliases',[])))
        for q in [q for q in queries if q][:2]:
            page=text(fetch('https://mikanani.me/Home/Search?'+urllib.parse.urlencode({'searchstr':q})))
            possible+=re.findall(r'href="/Home/Bangumi/(\d+)"',page)
            if possible:break
    for mid in list(dict.fromkeys(possible))[:8]:
        page=text(fetch('https://mikanani.me/Home/Bangumi/'+mid))
        if re.search(r'(?:bgm\.tv|bangumi\.tv|chii\.in)/subject/'+str(s['id'])+r'(?:["/?#])',page):return mid
    return None

def bdecode(data):
    pos=0; info_bytes=None
    def read():
        nonlocal pos,info_bytes
        c=data[pos:pos+1]
        if c==b'i':e=data.index(b'e',pos);v=int(data[pos+1:e]);pos=e+1;return v
        if c in (b'l',b'd'):
            pos+=1;o=[] if c==b'l' else {}
            while data[pos:pos+1]!=b'e':
                if c==b'l':o.append(read())
                else:
                    k=read();start=pos;o[k]=read()
                    if k==b'info':info_bytes=data[start:pos]
            pos+=1;return o
        e=data.index(b':',pos);n=int(data[pos:e]);pos=e+1;v=data[pos:pos+n];pos+=n;return v
    result=read();return result,hashlib.sha1(info_bytes).hexdigest()

def safe_relative(name):
    p=Path(name)
    if p.is_absolute() or p.drive or p.root or '..' in p.parts or '\x00' in name:raise ValueError('Unsafe torrent path')
    if any(':' in x for x in p.parts):raise ValueError('Unsafe Windows path')
    return p

def torrent_info(data):
    d,h=bdecode(data);info=d[b'info'];encoding=d.get(b'encoding',b'utf-8').decode('ascii','replace')
    def dec(v):
        try:return v.decode('utf8')
        except UnicodeDecodeError:return v.decode(encoding if encoding.lower() in ('gbk','gb2312','big5') else 'gb18030')
    root=dec(info.get(b'name.utf-8',info[b'name']));files=[]
    for i,f in enumerate(info.get(b'files',[{b'path':[info[b'name']],b'length':info.get(b'length',0)}])):
        parts=f.get(b'path.utf-8',f[b'path']);name='/'.join(dec(x) for x in parts)
        path=safe_relative((root+'/'+name) if b'files' in info else name)
        files.append({'index':i,'name':str(path),'size':f[b'length']})
    return h,files

def parse_candidates(data):
    root=ET.fromstring(data);result=[]
    for item in root.findall('./channel/item'):
        enclosure=item.find('enclosure');link=item.findtext('link','');title=item.findtext('title','')
        url=enclosure.get('url','') if enclosure is not None else ''
        if url and url.startswith('https://mikanani.me/Download/'):
            result.append({'title':title,'url':url,'page':link,'declared_size':int(enclosure.get('length') or 0)})
    return result

def score_candidate(c):
    t=c['title'].lower();score=0
    if not any(x in t for x in ['1080','1920x1080']):return -1
    if any(x in t for x in ['2160','4k','bdmv','iso','合集预告']):return -1
    if not any(x in t for x in ['简','繁','字幕','chs','cht','gb','big5','vcb','喵萌','动漫国','桜都','lilith','loli','极影','澄空','诸神','悠哈','dmg','dbd-raws']):return -1
    score+=20
    if any(x in t for x in ['bdrip','hevc','x265']):score+=5
    if any(x in t for x in ['合集','全集','[fin]','[batch]','reseed']):score+=25
    if any(x in t for x in ['简','chs','gb','scjp']):score+=3
    return score

def discover(s):
    mid=find_mikan(s)
    if not mid:return discover_legacy(s)
    items=parse_candidates(fetch(f'https://mikanani.me/RSS/Bangumi?bangumiId={mid}',cache=False))
    archive=text(fetch('https://mikanani.me/Home/Bangumi/'+mid))
    by_url={c['url']:c for c in items}
    for row in re.findall(r'(?s)<tr\b[^>]*>(.*?)</tr>',archive):
        episode=re.search(r'(?s)<a\b[^>]*href="(/Home/Episode/[a-f0-9]{40})"[^>]*>(.*?)</a>',row)
        torrent=re.search(r'href="(/Download/\d{8}/[a-f0-9]{40}\.torrent)"',row)
        if episode and torrent:
            url='https://mikanani.me'+torrent[1]
            by_url.setdefault(url,{'title':html.unescape(re.sub('<[^>]+>','',episode[2])).strip(),'url':url,'page':'https://mikanani.me'+episode[1]})
    items=list(by_url.values())
    good=sorted([c for c in items if score_candidate(c)>=0],key=score_candidate,reverse=True)
    if not good:return []
    batches=[c for c in good if any(x in c['title'].lower() for x in ['合集','全集','[fin]','[batch]','reseed','bdrip']) and not re.search(r'\[(?:0?\d|1\d)\](?!.*(?:全集|合集))',c['title'])]
    if batches:return batches[:1]  # one edition per subject, avoid duplicate whole-season downloads
    # Episodic releases: one exact release group, one version per episode.
    group=re.match(r'^[\[【]([^\]】]+)',good[0]['title'])
    group=group[1] if group else None
    episodes={}
    for c in good:
        if group and not c['title'].startswith(('['+group+']','【'+group+'】')):continue
        match=re.search(r'(?:\[|【| - )(\d{1,3})(?:v\d)?(?:\]|】|\s)',c['title'])
        if match:episodes.setdefault(int(match[1]),c)
    return [episodes[k] for k in sorted(episodes)]

def normalized(value):return re.sub(r'[^\w\u3040-\u30ff\u3400-\u9fff]','',value).casefold()

def discover_legacy(s):
    # Old titles may have releases but no Mikan season page. Require the full
    # canonical title/alias to occur in a release title; never guess short names.
    aliases=list(dict.fromkeys([s.get('name_cn') or '',s['name']]+s.get('aliases',[])))
    identities=[normalized(a) for a in aliases if len(normalized(a))>=4]
    candidates=[]
    for query in [a for a in aliases if a][:2]:
        page=text(fetch('https://mikanani.me/Home/Search?'+urllib.parse.urlencode({'searchstr':query})))
        for match in re.finditer(r'(?s)<a href="(/Home/Episode/[a-f0-9]{40})"[^>]*>(.*?)</a>',page):
            title=html.unescape(re.sub('<[^>]+>','',match[2])).strip()
            item={'title':title,'page':'https://mikanani.me'+match[1]}
            if score_candidate(item)<0 or not any(a in normalized(title) for a in identities):continue
            # Avoid single-episode results when selecting an old complete series.
            if s.get('platform') in ('TV','WEB') and not any(x in title.lower() for x in ['合集','全集','bdrip','[fin]','[batch]','reseed']):continue
            candidates.append(item)
        if candidates:break
    for c in sorted(candidates,key=score_candidate,reverse=True)[:3]:
        page=text(fetch(c['page']))
        url=re.search(r'href="(/Download/\d{8}/[a-f0-9]{40}\.torrent)"',page)
        if url:c['url']='https://mikanani.me'+url[1];return [c]
    return []

def scan_sources():
    import msvcrt
    lock=(HERE/'sources.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    catalog=json.loads((DATA/'catalog.json').read_text(encoding='utf8'))
    directory=DATA/'sources';directory.mkdir(exist_ok=True)
    for s in catalog:
        if (HERE/'STOP').exists():break
        target=directory/(str(s['id'])+'.json')
        if target.exists():continue
        for attempt in range(3):
            try:
                candidates=discover(s)
                result={'subject_id':s['id'],'title':s.get('name_cn') or s['name'],'candidates':candidates,'status':'found' if candidates else 'no_matching_source','checked_at':datetime.now().isoformat()}
                break
            except Exception as error:
                if attempt==2:result={'subject_id':s['id'],'title':s.get('name_cn') or s['name'],'candidates':[],'status':'request_error','error_type':type(error).__name__,'checked_at':datetime.now().isoformat()}
                else:time.sleep(5)
        atomic(target,result)
        counts=collections.Counter()
        for path in directory.glob('*.json'):
            try:counts[json.loads(path.read_text(encoding='utf8'))['status']]+=1
            except Exception:pass
        (OUT/'资源检索进度.md').write_text('# 动漫资源检索进度\n\n'+datetime.now().isoformat(timespec='seconds')+'\n\n目标 '+str(len(catalog))+' 个条目；已检查 '+str(sum(counts.values()))+' 个。\n\n'+str(dict(counts))+'\n\n缺少匹配资源与网络请求失败分别记录，不计为下载完成。\n',encoding='utf8')
        time.sleep(2)

def credential():
    script="$c=Import-Clixml '"+str(ROOT/'config/qb.credential.xml').replace("'","''")+"';@{username=$c.UserName;password=$c.GetNetworkCredential().Password}|ConvertTo-Json -Compress"
    r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],capture_output=True,check=True,creationflags=NO_WINDOW)
    return json.loads(r.stdout.decode('utf-8-sig'))

class Qbit:
    def __init__(self):
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call('auth/login',credential())
    def call(self,route,data=None,raw=None):
        headers={'Referer':QB+'/'};body=urllib.parse.urlencode(data).encode() if data is not None else None
        if raw:body,ctype=raw;headers['Content-Type']=ctype
        with self.opener.open(urllib.request.Request(QB+'/api/v2/'+route,data=body,headers=headers),timeout=20) as r:result=r.read().decode('utf8')
        try:return json.loads(result)
        except json.JSONDecodeError:return result
    def add(self,path,folder):
        boundary=uuid.uuid4().hex;parts=[]
        for k,v in {'savepath':str(folder),'stopped':'true','autoTMM':'false','category':'anime-batch'}.items():parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode())
        parts += [f'--{boundary}\r\nContent-Disposition: form-data; name="torrents"; filename="source.torrent"\r\nContent-Type: application/x-bittorrent\r\n\r\n'.encode(),path.read_bytes(),f'\r\n--{boundary}--\r\n'.encode()]
        self.call('torrents/add',raw=(b''.join(parts),'multipart/form-data; boundary='+boundary))

def load_state():return json.loads((DATA/'state.json').read_text(encoding='utf8')) if (DATA/'state.json').exists() else {'subjects':{},'tasks':{}}
def save_state(state):atomic(DATA/'state.json',state)

def selected_files(files):
    selected=[]
    for f in files:
        p=Path(f['name']);lower=f['name'].lower();ext=p.suffix.lower()
        if ext in ('.mkv','.mp4','.ass','.srt','.ssa','.ttf','.otf'):
            if any(x in lower for x in ['/cds/','\\cds\\','/scans/','\\scans\\','/sps/','\\sps\\','/pv/','\\pv\\','/menu/','\\menu\\']):continue
            selected.append(f)
        elif ext in ('.7z','.rar','.zip') and 'font' in lower:selected.append(f)
    return selected

def cloud_connection():
    credential_file=ROOT/'config/cloud-readonly.credential.xml'
    token_file=OUT/'CloudDrive只读令牌.txt'
    if credential_file.exists():
        script="$c=Import-Clixml '"+str(credential_file).replace("'","''")+"';$c.GetNetworkCredential().Password"
        r=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-Command',script],check=True,capture_output=True,creationflags=NO_WINDOW)
        token=r.stdout.decode('utf-8-sig').strip()
    elif token_file.exists():token=token_file.read_text(encoding='utf-8-sig').strip()
    else:return None
    if len(token)<20:return None
    sys.path.insert(0,str(HERE/'generated'))
    import grpc,clouddrive_pb2 as pb,clouddrive_pb2_grpc as rpc
    stub=rpc.CloudDriveFileSrvStub(grpc.insecure_channel('127.0.0.1:29798'))
    return stub,pb,(('authorization','Bearer '+token),)

def cloud_verified(remote,local,connection):
    if not connection:return False
    stub,pb,md=connection
    # Force refresh the parent from cloud; never trust a mounted-file existence check.
    matches=[]
    scoped=remote.removeprefix('/115open/动漫') or '/'
    for page in stub.GetSubFiles(pb.ListSubFileRequest(path=str(Path(scoped).parent).replace('\\','/'),forceRefresh=True),metadata=md,timeout=35):
        matches += [f for f in page.subFiles if f.name==Path(remote).name]
    if len(matches)!=1:return False
    f=matches[0]
    if not f.id or not f.isCloudFile or f.size!=local.stat().st_size:return False
    actual=f.fileHashes.get(2,'').upper()
    if not re.fullmatch('[0-9A-F]{40}',actual):return False
    h=hashlib.sha1()
    with local.open('rb') as stream:
        for part in iter(lambda:stream.read(4*1024**2),b''):h.update(part)
    return h.hexdigest().upper()==actual

def storage_committed(state):
    total=0
    for t in state['tasks'].values():
        if t['status'] in ('cloud_verified','abandoned'):continue
        size=t['selected_bytes']
        if t['status'] in ('waiting_for_peers','source_replaced','needs_attention'):
            progress=max(0,min(1,t.get('last_progress',t.get('progress',0))))
            size=int(size*progress)
        total+=size
    return total

def storage_ready(state,additional=0):
    allocated=storage_committed(state)
    free=shutil.disk_usage(DOWNLOADS).free
    return allocated+additional<=STAGING_GIB*GIB and free>=additional+30*GIB

def map_selected_files(chosen,qfiles):
    # libtorrent hides BitComet padding files and renumbers its file indexes.
    # Match the inspected path and size, then use qB's own indexes for priority.
    def identity(f):return (str(safe_relative(f['name'])).replace('\\','/').casefold(),f['size'])
    wanted={identity(f) for f in chosen}
    mapped=[f for f in qfiles if identity(f) in wanted]
    if len(wanted)!=len(chosen) or len(mapped)!=len(chosen):raise RuntimeError('qB file identity does not match inspected selection')
    return mapped

def add_task(qb,s,candidate,state):
    data=fetch(candidate['url']);h,files=torrent_info(data)
    key=candidate.get('task_key',h)
    if candidate.get('qb_fallback') and candidate.get('verified_hash')!=h:raise ValueError('Reviewed torrent hash changed')
    if key in state['tasks']:return 'duplicate'
    if 'task_key' not in candidate and any(t.get('source_hash',k)==h for k,t in state['tasks'].items()):return 'duplicate'
    chosen=[f for f in files if f['index'] in candidate['selected_ids']] if 'selected_ids' in candidate else selected_files(files)
    size=sum(f['size'] for f in chosen)
    if not any(Path(f['name']).suffix.lower() in ('.mkv','.mp4') for f in chosen) and 'task_key' not in candidate:return 'invalid'
    if size>CHUNK_GIB*GIB and 'task_key' not in candidate:
        chunks=[];chunk=[];used=0
        for f in chosen:
            if f['size']>60*GIB:log(f'single file exceeds staging limit for bgm {s["id"]}');return 'oversize'
            if chunk and used+f['size']>CHUNK_GIB*GIB:chunks.append(chunk);chunk=[];used=0
            chunk.append(f);used+=f['size']
        if chunk:chunks.append(chunk)
        state.setdefault('chunk_queue',[])
        for i,part in enumerate(chunks):
            c=dict(candidate,selected_ids=[f['index'] for f in part],task_key=h+':'+str(i))
            if i==0:candidate.update(c);chosen=part;size=sum(f['size'] for f in part);key=c['task_key']
            if not any(x['candidate']['task_key']==c['task_key'] for x in state['chunk_queue']):state['chunk_queue'].append({'subject':s,'candidate':c})
        save_state(state)
    if 'task_key' in candidate and any(t.get('source_hash',k)==h and t['status'] not in ('cloud_verified','abandoned') for k,t in state['tasks'].items()):return 'busy'
    if any(t['hash']==h for t in qb.call('torrents/info')):return 'busy'
    if not storage_ready(state,size):return 'budget'
    if shutil.disk_usage('X:/').free<size+100*GIB:raise RuntimeError('Cloud capacity guard: less than source plus 100 GiB reserve')
    path=DATA/(h+'.torrent');path.write_bytes(data);folder=DOWNLOADS/key.replace(':','_');folder.mkdir(exist_ok=True)
    qb.add(path,folder)
    qfiles=[]
    for _ in range(30):
        try:qfiles=qb.call('torrents/files?hash='+h)
        except Exception:pass
        if qfiles:break
        time.sleep(.5)
    if not qfiles:raise RuntimeError('qBittorrent metadata not ready')
    qchosen=map_selected_files(chosen,qfiles)
    if sum(f['size'] for f in qchosen)!=size:raise RuntimeError('qBittorrent file selection does not match inspected torrent')
    qb.call('torrents/filePrio',{'hash':h,'id':'|'.join(str(f['index']) for f in qfiles),'priority':0})
    qb.call('torrents/filePrio',{'hash':h,'id':'|'.join(str(f['index']) for f in qchosen),'priority':1})
    state['tasks'][key]={'source_hash':h,'subject_id':s['id'],'title':s.get('name_cn') or s['name'],'source_title':candidate['title'],'source_url':candidate['page'],'selected_bytes':size,'status':'downloading','files':[{'name':f['name'],'size':f['size'],'index':f['index']} for f in qchosen],'verified':[],'local_folder':str(folder),'fallback':bool(candidate.get('qb_fallback')),'episode_offset':candidate.get('episode_offset')}
    save_state(state)
    qb.call('torrents/start',{'hashes':h})
    log(f'queued bgm {s["id"]}: {size/GIB:.2f} GiB')
    return 'queued'

WAITING_STATUSES={'waiting_for_peers','source_replaced','needs_attention'}

def active_downloads(state):
    return sum(t['status'] not in {'cloud_verified','abandoned'}|WAITING_STATUSES for t in state['tasks'].values())

def maintain_downloads(qb,state,now=None):
    now=time.time() if now is None else now
    torrents={t['hash']:t for t in qb.call('torrents/info')}
    slots=active_downloads(state)
    for key,t in state['tasks'].items():
        if t['status'] in ('cloud_verified','abandoned','source_replaced'):continue
        h=t.get('source_hash',key);q=torrents.get(h)
        if not q:continue
        if q.get('category')!='anime-batch':continue
        if q['state'] in ('error','missingFiles'):
            qb.call('torrents/stop',{'hashes':h})
            t.update(status='needs_attention',last_error='qB: '+q['state'])
            continue
        progress=q.get('progress',0)
        old=t.get('last_progress',t.get('progress',0))
        t.setdefault('last_progress_at',q.get('added_on',now) if progress==0 else now)
        if progress>old+1e-7 or q.get('dlspeed',0)>0:t['last_progress_at']=now
        t['last_progress']=progress
        if t['status']=='waiting_for_peers':
            if now>=t.get('retry_after',now+1800) and slots<MAX_ACTIVE and storage_ready(state,max(0,t['selected_bytes']-int(t['selected_bytes']*min(1,max(0,progress))))):
                qb.call('torrents/start',{'hashes':h})
                qb.call('torrents/reannounce',{'hashes':h})
                t.update(status='downloading',last_progress_at=now,retry_grace_until=now+180);slots+=1
            continue
        if t['status']=='needs_attention':continue
        elapsed=q.get('time_active',0)
        average=q.get('downloaded',0)/elapsed if elapsed>0 else 0
        t['observed_average_kib_s']=round(average/1024,2)
        # A peer may advertise a complete copy while choking all real data.
        # Do not let protocol trickles keep a useless source active forever.
        if now>=t.get('retry_grace_until',0) and elapsed>=900 and average<16*1024 and q.get('dlspeed',0)<16*1024 and q.get('amount_left',0)>100*1024**2:
            qb.call('torrents/stop',{'hashes':h})
            t.update(status='waiting_for_peers',retry_after=now+1800,last_error='运行至少15分钟且平均低于16 KiB/s；慢源暂缓，保留已下载文件')
            slots-=1
            continue
        idle=now-t['last_progress_at']
        if q['state']=='stalledDL' and progress<1 and not q.get('dlspeed',0) and q.get('availability',0)<1 and not q.get('num_seeds',0):
            if idle>=300 and now-t.get('last_reannounce_at',0)>=600:
                qb.call('torrents/reannounce',{'hashes':h});t['last_reannounce_at']=now
            if idle>=900:
                qb.call('torrents/stop',{'hashes':h})
                t.update(status='waiting_for_peers',retry_after=now+1800,last_error='15分钟无进度且无完整做种；保留部分文件，稍后重试')
                slots-=1
    save_state(state)

def cloud_staging_name(task,h):
    name=str(task['subject_id'])+' '+re.sub(r'[<>:"/\\|?*]','_',task['title']).rstrip(' .')[:90]
    return name+(' [qB-'+h[:8]+']' if task.get('fallback') else '')

def completed_local(q,relative):
    paths=[Path(q['save_path'])/relative]
    if q.get('download_path'):paths.append(Path(q['download_path'])/relative)
    return next((p for p in paths if p.is_file()),None)

def fallback_tick(qb,state):
    path=DATA/'qb-fallback-plan.json'
    if not path.exists():return '暂无qB补充计划'
    plan=json.loads(path.read_text(encoding='utf8'))
    proposals=DATA/'repair-source-proposals.json'
    if proposals.exists():
        known={x['hash'] for x in plan['entries']}
        for item in json.loads(proposals.read_text(encoding='utf8')).get('entries',[]):
            if item['hash'] not in known:
                plan['entries'].append(item);known.add(item['hash'])
        plan['max_active']=MAX_ACTIVE
        atomic(path,plan)
    ledger=DATA/'cloud-queue.json'
    remote=json.loads(ledger.read_text(encoding='utf8')).get('tasks',{}) if ledger.exists() else {}
    for item in plan['entries']:
        if item['status']!='reserved':continue
        h=item['hash'];candidate=item['candidate']
        if (candidate.get('task_key') in state['tasks'] if candidate.get('task_key') else any(t.get('source_hash',k).split(':')[0]==h for k,t in state['tasks'].items())):
            item['status']='queued';atomic(path,plan);continue
        if any(x in remote for x in (h,item['url_hash'])):
            item['status']='covered_by_115';atomic(path,plan);continue
        if item.get('episode_repair'):
            for oldkey,oldtask in state['tasks'].items():
                if oldtask['subject_id']==item['subject']['id'] and oldtask['status']=='waiting_for_peers':
                    oldhash=oldtask.get('source_hash',oldkey).split(':')[0]
                    qb.call('torrents/stop',{'hashes':oldhash})
                    oldtask.update(status='source_replaced',replacement_hash=h)
            save_state(state)
        try:result=add_task(qb,item['subject'],candidate,state)
        except Exception as error:
            item.update(status='error',error_type=type(error).__name__,error_message=str(error)[:240]);atomic(path,plan)
            log('qB fallback retained on error: '+h+' '+type(error).__name__);continue
        if result not in ('budget','busy'):item['status']=result
        atomic(path,plan)
        if result=='queued':return '115与qB同时下载；qB已启动 '+item['subject']['name_cn']
        if result=='budget':return 'qB等待暂存空间释放'
    if (HERE/'QB_PRIMARY').exists():return qb_primary_tick(qb,state)
    return 'qB补充计划已排队；继续上传、核验和后续分块'

def qb_primary_tick(qb,state):
    """Continue reviewed source discovery with qB after cloud quota exhaustion."""
    import cloud_queue as cloud
    catalog=json.loads((DATA/'catalog.json').read_text(encoding='utf8'))
    remote=cloud.load()['tasks']
    primary_subjects=state.setdefault('qb_primary_subjects',[])
    covered_subjects={t['subject_id'] for t in remote.values() if t['status'] not in ('rejected','OFFLINE_ERROR')}
    covered_subjects.update(t['subject_id'] for t in state['tasks'].values() if t['subject_id'] not in primary_subjects and t['status']!='abandoned')
    covered=set(remote)
    covered.update(t.get('source_hash',k).split(':')[0] for k,t in state['tasks'].items())
    covered.update(x['candidate']['task_key'].split(':')[0] for x in state.get('chunk_queue',[]))
    errors=state.setdefault('qb_primary_errors',{})
    for subject,candidate,h in cloud.candidates(catalog):
        if subject['id'] in covered_subjects:continue
        if h in covered or candidate.get('magnet_only'):continue
        if time.time()<errors.get(h,{}).get('retry_after',0):continue
        if not candidate.get('manual_verified') and cloud.identity_conflict(subject,candidate,catalog):continue
        candidate=dict(candidate,qb_fallback=True,verified_hash=h)
        if subject['id'] not in primary_subjects:primary_subjects.append(subject['id'])
        try:result=add_task(qb,subject,candidate,state)
        except Exception as error:
            errors[h]={'error_type':type(error).__name__,'retry_after':time.time()+3600}
            save_state(state);continue
        if result=='queued':return 'qB主下载队列已启动 '+(subject.get('name_cn') or subject['name'])
        if result in ('budget','busy'):return 'qB等待暂存空间或当前任务完成'
        errors[h]={'result':result,'retry_after':time.time()+3600};save_state(state)
    return 'qB继续下载现有任务；等待可用的新资源'

def publish(qb,state,connection):
    torrents={t['hash']:t for t in qb.call('torrents/info')}
    copied=0;copied_bytes=0
    for key,t in state['tasks'].items():
        h=t.get('source_hash',key)
        if t['status'] in {'cloud_verified','abandoned'}|WAITING_STATUSES:continue
        try:
            q=torrents.get(h)
            if q:
                t['progress']=q.get('progress',0);t['speed_mib']=q.get('dlspeed',0)/2**20;t['downloader_state']=q.get('state','')
            if not q or any(x in q['state'].lower() for x in ['check','moving']):continue
            completed=None
            if q.get('progress',0)<1:
                completed={f['index'] for f in qb.call('torrents/files?hash='+h) if f.get('progress',0)>=1}
            if q.get('category')!='anime-batch':raise RuntimeError('Refuse cleanup: torrent is outside managed category')
            local_base=Path(t['local_folder']).resolve()
            if not local_base.is_relative_to(DOWNLOADS.resolve()):raise RuntimeError('Local folder guard failed')
            subject_dir=cloud_staging_name(t,h)
            all_verified=True
            for f in t['files']:
                if f['name'] in t['verified']:continue
                if completed is not None and f['index'] not in completed:all_verified=False;continue
                relative_source=safe_relative(f['name'])
                candidates=[Path(q['save_path'])/relative_source]
                if q.get('download_path'):candidates.append(Path(q['download_path'])/relative_source)
                local=next((p for p in candidates if p.is_file()),None)
                if local is None:all_verified=False;continue
                allowed_roots=[local_base,(ROOT/'downloads/incomplete').resolve()]
                if not any(local.resolve().is_relative_to(p) for p in allowed_roots):raise RuntimeError('Source path outside managed staging')
                if not local.is_file() or local.stat().st_size!=f['size']:raise RuntimeError('Completed source missing or wrong size')
                relative=Path('待整理/批量收藏')/subject_dir/safe_relative(f['name'])
                dest=CLOUD_MOUNT/relative
                if not dest.exists() or dest.stat().st_size!=f['size']:
                    if dest.exists():raise RuntimeError('Cloud destination collision; no overwrite')
                    dest.parent.mkdir(parents=True,exist_ok=True)
                    temporary=dest.with_name(dest.name+'.batch-'+h[:8]+'.uploading')
                    shutil.copyfile(local,temporary)
                    if dest.exists():raise RuntimeError('Cloud destination appeared during copy; local source retained')
                    temporary.rename(dest)
                    t['status']='upload_pending';save_state(state)
                    copied+=1;copied_bytes+=f['size'];all_verified=False
                    if copied>=16 or copied_bytes>=8*GIB:return
                    continue
                remote='/115open/动漫/'+str(relative).replace('\\','/')
                if not cloud_verified(remote,local,connection):all_verified=False;continue
                t['verified'].append(f['name']);save_state(state)
            if q.get('progress',0)>=1 and all_verified and len(t['verified'])==len(t['files']):
                # Recheck every selected file, immediately before the irreversible cleanup.
                for f in t['files']:
                    local=completed_local(q,safe_relative(f['name']))
                    if local is None:raise RuntimeError('Completed local file unavailable; cleanup withheld')
                    allowed=[local_base,(ROOT/'downloads/incomplete').resolve()]
                    if not any(local.resolve().is_relative_to(p) for p in allowed):raise RuntimeError('Cleanup source outside managed staging')
                    remote='/115open/动漫/待整理/批量收藏/'+subject_dir+'/'+str(safe_relative(f['name'])).replace('\\','/')
                    if not cloud_verified(remote,local,connection):raise RuntimeError('Final cloud recheck failed; local files retained')
                qb.call('torrents/stop',{'hashes':h})
                t['status']='cleanup_pending';save_state(state)
                qb.call('torrents/delete',{'hashes':h,'deleteFiles':'true'})
                t['status']='cloud_verified';save_state(state)
                log('remote SHA1 verified; local torrent data removed: '+h)
                return
            if not connection:t['status']='awaiting_cloud_token'
        except Exception as error:
            t.update(last_error_type=type(error).__name__,last_error=str(error)[:300],last_error_at=datetime.now().isoformat(timespec='seconds'))
            save_state(state)
            log('upload retained for '+h+': '+type(error).__name__+': '+str(error)[:180])
            continue


def report(state,catalog,message=''):
    counts=collections.Counter(s.get('status','pending') for s in state['subjects'].values())
    tasks=collections.Counter(t['status'] for t in state['tasks'].values())
    lines=['# 批量动漫收藏状态','',datetime.now().isoformat(timespec='seconds'),'',f'目标：2022-01-01至{TODAY}已开播的日本TV/WEB动画，加上Bangumi日本动画榜前100；按条目ID去重。',f'目标条目数：{len(catalog)}；资源检索：{dict(counts)}；下载任务：{dict(tasks)}。','',message,'','仅在强制刷新后的云端文件ID、大小及SHA1全部吻合时删除本地；不能核验时保留并停止扩充本地批次。','', '|条目|状态|进度|速度MiB/s|已核验文件|来源|','|---|---|---:|---:|---:|---|']
    for t in state['tasks'].values():lines.append(f'|{t["title"].replace("|","/")}|{t["status"]}|{t.get("progress",0):.1%}|{t.get("speed_mib",0):.2f}|{len(t["verified"])}/{len(t["files"])}|[资源]({t["source_url"]})|')
    (OUT/'批量收藏运行状态.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    save_state(state)

def run():
    import msvcrt
    lock=(HERE/'batch.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:log('another batch instance is running');return
    catalog=json.loads((DATA/'catalog.json').read_text(encoding='utf8')) if (DATA/'catalog.json').exists() else build_catalog()
    state=load_state()
    while not (HERE/'STOP').exists():
        try:
            phase='publish'
            qb=Qbit();maintain_downloads(qb,state);connection=cloud_connection();publish(qb,state,connection)
            if not storage_ready(state):
                report(state,catalog,'本地暂存预算已满，等待上传核验和清理。');time.sleep(60);continue
            active=active_downloads(state)
            if active>=MAX_ACTIVE:
                report(state,catalog,f'{MAX_ACTIVE}个下载/上传任务占用名额；慢源暂缓后重试。');time.sleep(60);continue
            busy_hashes={t.get('source_hash',k) for k,t in state['tasks'].items() if t['status'] not in ('cloud_verified','abandoned')}
            chunk=next((x for x in state.get('chunk_queue',[]) if x['candidate']['task_key'] not in state['tasks'] and x['candidate']['task_key'].split(':')[0] not in busy_hashes),None)
            if chunk:
                result=add_task(qb,chunk['subject'],chunk['candidate'],state)
                report(state,catalog,'正在分批处理长篇合集。');time.sleep(60 if result in ('budget','busy') else 3);continue
            if (HERE/'QB_FALLBACK').exists():
                report(state,catalog,fallback_tick(qb,state));time.sleep(3);continue
            if (HERE/'CLOUD_ONLY').exists():
                report(state,catalog,'现有本地任务及其后续分块继续下载、上传、核验；新作品由115云端下载。');time.sleep(30);continue
            explicit=next((s for s in state.get('explicit_sources',[]) if s['hash'] not in state['tasks']),None)
            if explicit:
                add_task(qb,explicit['subject'],explicit['candidate'],state)
                report(state,catalog,'优先完成春物和空之境界。');time.sleep(3);continue
            subject=next((s for s in catalog if state['subjects'].get(str(s['id']),{}).get('status')=='pending_sources'),None)
            if not subject:subject=next((s for s in catalog if str(s['id']) not in state['subjects']),None)
            if not subject:
                report(state,catalog,'本轮资源检索完成；缺资源条目已记录，未宣称全部下载完成。');time.sleep(300);continue
            sid=str(subject['id'])
            phase='discover'
            if sid not in state['subjects']:
                source_file=DATA/'sources'/(sid+'.json')
                if not source_file.exists():
                    report(state,catalog,'等待后台资源检索生成下一条目来源。');time.sleep(10);continue
                source_result=json.loads(source_file.read_text(encoding='utf8'))
                candidates=source_result['candidates']
                state['subjects'][sid]={'status':'pending_sources' if candidates else 'no_matching_source','checked_at':datetime.now().isoformat(),'candidates':candidates,'next':0,'queued':0,'duplicates':0}
                save_state(state)
            entry=state['subjects'][sid];candidates=entry['candidates']
            while entry['next']<len(candidates):
                result=add_task(qb,subject,candidates[entry['next']],state)
                if result in ('budget','busy'):break
                entry['next']+=1
                if result=='queued':entry['queued']+=1;break
                if result=='duplicate':entry['duplicates']+=1
            if entry['next']>=len(candidates):entry['status']='queued' if entry['queued'] else 'duplicate_covered' if entry['duplicates'] else 'no_matching_source'
            report(state,catalog,'已启动本地分批下载；等候云端校验令牌。' if not connection else '采集、上传、核验和清理运行中。')
            time.sleep(3)
        except Exception as error:
            if locals().get('phase')=='discover':
                strikes=state.setdefault('failures',{});strikes[sid]=strikes.get(sid,0)+1
                if strikes[sid]>=3:state['subjects'][sid]={'status':'request_error','error_type':type(error).__name__,'checked_at':datetime.now().isoformat()}
            log(type(error).__name__+': '+str(error))
            report(state,catalog,'运行异常，已保留本地数据：'+type(error).__name__+': '+str(error))
            time.sleep(60)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['catalog','discover','run']);a=p.parse_args()
    if a.action=='catalog':build_catalog()
    elif a.action=='discover':scan_sources()
    else:run()
