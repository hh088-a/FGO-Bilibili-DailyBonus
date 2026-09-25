# 开发日志

记录本项目的开发过程：从最初的"部署日服脚本"到"为国服从零实现一套签到系统"。
希望能给想做类似工具的人一些参考。

> 时间：2026-09-25，一天内完成调研、实现、验证、部署、开源发布。

## 第一阶段：起点与转向

### 1.1 最初的目标

需求很简单：部署 [hexstr/FGODailyBonus](https://github.com/hexstr/FGODailyBonus) —— 一个知名的 FGO 每日签到脚本，通过 GitHub Actions 定时运行。

克隆代码后先做了静态分析，发现它的核心设计：

- 服务器地址写死为 `https://game.fate-go.jp`（日服）
- 凭据体系是游戏内的 `authKey` / `secretKey` / `userId`（从日服客户端数据文件提取）
- `cfg.json` 存放 appVer / dataVer 等版本元数据，登录时自动处理版本升级

### 1.2 关键转折：用户是国服（B服）

确认需求时发现用户玩的是**国服 bilibili 服**。这是完全不同的体系：

| | 日服 | 国服（B服） |
|---|---|---|
| 登录方式 | 游戏内 authKey/secretKey 直登 | B站 OAuth access_token 授权 |
| 服务器 | game.fate-go.jp | le1-bili-fate.bilibiligame.net |
| 客户端包名 | com.aniplex.fategrandorder | com.bilibili.fatego |
| 协议细节 | verCode + RSA 签名 | B站 token 校验 + md5(FUNNY_KEY+sgusk) |

**结论：原项目无法直接用于国服，需要重写。**

## 第二阶段：国服协议调研

### 2.1 生态调研

搜索 GitHub 后发现：国服没有现成的、维护中的"Actions 签到"项目。国服的生态主要是：

- [Chaldea](https://github.com/chaldea-center/chaldea)：FGO 助手 App（Flutter），包含国服登录协议实现
- 各类 toplogin 抓包/提取工具：抓包后导入 Chaldea 使用
- BBC（bbchannel）：基于图像识别的模拟器刷本工具

其中 [AkatuRegumi/fgo-cn-toplogin-extractor](https://github.com/AkatuRegumi/fgo-cn-toplogin-extractor) 是 Python 实现，源码清晰展示了完整的国服登录链路，成为最重要的参考。

### 2.2 摸清国服登录链路

从源码和 Chaldea 的协议研究中整理出四步链路：

```
1. B站扫码 → TV 端 OAuth → access_token（passport.bilibili.com）
2. POST member.php            → 拿 gamedata（当前 dataVer）
3. POST logintomembercenter.php → 用 B站 token 换 rguid/rgusk
4. POST login.php              → 建立游戏会话，得 sguid/sgusk
5. POST ac.php?_key=toplogin   → usk = md5(FUNNY_KEY + sgusk)
                                  ↑ 这一步就是每日签到
```

关键细节：

- 版本元数据（appVer/dataVer/unityVer）不必自己维护，Chaldea 提供了公共接口 `data-cn.chaldea.center/gametop.json`，会自动随版本更新——这解决了日服脚本需要手动维护 cfg.json 的痛点
- `toplogin` 响应里就包含签到奖励、连续登录天数、圣晶石等全部信息

### 2.3 设计决策

- **不用抓包**：采用 B站 TV 端扫码登录（二维码 + 轮询），用户不需要配置代理/证书，也不需要提供密码
- **先本地验证再部署**：登录协议这种东西，必须先在本机跑通确认能签到，再谈自动化
- **凭据与代码分离**：`auth.json` 本地保存 / Secrets 云端保存，永远不进 git

## 第三阶段：实现与本地验证

### 3.1 代码结构

```
fgo_cn.py    协议层：B站扫码 OAuth + 四步登录链路
login_qr.py  凭据工具：生成二维码 → 等待扫码 → 保存 auth.json
checkin.py   主程序：读凭据 → 自动续期 → toplogin → 解析输出签到报告
update_secret.py  CI 辅助：token 刷新后回写仓库 Secrets
```

### 3.2 踩坑记录

**坑 1：二维码展示**
最初把二维码存成 PNG 图片，但用户端看不到。解决方案：用 `qrcode` 库的 `print_ascii()` 直接在终端输出字符画二维码，同时保留 PNG 和链接三种方式。

**坑 2：绑错账号**
第一次扫码成功后签到返回的是 1 级小号——用户B站App里登录的不是绑定 FGO 大号的账号。国服链路的授权完全跟随B站App当前账号，所以扫码前必须先确认App切对了号。这个教训后来写进了 README 的醒目提示。

**坑 3（最大的收获）：token 刷新端点**
B站 TV token 有效期实测为 **180 天**（比预期的 30 天乐观）。但为了实现"永久免扫码"，还是决定做自动续期。测试刷新端点连踩两坑：

```
POST /x/passport-tv-login/token/refresh   → 404（端点不存在）
POST /api/oauth2/refreshToken              → -101 账号未登录
POST /api/oauth2/refreshToken              → code:0 成功 ✓
  （参数里同时带上 access_token + refresh_token，
    appkey/appsec 签名）
```

⚠️ 注意：刷新成功会**立即作废旧 token**，所以拿到新 token 必须马上落盘，否则凭据就断了。

## 第四阶段：GitHub Actions 部署

### 4.1 架构设计

```
每天 cron 触发
  → 从 Secret FGO_AUTH_JSON 读凭据
  → 检查有效期，<30 天则自动刷新
  → toplogin 签到
  → 若 token 刷新过：用 PAT 调 GitHub API 把新凭据回写 Secret
```

这样只要任务每天正常运行，token 有效期会不断重置为 180 天，**理论上永远不需要重新扫码**。

### 4.2 踩坑记录

**坑 4：gh CLI 登录**
`gh auth login --with-token` 要求 PAT 带 `read:org` scope，而部署用的 PAT 只勾了 `repo`+`workflow`。解决：不走 auth login，改用 `GH_TOKEN` 环境变量驱动 gh 命令，git push 用一次性 `http.extraHeader` 凭据（不把 token 写进 .git/config）。

**坑 5：UTF-8 BOM 破坏 Secret（本次部署唯一的线上事故）**
第一次 Actions 运行失败，日志报：

```
json.decoder.JSONDecodeError: Unexpected UTF-8 BOM
```

原因：PowerShell 5.1 中 `$OutputEncoding=[Text.Encoding]::UTF8` **自带 BOM**，`Get-Content | gh secret set` 管道传输时把 BOM 带进了 secret 值。

双重修复：

1. `checkin.py` 解析时 `lstrip('\ufeff')` 容忍 BOM（防御性）
2. 用 `New-Object System.Text.UTF8Encoding($false)`（无 BOM）重设 secret

教训：**在 PowerShell 里给程序传数据，永远用无 BOM 的 UTF-8。**

**坑 6：PowerShell 的编码连环坑**
后续又遇到 `Set-Content` 默认写 UTF-16 导致 GitHub API 400、`curl` 是 `Invoke-WebRequest` 别名、控制台 GBK 乱码等一串问题。最终对策：涉及 API 调用的操作全部改用 Python `requests`，绕开 Shell 编码差异。

### 4.3 验证

第二次 Actions 运行全绿：日志显示完整链路和"签到成功"，云端部署完成。

## 第五阶段：开源发布

### 5.1 为什么不直接公开部署仓库

公开仓库的 **Actions 日志也是公开的**——每天签到的账号信息（御主名、等级、石头数）会泄露。所以拆成两个仓库：

- **私有仓库**：跑自己的签到（日志私有）
- **公开模板仓库**：纯代码 + 文档，禁用 workflow，供他人 fork

### 5.2 许可证选择

协议实现参考了两个 AGPL-3.0 项目（Chaldea、fgo-cn-toplogin-extractor）。虽然代码是独立编写的，但协议研究成果具有传染性约束，出于合规和尊重原作者，选择 **AGPL-3.0** 发布。

## 经验总结

1. **先验证再自动化**：登录协议类项目，本地跑通一次比写十行文档都有用
2. **凭据的生命周期设计**：token 自动续期 + 回写 Secrets 是"免维护"的关键，但要注意刷新即作废旧 token
3. **Shell 是跨平台脚本的最大敌人**：Windows PowerShell 的编码默认值（GBK 控制台、UTF-16 文件、带 BOM 的管道）几乎每个都踩了一遍，复杂操作交给 Python 更稳妥
4. **公开 ≠ 直接公开**：涉及个人账号数据的自动化项目，要把"部署实例"和"开源模板"分开

## 参考与致谢

- [hexstr/FGODailyBonus](https://github.com/hexstr/FGODailyBonus) —— 项目灵感来源（日服）
- [chaldea-center/chaldea](https://github.com/chaldea-center/chaldea) —— 国服协议研究与公共版本元数据接口
- [AkatuRegumi/fgo-cn-toplogin-extractor](https://github.com/AkatuRegumi/fgo-cn-toplogin-extractor) —— 国服 TopLogin 链路实现参考
