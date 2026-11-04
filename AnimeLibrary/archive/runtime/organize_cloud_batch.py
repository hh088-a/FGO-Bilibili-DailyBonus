"""Plan, move, rename, and verify completed 115 releases without video downloads."""
import argparse
import collections
import json
import re
from pathlib import PurePosixPath as P

import organize_115 as base
batch=base.batch
FOLDER=batch.OUT/'115批量整理清单'
PLAN=batch.OUT/'115批量整理计划.json'
STATE=batch.DATA/'cloud-organized.json'
VIDEO={'.mkv','.mp4','.avi','.m2ts'}
SUBS={'.ass','.srt','.ssa','.idx','.sub'}
TV_FOLDERS={}
TV_NAMES={}
TV_START_YEARS={}

def clean(s):return re.sub(r'[<>:"/\\|?*]','_',s).rstrip(' .')
def label(s):return s.get('name_cn') or s['name']
def batch_key(s):return str(s.get('_batch_key',s['id']))

def extra(item,container):
    parts=P(item['path'].removeprefix(container+'/')).parts
    # The first component is the original release wrapper and may mention SPs
    # or movies in its collection description. Only inspect inner directories.
    directories=[x.casefold() for x in parts[1:-1]]
    if any(x in {'preview','previews','短剧','特别动画','图集'} for x in directories):return True
    if re.search(r'\bPreview\b|\[SP Anime\]|\[After Broadcasting Short Drama\]',item['name'],re.I):return True
    if any(re.search(r'^(?:ed|op)$|^(?:sp|sps|specials|bonus|extras|cds|music|scans|menus?|pv|ncop|nced|特典|映像特典|原画稿|台本|图集)',x) for x in directories):return True
    if re.search(r'\s(?:NCOP|NCED|PV\d*|CM|Menu)\b',item['name'],re.I):return True
    # Match explicit release tags, not language codes inside e.g. Sub(...,SP,...).
    return bool(re.search(r'(?:^|\[| - )(?:tokuten[-_ ]?\d*|extra[-_ ]?\d*|ncop\d*|nced\d*|pv\d*|cm\d*|sp(?:[-_ ]?\d+)?|menu\w*|bd_menu|bdcm|interviews?|live|work_world_file|tachikoma_na_hibi)(?:\]|\b)',item['name'],re.I))

def episode(name,season):
    m=re.search(r'\bS(\d{1,2})E(\d{1,3})\b',name,re.I)
    if m:return int(m[1]),int(m[2])
    for pattern in (r'(?:^|\])\s*FLCL[ _-]+(\d{1,2})\b',r'第\s*(\d{1,3})\s*[話话集]',r'\[(\d{1,3})(?:_?v\d|_?END)?\]',r'[#＃](\d{1,3})\b',r' - (\d{1,3})(?:v\d)?(?:\s|\[|\.(?!\d))',r'\s(\d{2,3})\s*(?=[\[(](?:BD|WEB|1080))'):
        m=re.search(pattern,name,re.I)
        if m:return season,int(m[1])
    return None

def subtitle_suffix(suffix):
    lower=suffix.casefold().strip('.')
    bilingual=any(x in lower for x in ('jp','jap','双语'))
    if any(x in lower for x in ('tvb','粵','粤')):return '.yue.粤语字幕'
    if any(x in lower for x in ('tc','cht','big5','繁')):return '.zh-Hant'+('.中日双语' if bilingual else '')
    if any(x in lower for x in ('sc','chs','gb','简')):return '.zh-Hans'+('.中日双语' if bilingual else '')+'.default'
    if lower in ('ja','jpn','jp','jap'):return '.ja'
    if lower in ('en','eng','english'):return '.en'
    return '.und.'+clean(lower or '字幕')

def tv_target(name,year,tmdb,season,ep):
    name=TV_NAMES.get(str(tmdb),name);year=TV_START_YEARS.get(str(tmdb),year)
    folder=TV_FOLDERS.get(str(tmdb),clean(name)+(f' ({year})' if year else '')+f' [tmdbid-{tmdb}]')
    return '/剧集/'+folder+f'/Season {season:02d}/'+clean(name)+f' - S{season:02d}E{ep:02d}'

