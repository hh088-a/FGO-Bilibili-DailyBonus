// FGO 签到外部触发 Worker
// 定时(cron)或手动 HTTP 调用 GitHub Actions 的 workflow_dispatch。

const API = "https://api.github.com";

export default {
  // Cloudflare Cron 触发
  async scheduled(_event, env, ctx) {
    ctx.waitUntil(dispatch(env, "cron"));
  },

  // 手动触发: GET /trigger?key=<TRIGGER_KEY>
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname !== "/trigger") {
      return Response.json({ ok: true, usage: "GET /trigger?key=..." }, { status: 200 });
    }
    if (!env.TRIGGER_KEY || url.searchParams.get("key") !== env.TRIGGER_KEY) {
      return new Response("forbidden", { status: 401 });
    }
    const res = await dispatch(env, "manual");
    return new Response(res.body + "\n", { status: res.status });
  },
};

async function dispatch(env, source) {
  const owner = env.REPO_OWNER;
  const repo = env.REPO_NAME;
  const workflow = env.WORKFLOW_FILE || "checkin.yml";
  const ref = env.REF || "main";

  if (!owner || !repo || !env.GITHUB_PAT) {
    const msg = "缺少配置: 需要 REPO_OWNER / REPO_NAME / GITHUB_PAT";
    console.error(msg);
    return { status: 500, body: msg };
  }

  const res = await fetch(
    `${API}/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_PAT}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fgo-cron-worker",
      },
      body: JSON.stringify({ ref }),
    }
  );

  const ok = res.status === 204;
  const text = await res.text();
  console.log(source, "dispatch", ok ? "ok" : `fail ${res.status}`, text.slice(0, 300));
  return {
    status: ok ? 200 : res.status,
    body: ok
      ? `已触发 ${owner}/${repo} ${workflow} (ref=${ref})`
      : `触发失败 HTTP ${res.status}: ${text.slice(0, 300)}`,
  };
}
