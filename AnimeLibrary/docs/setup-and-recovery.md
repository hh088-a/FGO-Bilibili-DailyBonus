# 部署前提与恢复

## 归档的用途

仓库保存核心逻辑、回归测试和工作记录。它不包含生产账本、来源清单、媒体、生成的协议客户端和凭据，也没有一键从全新机器恢复所有状态的安装器。不能仅靠此仓库判断云端哪些来源已提交或哪些本地副本可以清理。

## 环境基线

- Windows，Python 3.11；qBittorrent 5.3.0。
- CloudDrive2 已挂载 115 到 X 盘，本机 gRPC 接口和权限由用户配置。
- Jellyfin Server 12.4.0、Jellyfin Media Player 1.12.0。
- 可选的 PotPlayer 官方运行文件及 JavaScript Injector 4.1.0.0（Jellyfin 12 构建）。
- Python 依赖版本记录于 `requirements.txt`，来自本机已安装环境；新机器需确认包可用性与 CloudDrive protobuf 兼容性。

## 核心代码的脱敏差异

1. 原生产报告输出位置包含个人工作区绝对路径，归档改为相对于 `ROOT` 的 `reports`。
2. 云端账号标识改从 `ANIME_CLOUD_ACCOUNT_ID` 环境变量读取；未填写时调用额度/云任务接口会失败，不回退到原账号。
3. 删除指向本机正在运行模块的 import 路径注入；测试只导入仓库内的副本。
4. `archive/runtime/batch.py` 的 `HERE` 是模块目录、`ROOT` 是其父目录。部署时应复制到已准备好的 `AnimeLibrary\batch`，不要在源码归档目录直接启动生产工作。

核心脚本的目录生成截止日期和人工审核的作品映射作为历史快照保留。更新收藏时间范围、云路径前缀或上映身份规则需要单独审阅，不会随机器日期自动正确变化。

## 生产前置资料

- qB WebUI 登录信息，保存在本机 `config\qb.credential.xml`。
- Jellyfin 管理凭据，保存在本机 `config\admin.credential.xml`。
- CloudDrive 核验凭据，脚本读取 `config\cloud-readonly.credential.xml`。该文件名来自历史配置，实际权限以 CloudDrive 中授予的范围为准。
- 本机生成的 `clouddrive_pb2.py` 与 `clouddrive_pb2_grpc.py`，应由与所装 CloudDrive 服务匹配的官方协议定义生成，放到 `batch\generated`。不从未知二进制包获取这些代码。
- 生产 `catalog.json`、来源、任务账本、云队列账本、整理计划与停止标记的独立备份。

本地凭据以 Windows DPAPI/Export-Clixml 保存，通常绑定原 Windows 用户/机器。将加密 XML 搬到其他机器并不能保证可解密；新机器应由用户重新配置。核验只需查询权限，云端创建任务/目录/移动/重命名则需要对应写权限，不能把只读令牌描述为具有这些权限。

## 恢复顺序

1. 确认 115 登录及挂载正常，核对云端正式库和待整理目录。
2. 恢复本机服务及独立保存的账本与停止标记；先保持下载/整理暂停。
3. 配置本机凭据、环境变量与匹配的 protobuf 客户端。
4. 核对账本任务身份、qB 现有任务、云队列、已经整理的文件；不要直接批量重新添加来源。
5. 本地暂存逐个核验，未获得远端 ID、大小、SHA1 一致的证据时保留。
6. 先生成少量整理计划并复核，再处理已完成资源；恢复 Jellyfin 扫描。
7. 明确确认额度与提交意图后才单独处理 `CLOUD_QUOTA_STOP`；一般启动入口不会清除它。
8. 确认本机功能正常后，再恢复 Tailscale 分享与朋友访问验证。

## 不从仓库恢复的内容

种子/磁力资源、媒体、字幕正文、数据库、邀请、私人域名与原账号配置需要用户自己的本地备份。多余 Emby 的配置数据库备份也只保存在本机，不属于 GitHub 交付内容。