def movie_target(name,year,tmdb):
    stem=clean(name)+f' ({year})'
    return '/电影/'+stem+(f' [tmdbid-{tmdb}]' if tmdb else '')+'/'+stem

def classify(s,v,container):
    name=v['name'];sid=s['id']
    if sid==233:
        chapter=re.search(r'\[(0[1-8])\]',name)
        if not chapter:return None
        config=[('第一章 俯瞰风景',2007,23150),('第二章 杀人考察（前）',2007,23151),('第三章 痛觉残留',2008,23153),('第四章 伽蓝之洞',2008,23154),('第五章 矛盾螺旋',2008,23155),('第六章 忘却录音',2008,23166),('第七章 杀人考察（后）',2009,23167),('终章',2011,None)]
        title,year,tmdb=config[int(chapter[1])-1]
        return movie_target('空之境界 '+title,year,tmdb),'movie'
    if sid==43581:
        if '[Mirai Fukuin - Extra Chorus]' in name:return movie_target('空之境界 未来福音 Extra Chorus',2013,253987),'movie'
        if '[Mirai Fukuin]' in name:return movie_target('空之境界 未来福音',2013,212156),'movie'
        return None
    if extra(v,container):return None
    if sid==1728:
        ep=episode(name,1)
        if 'Tsuiokuhen' in name and ep:return tv_target('浪客剑心 追忆篇',1999,317885,*ep),'episode'
        if 'Seisouhen' in name and ep:return tv_target('浪客剑心 星霜篇',2001,313336,*ep),'episode'
        if 'Ishin Shishi e no Requiem' in name:return movie_target('浪客剑心 维新志士的镇魂歌',1997,39977),'movie'
        return None
    if sid==9622 and 'A New Translation' in name:
        if 'Translation III' in name:return movie_target('机动战士Z高达Ⅲ 星辰的鼓动是爱',2006,30606),'movie'
        if 'Translation II' in name:return movie_target('机动战士Z高达Ⅱ 恋人们',2005,19257),'movie'
        return movie_target('机动战士Z高达Ⅰ 星之继承者',2005,19256),'movie'
    if sid==1453 and 'Adolescence Mokushiroku' in name:return movie_target('少女革命 思春期默示录',1999,19738),'movie'
    if sid==425587 and 'Memories' in name:
        ep=episode(name,0)
        if ep and 1<=ep[1]<=4:return tv_target('我的英雄学院',2016,65930,0,ep[1]+12),'episode'
        return None
    if sid==453140:
        parsed=episode(name,3)
        if parsed and parsed[1]==0:return None  # Retain the recap in the original archive.
    if sid==492352 and s.get('_review_movie_parts')==2:
        parsed=episode(name,0)
        if parsed and 1<=parsed[1]<=2:
            return movie_target(label(s),s['date'][:4],1287324)+' - part'+str(parsed[1]),'movie'
        return None
    mapping=s.get('tmdb') or ''
    year=(s.get('date') or '')[:4]
    if mapping.startswith('movie/'):
        return movie_target(label(s),year,mapping.split('/')[1]),'movie'
    if mapping.startswith('tv/'):
        m=re.search(r'/season/(\d+)',mapping);season=int(m[1]) if m else 1
        parsed=episode(name,season)
        show=label(s)
        if m:show=re.sub(r'\s*(?:第[一二三四五六七八九十\d]+(?:季|部分)|续章)\s*$','',show);year=''
        if not parsed:
            special=re.search(r'\b(OVA|OAD)(?:[-_ ]?(\d+))?\b',name,re.I)
            if not special:return None
            tmdb=mapping.split('/')[1];show=TV_NAMES.get(tmdb,show);year=TV_START_YEARS.get(tmdb,year)
            folder=TV_FOLDERS.get(tmdb,clean(show)+(f' ({year})' if year else '')+f' [tmdbid-{tmdb}]')
            return '/剧集/'+folder+'/Season 00/'+clean(show)+' - '+special[0].strip(),'episode'
        if s.get('_review_episode_offset') is not None:parsed=(parsed[0],parsed[1]+int(s['_review_episode_offset']))
        return tv_target(show,year,mapping.split('/')[1],*parsed),'episode'
    return None

