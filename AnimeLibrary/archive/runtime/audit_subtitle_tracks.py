import sys,json,collections,urllib.parse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parent))
from jellyfin_local import session,batch

def normalize(path):return path.replace('\\','/').removeprefix('X:/动漫').casefold()

def run():
    items={}
    with session() as (call,user):
        offset=0
        while True:
            query=urllib.parse.urlencode(dict(Recursive='true',IncludeItemTypes='Movie,Episode',Fields='Path,MediaStreams',StartIndex=offset,Limit=500))
            data=call('/Items?'+query)
            for x in data['Items']:items[normalize(x.get('Path',''))]=x
            offset+=len(data['Items'])
            if not data['Items'] or offset>=data['TotalRecordCount']:break
    packs=json.loads((batch.OUT/'同源字幕待配对.json').read_text(encoding='utf8'));cases=[]
    for pack in packs:
        for video in pack['videos']:
            if video.get('kind') not in ('episode','movie'):continue
            item=items.get(normalize(video['destination']));status='pending_library_index'
            if item:
                subs=[x for x in item.get('MediaStreams',[]) if x.get('Type')=='Subtitle']
                if any(x.get('Language','').casefold() in ('chi','zho','zh','chs','cht','cmn') or any(k in x.get('DisplayTitle','').casefold() for k in ('chinese','简','繁','chs','cht','中文')) for x in subs):status='chinese_track_present'
                elif subs and any(not x.get('Language') or x.get('Language')=='und' for x in subs):status='subtitle_language_needs_review'
                elif any(x.get('Type')=='Video' for x in item.get('MediaStreams',[])):status='missing_chinese_subtitle'
                else:status='pending_media_probe'
            cases.append(dict(key=pack['key'],title=pack['title'],package=pack['package'],video=video,jellyfin_id=item['Id'] if item else None,status=status))
    unique={x['video']['destination']:x for x in cases}
    provenance={}
    state=json.loads((batch.DATA/'cloud-organized.json').read_text(encoding='utf8'))
    for key,entry in state.items():
        if entry.get('status')!='verified':continue
        p=batch.OUT/'115批量整理清单'/(key+'.after.json')
        if not p.exists():continue
        for video in json.loads(p.read_text(encoding='utf8')).get('library_files',[]):
            provenance[normalize(video['destination'])]={'key':key,'title':entry.get('title'),'video':video}
    general=[]
    for path,item in items.items():
        streams=item.get('MediaStreams',[]);subs=[x for x in streams if x.get('Type')=='Subtitle']
        if any(x.get('Language','').casefold().startswith(('zh','chi','zho','cmn')) or any(k in x.get('DisplayTitle','').casefold() for k in ('chinese','简','繁','chs','cht','中文')) for x in subs):continue
        info=provenance.get(path,{})
        if not any(x.get('Type')=='Video' for x in streams):status='pending_media_probe'
        elif subs and any(not x.get('Language') or x.get('Language')=='und' for x in subs):status='subtitle_language_needs_review'
        elif path.endswith('.mp4'):status='possible_burned_in_subtitles'
        else:status='missing_chinese_track_needs_review'
        if info.get('key','').split('.')[0]=='354700' and __import__('re').search(r'E(?:35|178)\.',path):status='confirmed_silent_episode'
        general.append(dict(path=item.get('Path'),jellyfin_id=item['Id'],status=status,**info))
    summary=dict(indexed_videos=len(items),with_subtitle_packages=len(unique),states=dict(collections.Counter(x['status'] for x in unique.values())),all_video_flags=dict(collections.Counter(x['status'] for x in general)))
    batch.atomic(batch.OUT/'媒体库字幕检查.json',dict(summary=summary,cases=cases,all_video_flags=general))
    print(json.dumps(summary,ensure_ascii=False));print('MISSING',[(x['title'],x['video']['name']) for x in unique.values() if x['status']=='missing_chinese_subtitle'][:15])

if __name__=='__main__':run()
