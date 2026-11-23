// 直接粘进 Cloudflare Dashboard 的 Worker 编辑器即可
const OWNER = "zero3334";             // ← 改成你的 GitHub 用户名
const REPO = "FGO-Bilibili-DailyBonus";
const WORKFLOW = "checkin.yml";
const REF = "main";

export default {
  async scheduled(_event, env, ctx) {
    // Cron 到点后立即触发 GitHub Actions
    const url =
      `https://api.github.com/repos/${OWNER}/${REPO}` +
      `/actions/workflows/${WORKFLOW}/dispatches`;
    const r = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GH_PAT}`,
        Accept: "application/vnd.github+json",
        "User-Agent": "fgo-cron-worker",
        "Content-Type": "application/json",
      },
      body: JSON.stringify({ ref: REF }),
    });
    if (r.status !== 204) {
      const body = await r.text();
      console.log("dispatch failed", r.status, body);
      throw new Error("dispatch failed: " + r.status + " " + body);
    }
    console.log("dispatched ok", OWNER + "/" + REPO);
  },
};