def build(records=None,persist=True):
    if records is None:records=json.loads((batch.OUT/'115本次整理批次.json').read_text(encoding='utf8'))
    plans=[];targets=set()
    for record in records:
        s=record['subject'];container=record['tasks'][0]['destination']
        items=json.loads((FOLDER/(batch_key(s)+'.before.json')).read_text(encoding='utf8'))
        files=[x for x in items if not x['dir']]
        assert all(x['id'] and len(x['sha1'])==40 for x in files),'Missing authoritative cloud hashes'
        if (s.get('tmdb') or '').startswith('tv/'):
            assert 0<int(s.get('eps') or 0) and (int(s['eps'])<=200 or s.get('_review_long')),'Long-running series needs explicit season/episode mapping'
        transfers=[];video_pairs=[]
        for v in files:
            if P(v['name']).suffix.lower() not in VIDEO:continue
            result=classify(s,v,container)
            if result:
                stem,kind=result
                dest=stem+P(v['name']).suffix.lower()
                assert dest not in targets,'Ambiguous editions: '+dest
                targets.add(dest);transfers.append(dict(v,destination=dest,kind=kind));video_pairs.append((v,stem))
        # Validate all expected regular episodes before performing any mutations.
        expected=s.get('eps')
        missing_numbers=[]
        regular=[x for x in transfers if x['kind']=='episode' and '/Season 00/' not in x['destination']]
        if s['id']!=1728 and (s.get('tmdb') or '').startswith('tv/'):
            assert 0<len(regular)<=expected,(s['id'],'episode count',len(regular),expected)
            numbers=sorted(int(re.search(r'E(\d+)\.',x['destination'])[1]) for x in regular)
            explicit_start=re.search(r'/episode/(\d+)',s.get('tmdb') or '')
            start=int(explicit_start[1]) if explicit_start else 1
            if start>1 and numbers[0]==1:
                offset=start-1
                for x in regular:
                    x['destination']=re.sub(r'E(\d+)(?=\.)',lambda v:f'E{int(v[1])+offset:02d}',x['destination'])
                numbers=[n+offset for n in numbers]
                # Propagate numbering to subtitle pairing below.
                corrected={x['id']:str(P(x['destination']).with_suffix('')) for x in regular}
                video_pairs=[(v,corrected.get(v['id'],stem)) for v,stem in video_pairs]
            if s.get('_review_allow_gaps'):
                assert len(numbers)==len(set(numbers)) and all(start<=n<start+expected for n in numbers),(s['id'],'reviewed episode bounds',numbers)
            else:assert numbers==list(range(start,start+len(regular))),(s['id'],'episode sequence',numbers)
            missing_numbers=sorted(set(range(start,start+expected))-set(numbers))
        if (s.get('tmdb') or '').startswith('movie/'):
            movies=[x for x in transfers if x['kind']=='movie']
            expected_parts=int(s.get('_review_movie_parts',1))
            assert len(movies)==expected_parts,(s['id'],'Ambiguous main movie')
            if expected_parts>1:
                parts=[re.fullmatch(r'(.+) - part(\d+)\.[^.]+',x['destination']) for x in movies]
                assert all(parts) and len({m[1] for m in parts})==1 and sorted(int(m[2]) for m in parts)==list(range(1,expected_parts+1)),'Incomplete or ambiguous movie parts'
        used=set()
        for v,stem in video_pairs:
            video_stem=P(v['name']).stem
            paired=[x for x in files if P(x['name']).suffix.lower() in SUBS and x['name'].startswith(video_stem+'.')]
            for sub in paired:
                assert sub['id'] not in used,'Subtitle matches multiple videos'
                used.add(sub['id'])
                suffix=sub['name'][len(video_stem):-len(P(sub['name']).suffix)]
                dest=stem+subtitle_suffix(suffix)+P(sub['name']).suffix.lower()
                assert dest not in targets,'Subtitle language/version collision: '+dest
                targets.add(dest);transfers.append(dict(sub,destination=dest,kind='subtitle'))
        assert transfers,(s['id'],'No recognized main content')
        plans.append({'subject_id':s['id'],'state_key':batch_key(s),'title':label(s),'source':container,'archive':'/归档/资料/'+P(container).name,
                      'task_hashes':[t['hash'] for t in record['tasks']],'files_before':len(files),'transfers':transfers,
                      'declared_episodes':s.get('eps'),'regular_episodes':len(regular),'missing_numbers':missing_numbers})
    if persist:batch.atomic(PLAN,plans)
    print('PLANNED',len(plans),'releases;',dict(collections.Counter(x['kind'] for p in plans for x in p['transfers'])),flush=True)
    return plans

