# Jellyfin 桌面端 → PotPlayer

## 已落地组合

Jellyfin Server 12.4.0 提供海报库；Jellyfin Media Player 1.12.0 是用户点击播放的桌面界面；PotPlayer 是实际本机播放器。CloudDrive2 必须运行，`X:\动漫` 必须可读。

使用 [PlayBridge](https://github.com/Damocles-fr/PlayBridge) 的桌面实验接入脚本，由 [JavaScript Injector](https://github.com/n00bcodr/Jellyfin-JavaScript-Injector) 4.1.0.0 的 Jellyfin 12 构建加载。脚本要求登录，并只匹配本机桌面 DeviceId，其他浏览器/客户端保持原来的播放路径。

## 本机适配

1. 使用官方签名 PotPlayer 运行文件，不修改全局视频关联。播放器二进制与安装包不存入仓库。
2. URI 处理器位于运行根目录 `player\bridge\potplayer_bridge.py`，调用固定的 `player\PotPlayer\PotPlayerMini64.exe`。
3. 处理器只允许 `X:\动漫` 下指定扩展名的视频，拒绝库外路径、父目录跳转、额外流媒体查询参数和非视频文件。
4. 调用使用参数列表，不通过 shell 拼接中文路径、空格或 `&`。
5. 注册 Windows 当前用户 `playbridge` URI，不需要全局改动文件关联；实际文件路径使用 resolve 后的路径，兼容 MSIX LocalAppData 视图。
6. 桌面端使用 `window.NativeShell.openUrl(url)`。URI 采用 `playbridge:///X%3A/...`，避免 Qt 将编码盘符视作无效主机名。

使用仓库脚本时应先复制到上述部署位置，核对播放器存在，再注册；不能直接把 `player` 源码文件夹的相对布局误当成生产运行布局。

## 注入脚本的必要差异

上游脚本保留上游许可证，在本机配置中做以下定点调整：

```javascript
// 只替换这一处常量；不要全文替换占位词，因为脚本自身还有未配置检查。
const ALLOWED_DEVICE_ID = 'YOUR_DESKTOP_DEVICE_ID';
const STREAM_LINKS = false;

// 原：return PROTOCOL + encoded + streamQuery(src);
return PROTOCOL + '/' + encoded + streamQuery(src);

// 原：window.location.replace(url);
if (typeof window.NativeShell?.openUrl === 'function') {
  window.NativeShell.openUrl(url);
} else {
  window.location.replace(url);
}
```

这些是插入原有函数位置的说明片段，不能直接当作完整脚本粘贴。仓库不包含绑定个人设备的最终注入配置；应从上游取得脚本、阅读后按本机 DeviceId 修改。

## 验收

在 Jellyfin 桌面客户端实际点击：

- 《白箱》S01E01：PotPlayer 启动，打开正确 X 盘文件，中文字幕显示，自动列出同季 24 集。
- 《轻音少女 剧场版》：PotPlayer 启动并显示电影画面。

同时记录了 URI 处理日志和进程参数进行核对。截图保留本机，没有将影音截图或私人设备配置作为仓库附件上传。

## 限制与回退

这是第三方实验接入，**PotPlayer 播放进度和已看状态不会自动回传 Jellyfin**；Jellyfin 的字幕/音轨下拉选项也不会随这个路径传给 PotPlayer，应在 PotPlayer 内操作。客户端升级或清空数据后 DeviceId 可能变化，需要重新配置。

要恢复内置播放：Jellyfin 控制台 → 插件 → JavaScript Injector，关闭 `AnimeLibrary PotPlayer Desktop`，保存，退出并重新打开桌面客户端。

曾比较 Kodi、Emby、Plex 等方案。Kodi 可作为整套客户端替代并接入外部播放器；本次最终选择继续保留 Jellyfin 媒体管理，新增 PotPlayer 播放入口，没有重新安装已清理的 Emby。上游参考：[Kodi 外部播放器](https://kodi.wiki/view/External_players)、[Jellyfin Kodi 客户端](https://jellyfin.org/docs/general/clients/kodi/)。
