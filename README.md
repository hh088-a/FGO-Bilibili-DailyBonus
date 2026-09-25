# FGO-Bilibili-DailyBonus

**Fate/Grand Order 国服（B服）每日自动签到脚本** —— GitHub Actions 云端定时运行，B站 token 自动续期，一次扫码长期免维护。

![License](https://img.shields.io/badge/license-AGPL--3.0-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-green)
![Platform](https://img.shields.io/badge/platform-%E5%AE%89%E5%8D%93B%E6%9C%8D%20%7C%20iOSB%E6%9C%8D-orange)

## ✨ 特性

- 🗓️ **每日自动签到**：通过 GitHub Actions 定时执行 `toplogin`，无需自己的服务器，无需电脑开机
- 🔄 **token 自动续期**：B站 access_token 有效期 180 天，剩余不足 30 天时自动刷新并回写仓库 Secrets，**一次扫码，长期免维护**
- 📊 **签到报告**：输出御主等级、圣晶石、呼符、连续/累计登录天数、当日签到奖励明细
- 📱 **双平台**：支持安卓 B服、iOS B服
- 💻 **也可纯本地运行**：不依赖 GitHub，配合 Windows 任务计划即可本地定时签到（国内 IP，风控风险更低）

## 🔧 原理

FGO 国服使用B站账号体系登录，签到链路为：

```
B站App扫码 → 获取 OAuth access_token
    → member (gamedata) → logintomembercenter (B站授权校验)
    → login (建立游戏会话) → toplogin ← 这一步即每日签到
```

> 本项目灵感来自日服签到脚本 [hexstr/FGODailyBonus](https://github.com/hexstr/FGODailyBonus)。
> 由于日服与国服的登录协议、加密、服务器完全不同，本项目是针对国服的独立实现。
> 有兴趣了解从零调研到部署上线的全过程？请看 [📖 开发日志](DEVELOPMENT.md)。

## 🚀 快速开始

### 1. Fork 本仓库

点击右上角 **Fork**。

### 2. 本地扫码，获取登录凭据

需要 **Python 3.10+**：

```bash
pip install -r requirements.txt
python login_qr.py run "你的FGO御主名"
```

用手机 **Bilibili App** 扫描终端里的二维码并确认登录（⚠️ 确认App当前登录的是**绑定FGO账号的那个B站号**）。成功后凭据保存到本地 `auth.json`。

> `auth.json` 等同账号密码，请勿分享、勿提交到任何仓库（已在 .gitignore 中排除）。

### 3. 在 Fork 的仓库中设置 Secrets

进入你 Fork 的仓库 → **Settings → Secrets and variables → Actions → New repository secret**：

| Secret | 值 | 说明 |
|---|---|---|
| `FGO_AUTH_JSON` | `auth.json` 文件的**全部内容** | B站登录凭据 |
| `FGO_UPDATE_PAT` | [创建链接](https://github.com/settings/tokens) | classic PAT，勾选 `repo` 权限，用于 token 续期后自动回写 Secrets |

### 4. 启用 Actions 并验证

进入你 Fork 的仓库 → **Actions** → 启用 → 选择 `FGO B服每日签到` → **Run workflow** 手动触发一次，确认日志输出 `签到成功`。

### 5. 定时运行

默认每天 **北京时间 01:05**（UTC 17:05）自动签到（FGO 每日 0 点刷新后）。如需修改，编辑 `.github/workflows/checkin.yml` 中的 `cron`。

> 注意：GitHub 定时任务在高峰期可能延迟数十分钟，属正常现象。

## 💻 纯本地运行（可选，不用 GitHub）

完成上面第 2 步后：

```bash
python checkin.py
```

配合 **Windows 任务计划程序**每天定时执行即可。本地运行使用国内 IP，相比 GitHub Actions 的海外 IP 更不容易触发风控。

## 🔄 token 自动续期说明

- B站 TV 端 token 有效期 **180 天**
- 每次运行时检查：剩余不足 30 天则自动刷新，有效期重置为 180 天
- CI 环境下新 token 通过 `FGO_UPDATE_PAT` 自动回写 Secrets
- 理论上只要任务每天正常运行，**永远不需要再次扫码**

## ❓ 常见问题

**Q: 签到失败，提示风控/授权失败？**
A: GitHub Actions 服务器在海外，B站可能对异地登录风控。建议改用纯本地运行方式。

**Q: token 过期/失效了？**
A: 重新执行 `python login_qr.py run "御主名"` 扫码，把新的 `auth.json` 内容更新到 Secret `FGO_AUTH_JSON`。

**Q: iOS B服怎么用？**
A: 扫码时加个 `ios` 参数即可：`python login_qr.py run "御主名" ios`，其余流程完全相同。

**Q: 签到日志里没有奖励明细？**
A: 说明当天已经登录过游戏（奖励每天只能领一次），属于正常现象，第二天再看。

**Q: 会封号吗？**
A: 无法承诺。第三方模拟客户端登录存在触发风控/违反用户协议的可能，请仅用于自己的账号并自行评估风险。

## ⚠️ 免责声明

- 本项目为**非官方**第三方开源工具，与 bilibili、Fate/Grand Order、Aniplex、Lasengle 等无任何隶属、授权或合作关系
- 使用本项目可能违反相关平台服务条款，存在账号被限制/封禁的风险，**使用后果请自负**
- 本项目不承诺"绝不触发风控"或"绝不封号"
- 请勿将本项目用于任何商业用途，仅供学习交流

## 🙏 致谢

- [hexstr/FGODailyBonus](https://github.com/hexstr/FGODailyBonus) —— 日服签到脚本，本项目的灵感来源
- [chaldea-center/chaldea](https://github.com/chaldea-center/chaldea) —— FGO 国服登录协议研究参考
- [AkatuRegumi/fgo-cn-toplogin-extractor](https://github.com/AkatuRegumi/fgo-cn-toplogin-extractor) —— 国服 TopLogin 链路实现参考

## 📄 License

[GNU Affero General Public License v3.0](LICENSE)

本项目参考了上述 AGPL-3.0 许可项目的协议研究成果，依其许可证要求以 AGPL-3.0 发布。