class Bulk(base.Organizer):
    def __init__(self):
        self.stub,self.pb,self.md=batch.cloud_connection();self.directory_cache=set()
    def record(self,action,source,destination,identity):
        with (batch.OUT/'115批量整理操作.jsonl').open('a',encoding='utf8') as out:
            out.write(json.dumps({'action':action,'source':source,'destination':destination,'id':identity},ensure_ascii=False)+'\n')
    def ensure_dir(self,path):
        if path in self.directory_cache or path=='/':return
        self.ensure_dir(str(P(path).parent))
        super().ensure_dir(path);self.directory_cache.add(path)
    def transfer(self,changes):
        # Group renames by original directory, then server-side moves by destination.
        all_destinations=collections.defaultdict(list)
        for x in changes:all_destinations[str(P(x['destination']).parent)].append(x)
        for parent,files in all_destinations.items():
            self.ensure_dir(parent)
            siblings={f.name:f for f in self.ls(parent)}
            for x in files:
                existing=siblings.get(P(x['destination']).name)
                if existing:assert existing.id==x['id'] and existing.size==x['size'] and existing.fileHashes.get(2,'')==x['sha1'],'Destination collision or checksum mismatch'
        by_parent=collections.defaultdict(list)
        for x in changes:by_parent[str(P(x['path']).parent)].append(x)
        for parent,files in by_parent.items():
            pending=[];destination_lists={}
            for x in files:
                dest_parent=str(P(x['destination']).parent);self.ensure_dir(dest_parent)
                if dest_parent not in destination_lists:destination_lists[dest_parent]={f.name:f for f in self.ls(dest_parent)}
                dest=destination_lists[dest_parent].get(P(x['destination']).name)
                if dest:
                    assert dest.id==x['id'] and dest.size==x['size'] and dest.fileHashes.get(2,'')==x['sha1'],'Destination collision or checksum mismatch'
                else:pending.append(x)
            if not pending:continue
            self.rename_batch(parent,[(x['name'],P(x['destination']).name,x['id']) for x in pending])
            grouped=collections.defaultdict(list)
            for x in pending:grouped[str(P(x['destination']).parent)].append(x)
            for dest_parent,group in grouped.items():
                for index in range(0,len(group),20):
                    chunk=group[index:index+20]
                    r=self.stub.MoveFile(self.pb.MoveFileRequest(theFilePaths=[parent+'/'+P(x['destination']).name for x in chunk],destPath=dest_parent,conflictPolicy=self.pb.MoveFileRequest.Skip),metadata=self.md,timeout=60)
                    if not r.success:raise RuntimeError('Cloud move failed: '+r.errorMessage)
                    for x in chunk:self.record('move',x['path'],x['destination'],x['id'])

def verify_originals(original,final,archive):
    unchanged={k:v for k,v in final.items() if k in original}
    assert unchanged==original,'Original file missing or ID/size/SHA1 changed during organization'
    # Media scanners can create NFO sidecars while folders are being moved.
    # Their presence does not change an original video, subtitle or archive.
    additions=set(final)-set(original)
    metadata={f['id'] for f in archive if not f['dir'] and P(f['name']).suffix.lower()=='.nfo' and len(f['sha1'])==40}
    assert additions<=metadata,'Unexpected non-metadata file appeared during organization'
    return len(additions)

