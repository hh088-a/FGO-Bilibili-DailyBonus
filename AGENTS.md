# AGENTS.md — FGO-Bilibili-DailyBonus

本仓库是 `FGO-CN-DailyBonus`（私有）的**公开镜像**，AGPL-3.0。

- 与私有仓库代码一致；**改私有后需手动同步** `fgo_cn.py`、`checkin.py`、`.github/workflows/checkin.yml`、`README.md`、`DEVELOPMENT.md` 并推送。
- 本仓库的 GitHub Actions workflow 已 `disabled_manually`，**不要启用**（缺 secrets 会跑失败）。
- 不要提交任何凭据（`auth.json`/`qr.png` 等已在 `.gitignore`）。

详见 `README.md` / `DEVELOPMENT.md`。
