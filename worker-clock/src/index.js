/**
 * grace-publish-clock
 *
 * Cron -> POST a workflow_dispatch to the auto-publish workflow. That is the
 * whole job. Cloudflare's cron is the clock we operate; GitHub's schedule stays
 * enabled as a backup, and the workflow's `concurrency: auto-publish` group
 * queues rather than overlaps if both happen to fire.
 *
 * Secrets (wrangler secret put):
 *   GH_DISPATCH_TOKEN  fine-grained PAT, Actions: read+write on this repo only
 *   NTFY_TOPIC         same topic the workflow notifies on
 *
 * Neither is ever logged. A dispatch failure is the one thing worth waking
 * someone for, because a silent clock means silent staleness.
 */

const OWNER = 'chrisrank01';
const REPO = 'grace-guest-assistant';
const WORKFLOW = 'auto-publish.yml';
const DISPATCH_URL =
  `https://api.github.com/repos/${OWNER}/${REPO}/actions/workflows/${WORKFLOW}/dispatches`;

async function alert(env, title, body) {
  if (!env.NTFY_TOPIC) return;
  try {
    await fetch(`https://ntfy.sh/${env.NTFY_TOPIC}`, {
      method: 'POST',
      headers: { Title: title, Priority: 'high', Tags: 'rotating_light' },
      body
    });
  } catch (err) {
    /* the alert channel failing is not worth throwing over */
  }
}

async function dispatch(env) {
  const stamp = new Date().toISOString();
  if (!env.GH_DISPATCH_TOKEN) {
    await alert(env, 'Grace clock: dispatch FAILED', `no GH_DISPATCH_TOKEN set · ${stamp}`);
    return { ok: false, status: 0 };
  }
  let response;
  try {
    response = await fetch(DISPATCH_URL, {
      method: 'POST',
      headers: {
        Authorization: `Bearer ${env.GH_DISPATCH_TOKEN}`,
        Accept: 'application/vnd.github+json',
        'X-GitHub-Api-Version': '2022-11-28',
        'User-Agent': 'grace-publish-clock',
        'Content-Type': 'application/json'
      },
      body: JSON.stringify({ ref: 'main' })
    });
  } catch (err) {
    // Body carries the status and timestamp only - never the token, never the
    // response text, which can echo request context.
    await alert(env, 'Grace clock: dispatch FAILED', `fetch threw · ${stamp}`);
    return { ok: false, status: 0 };
  }
  if (!response.ok) {
    await alert(env, 'Grace clock: dispatch FAILED', `HTTP ${response.status} · ${stamp}`);
    return { ok: false, status: response.status };
  }
  return { ok: true, status: response.status };
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(dispatch(env));
  },

  // Manual probe: GET / returns the dispatch result as JSON. Handy for proving
  // the token works without waiting two hours for a tick.
  async fetch(request, env) {
    const result = await dispatch(env);
    return new Response(JSON.stringify(result), {
      status: 200,
      headers: { 'Content-Type': 'application/json' }
    });
  }
};