def run(plans=None):
    if plans is None:plans=json.loads(PLAN.read_text(encoding='utf8')) if PLAN.exists() else build()
    state=json.loads(STATE.read_text(encoding='utf8')) if STATE.exists() else {}
    o=Bulk()
    for plan in plans:
        sid=str(plan.get('state_key',plan['subject_id']))
        if state.get(sid,{}).get('status')=='verified':continue
        before=json.loads((FOLDER/(sid+'.before.json')).read_text(encoding='utf8'))
        original={x['id']:(x['size'],x['sha1']) for x in before if not x['dir']}
        assert len(original)==plan['files_before']
        archived=next((f for f in o.ls('/归档/资料') if f.name==P(plan['archive']).name),None) if 'archive_started' in state.get(sid,{}) else None
        if not archived:
            # The source is only a fully finished cloud batch; uploader staging is excluded.
            o.transfer(plan['transfers'])
            o.ensure_dir('/归档/资料')
            folder=next((f for f in o.ls(str(P(plan['source']).parent)) if f.name==P(plan['source']).name),None)
            if folder:
                state[sid]={'status':'verifying','archive_started':True};batch.atomic(STATE,state)
                o.move(plan['source'],'/归档/资料',folder.id)
        after=o.tree(plan['archive'])
        final={x['id']:(x['size'],x['sha1']) for x in after if not x['dir']}
        for parent in {str(P(x['destination']).parent) for x in plan['transfers']}:
            for f in o.ls(parent):
                if not f.isDirectory and f.id in original:
                    final[f.id]=(f.size,f.fileHashes.get(2,''))
        generated_metadata=verify_originals(original,final,after)
        for x in plan['transfers']:
            assert final.get(x['id'])==(x['size'],x['sha1'])
        batch.atomic(FOLDER/(sid+'.after.json'),{'archive':after,'library_files':plan['transfers']})
        state[sid]={'status':'verified','title':plan['title'],'archive':plan['archive'],'files_verified':len(original),
                    'episodes':sum(x['kind']=='episode' for x in plan['transfers']),'movies':len({re.sub(r' - part\d+(?=\.[^.]+$)','',x['destination']) for x in plan['transfers'] if x['kind']=='movie'}),
                    'subtitles':sum(x['kind']=='subtitle' for x in plan['transfers']),'task_hashes':plan['task_hashes'],
                    'generated_metadata_files':generated_metadata,'regular_episodes':plan.get('regular_episodes'),'declared_episodes':plan.get('declared_episodes'),
                    'missing_numbers':plan.get('missing_numbers',[])}
        batch.atomic(STATE,state)
        print('VERIFIED',plan['title'],len(original),'files;',state[sid]['episodes'],'episodes;',state[sid]['movies'],'movies',flush=True)
    counts=collections.Counter()
    for s in state.values():
        if s.get('status')=='verified':
            for k in ('episodes','movies','subtitles','files_verified'):counts[k]+=s[k]
    lines=['# 115本批整理结果','',f'本批已核验{len(state)}个资源合集：{counts["episodes"]}集/OVA、{counts["movies"]}部电影、{counts["subtitles"]}份外挂字幕。',
           f'共{counts["files_verified"]}个原有文件的云端ID、大小和SHA1保持一致。没有下载影音文件到电脑，没有删除云端文件。','',
           '剧集：X:\\动漫\\剧集；电影：X:\\动漫\\电影；原声、特典、字体包和原目录资料：X:\\动漫\\归档\\资料。',
           '已经有明确季集标记的特别篇保留在Season 00；未确认编号的特典保留在资料归档。',
           '字幕与对应视频同名，简体字幕标为默认；内嵌字幕的视频保持内容不变。','',
           '|资源合集|集/OVA|电影|外挂字幕|核验文件|','|---|---:|---:|---:|---:|']
    for s in state.values():
        if s.get('status')=='verified':lines.append(f'|{s["title"].replace("|","/")}|{s["episodes"]}|{s["movies"]}|{s["subtitles"]}|{s["files_verified"]}|')
    lines+=['','命名规则参考：[Jellyfin剧集](https://jellyfin.org/docs/general/server/media/shows/)及[电影](https://jellyfin.org/docs/general/server/media/movies/)。']
    (batch.OUT/'115本批整理结果.md').write_text('\n'.join(lines)+'\n',encoding='utf8')
    print('COMPLETE',dict(counts),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('action',choices=['plan','run']);a=p.parse_args()
    build() if a.action=='plan' else run()
