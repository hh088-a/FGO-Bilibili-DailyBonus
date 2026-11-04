"""Import finished cloud releases while the independent 115 queue keeps downloading."""
import argparse
import collections
import hashlib
import json
import re
import subprocess
import time
from pathlib import PurePosixPath as P

import cloud_queue as cloud
import organize_cloud_batch as organizer
batch=cloud.batch
STOP=batch.HERE/'STOP_ORGANIZE'
WATCH=batch.DATA/'library-watch.json'
PLANS=batch.DATA/'organize-plans'
PLANS.mkdir(exist_ok=True)

def read(path,default):
    return json.loads(path.read_text(encoding='utf-8-sig')) if path.exists() else default

def eligible(record,remote,pb,expected_hashes):
    entries={t['hash']:t for t in record['tasks']}
    return bool(expected_hashes) and expected_hashes<=entries.keys() and all(h in remote and remote[h].status==pb.OFFLINE_FINISHED for h in entries)

def available(q):
    ledger=cloud.load();remote=q.all_tasks();catalog={s['id']:s for s in q.catalog}
    extra=batch.DATA/'repair-subjects.json'
    if extra.exists():catalog.update({s['id']:s for s in json.loads(extra.read_text(encoding='utf8'))})
    catalog.setdefault(233,{'id':233,'name_cn':'空之境界八章','name':'Kara no Kyoukai','tmdb':'collection/233','platform':'合集'})
    catalog.setdefault(43581,{'id':43581,'name_cn':'空之境界未来福音','name':'Mirai Fukuin','tmdb':'collection/43581','platform':'合集'})
    organized=read(organizer.STATE,{})
    done={h for s in organized.values() if s.get('status')=='verified' for h in s.get('task_hashes',[])}
    groups=collections.defaultdict(list)
    for h,t in ledger['tasks'].items():groups[(t['subject_id'],t['destination'])].append(t)
    result=[]
    for (sid,destination),tasks in groups.items():
        if all(t['hash'] in done for t in tasks):continue
        source=batch.DATA/'sources'/(str(sid)+'.json')
        source_record=read(source,{})
        expected=set()
        for c in source_record.get('candidates',[]):
            m=re.search(r'/([a-f0-9]{40})\.torrent$',c.get('url',''))
            if m:expected.add(m[1])
        if any(t.get('external') for t in tasks):expected={t['hash'] for t in tasks}
        expected.difference_update(done)
        current=[t for t in tasks if t['hash'] not in done]
        subject=dict(catalog.get(sid,{'id':sid,'name_cn':tasks[0]['title']}))
        # Explicit, unique in-range episode numbers remain valid when other
        # episodes are absent. Preserve the gaps rather than renumbering files.
        if (subject.get('tmdb') or '').startswith('tv/'):subject['_review_allow_gaps']=True
        if any(t.get('external') for t in tasks) or str(sid) in organized:
            subject['_batch_key']=str(sid)+'.'+hashlib.sha256(destination.encode()).hexdigest()[:12]
        record={'subject':subject,'tasks':current}
        if eligible(record,remote,q.pb,expected):result.append(record)
    # Local staging may only move after every existing chunk of that source has
    # already passed the uploader's verification and cleanup protocol.
    local=batch.load_state();local_groups=collections.defaultdict(list)
    for key,t in local['tasks'].items():
        if t.get('status')!='abandoned':local_groups[(t['subject_id'],bool(t.get('fallback')),t.get('source_hash',key).split(':')[0] if t.get('fallback') else '')].append((key,t))
    for (sid,fallback,source),tasks in local_groups.items():
        if not fallback and str(sid) in organized and organized[str(sid)].get('status')=='verified':continue
        if sid not in catalog:continue
        required={k for k,_ in tasks}
        required.update(x['candidate']['task_key'] for x in local.get('chunk_queue',[]) if x['subject']['id']==sid and (not fallback or x['candidate']['task_key'].split(':')[0]==source))
        if not all(k in local['tasks'] and local['tasks'][k]['status']=='cloud_verified' for k in required):continue
        hs={t.get('source_hash',k).split(':')[0] for k,t in tasks}
        if hs<=done:continue
        dest='/待整理/批量收藏/'+batch.cloud_staging_name(tasks[0][1],source)
        subject=dict(catalog[sid])
        offsets={t['episode_offset'] for k,t in tasks if t.get('episode_offset') is not None}
        if offsets:
            assert len(offsets)==1,'Mixed episode mappings in one repaired source'
            subject['_review_episode_offset']=next(iter(offsets))
        if fallback:
            subject['_batch_key']=str(sid)+'.qb.'+source[:12]
            if (subject.get('tmdb') or '').startswith('tv/'):subject['_review_allow_gaps']=True
        result.append({'subject':subject,'tasks':[{'hash':h,'destination':dest} for h in hs]})
    return result

