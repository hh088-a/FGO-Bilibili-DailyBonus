# 第三方组件与来源

本项目是部署与运维工作归档。第三方应用、协议、数据和脚本遵循各自许可证；本仓库没有重新分发这些应用的安装包、媒体资源、私有配置或账号授权。

|组件|用途与来源|
|---|---|
|[Jellyfin](https://jellyfin.org/)|媒体服务和索引；[服务端源码](https://github.com/jellyfin/jellyfin)|
|[Jellyfin Media Player](https://github.com/jellyfin/jellyfin-media-player)|Windows 桌面客户端；本机外链适配参考 v1.12.0 的 NativeShell/SystemComponent 实现|
|[qBittorrent](https://www.qbittorrent.org/)|本地下载；[WebUI API 参考](https://github.com/qbittorrent/qBittorrent/wiki/WebUI-API-%28qBittorrent-5.0%29)|
|[CloudDrive2](https://www.clouddrive2.com/)|115 挂载和云端文件/离线任务 API；协议客户端需匹配用户安装版本|
|[115](https://115.com/)|用户自己的网盘存储与云端任务服务|
|[Bangumi API](https://github.com/bangumi/api)|动画目录与排名快照来源|
|[bangumi-data](https://github.com/bangumi-data/bangumi-data)|作品跨站身份映射；数据未复制进仓库|
|[PotPlayer](https://potplayer.tv/)|本机播放；本次使用官方发布并验证 Kakao Corp. 有效签名，二进制不入库|
|[PlayBridge](https://github.com/Damocles-fr/PlayBridge)|桌面端接入方案，MIT；仓库记录适配差异，最终个人设备注入配置留在本机|
|[JavaScript Injector](https://github.com/n00bcodr/Jellyfin-JavaScript-Injector)|Jellyfin 注入插件，GPL-3.0；使用 4.1.0.0 的 Jellyfin 12 构建，不随仓库分发 DLL|
|[Tailscale](https://tailscale.com/)|异地 HTTPS 访问；真实 Tailnet 与规则留在本机|
|[embyToLocalPlayer](https://github.com/kjtsune/embyToLocalPlayer)|评估过的另一种外部播放器方案，未作为本次已落地实现|

工作中接触过的来源站只作为本地候选核验输入；仓库不保存或发布具体资源页面、种子、磁力链接和 tracker 凭据。代码中的通用请求逻辑不代表第三方站点可用性或授权保证。

尚未为整个归档指定新的开源许可证，不对第三方组件或既有数据作重新授权。
