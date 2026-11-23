
const API = "https://api.github.com";

export default {
  // Cloudflare Cron 定时触发
  async scheduled(event, env, ctx) {
    console.log("========== Cron Trigger ==========");
    console.log("Cron:", event.cron);
    console.log(
      "Scheduled Time:",
      new Date(event.scheduledTime).toISOString()
    );

    ctx.waitUntil(
      dispatch(env, "cron").catch((error) => {
        console.error("Cron execution error:", error);
      })
    );
  },

  // 手动 HTTP 触发：GET /trigger?key=TRIGGER_KEY
  async fetch(request, env) {
    const url = new URL(request.url);

    if (url.pathname !== "/trigger") {
      return Response.json({
        ok: true,
        usage: "GET /trigger?key=YOUR_TRIGGER_KEY",
      });
    }

    if (
      !env.TRIGGER_KEY ||
      url.searchParams.get("key") !== env.TRIGGER_KEY
    ) {
      return new Response("forbidden", { status: 401 });
    }

    const result = await dispatch(env, "manual");

    return new Response(result.body + "\n", {
      status: result.status,
      headers: {
        "Content-Type": "text/plain; charset=utf-8",
      },
    });
  },
};

// 触发 GitHub Actions
async function dispatch(env, source) {
  const owner = env.REPO_OWNER;
  const repo = env.REPO_NAME;
  const workflow = env.WORKFLOW_FILE || "checkin.yml";
  const ref = env.REF || "main";

  console.log("========== GitHub Dispatch ==========");
  console.log("Source:", source);
  console.log("Repository:", `${owner}/${repo}`);
  console.log("Workflow:", workflow);
  console.log("Branch:", ref);

  // 检查必要环境变量
  if (!owner || !repo || !env.GITHUB_PAT) {
    const msg =
      "缺少配置: 需要 REPO_OWNER / REPO_NAME / GITHUB_PAT";

    console.error(msg);

    return {
      status: 500,
      body: msg,
    };
  }

  try {
    const url =
      `${API}/repos/${owner}/${repo}/actions/workflows/${workflow}/dispatches`;

    const res = await fetch(url, {
      method: "POST",
      headers: {
        Authorization: `Bearer ${env.GITHUB_PAT}`,
        Accept: "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "fgo-cron-worker",
      },
      body: JSON.stringify({ ref }),
    });

    const responseText = await res.text();

    const ok = res.status === 204;

    console.log(
      source,
      "Dispatch:",
      ok ? "SUCCESS" : "FAILED",
      "HTTP:",
      res.status
    );

    if (!ok) {
      console.error("GitHub API Error:", responseText.slice(0, 500));
    }

    return {
      status: ok ? 200 : res.status,
      body: ok
        ? `已触发 ${owner}/${repo} ${workflow} (ref=${ref})`
        : `触发失败 HTTP ${res.status}: ${responseText.slice(0, 500)}`,
    };
  } catch (error) {
    console.error("GitHub request exception:", error);

    return {
      status: 500,
      body: `请求异常: ${error.message}`,
    };
  }
}