def configure_names(o):
    organizer.TV_FOLDERS={}
    for f in o.ls('/剧集'):
        m=re.search(r'\[tmdbid-(\d+)\]',f.name)
        if f.isDirectory and m:organizer.TV_FOLDERS[m[1]]=f.name
    if organizer.TV_NAMES:return
    data=read(batch.DATA/'mapping.json',{})
    for item in data.get('items',[]):
        for site in item.get('sites',[]):
            m=re.fullmatch(r'tv/(\d+)',str(site.get('id',''))) if site.get('site')=='tmdb' else None
            if not m:continue
            names=item.get('titleTranslate',{}).get('zh-Hans',[])
            if names:organizer.TV_NAMES.setdefault(m[1],names[0])
            begin=item.get('begin','')
            if begin and re.match(r'\d{4}',begin):organizer.TV_START_YEARS.setdefault(m[1],begin[:4])

def refresh(state):
    if not state.get('dirty') or time.time()-state.get('last_refresh',0)<300:return
    p=subprocess.run(['powershell.exe','-NoProfile','-NonInteractive','-File',str(batch.HERE/'Refresh-IfIdle.ps1')],capture_output=True,creationflags=batch.NO_WINDOW,timeout=30)
    try:result=json.loads(p.stdout.decode('utf-8-sig').strip().splitlines()[-1])
    except (ValueError,IndexError):result={'status':'unavailable'}
    state['library_scan']=result
    if result.get('status')=='refreshed':state.update(dirty=False,last_refresh=time.time())

def report(state):
    done=read(organizer.STATE,{})
    valid=[r for r in done.values() if r.get('status')=='verified']
    totals={k:sum(r.get(k,0) for r in valid) for k in ('episodes','movies','subtitles','files_verified')}
    state.update(updated_at=cloud.now(),organized_releases=len(valid),totals=totals)
    batch.atomic(WATCH,state)
    lines=['# 115自动整理状态','',state['updated_at'],'',
           '115云下载队列与整理队列同时运行。只移动相关种子全部完成的作品；本地上传任务需要所有分块完成云端核验后才整理。',
           f'已核验整理：{len(valid)}个资源合集、{totals["episodes"]}集/OVA、{totals["movies"]}部电影、{totals["subtitles"]}份外挂字幕。',
           f'当前：{state.get("activity","检查已完成任务")}；待确认记录：{len(state.get("held",{}))}。',
           '记录的是已取得资源，不把缺少的集数计为收藏完成。无法确认编号、媒体类型或已有同名版本时，保留原位并继续处理其他作品。',
           '115任务在云端下载；qB补充任务使用受限本地暂存，上传并核验后清理。不删除云端影音；整理前后核对ID、大小和SHA1。115额度用完停止新增云任务。',
           '影音库已有扫描运行时不重复发起；新增整理内容会在扫描空闲后刷新。','',
           '剧集：X:\\动漫\\剧集；电影：X:\\动漫\\电影；资料归档：X:\\动漫\\归档\\资料。','']
    if state.get('held'):
        lines+=['|暂缓条目|原因|','|---|---|']
        for x in list(state['held'].values())[-25:]:lines.append('|'+x['title'].replace('|','/')+'|'+x['reason'].replace('|','/')+'|')
    (batch.OUT/'115自动整理状态.md').write_text('\n'.join(lines)+'\n',encoding='utf8')

