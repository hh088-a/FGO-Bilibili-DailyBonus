"""115 server-side download queue. No local video downloads or credential logging."""
import os
import argparse
import collections
import json
import re
import time
from datetime import datetime
from pathlib import Path

import batch

HERE=batch.HERE
LEDGER=batch.DATA/'cloud-queue.json'
STOP=HERE/'STOP_CLOUD'
QUOTA_STOP=HERE/'CLOUD_QUOTA_STOP'
MAX_ACTIVE=10
DEST='/待整理/云端下载'
RESERVE=100*2**30

def now():return datetime.now().isoformat(timespec='seconds')

def title(s):return s.get('name_cn') or s.get('name') or str(s['id'])

def load():
    if LEDGER.exists():return json.loads(LEDGER.read_text(encoding='utf8'))
    return {'tasks':{},'skipped':{},'status':'starting','created_at':now()}

def identities(s):
    return {batch.normalized(x) for x in [s.get('name_cn',''),s.get('name','')]+s.get('aliases',[]) if len(batch.normalized(x))>=4}

def identity_conflict(s,c,catalog):
    """Hold a release naming a longer sequel identity rather than its parent."""
    # Do not join a series name to the next bracketed episode number (e.g. 01).
    segments=[batch.normalized(x) for x in re.split(r'[\[\]【】/|+()（）]',c['title'])]
    def contains(name):
        pattern=re.escape(name)+(r'(?!\d)' if name[-1:].isdigit() else '')
        return any(re.search(pattern,segment) for segment in segments)
    matches=[x for x in identities(s) if contains(x)]
    if not matches:return 'release_title_not_confirmed'
    if not s.get('mikan_id'):
        # Search results for old works frequently point to sequels/remakes.
        # Without a season page validated against the exact Bangumi ID, require
        # an entire name segment, rather than a parent-title prefix.
        expected=re.search(r'/season/(\d+)',s.get('tmdb') or '')
        season=int(expected[1]) if expected else 1
        technical_suffixes=('',f's{season:02d}',f's{season}',f'season{season}','全集','大合集')
        if not any(segment==name+suffix for segment in segments for name in identities(s) for suffix in technical_suffixes):
            return 'legacy_version_not_confirmed'
        if any(word in c['title'] for word in ('补缺','补档缺集','缺集补全','片段合集')):
            return 'partial_legacy_collection'
    for other in catalog:
        if other['id']==s['id']:continue
        for longer in identities(other):
            if contains(longer) and any(longer.startswith(short) and len(longer)>len(short) for short in matches):
                # A combined-season collection explicitly covers its parent too.
                if not any(x in c['title'] for x in ['三季','两季','全季','第一季+','1-3季','1-2季']):
                    return 'possible_sequel:'+str(other['id'])
    return ''

def local_coverage():
    state=batch.load_state()
    hashes={t.get('source_hash',k).split(':')[0] for k,t in state['tasks'].items()}
    subjects={t['subject_id'] for t in state['tasks'].values() if t.get('status')!='abandoned' and not t.get('fallback')}
    hashes.update(x['candidate']['task_key'].split(':')[0] for x in state.get('chunk_queue',[]))
    plan=batch.DATA/'qb-fallback-plan.json'
    if plan.exists():
        for item in json.loads(plan.read_text(encoding='utf8')).get('entries',[]):
            if item.get('status') in ('reserved','queued','duplicate'):
                hashes.update((item['hash'],item['url_hash']))
    return hashes,subjects

def candidates(catalog):
    external=batch.DATA/'external-sources.json'
    if external.exists():
        for entry in json.loads(external.read_text(encoding='utf8')):
            h=entry.get('hash','').lower();c=entry.get('candidate',{})
            if re.fullmatch(r'[a-f0-9]{40}',h) and c.get('manual_verified'):
                yield entry['subject'],dict(c,external=True),h
    for s in catalog:
        path=batch.DATA/'sources'/(str(s['id'])+'.json')
        if not path.exists():continue
        try:record=json.loads(path.read_text(encoding='utf8'))
        except (ValueError,OSError):continue
        for c in record.get('candidates',[]):
            match=re.fullmatch(r'https://mikanani\.me/Download/\d{8}/([a-f0-9]{40})\.torrent',c.get('url',''))
            if match:yield s,c,match[1]

