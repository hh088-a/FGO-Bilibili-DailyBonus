# 开发日志

> 一个御主的自我修养：人可以睡，签不能断。

## 起源：一次断签惨案

每个 FGO 玩家都经历过这样的夜晚——刷完无限池倒头就睡，凌晨猛然惊醒：**今天没登录**。

几百天的连续登录记录，断了就是断了，从第 1 天重新来过。这种感觉比十连全是礼装还难受。

日服玩家早就有救星：[hexstr/FGODailyBonus](https://github.com/hexstr/FGODailyBonus)，GitHub Actions 定时签到，稳定运行多年。而国服玩家搜遍 GitHub，只有抓包工具、刷本脚本，唯独没有一个"开箱即用的云端签到方案"。

原因很快找到了：日服脚本的服务器写死 `game.fate-go.jp`，凭据是游戏内的 authKey/secretKey，而国服走的是**完全不同的B站账号体系**——这不是改个地址就能适配的，得重写。

| | 日服 | 国服（B服） |
|---|---|---|
| 登录方式 | 游戏内 authKey/secretKey 直登 | B站 OAuth access_token 授权 |
| 游戏服务器 | game.fate-go.jp | le1-bili-fate.bilibiligame.net |
| 客户端 | com.aniplex.fategrandorder | com.bilibili.fatego |
| 会话校验 | verCode + RSA 签名 | B站 token 校验 + md5(KEY+sgusk) |

既然没有轮子，那就自己造一个。

## 摸清国服的登录链路

国服协议没有官方文档，好在社区前辈已经把路趟出来了。[chaldea-center/chaldea](https://github.com/chaldea-center/chaldea) 的协议研究和 [AkatuRegumi/fgo-cn-toplogin-extractor](https://github.com/AkatuRegumi/fgo-cn-toplogin-extractor) 的 Python 实现，把完整的登录链路摆在了明处：

```
B站App扫码 → TV端 OAuth → access_token（passport.bilibili.com）
  → member.php                拿 gamedata（当前 dataVer）
  → logintomembercenter.php   用B站 token 换 rguid / rgusk
  → login.php                 建立游戏会话，得 sguid / sgusk
  → ac.php?_key=toplogin      usk = md5(FUNNY_KEY + sgusk)
                              ↑ 每日签到就藏在这最后一步
```

调研中最大的惊喜：Chaldea 维护着一个公共版本元数据接口（`data-cn.chaldea.center/gametop.json`），appVer、dataVer、unityVer 随游戏版本实时更新。日服脚本需要用户手动维护 `cfg.json` 的痛点，在国服直接被这个接口解决了——版本更新？不存在的，接口会出手。

另一个值得庆幸的发现：`toplogin` 的响应里什么都有——连续登录天数、等级、圣晶石、呼符、当日签到奖励明细。签到和报告一步到位，不用额外请求。

## 几个关键的设计决策

**扫码登录，而不是抓包或密码。**
国服登录绕不开B站授权。抓包要装证书配代理，门槛高；要密码更是想都别想。B站 TV 端的扫码 OAuth（`passport-tv-login`）是最优解：用户手机App扫一下、点确认，access_token 到手，全程不碰密码。安全性拉满，体验也最好。

**凭据与代码严格分离。**
`auth.json` 本地存、Secrets 云端存，`.gitignore` 从第一个 commit 就排除。凭据永远不进 git 历史，这是底线。

**先本地跑通，再上云。**
登录协议这种东西，本地都没签到成功就急着部署 Actions，等于拿着没强化满的队就冲高难本。本地验证 → 确认奖励到账 → 再谈自动化。

**token 自动续期（本项目的核心设计）。**
如果每次 token 过期都要重新扫码，那这脚本最多算"半自动"。实测B站 TV token 有效期 180 天，于是设计了这样的闭环：

```
每次运行时：token 剩余 < 30 天？
  → 是：自动刷新（有效期重置为 180 天）
  → CI 环境：用 PAT 把新凭据回写仓库 Secret
```

只要任务每天正常跑，token 就永远新鲜——**一次扫码，长期免维护**。

## 踩坑实录

### 坑一：B站 token 刷新端点（三连才中）

刷新端点没有任何文档，只能摸着石头过河：

```
POST /x/passport-tv-login/token/refresh   → 404，端点不存在
POST /api/oauth2/refreshToken              → -101 账号未登录
POST /api/oauth2/refreshToken              → code:0 ✓
  （关键：参数里同时带 access_token + refresh_token，
    用 TV 端 appkey/appsec 签名）
```

⚠️ 这里有个凶险的细节：**刷新成功的瞬间旧 token 立即作废**。拿到新 token 必须马上落盘/回写，慢一步凭据就断了——比手滑把芙芙喂错人还没法撤回。

### 坑二：PowerShell 的 UTF-8 BOM（本项目唯一的线上事故）

部署后第一次 Actions 运行直接报错：

```
json.decoder.JSONDecodeError: Unexpected UTF-8 BOM
```

排查发现：PowerShell 5.1 的 `[Text.Encoding]::UTF8` **自带 BOM**，凭据经 `Get-Content | gh secret set` 管道写入 secret 时，BOM 被一并带了进去，JSON 解析当场去世。

修复双管齐下：解析端 `lstrip('\ufeff')` 做防御性兼容；写入端改用 `New-Object System.Text.UTF8Encoding($false)`（无 BOM）。

**教训：在 Windows 上用 PowerShell 给程序喂数据，永远、永远用无 BOM 的 UTF-8。**

### 坑三：gh CLI 的 scope 陷阱

`gh auth login --with-token` 强制要求 PAT 带 `read:org` scope，而部署 PAT 只需 `repo` + `workflow`。解法：跳过 auth login，改用 `GH_TOKEN` 环境变量驱动 gh；git push 用一次性 `http.extraHeader` 凭据，token 不落盘到 `.git/config`。

## 为什么拆成两个仓库

公开仓库的 **Actions 日志是公开的**——每天签到的等级、石头数都会跟着日志一起裸奔。所以：

- **私有仓库**：跑自己的签到，日志私有，岁月静好
- **公开模板仓库**：纯代码 + 文档，workflow 默认禁用，fork 之后按 README 配置自己的 Secrets 即可

部署实例与开源模板分离，各干各的，互不干扰。

## 抓包炼金：从网络错误到青铜果实

签到稳定之后，需求开始膨胀：每次运行能不能顺手把多余的 AP 换成苹果？（树苗 + 40AP = 1 青铜果实，AP 满着不换，比抽卡歪了还亏。）

问题是：这个合成接口的 `_key` **没有任何公开文档**——登录链路有前辈趟过路，商店接口只能自己抓。于是搭了一套 mitmproxy 中间人环境：MuMu 模拟器 + adb root + 系统证书 + 代理转发，让游戏的所有 HTTPS 流量都先经过我这里。

游戏直接甩来一句"网络错误"。证书它不认。

### 坑四：证书格式（PEM，不是 DER）

网上教程清一色教你把证书转成 DER、命名 `<hash>.0`。推上去，游戏照样报错。拉下 Android 15 自带的系统证书一看——**人家是 PEM 格式**。文档抄的是上个时代的。

### 坑五：哈希算法（MD5，不是 RIPEMD160）

文件名的 `<hash>` 怎么算？OpenSSL 的 `subject_hash_old`（RIPEMD160）算出来 `3f201b09`，游戏不认。拿设备上一张**已知证书**反推：它的文件名是 `01419da9`，MD5 小端一算——精确命中。修正后 `c8750f0d.0`，一次到位。

> 调试玄学问题的正确姿势：别猜公式，找一个标准答案反着推。

### 坑六：命名空间套娃（最凶的一关）

证书装进 `/apex/.../cacerts`，`ls` 看得见，游戏还是不认。直到祭出 `/proc/<pid>/root` 才看清真相——**每个进程有自己的挂载命名空间**：

```
init ns      ✅ 有证书（adb 挂载在这）
zygote32 ns  ❌ 没有（我第一次装错了地方）
zygote64 ns  ❌ 没有 ← 游戏是 64 位，从这里 fork
应用 ns      ❌ fork 时复制父 zygote 的视图
```

`nsenter -t <zygote64> -m` 进去重装一遍，游戏重启后立刻握手成功——日志从"certificate unknown"变成一路 200 OK，比十连出金还舒坦。

### 抓到了什么

游戏内点开 AP 旁的加号，一次合成，请求响应全部到手：

```
请求: ac.php?_key=shoppurchase   id=13000000  num=1
响应: resCode=00  purchaseName="青铜果实"  PurchaseNum=1
      + 新会话种子 usk（下一次请求 = md5(FUNNY_KEY + 种子)）
```

关键发现：**usk 每次响应都会轮换**。登录链的 `md5(FUNNY_KEY + sgusk)` 公式在会话内继续生效，只是种子换成了响应里下发的新值——链式推进，断链即失效。这正是会话防重放的设计，也解释了为什么抓包必须拿到**响应体**。

### 落地

`FGO_APPLE_NUM` 环境变量/仓库 Variable 控制每次运行的合成数量：签到成功后逐个发送 `shoppurchase`，逐次轮换 usk，AP 或树苗不够时服务器返回错误码，优雅停止、绝不影响签到本身。本地实测 `1/1 个 (青铜果实)`，收官。

抓包环境（证书、代理、mitmproxy）随后已拆除——工具用完就收，留着中间人证书过年吗？

## 许可证

协议实现参考了两个 AGPL-3.0 项目（Chaldea、fgo-cn-toplogin-extractor）的公开研究成果。尊重前辈，按规矩来：本项目以 **AGPL-3.0** 发布。

## 写在最后

每天北京时间 01:05，当你抱着芙芙进入梦乡，这个小脚本会在云端准时替你上线——领圣晶石、领呼符、续上连续登录天数，然后安静下线。

圣晶石会有的，呼符也会有的。断签？不会再有了。

祝各位御主十连满宝，无限池把把掉落礼装。

## 参考与致谢

- [hexstr/FGODailyBonus](https://github.com/hexstr/FGODailyBonus) —— 日服签到脚本，本项目的灵感来源
- [chaldea-center/chaldea](https://github.com/chaldea-center/chaldea) —— 国服协议研究 & 公共版本元数据接口
- [AkatuRegumi/fgo-cn-toplogin-extractor](https://github.com/AkatuRegumi/fgo-cn-toplogin-extractor) —— 国服 TopLogin 链路实现参考
