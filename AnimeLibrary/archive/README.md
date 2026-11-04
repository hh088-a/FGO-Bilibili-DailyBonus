# 核心源码归档

这些文件来自本机运行基线，并做了报告路径、云端账号标识和模块加载路径脱敏。没有将此次整理覆盖到正在工作的部署目录。

|文件|职责|
|---|---|
|`runtime/batch.py`|目录生成、来源候选、种子文件选择、qB 调度、分块、上传与云端核验|
|`runtime/cloud_queue.py`|115 云端任务、名额、去重、额度停止与状态报告|
|`runtime/library_watch.py`|观察完成资源、补源批次与整理器衔接|
|`runtime/organize_115.py`|云端枚举、创建目录、移动、重命名、身份记录的基础操作|
|`runtime/organize_cloud_batch.py`|整理计划、影片/集数/字幕分类、前后完整性核验|
|`runtime/jellyfin_local.py`|本机凭据解密、短会话 API 调用与退出|
|`runtime/library_completeness.py`|基于本机整理清单统计可确认的收藏完整性|
|`runtime/audit_subtitle_tracks.py`|媒体库字幕轨道与外部字幕核对|
|`runtime/http.ps1`|目录与来源元数据 HTTP 请求辅助|
|`runtime/Start-Batch.ps1`|已部署机器的本地任务启动入口|
|`runtime/Start-CloudQueue.ps1`|整理与云队列启动，尊重额度停止锁|
|`runtime/Pause-Batch.ps1`|停止调度和脚本管理的 qB 下载，保留一致状态|
|`runtime/Refresh-IfIdle.ps1`|空闲时刷新媒体库|

`organize_115.py` 的命令行入口仍包含首批作品的一次性组织规则；`cloud_queue.py`、`library_watch.py`、`organize_cloud_batch.py` 是批量流程。不要把有历史专用入口的文件误认为适用于任意目录的无配置工具。

这些脚本可能创建任务、移动/重命名云文件，以及在核验后清理管理范围内的本地副本。部署需要先阅读 [恢复说明](../docs/setup-and-recovery.md)，准备原生产账本和凭据。`tests` 中使用桩与临时目录，不对真实服务执行这些操作。

初期采集器、逐次换源/字幕修复/人工审阅的一次性脚本通过总结保留其处理规则，未原样发布；它们往往引用私人资源清单、历史状态和绝对路径。归档保留最终核心实现及有意义的回归，避免把一次性补丁当成可重复执行的安装步骤。

`docs/source-manifest.json` 记录核心文件的原始与归档 SHA256 及是否经过适配，供本机对照；不包含原运行数据、账号或目录清单。