class CloudQueue:
    def __init__(self):
        self.stub,self.pb,self.md=batch.cloud_connection()
        self.state=load()
        self.catalog=json.loads((batch.DATA/'catalog.json').read_text(encoding='utf8'))
        self.folders=set()

    def save(self):
        self.state['updated_at']=now()
        batch.atomic(LEDGER,self.state)

    def quota(self):
        return self.stub.GetOfflineQuotaInfo(self.pb.OfflineQuotaRequest(cloudName='115open',cloudAccountId=os.environ['ANIME_CLOUD_ACCOUNT_ID'],path='/'),metadata=self.md,timeout=25)

    def all_tasks(self):
        tasks={};page=1
        while True:
            r=self.stub.ListAllOfflineFiles(self.pb.OfflineFileListAllRequest(cloudName='115open',cloudAccountId=os.environ['ANIME_CLOUD_ACCOUNT_ID'],page=page,path='/'),metadata=self.md,timeout=30)
            for f in r.offlineFiles:
                if f.infoHash:tasks[f.infoHash.lower()]=f
            if page>=r.pageCount:break
            page+=1
            if page>1000:raise RuntimeError('Offline pagination exceeded safety bound')
        return tasks

    def task_snapshot(self):
        cached=getattr(self,'_task_snapshot',None)
        if cached is None or time.monotonic()-cached[0]>=getattr(self,'remote_cache_seconds',20):
            if cached is None or time.monotonic()-getattr(self,'_full_snapshot_at',0)>=getattr(self,'full_cache_seconds',900):
                tasks=self.all_tasks();self._full_snapshot_at=time.monotonic()
            else:
                # Recent requests fit in the latest page. Preserve older active
                # jobs conservatively until the next complete reconciliation.
                tasks=dict(cached[1])
                r=self.stub.ListAllOfflineFiles(self.pb.OfflineFileListAllRequest(cloudName='115open',cloudAccountId=os.environ['ANIME_CLOUD_ACCOUNT_ID'],page=1,path='/'),metadata=self.md,timeout=30)
                for f in r.offlineFiles:
                    if f.infoHash:tasks[f.infoHash.lower()]=f
            cached=(time.monotonic(),tasks);self._task_snapshot=cached
        return cached[1]

    def ensure_dir(self,path):
        if path in self.folders:return
        parent=str(Path(path).parent).replace('\\','/')
        if parent not in ('/','.') and parent not in self.folders:self.ensure_dir(parent)
        children=[]
        for page in self.stub.GetSubFiles(self.pb.ListSubFileRequest(path=parent,forceRefresh=True),metadata=self.md,timeout=25):children.extend(page.subFiles)
        item=next((f for f in children if f.name==Path(path).name),None)
        if item:
            if not item.isDirectory:raise RuntimeError('Destination is a file')
        else:
            r=self.stub.CreateFolder(self.pb.CreateFolderRequest(parentPath=parent,folderName=Path(path).name),metadata=self.md,timeout=30)
            if not r.result.success:raise RuntimeError('Cloud folder creation failed')
        self.folders.add(path)

    def report(self,message=''):
        counts=collections.Counter(t['status'] for t in self.state['tasks'].values())
        lines=['# 115云端下载状态','',now(),'',f'目标目录：X:\\动漫\\待整理\\云端下载；最多同时{MAX_ACTIVE}个云下载任务。',
               f'最新额度：{self.state.get("quota_left","未读取")} / {self.state.get("quota_total","未读取")}；运行状态：{self.state["status"]}。',
               f'本队列记录：{dict(counts)}；去重/本地覆盖/待确认：{len(self.state["skipped"])}。','',message,'',
               '每个种子提交前检查剩余额度；额度为0或服务器明确提示额度用完时，写入持久停止标记并退出，不自动等待下次续额。',
               '下载发生在115服务器；不下载影音文件到电脑。云端完成不等于已整理进Jellyfin。现有qB任务及后续分块继续完成。','',
               '|作品|云端状态|进度|资源|','|---|---|---:|---|']
        for t in self.state['tasks'].values():
            lines.append(f'|{t["title"].replace("|","/")}|{t["status"]}|{t.get("progress",0):.1f}%|[来源]({t["source_page"]})|')
        (batch.OUT/'115云端下载状态.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
        self.save()

    def exhausted(self,message):
        self.state['status']='quota_exhausted'
        batch.atomic(QUOTA_STOP,{'stopped_at':now(),'reason':message,'quota_left':self.state.get('quota_left')})
        self.report('额度已用完，已停止新增提交。qB既有下载继续。')

    def tick(self):
        quota=self.quota()
        self.state.update(quota_left=quota.left,quota_total=quota.total)
        remote=self.task_snapshot()
        for h,t in self.state['tasks'].items():
            if h in remote:
                f=remote[h];t.update(status=self.pb.OfflineFileStatus.Name(f.status),progress=f.percendDone,cloud_file_id=f.fileId)
        if quota.left<=0:
            self.exhausted('CloudDrive GetOfflineQuotaInfo.left <= 0')
            return False
        active=sum(f.status in (self.pb.OFFLINE_INIT,self.pb.OFFLINE_DOWNLOADING,self.pb.OFFLINE_UNKNOWN) for f in remote.values())
        # Accepted or ambiguous submissions remain reserved until observed by the server.
        waiting=[t for h,t in self.state['tasks'].items() if h not in remote and t['status'] in ('submitting','accepted','uncertain')]
        active+=len(waiting)
        if active>=MAX_ACTIVE:
            self.state['status']='waiting_for_cloud_slots';self.report('等待云下载任务释放并发名额。');return True
        local_hashes,local_subjects=local_coverage()
        for s,c,h in candidates(self.catalog):
            if h in self.state['tasks']:continue
            key=str(s['id'])+':'+h
            if key in self.state['skipped']:continue
            reason=''
            if h in remote:reason='already_in_115'
            elif h in local_hashes or s['id'] in local_subjects:reason='existing_local_source'
            else:reason='' if c.get('manual_verified') else identity_conflict(s,c,self.catalog)
            if reason:
                self.state['skipped'][key]={'title':title(s),'reason':reason};continue
            # Only metadata (.torrent) is fetched; all video bytes go to 115.
            failed=self.state.setdefault('source_errors',{}).get(h,{})
            if time.time()<failed.get('retry_after',0):continue
            if c.get('magnet_only') and c.get('manual_verified'):
                size=int(c['declared_size']);file_count=None
                if not 0<size<2**41:raise ValueError('Invalid reviewed source size')
            else:
                try:
                    data=batch.fetch(c['url']);actual_hash,files=batch.torrent_info(data)
                except Exception as e:
                    self.state['source_errors'][h]={'title':title(s),'error_type':type(e).__name__,'retry_after':time.time()+3600}
                    self.save();continue
                if actual_hash!=h:
                    self.state['skipped'][key]={'title':title(s),'reason':'torrent_metadata_hash_mismatch'}
                    self.save();continue
                size=sum(f['size'] for f in files);file_count=len(files)
                if not any(Path(f['name']).suffix.lower() in ('.mkv','.mp4') for f in files):
                    self.state['skipped'][key]={'title':title(s),'reason':'no_video'};continue
            space=self.stub.GetSpaceInfo(self.pb.FileRequest(path='/'),metadata=self.md,timeout=25)
            reserved=sum(t.get('bytes',0) for t in self.state['tasks'].values() if t['status'] not in ('OFFLINE_FINISHED','OFFLINE_ERROR','rejected'))
            if space.freeSpace<size+reserved+RESERVE:
                self.state['status']='capacity_stop';self.report('云盘剩余空间不足以覆盖待完成任务及100 GiB预留，停止提交。');return False
            folder=DEST+'/'+str(s['id'])+' '+re.sub(r'[<>:"/\\|?*]','_',title(s)).rstrip(' .')[:90]
            if c.get('external'):folder+=' [补源-'+h[:8]+']'
            self.ensure_dir(folder)
            # Recheck immediately before every credit-consuming request.
            if STOP.exists():
                self.state['status']='paused';self.report('已按暂停要求停止提交。');return False
            quota=self.quota();self.state.update(quota_left=quota.left,quota_total=quota.total)
            if quota.left<=0:self.exhausted('Quota exhausted before submission');return False
            t={'subject_id':s['id'],'title':title(s),'release_title':c['title'],'source_page':c['page'],'hash':h,'bytes':size,'file_count':file_count,'destination':folder,'status':'submitting','created_at':now(),'progress':0,'external':bool(c.get('external')),'metadata_checked':not c.get('magnet_only',False)}
            self.state['tasks'][h]=t;self.save()
            try:
                r=self.stub.AddOfflineFiles(self.pb.AddOfflineFileRequest(urls='magnet:?xt=urn:btih:'+h,toFolder=folder,checkFolderAfterSecs=30),metadata=self.md,timeout=40)
            except Exception as e:
                t.update(status='uncertain',error_type=type(e).__name__)
                self.state['status']='reconcile_pending';self.report('一次提交结果未确认，保留账本；不重复提交该种子。');return True
            if not r.success:
                t.update(status='rejected',error=r.errorMessage[:300])
                lower=r.errorMessage.lower()
                if any(x in lower for x in ('quota','额度','配额','次数不足','次数已用完')):
                    self.exhausted('Provider rejected submission because of quota');return False
                self.state['status']='submission_rejected';self.report('115拒绝一次提交，暂停本队列，避免重复扣额；错误已记录。');return False
            t['status']='accepted'
            self.state['status']='running';self.report('已提交新种子，等待115服务器下载。')
            return True
        self.state['status']='waiting_for_source_discovery'
        self.report('已处理当前找到的资源，等待后台继续检索；无匹配资源不计为下载完成。')
        return True

def run(once=False):
    import msvcrt
    lock=(HERE/'cloud-queue.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    q=CloudQueue()
    if QUOTA_STOP.exists():q.state['status']='quota_exhausted';q.report('保留额度耗尽停止状态，需要明确重新启动后才恢复。');return
    while not STOP.exists():
        try:
            if not q.tick():return
        except Exception as e:
            q.state['status']='temporary_error';q.state['last_error_type']=type(e).__name__
            q.report('接口暂时不可用，60秒后重查；不打印凭据，不重复提交不确定任务。')
            if once:return
            time.sleep(60)
        if once:return
        # Keep requests sequential and bounded; don't flood the provider.
        time.sleep(2 if q.state['status']=='running' else 5 if q.state['status']=='waiting_for_cloud_slots' else 30)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');args=p.parse_args();run(args.once)
