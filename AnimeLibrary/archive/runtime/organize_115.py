"""Organize a completed 115 release using cloud metadata operations only."""
import collections
import json
import os
import re
import sys
from pathlib import Path, PurePosixPath as P


import batch

SHOW='我的青春恋爱物语果然有问题 (2013) [tmdbid-65676]'
ROOT='/剧集/'+SHOW
OLD='/待整理/[VCB-Studio] Oregairu'
SNAP=batch.OUT/'115整理前清单.json'
JOURNAL=batch.OUT/'115整理操作记录.json'
MANIFEST=batch.OUT/'115整理后清单.json'

class Organizer:
    def __init__(self):
        self.stub,self.pb,self.md=batch.cloud_connection()
        self.journal=json.loads(JOURNAL.read_text(encoding='utf8')) if JOURNAL.exists() else []

    def ls(self,path):
        result=[]
        for page in self.stub.GetSubFiles(self.pb.ListSubFileRequest(path=path,forceRefresh=True),metadata=self.md,timeout=30):
            result.extend(page.subFiles)
        return result

    def record(self,action,source,destination,identity):
        self.journal.append({'action':action,'source':source,'destination':destination,'id':identity})
        batch.atomic(JOURNAL,self.journal)

    def ensure_dir(self,path):
        parent=str(P(path).parent)
        match=next((f for f in self.ls(parent) if f.name==P(path).name),None)
        if match:
            assert match.isDirectory,path
            return
        r=self.stub.CreateFolder(self.pb.CreateFolderRequest(parentPath=parent,folderName=P(path).name),metadata=self.md,timeout=30)
        if not r.result.success:raise RuntimeError('CreateFolder: '+r.result.errorMessage)
        self.record('mkdir','',path,r.folderCreated.id)

    def rename(self,source,destination,identity):
        assert P(source).parent==P(destination).parent
        siblings=self.ls(str(P(source).parent))
        target=next((f for f in siblings if f.name==P(destination).name),None)
        if target:
            assert target.id==identity,'Destination collision: '+destination
            return
        original=next((f for f in siblings if f.name==P(source).name),None)
        assert original and original.id==identity,'Unexpected source: '+source
        r=self.stub.RenameFile(self.pb.RenameFileRequest(theFilePath=source,newName=P(destination).name),metadata=self.md,timeout=30)
        if not r.success:raise RuntimeError('Rename: '+r.errorMessage)
        self.record('rename',source,destination,identity)

    def move(self,source,parent,identity):
        destination=parent+'/'+P(source).name
        target=next((f for f in self.ls(parent) if f.name==P(source).name),None)
        if target:
            assert target.id==identity,'Destination collision: '+destination
            return
        original=next((f for f in self.ls(str(P(source).parent)) if f.name==P(source).name),None)
        assert original and original.id==identity,'Unexpected move source: '+source
        r=self.stub.MoveFile(self.pb.MoveFileRequest(theFilePaths=[source],destPath=parent,conflictPolicy=self.pb.MoveFileRequest.Skip),metadata=self.md,timeout=45)
        if not r.success:raise RuntimeError('Move: '+r.errorMessage)
        self.record('move',source,destination,identity)

    def rename_batch(self,path,changes):
        siblings={f.name:f for f in self.ls(path)}
        pending=[]
        for old,new,identity in changes:
            if old==new:continue
            if new in siblings:
                assert siblings[new].id==identity,'Rename collision: '+new
                continue
            assert old in siblings and siblings[old].id==identity,'Missing original: '+old
            pending.append((old,new,identity))
        for i in range(0,len(pending),20):
            group=pending[i:i+20]
            r=self.stub.RenameFiles(self.pb.RenameFilesRequest(renameFiles=[self.pb.RenameFileRequest(theFilePath=path+'/'+old,newName=new) for old,new,_ in group]),metadata=self.md,timeout=45)
            if not r.success:raise RuntimeError('Batch rename: '+r.errorMessage)
            for old,new,identity in group:self.record('rename',path+'/'+old,path+'/'+new,identity)

    def tree(self,root):
        queue=collections.deque([root]);found=[]
        while queue:
            for f in self.ls(queue.popleft()):
                found.append({'path':f.fullPathName,'name':f.name,'id':f.id,'dir':f.isDirectory,'size':f.size,'sha1':f.fileHashes.get(2,'')})
                if f.isDirectory:queue.append(f.fullPathName)
                assert len(found)<2500,'Unexpectedly large tree'
        return found

def season_number(name):
    return 3 if '. Kan ' in name else 2 if '. Zoku ' in name else 1