def reviewed_subject(subject,items):
    """Translate only two reviewed release numbering conventions."""
    s=dict(subject)
    videos=[x for x in items if not x['dir'] and P(x['name']).suffix.lower() in organizer.VIDEO]
    if not videos:return s
    nums=[organizer.episode(x['name'],1) for x in videos]
    if not all(nums):return s
    numbers=[n[1] for n in nums]
    if s['id']==441939 and all('Kimetsu no Yaiba - ' in x['name'] for x in videos) and all(56<=n<=63 for n in numbers):
        s['_review_episode_offset']=-55
    if s['id']==457956 and all('TP Bon - ' in x['name'] for x in videos) and all(13<=n<=24 for n in numbers):
        catalog=read(batch.DATA/'catalog.json',[])
        sequel=next(x for x in catalog if x['id']==486676)
        key=organizer.batch_key(s)
        s.update(sequel)
        s.update(_batch_key=key,_review_episode_offset=-12,_review_allow_gaps=True)
    if s['id']==507433 and all('Kankin Kuiki Level X' in x['name'] for x in videos) and all(7<=n<=12 for n in numbers):
        sequel=next(x for x in read(batch.DATA/'catalog.json',[]) if x['id']==517532)
        key=organizer.batch_key(s);s.update(sequel)
        s.update(_batch_key=key,_review_allow_gaps=True)
    if s['id']==457326 and all('Sennen Kessenhen-Soukokutan - ' in x['name'] for x in videos) and all(1<=n<=14 for n in numbers):
        s['_review_episode_offset']=26
    if s['id']==453140 and all('Kimi ni Todoke S3 - ' in x['name'] for x in videos) and all(0<=n<=5 for n in numbers):
        s['tmdb']='tv/68854/season/3'
    if s['id']==492352 and all('5Hanayome SP2 - ' in x['name'] for x in videos) and sorted(numbers)==[1,2]:
        s['_review_movie_parts']=2
    if s['id']==487630 and all('Ore dake Level Up na Ken Season 2 - ' in x['name'] for x in videos) and all(1<=n<=13 for n in numbers):
        s['_review_episode_offset']=12
    return s

def cycle(q,state):
    state['activity']='检查已完成云下载'
    for record in available(q):
        if STOP.exists():break
        s=record['subject'];sid=str(s['id']);name=cloud.title(s)
        key=organizer.batch_key(s)
        old=state.setdefault('held',{}).get(sid)
        if old and time.time()<old.get('retry_after',0):continue
        try:
            state['activity']='整理 '+name;report(state)
            # Long-running shows need an episode-to-season mapping, not a guess.
            if (s.get('tmdb') or '').startswith('tv/') and not 0<int(s.get('eps') or 0)<=200:
                raise ValueError('长篇动画需要明确的季集映射，原目录保留')
            o=organizer.Bulk();configure_names(o)
            plan_file=PLANS/(key+'.json')
            if plan_file.exists():plans=read(plan_file,[])
            else:
                before=organizer.FOLDER/(key+'.before.json')
                if not before.exists():batch.atomic(before,o.tree(record['tasks'][0]['destination']))
                corrected=reviewed_subject(s,read(before,[]))
                plans=organizer.build([dict(record,subject=corrected)],persist=False)
                batch.atomic(plan_file,plans)
            organizer.run(plans)
            state.update(dirty=True,last_success=cloud.now());state['held'].pop(sid,None)
            refresh(state);report(state)
        except Exception as e:
            reason=(str(e)[:240] or type(e).__name__) if isinstance(e,(AssertionError,ValueError)) else type(e).__name__
            if sid=='822':reason='当前种子为Alternative/Progressive续作，缺少2000年本篇，保留待核对'
            if sid=='1424':reason='当前种子为第二季及电影合集，缺少目标第一季，保留待核对'
            state['held'][sid]={'title':name,'reason':reason,'retry_after':time.time()+3600}
            state['activity']='暂缓该条目并保留所有文件，继续其他作品';report(state)
    refresh(state);state['activity']='等待下一部资源完成';report(state)

def run(once=False):
    import msvcrt
    lock=(batch.HERE/'library-watch.lock').open('a+b');lock.write(b'0');lock.flush();lock.seek(0)
    try:msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
    except OSError:return
    q=cloud.CloudQueue();state=read(WATCH,{'held':{},'dirty':True})
    while not STOP.exists():
        try:cycle(q,state)
        except Exception as e:
            state['activity']='接口暂不可用，稍后重查';state['last_error_type']=type(e).__name__;report(state)
        if once:return
        time.sleep(60)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--once',action='store_true');a=p.parse_args();run(a.once)
