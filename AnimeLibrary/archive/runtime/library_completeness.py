import os,sys,json,re,collections
from pathlib import Path,PurePosixPath as P

import batch

def run():
    catalog=json.loads((batch.DATA/'catalog.json').read_text(encoding='utf8'))
    organized=json.loads((batch.DATA/'cloud-organized.json').read_text(encoding='utf8'))
    plans=[];missing_plans=[];subject_paths=collections.defaultdict(set)
    for key,state in organized.items():
        if state.get('status')!='verified':continue
        paths=[batch.DATA/folder/(key+'.json') for folder in ('manual-plans-20261104','manual-plans','organize-plans')]
        after=batch.OUT/'115批量整理清单'/(key+'.after.json')
        path=next((p for p in paths if p.exists()),None)
        if after.exists():
            value=json.loads(after.read_text(encoding='utf8'))
            items=[{'subject_id':int(key.split('.')[0]),'transfers':value['library_files']}]
        elif path:
            value=json.loads(path.read_text(encoding='utf8'));items=value if isinstance(value,list) else [value]
        else:missing_plans.append(key);continue
        for plan in items:
            plans.append(plan)
            for x in plan.get('transfers',[]):
                if P(x['destination']).suffix.lower() in ('.mkv','.mp4','.avi','.m2ts'):subject_paths[plan['subject_id']].add(x['destination'])
    tv=collections.defaultdict(set);bgm=collections.defaultdict(set);movies=set();paths=set()
    for values in subject_paths.values():paths.update(values)
    for path in paths:
        provider=re.search(r'\[tmdbid-(\d+)\]',path);custom=re.search(r'\[bgmid-(\d+)\]',path);ep=re.search(r' - S(\d+)E(\d+)',path)
        if path.startswith('/电影/') and provider:movies.add(int(provider[1]))
        if ep:
            season,n=map(int,ep.groups())
            if provider:tv[(int(provider[1]),season)].add(n)
            if custom:bgm[int(custom[1])].add(n)
    rows=[]
    for s in catalog:
        sid=s['id'];mapping=s.get('tmdb') or '';expected=int(s.get('eps') or 0);present=set();wanted=set();status='not_in_library';method=''
        if sid in bgm:
            present=bgm[sid];wanted=set(range(1,expected+1));method='bgm_local_nfo'
        elif mapping.startswith('tv/'):
            tmdb=int(mapping.split('/')[1]);season=int(re.search(r'/season/(\d+)',mapping)[1]) if '/season/' in mapping else 1
            start=int(re.search(r'/episode/(\d+)',mapping)[1]) if '/episode/' in mapping else 1
            wanted=set(range(start,start+expected));present=tv.get((tmdb,season),set())&wanted if expected else tv.get((tmdb,season),set());method='tmdb_episode_map'
        elif mapping.startswith('movie/'):
            present={1} if int(mapping.split('/')[1]) in movies else set();wanted={1};method='tmdb_movie'
        elif subject_paths.get(sid):
            status='in_library_mapping_review';method='unmapped_verified_files'
        if method!='unmapped_verified_files':
            if not present:status='not_in_library'
            elif not wanted:status='in_library_unknown_total'
            elif wanted<=present:status='complete'
            else:status='partial'
        source=batch.DATA/'sources'/(str(sid)+'.json');source_status=json.loads(source.read_text(encoding='utf8')).get('status') if source.exists() else 'not_checked'
        rows.append(dict(id=sid,title=s.get('name_cn') or s['name'],date=s.get('date'),platform=s.get('platform'),expected=expected,present_count=len(present),missing=sorted(wanted-present),status=status,source_status=source_status,method=method,tmdb=mapping))
    counts=dict(collections.Counter(x['status'] for x in rows));source_counts=dict(collections.Counter(x['source_status'] for x in rows if x['status']=='not_in_library'))
    summary=dict(target_total=len(catalog),counts=counts,not_complete=len(catalog)-counts.get('complete',0),not_in_library_source_status=source_counts,verified_plans_missing=missing_plans,library_video_paths=len(paths))
    batch.atomic(batch.OUT/'动漫收藏完整性统计.json',dict(summary=summary,items=rows))
    print(json.dumps(summary,ensure_ascii=False),flush=True)
    print('PARTIAL',[(x['id'],x['title'],len(x['missing'])) for x in rows if x['status']=='partial'],flush=True)
    return rows,summary

if __name__=='__main__':run()