def new_name(item,season):
    name=item['name'];ext=P(name).suffix
    if '[Fonts]' in name:return '字幕字体'+ext
    match=re.search(r'\[(\d{2}|OVA)\]',name)
    if not match:return name
    code=match[1]
    stem=('我的青春恋爱物语果然有问题 - '+f'S{season:02d}E{int(code):02d} - 1080p') if code!='OVA' else ('我的青春恋爱物语果然有问题 - '+f'第{season}季 OVA')
    if ext.lower()=='.ass':
        suffix=name.rsplit('].',1)[-1].removesuffix('.ass')
        if suffix in ('Chs&Jap','JPSC'):stem+='.zh-Hans.中日双语.default'
        elif suffix in ('Cht&Jap','JPTC'):stem+='.zh-Hant.中日双语'
        elif suffix=='Jap':stem+='.ja'
        elif suffix=='SC':stem+='.zh-Hans.default'
        elif suffix=='TC':stem+='.zh-Hant'
        else:raise RuntimeError('Unknown subtitle language: '+name)
    return stem+ext

def run():
    before=json.loads(SNAP.read_text(encoding='utf8'))
    roots=[x for x in before if x['dir'] and str(P(x['path']).parent)==OLD]
    assert len(roots)==3
    expected={x['id']:(x['size'],x['sha1']) for x in before if not x['dir']}
    assert len(expected)==582 and all(sha for _,sha in expected.values())
    o=Organizer()
    completed=[f for f in o.stub.ListOfflineFilesByPath(o.pb.FileRequest(path='/待整理'),metadata=o.md,timeout=20).offlineFiles if f.infoHash=='c1b386df63f5fa7619f7a1fa9be1873fcb84f8a5']
    assert len(completed)==1 and completed[0].status==o.pb.OFFLINE_FINISHED
    root_id=completed[0].fileId
    root_in_tv=next((f for f in o.ls('/剧集') if f.name==SHOW),None)
    if root_in_tv:assert root_in_tv.id==root_id
    else:
        o.rename(OLD,'/待整理/'+SHOW,root_id)
        o.move('/待整理/'+SHOW,'/剧集',root_id)
    o.ensure_dir(ROOT+'/Season 00')
    for season_root in sorted(roots,key=lambda x:season_number(x['name'])):
        season=season_number(season_root['name'])
        destination=ROOT+f'/Season {season:02d}'
        o.rename(ROOT+'/'+season_root['name'],destination,season_root['id'])
        o.ensure_dir(destination+'/extras')
        direct=[x for x in before if str(P(x['path']).parent)==season_root['path']]
        # Keep original soundtrack, booklet scans, and promotional material intact.
        for item in direct:
            if item['dir']:
                o.move(destination+'/'+item['name'],destination+'/extras',item['id'])
        changes=[(x['name'],new_name(x,season),x['id']) for x in direct if not x['dir']]
        assert len({b for _,b,_ in changes})==len(changes)
        o.rename_batch(destination,changes)
        for item in direct:
            if not item['dir'] and '[OVA]' in item['name']:
                o.move(destination+'/'+new_name(item,season),ROOT+'/Season 00',item['id'])
        print('organized season',season,flush=True)
    after=o.tree(ROOT)
    actual={x['id']:(x['size'],x['sha1']) for x in after if not x['dir']}
    assert actual==expected,'File ID/size/SHA1 manifest mismatch; no deletion performed'
    videos=collections.Counter()
    for item in after:
        if not item['dir'] and item['name'].endswith('.mkv'):
            parent=str(P(item['path']).parent)
            if re.fullmatch(re.escape(ROOT)+r'/Season \d{2}',parent):videos[P(parent).name]+=1
    assert videos=={'Season 01':13,'Season 02':13,'Season 03':12,'Season 00':3},videos
    batch.atomic(MANIFEST,after)
    report=['# 115动漫整理结果','',f'位置：X:\\动漫\\剧集\\{SHOW}','',
            '正片：第一季13集、第二季13集、第三季12集；OVA 3部放入Season 00，保留描述名称，不猜测资料库特别篇编号。',
            '简体/繁体/日文字幕与视频同名配对；简体字幕设为默认。原声、扫图、宣传片及特典保存在各季extras目录，字体包保留在各季目录。',
            '整理前后582个文件的云端ID、大小、SHA1逐一一致。操作只在115服务器上移动和改名，没有下载影音到本地。',
            '批量收藏目录仍有正在上传的数据，保留原路径；完成云端核验后再归档。','',
            '[命名规则依据：Jellyfin官方文档](https://jellyfin.org/docs/general/server/media/shows/)','',
            '操作记录：115整理操作记录.json；原始清单：115整理前清单.json；整理后清单：115整理后清单.json。']
    (batch.OUT/'115整理结果.md').write_text('\n'.join(report)+'\n',encoding='utf8')
    print('verified',len(expected),'files;',dict(videos),flush=True)

if __name__=='__main__':run()
