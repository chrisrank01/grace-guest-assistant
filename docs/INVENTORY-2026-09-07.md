# Grace Guest Assistant — technical inventory

**Compiled:** 2026-09-08 UTC (filename retains the 2026-09-07 label it was commissioned under)
**Compiled by:** read-only sweep of the live account, the repo, and the corpus Sheet
**Scope:** everything a person rebuilding or taking over this system would need to find

**On secrets:** this file records credential **names, locations, scopes and owners** only.
No credential value appears anywhere in it. `NTFY_TOPIC`'s value is itself a credential and
is never printed. The service account's `client_email` and the GCP project id are
identifiers, not secrets, and are recorded. Where a command's output would have contained a
value, the value is replaced with `<REDACTED>`.

Anything that could not be obtained is marked **NOT OBTAINED** with the reason, rather than
guessed at or quietly dropped.

---

## 1. Cloudflare — the whole account

### 1.1 Account

```
$ npx wrangler whoami
👋 You are logged in with an OAuth Token, associated with the email chris@relax-tech.com.
🔐 Credentials are stored in: /Users/christopherrank/.wrangler/config/default.toml
┌────────────────────────────────┬──────────────────────────────────┐
│ Account Name                   │ Account ID                       │
├────────────────────────────────┼──────────────────────────────────┤
│ Chris@relax-tech.com's Account │ 542c6caf232f86b4a1e6e69cb49e5326 │
└────────────────────────────────┴──────────────────────────────────┘
```

The local OAuth token value is `<REDACTED>` — it lives in `~/.wrangler/config/default.toml`
and is a **personal** credential, not a Grace one. Its scopes, which matter for what this
inventory could and could not read:

```
user (read) · offline_access · account (read) · workers (write) · workers_kv (write)
workers_routes (write) · workers_scripts (write) · workers_tail (read) · d1 (write)
pages (write) · zone (read) · ssl_certs (write) · ai (write) · ai-search (write/run)
websearch.run · agent-memory (write) · queues (write) · pipelines (write)
secrets_store (write) · artifacts (write) · flagship (write) · containers (write)
cloudchamber (write) · connectivity (admin) · email_routing (write) · email_sending (write)
browser (write) · challenge-widgets.write
```

Note `zone (read)` covers zone **metadata** only. It does **not** carry `dns_records:read`
or any Zero Trust scope, which is why §1.5 and §1.6 are partly NOT OBTAINED.

### 1.2 Pages projects

```
$ npx wrangler pages project list
┌─────────────────┬───────────────────────────────────────────────────────┬──────────────┬───────────────┐
│ Project Name    │ Project Domains                                       │ Git Provider │ Last Modified │
├─────────────────┼───────────────────────────────────────────────────────┼──────────────┼───────────────┤
│ grace-assistant │ grace-assistant.pages.dev, assistant.discovergrace.ai │ No           │ 14 hours ago  │
├─────────────────┼───────────────────────────────────────────────────────┼──────────────┼───────────────┤
│ grace-demo      │ grace-demo.pages.dev                                  │ No           │ 1 week ago    │
└─────────────────┴───────────────────────────────────────────────────────┴──────────────┴───────────────┘
```

Two projects. No others.

#### grace-assistant

| Field | Value |
|---|---|
| subdomain | `grace-assistant.pages.dev` |
| domains | `grace-assistant.pages.dev`, `assistant.discovergrace.ai` |
| production branch | `main` |
| source | **none — direct upload** (no Git integration; `wrangler pages deploy public`) |
| build config | none (`web_analytics_tag: null`, `web_analytics_token: null`) |
| compatibility date | `2026-08-27` (production and preview) |
| compatibility flags | none |
| env vars | none, either environment |
| bindings (KV/R2/D1/DO/queues/services/AI) | none |
| created | 2026-08-27T16:14:39Z |
| latest deployment | `38979b81-d913-472c-bfaa-a8b97bdc6ca4` @ 2026-09-08T01:18:40Z |

Custom domain: `assistant.discovergrace.ai` — status `active`, certificate `active`,
zone tag `f944e17d06e784b38cd51af0d1836b1d`.

Top 5 deployments:

```
38979b81-d913-472c-bfaa-a8b97bdc6ca4  Production  main  a17667a   14 hours ago
cc05d33e-7d3c-4a27-8ea3-fb675aecb837  Production  main  a17667a   14 hours ago
a487bddd-ec83-453f-9de8-c0ead0271eff  Production  main  0f337f5   14 hours ago
c5987c01-3a4e-4d3b-b395-83758a6f4766  Production  main  0f337f5   1 week ago
3eac3a61-6772-453d-97f7-3f4e0485c8f4  Production  main  9b6ebce   1 week ago
```

The `Source` column is the git SHA of the working tree at deploy time, and it is **not
reliable** — `a487bddd` and `cc05d33e` both report `a17667a` although only `cc05d33e`
carries the correct `answers.json`. Deployments made from a dirty tree carry the last
commit's SHA, not the content actually shipped. Use the md5 of the served file, not this
column.

#### grace-demo

| Field | Value |
|---|---|
| subdomain | `grace-demo.pages.dev` |
| domains | `grace-demo.pages.dev` only — **no custom domain** |
| production branch | `main` |
| source | none — direct upload |
| build config | none |
| compatibility date | `2026-08-27` |
| env vars / bindings | none |
| created | 2026-08-27T16:56:10Z |
| latest deployment | `e29d356e-ea15-4657-8e32-500c8c0a7429` @ 2026-08-27T17:22:40Z |

Top 5 deployments — all `Production / main / 1452704`, all one week old:
`e29d356e`, `606813d5`, `e1ca2684`, `e802f7bc`, `25978147`.

### 1.3 Workers

```
$ GET /accounts/542c…5326/workers/scripts
grace-assistant-router | modified 2026-08-27T17:50:46 | usage standard
grace-publish-clock    | modified 2026-08-28T17:25:58 | usage standard
```

Account `workers.dev` subdomain: **`relax-tech`** — so the public URLs are
`https://grace-assistant-router.relax-tech.workers.dev` and
`https://grace-publish-clock.relax-tech.workers.dev`.

**Worker custom domains: NONE.** Both Workers are reachable only on `workers.dev`, and both
have `workers.dev` **enabled**: `{"enabled": true, "previews_enabled": true}`.

#### grace-assistant-router

`worker/wrangler.toml`, verbatim (nothing to redact — it holds no values):

```toml
name = "grace-assistant-router"
main = "src/index.js"
compatibility_date = "2025-01-01"
```

```
$ npx wrangler secret list --name grace-assistant-router
[ { "name": "ANTHROPIC_API_KEY", "type": "secret_text" } ]
```

| Setting | Value |
|---|---|
| compatibility_date | `2025-01-01` (note: **not** the `2026-08-27` the Pages projects use) |
| compatibility_flags | none |
| usage_model | standard |
| logpush | false |
| observability | **null — not enabled** |
| placement | `{}` (default) |
| tail_consumers | none |
| limits | none |
| cron triggers | **NONE** |
| bindings | `ANTHROPIC_API_KEY` (secret_text, value `<REDACTED>`) |

Deployment history (`npx wrangler deployments list --name grace-assistant-router`):

```
2026-08-27T16:11:18.590Z  chris@relax-tech.com  Upload         version 7e97f504-5a40-4d8e-9d0a-bb143fc5eb71
2026-08-27T16:12:56.634Z  chris@relax-tech.com  Secret Change  version 03fc1526-3c37-4f10-b7aa-c1a2a95980da
```

#### grace-publish-clock

`worker-clock/wrangler.toml`, verbatim (nothing to redact):

```toml
name = "grace-publish-clock"
main = "src/index.js"
compatibility_date = "2025-01-01"

# The reliable clock. GitHub's own schedule: block is kept as a redundant backup
# but proved unreliable (7 consecutive ticks missed, 2026-08-28), so this Worker
# is what actually drives the cadence.
[triggers]
crons = ["17 */2 * * *"]
```

```
$ npx wrangler secret list --name grace-publish-clock
[ { "name": "GH_DISPATCH_TOKEN", "type": "secret_text" },
  { "name": "NTFY_TOPIC",        "type": "secret_text" } ]
```

| Setting | Value |
|---|---|
| compatibility_date | `2025-01-01` |
| observability | **null — not enabled** |
| logpush | false |
| cron triggers | `17 */2 * * *`, created and last modified 2026-08-28T17:25:59Z |
| bindings | `GH_DISPATCH_TOKEN`, `NTFY_TOPIC` (both secret_text, values `<REDACTED>`) |

Deployment history:

```
2026-08-28T17:25:57.810Z  chris@relax-tech.com  Upload         version 4b5f1d96-99c3-4d2b-b736-154cc6f46101
2026-08-28T17:33:18.964Z  chris@relax-tech.com  Secret Change  version a51422dd-0d18-40b2-b1e7-8fd95a89e4f4
```

### 1.4 Zones

```
discovergrace.ai | id f944e17d06e784b38cd51af0d1836b1d | active | Free Website
relaxtech.us     | id e86eec7f737b5e5240639e986f75c025 | active | Free Website
```

Both on nameservers `irena.ns.cloudflare.com`, `nicolas.ns.cloudflare.com`.
`relaxtech.us` is RTS's own domain and has nothing to do with Grace — noted so a future
reader does not assume the account is Grace-only.

**`discovergrace.com` is NOT a zone on this account.** Grace's live WordPress site is hosted
and DNS-managed elsewhere. Only `discovergrace.ai` — the assistant's own domain — is here.

### 1.5 DNS records for discovergrace.ai

**NOT OBTAINED — the available token lacks DNS read permission.**

```
$ GET /zones/f944e17d06e784b38cd51af0d1836b1d/dns_records
{"code": 10000, "message": "Authentication error"}
```

The wrangler OAuth token carries `zone (read)`, which is zone metadata only; listing DNS
records needs `#dns_records:read`, which no token available on this machine has. The
GitHub `CLOUDFLARE_API_TOKEN` secret is scoped to Pages:Edit and its value is deliberately
not retrievable.

What *is* externally verifiable by public resolution:

```
discovergrace.ai           A: 104.21.93.75, 172.67.206.166
assistant.discovergrace.ai A: 104.21.93.75, 172.67.206.166
www.discovergrace.ai       A: (no answer)
```

Both names resolve to Cloudflare anycast addresses, consistent with **proxied** records, and
`assistant` is confirmed as an active Pages custom domain in §1.2. `www` does not resolve.

**To complete this section, copy from the dashboard:** Cloudflare → `discovergrace.ai` →
**DNS → Records**. For every row record: Type, Name, Content/Target, Proxy status
(orange/grey cloud), TTL. Expect at minimum a CNAME `assistant` →
`grace-assistant.pages.dev` (proxied) plus whatever serves the apex.

### 1.6 Cloudflare Access / Zero Trust

**PARTLY NOT OBTAINED — the token has no Zero Trust scope.**

```
$ GET /accounts/542c…5326/access/apps            -> success: true, result: []   (scope-filtered, not truly empty)
$ GET /accounts/542c…5326/access/organizations   -> {"code":10000,"message":"Authentication error"}
$ GET /accounts/542c…5326/access/groups          -> {"code":10000,"message":"Authentication error"}
$ GET /accounts/542c…5326/access/identity_providers -> success: true, result: [] (same)
```

The empty `apps` list is a permissions artefact, not the truth — Access is demonstrably
active:

```
$ curl -sSL https://grace-demo.pages.dev/plan-your-visit/
HTTP 302 -> https://rapid-pond-2632.cloudflareaccess.com/cdn-cgi/access/login/grace-demo.pages.dev?...
```

**Independently established:** the Zero Trust **team domain is `rapid-pond-2632`**
(`rapid-pond-2632.cloudflareaccess.com`), and it gates `grace-demo.pages.dev`.

**NOT OBTAINED:** app name, covered domains list, policy name, session duration, identity
provider, allowed identities. Per HANDOFF §1 these are the app "grace-demo - Cloudflare
Pages" covering `*.grace-demo.pages.dev` and the apex, policy "Grace Demo Viewers", **two
named email addresses** via one-time PIN — but none of that was verifiable here and it is
recorded as documentation, not as observation.

**To complete this section, copy from the dashboard:** Cloudflare **Zero Trust** →
Access → Applications → the grace-demo app → Overview (domains, session duration, identity
providers) and Policies (name, action, include rules). Record the *count* of allowed
addresses, not the addresses.

### 1.7 Everything else in the account

| Resource | State |
|---|---|
| KV namespaces | **NONE** |
| D1 databases | **NONE** |
| Queues | **NONE** |
| Worker custom domains | **NONE** |
| R2 buckets | **NONE** — API returns "Please enable R2 through the Cloudflare Dashboard", i.e. R2 has never been turned on |
| Pages projects | 2, both listed above |
| Zone page rules (discovergrace.ai) | NOT OBTAINED — `Unauthorized to access requested resource` |
| Zone rulesets / WAF / redirects | NOT OBTAINED — `Authentication error` |
| Account rulesets | NOT OBTAINED — same |

So: **no state stores of any kind.** The whole system is stateless apart from the Sheet and
the Git history. The rules/WAF gaps are token-scope limitations; check
`discovergrace.ai → Rules` in the dashboard to close them.

---

## 2. GitHub

### 2.1 Repository

| Field | Value |
|---|---|
| nameWithOwner | `chrisrank01/grace-guest-assistant` |
| visibility | **PUBLIC** |
| default branch | `main` |
| isFork | false |
| isArchived | false |
| topics | none |
| description | none |
| license | none |
| created | 2026-08-27T13:13:48Z |
| last push | 2026-09-08T01:21:23Z |

### 2.2 Secrets (names only)

```
$ gh secret list
CLOUDFLARE_API_TOKEN    2026-08-28T00:36:02Z
GCP_SA_KEY              2026-08-28T00:38:40Z
NTFY_TOPIC              2026-08-28T17:11:09Z
```

```
$ gh variable list
(none)
```

Values are not retrievable through the API and were not sought.

### 2.3 Actions permissions

```
$ gh api repos/chrisrank01/grace-guest-assistant/actions/permissions
{"enabled":true,"allowed_actions":"all","sha_pinning_required":false}

$ gh api repos/chrisrank01/grace-guest-assistant/actions/permissions/workflow
{"default_workflow_permissions":"read","can_approve_pull_request_reviews":false}
```

Default token permission is `read`; the workflow raises it to `contents: write` explicitly.

### 2.4 Branch protection

```
$ gh api repos/chrisrank01/grace-guest-assistant/branches/main/protection
{"message":"Branch not protected","status":"404"}

$ gh api repos/chrisrank01/grace-guest-assistant/rulesets
[]
```

**There are no branch protection rules and no rulesets.** `main` accepts direct pushes and
force pushes from anyone with write access, and it is the branch CI deploys from.

### 2.5 `.github/workflows/`

One file: `.github/workflows/auto-publish.yml`, 11,449 bytes. Reproduced verbatim
(it contains no secret values — only `${{ secrets.NAME }}` references):

```yaml
name: auto-publish

# Ships approved Sheet content to the live widget without a human in the loop.
# The gates are: the Status column (HOLD never ships), publish.py's validator
# (exit 2 = nothing written), and a quiescence debounce so a half-finished edit
# cannot go out mid-typing.
#
# CADENCE: a Cloudflare cron we operate (worker-clock/) dispatches this every two
# hours. GitHub's own schedule: block below is a redundant backup - it has proven
# unreliable (16h / 7 consecutive ticks missed on 2026-08-28) and must not be
# treated as the primary clock.

on:
  schedule:
    - cron: '17 */2 * * *'     # BACKUP only. See note above.
  workflow_dispatch:
    inputs:
      force_publish:
        description: 'Skip the 30-minute quiescence debounce (dispatch only)'
        type: boolean
        default: false
      simulate:
        description: 'Test the notification paths without touching production'
        type: choice
        options: [none, failure, deploy_ping]
        default: none

concurrency:
  group: auto-publish
  cancel-in-progress: false  # queue runs; never let two deploys overlap

permissions:
  contents: write            # to commit the regenerated answers.json

jobs:
  # ---- backup-defers guard ---------------------------------------------
  # Every tick currently runs TWICE: the Cloudflare worker dispatches at :17:38
  # and GitHub's backup cron lands ~3 minutes later. Both do a full Sheet read,
  # and on a tick that actually deploys they can race - the second run's commit
  # is rejected non-fast-forward, which shows red and pushes a failure alert for
  # a publish that already succeeded (see HANDOFF INCIDENT LOG, run #2).
  #
  # So the BACKUP stands down when a run has already started recently. Two rules
  # that look arbitrary and are not:
  #   - Only `schedule` defers. A workflow_dispatch is the primary clock (or a
  #     human) and never skips, so this can never suppress a real publish.
  #   - It defers regardless of how that recent run TURNED OUT. The backup exists
  #     to cover a clock that never fired, not a publish that failed; a failed
  #     primary has already sent its own high-priority alert, and re-running it
  #     here would only duplicate the failure.
  # 45 min is comfortably above the observed ~3 min pairing gap and well under
  # the 2h cadence, so a genuinely missed tick always lets the backup through.
  guard:
    runs-on: ubuntu-latest
    permissions:
      actions: read            # list this workflow's runs; contents not needed
    outputs:
      skip: ${{ steps.check.outputs.skip }}
    steps:
      - name: Backup defers to a recent run
        id: check
        env:
          GH_TOKEN: ${{ github.token }}
          RUN_ID: ${{ github.run_id }}
          WINDOW_MIN: '45'
          WINDOW_SEC: '2700'
        run: |
          set -uo pipefail

          if [ "${{ github.event_name }}" != "schedule" ]; then
            echo "event=${{ github.event_name }} - primary clock, never defers"
            echo "skip=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          # The window is computed inside jq (`now`) rather than with `date -d`,
          # so the same expression runs unchanged on the Ubuntu runner and on a
          # BSD-date Mac - which is what lets the fixture harness exercise this
          # exact code instead of a reimplementation of it.
          RECENT="$(gh api \
            "repos/${{ github.repository }}/actions/workflows/auto-publish.yml/runs?per_page=50" \
            --jq '[.workflow_runs[]
                   | select(.id != (env.RUN_ID | tonumber))
                   | select(.run_started_at != null)
                   | select((.run_started_at | fromdateiso8601) > (now - (env.WINDOW_SEC | tonumber)))
                   | "\(.id) \(.run_started_at) \(.event) \(.status)/\(.conclusion)"] | .[]')" \
            || RECENT="__API_ERROR__"

          # Fail OPEN. A backup that runs when it did not need to costs one extra
          # Sheet read and reports nochange; a backup silently suppressed by an
          # API hiccup loses the tick with nothing to show for it.
          if [ "$RECENT" = "__API_ERROR__" ]; then
            echo "could not list runs - failing open, letting the backup proceed"
            echo "skip=false" >> "$GITHUB_OUTPUT"
            exit 0
          fi

          if [ -n "$RECENT" ]; then
            echo "$RECENT" | sed 's/^/  recent run: /'
            LINE="RESULT status=skipped_duplicate reason=recent_run"
            echo "$LINE"
            echo "$LINE" >> "$GITHUB_STEP_SUMMARY"
            echo "skip=true" >> "$GITHUB_OUTPUT"
          else
            echo "no run started in the last ${WINDOW_MIN}m - backup proceeding"
            echo "skip=false" >> "$GITHUB_OUTPUT"
          fi

  publish:
    needs: guard
    if: needs.guard.outputs.skip != 'true'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install Python deps
        run: pip install --quiet gspread google-auth

      - name: Install wrangler
        run: npm install --no-save wrangler@4

      # ---- simulation shortcuts ------------------------------------------
      # Exercise the notification wiring without reading the Sheet or deploying.
      - name: SIMULATE failure
        if: inputs.simulate == 'failure'
        run: |
          echo "SIMULATED failure - no Sheet read, no deploy"
          exit 1

      - name: SIMULATE deploy ping
        id: simping
        if: inputs.simulate == 'deploy_ping'
        run: |
          # Must publish the same `result_line` output the real Publish step does,
          # or the notify step below has nothing to match on and silently skips.
          LINE="RESULT status=deployed questions=SIMULATED warnings=0 changed=1"
          echo "$LINE"
          echo "result_line=$LINE" >> "$GITHUB_OUTPUT"
          echo "$LINE" >> "$GITHUB_STEP_SUMMARY"

      - name: Write service-account key to a private temp file
        if: inputs.simulate == 'none' || inputs.simulate == ''
        env:
          GCP_SA_KEY: ${{ secrets.GCP_SA_KEY }}
        run: |
          # Written outside the workspace so it can never be picked up by a
          # later `git add`. umask first so it is never briefly world-readable.
          umask 077
          KEY_FILE="$RUNNER_TEMP/grace-publisher.json"
          printf '%s' "$GCP_SA_KEY" > "$KEY_FILE"
          chmod 600 "$KEY_FILE"
          echo "GRACE_PUBLISHER_KEY=$KEY_FILE" >> "$GITHUB_ENV"
          # Never echo the key, its length, or any prefix of it.
          echo "key written to \$RUNNER_TEMP (contents not logged)"

      - name: Publish
        id: publish
        if: inputs.simulate == 'none' || inputs.simulate == ''
        env:
          GRACE_PUBLISHER_KEY: ${{ env.GRACE_PUBLISHER_KEY }}
          CLOUDFLARE_API_TOKEN: ${{ secrets.CLOUDFLARE_API_TOKEN }}
          PATH: ${{ github.workspace }}/node_modules/.bin:/usr/local/bin:/usr/bin:/bin
        run: |
          # force_publish is dispatch-only by construction: `inputs` is empty on a
          # schedule event, so the debounce can never be skipped by the clock.
          QUIET_MIN=30
          if [ "${{ inputs.force_publish }}" = "true" ] && [ "${{ github.event_name }}" = "workflow_dispatch" ]; then
            QUIET_MIN=0
            echo "force_publish: debounce skipped"
          fi
          set -o pipefail
          python publish.py --deploy --min-quiet-minutes "$QUIET_MIN" --quiet | tee publish.out
          RESULT_LINE="$(grep -m1 '^RESULT ' publish.out || echo 'RESULT status=unknown')"
          echo "result_line=$RESULT_LINE" >> "$GITHUB_OUTPUT"
          echo "$RESULT_LINE" >> "$GITHUB_STEP_SUMMARY"

      - name: Commit regenerated answers.json if it changed
        if: inputs.simulate == 'none' || inputs.simulate == ''
        run: |
          if git diff --quiet -- public/answers.json; then
            echo "no content change - nothing to commit"
            exit 0
          fi
          git config user.name  "grace-auto-publish"
          git config user.email "actions@users.noreply.github.com"
          git add public/answers.json
          git commit -m "auto-publish: $(date -u '+%Y-%m-%d %H:%M UTC')"
          # Another push can land mid-run (it has). Rebase and retry once rather
          # than failing a run whose deploy already succeeded.
          git pull --rebase --quiet origin main || true
          git push || (sleep 5 && git pull --rebase --quiet origin main && git push)

      # ---- notifications --------------------------------------------------
      - name: Notify on failure
        if: failure()
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
        run: |
          curl -s -m 20 \
            -H "Title: Grace publish FAILED" \
            -H "Priority: high" \
            -H "Tags: rotating_light" \
            -d "run ${{ github.run_id }} · $(date -u '+%Y-%m-%d %H:%M UTC') · see Actions log" \
            "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null || true

      # Reads whichever step produced a RESULT line - the real publish, or the
      # simulation. Matching only on steps.publish meant deploy_ping silently
      # tested nothing.
      - name: Notify on deploy
        if: >-
          success() &&
          (contains(steps.publish.outputs.result_line, 'status=deployed') ||
           contains(steps.simping.outputs.result_line, 'status=deployed'))
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
          RESULT_LINE: ${{ steps.publish.outputs.result_line || steps.simping.outputs.result_line }}
        run: |
          curl -s -m 20 \
            -H "Title: Grace published" \
            -H "Priority: default" \
            -H "Tags: white_check_mark" \
            -d "$RESULT_LINE · $(date -u '+%H:%M UTC')" \
            "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null || true

      # Min priority lists silently and never buzzes, so this is not a message
      # you read - it is a message whose ABSENCE you notice. A day with no line
      # means the clock, the workflow or the ntfy topic died, which is the one
      # failure mode nothing else here catches (HANDOFF, "Known gap": a clock
      # that never fires raises no alarm).
      # Once a day: the primary clock dispatches on even hours, so hour 12 UTC
      # matches exactly one dispatch (12:17) per day. The hour is checked in the
      # shell because workflow expressions have no access to the current time.
      - name: Daily heartbeat
        if: >-
          success() &&
          github.event_name == 'workflow_dispatch' &&
          (inputs.simulate == 'none' || inputs.simulate == '')
        env:
          NTFY_TOPIC: ${{ secrets.NTFY_TOPIC }}
          RESULT_LINE: ${{ steps.publish.outputs.result_line }}
        run: |
          HOUR="$(date -u '+%H')"
          if [ "$HOUR" != "12" ]; then
            echo "hour $HOUR UTC - not the heartbeat hour, nothing sent"
            exit 0
          fi
          curl -s -m 20 \
            -H "Title: Daily heartbeat" \
            -H "Priority: min" \
            -H "Tags: green_heart" \
            -d "${RESULT_LINE:-RESULT status=unknown} · $(date -u '+%Y-%m-%d %H:%M UTC')" \
            "https://ntfy.sh/${NTFY_TOPIC}" > /dev/null || true

      - name: Remove the key
        if: always()
        run: rm -f "$RUNNER_TEMP/grace-publisher.json"
```

### 2.6 Recent history

```
$ git log --oneline -20
b7f9697 Round the panel corners and pill the pinned buttons
a17667a Apply T Munroe design review: brand hexes, chip pill, launcher scale, Quincy Medium
014cae7 auto-publish: 2026-08-30 16:18 UTC
0f337f5 Pipeline hygiene: backup cron defers to a recent run, plus a daily silent heartbeat
9b6ebce Suppress the handoff echo (flag-gated) and stop the close button stealing focus
9186d6c Widget experiment (DEFAULT OFF): hide tapped questions, exhaustion hands off to a person
72e32b4 Stop the nightly date-stamp deploy: exclude _editorNote from the change compare
a18be09 auto-publish: 2026-08-29 00:18 UTC
ce82b6e Record Figma production-reference file; flag three token-card errors
23d5d3c session state 2026-08-28 — build complete, chat continuity
f9d6f4c handoff documentation
747930d Fix: simulate=deploy_ping never fired the success notification
611c77f Hardening: reliable clock worker, publish gates, NTFY alerts, tools/
328bdc1 auto-publish: 2026-08-28 17:17 UTC
2d00cb2 session state 2026-08-27
856d6b5 auto-publish: 2026-08-28 00:49 UTC
a30ed69 Auto-publish: scheduled Sheet->production pipeline
0f0d0d3 Phase 5: Sheet->production publish pipeline + deployed widget/worker source
1452704 Add widget, gitignore corpus and .DS_Store
eb28a17 Initial project scaffold
```

Only 4 of 20 commits are `auto-publish` — the pipeline has published four times in eleven
days. Everything else is hand-authored.

---

## 3. Google

### 3.1 The Sheet

| Field | Value |
|---|---|
| fileId | `1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY` |
| **actual title** | **`grace-assistant-corpus-2026-08-27`** |
| mimeType | `application/vnd.google-apps.spreadsheet` |
| owner | `chris@relax-tech.com` |
| created | 2026-08-27T15:09:41.651Z |
| last modified | 2026-08-30T14:08:03.969Z |
| shared | true |

Tabs, in order: **`READ ME`, `ANSWERS`, `PLACEMENT`, `FLAGS`, `CHANGE LOG`**

### 3.2 ANSWERS

Header row **4**; data from row 5. Grid 1000×26; 74 populated rows; **70 data rows**.

| Col | Header (verbatim) |
|---|---|
| A | `ID` |
| B | `Slug` |
| C | `Page` |
| D | `Tap Question (guest sees)` |
| E | `Answer Text (pre-approved)` |
| F | `Primary Action → Destination` |
| G | `Topic Tags` |
| H | `Status` |
| I | `Source / Notes` |
| J | `Follow-up IDs (slugs)` |

The arrow in column F is U+2192.

**By Status:** `DRAFT: 48`, `HOLD: 22`. **There are zero APPROVED rows.**

**By Page:** Plan Your Visit 7 · Giving 6 · GraceKids 6 · Family Ministry 6 · Homepage 5 ·
Care 5 · Start Here 5 · GraceStudents 4 · Orlando 3 · Serving 3 · Groups 3 · Baptism 3 ·
About Grace 3 · Online 2 · (any page) 2 · Events 2 · Grace Does Good 2 · Classes 2 ·
Contact 1

### 3.3 PLACEMENT

Header row **4**; data from row 5. Grid 1002×26; 31 populated rows; **27 data rows**.

| Col | Header (verbatim) |
|---|---|
| A | `Page` |
| B | `URL path` |
| C | `Show / Hide` |
| D | `Starter question IDs (3–5)` |
| E | `Why` |

**By Show / Hide:** `SHOW: 17`, `HIDE: 9`, blank: 1 (the `——— HIDE below ———` separator row).

27 distinct URL-path values, including glob forms used for the HIDE rows
(`/sermons/, /sermon/*`, `/watch/*`, `*.churchcenter.com/*`, `*`, and a blank on the
separator row).

### 3.4 Service account

| Field | Value |
|---|---|
| client_email | `grace-publisher@flowing-sign-487115-t3.iam.gserviceaccount.com` |
| GCP project id | `flowing-sign-487115-t3` |
| GCP project number | `450055151257` — **per HANDOFF §2; not independently verified** (the SA cannot read project metadata) |
| type | `service_account` |
| private_key / private_key_id | `<REDACTED>` |
| local key file | `secrets/grace-publisher.json`, 2,390 bytes, mode `600`, gitignored via `secrets/` |

**OAuth scopes**, read from `publish.py` L86 (not from memory):

```python
SCOPES = [
    'https://www.googleapis.com/auth/spreadsheets.readonly',
    # Needed only for the quiescence debounce (Drive file modifiedTime).
    # Requires the Drive API to be enabled on the GCP project as well.
    'https://www.googleapis.com/auth/drive.metadata.readonly',
]
```

`smoke_test.py` requests a narrower set — `spreadsheets.readonly` only.

**Enabled APIs: NOT OBTAINED** — `serviceusage.googleapis.com` returns HTTP 403
`Request had insufficient authentication scopes`; the SA holds only the two read scopes
above. *Inferred from behaviour:* both the **Sheets API** and the **Drive API** are enabled,
because live calls to each succeeded during this sweep. To confirm the full list, use the
GCP console → project `flowing-sign-487115-t3` → APIs & Services → Enabled APIs.

### 3.5 The service account's role on the Sheet

**Viewer — verified, with no write attempted.**

```
$ GET https://www.googleapis.com/drive/v3/files/{fileId}?fields=capabilities(...)
capabilities: {'canComment': False, 'canDownload': True, 'canEdit': False, 'canShare': False}
```

`canEdit: False` is Drive reporting the authenticated principal's own permission, so it is
direct evidence rather than an inference. This is a **better check than the one HANDOFF
documents** (attempt a no-op write, expect 403): it is read-only, instant, and cannot
accidentally succeed.

Listing the file's full permission set returns HTTP 403 (`drive.metadata.readonly` is not
sufficient), so the *other* principals on the Sheet are **NOT OBTAINED** — read them from
the Sheet's Share dialog.

Note the SA is doubly constrained: even were it promoted to Editor, its OAuth scope is
`spreadsheets.readonly`, so `publish.py` still could not write.

---

## 4. The repo, file by file

### 4.1 Tracked files (25 files, 275,574 bytes)

```
    11449  .github/workflows/auto-publish.yml
      200  .gitignore
    17264  HANDOFF.md
    11079  PUBLISHING.md
      104  README.md
    30145  SESSION-2026-08-27.md
    18046  SESSION-2026-08-28.md
      469  public/_headers
     7218  public/answers.json
    36692  public/fonts/QuincyCF-Medium.woff2
    43293  public/grace-assistant.js
     6176  public/test.html
    25469  publish.py
     8318  reports/phase3-widget-build.md
      863  smoke_test.py
     5578  tools/sheet_amend_f.py
     5921  tools/sheet_normalize_show.py
     9094  tools/sheet_remap.py
     3637  tools/sheet_validation.py
     5217  tools/sheet_validation2.py
    16435  tools/sheet_write.py
     2783  worker-clock/src/index.js
      323  worker-clock/wrangler.toml
     9713  worker/src/index.js
       88  worker/wrangler.toml
```

### 4.2 `.gitignore` verbatim

```
node_modules/
.dev.vars
*.key
*.json.key
secrets/
.env
*.local
corpus/
.DS_Store
demo-site/
.venv/
build/
*service-account*.json
__pycache__/
*.pyc
.dev.vars*
.wrangler/
*.swp
*.swo
*~
demo-site-raw/
```

Line 2 (`.dev.vars`) and line 16 (`.dev.vars*`) overlap — line 16 is the widened pattern
added after the swap-file near-miss (HANDOFF §6); line 2 is now redundant but harmless.

### 4.3 Untracked files

```
$ git status --porcelain --untracked-files=all | grep '^??'
?? GRACE-WIDGET-BUILD-STATE-2026-08-27.md
```

One file, 6,277 bytes, dated 2026-08-27. **Should it be tracked?** It is a build-state
snapshot from day one and is superseded by `SESSION-2026-08-27.md` (30,145 bytes, tracked)
which covers the same day in far more depth. Recommendation: **delete it, or track it** —
leaving it untracked means it is invisible to anyone who clones, and it will keep showing up
as noise in every `git status` (it has done so in every session this week).

Ignored-but-present directories of note: `.venv/`, `build/`, `corpus/`, `demo-site/`,
`demo-site-raw/`, `.wrangler/`, plus `worker/.dev.vars` — see §6.

### 4.4 `publish.py` (25,469 bytes)

#### Module-level constants

| Constant | Line | Value |
|---|---|---|
| `SHEET_KEY` | 29 | `'1uxB85U-lRTZo75eGdmB23PAvJ2jdyLvvezaQIzaaekY'` |
| `KEY_PATH` | 33 | `os.environ.get('GRACE_PUBLISHER_KEY', 'secrets/grace-publisher.json')` |
| `PILOT_ROUTES` | 37 | `['/plan-your-visit/', '/giving/']` |
| `SHIP_STATUSES` | 42 | `{'DRAFT', 'APPROVED'}` |
| `TALK_PERSON_SLUG` | 75 | `'talk-person'` |
| `COL_Q` | 79 | `'Tap Question (guest sees)'` |
| `COL_A` | 80 | `'Answer Text (pre-approved)'` |
| `COL_LINK` | 81 | `'Primary Action → Destination'` |
| `COL_STATUS` | 82 | `'Status'` |
| `COL_FOLLOWUPS` | 83 | `'Follow-up IDs (slugs)'` |
| `HEADER_ROW` | 85 | `4` (1-indexed; data starts at row 5) |
| `OUT_BUILD` | 92 | `'build/answers.json'` |
| `OUT_PUBLIC` | 93 | `'public/answers.json'` |
| `PAGES_PROJECT` | 94 | `'grace-assistant'` |
| `LIVE_URL` | 95 | `'https://grace-assistant.pages.dev/grace-assistant.js'` |
| `LIVE_JSON` | 96 | `'https://grace-assistant.pages.dev/answers.json'` |
| `WARNINGS` | 98 | `[]` |
| `FATAL` | 99 | `[]` |
| `QUIET` | 100 | `False` |

`GLOBAL_META` (L45):

```python
{'title': 'Grace', 'subtitle': 'Guest Assistant', 'launcherLabel': 'Ask Grace',
 'startersLabel': 'Common questions', 'followupsLabel': 'WOULD YOU ALSO LIKE TO KNOW',
 'footerHint': 'Tap a question — no typing needed', 'restartLabel': 'Start over',
 'homeLabel': '← Back'}
```

`ROUTE_META_FALLBACK` (L60):

```python
{'/plan-your-visit/': {'title': 'Planning your visit',
                       'launcherLabel': 'Planning a visit? Tap here',
                       'intro': "Glad you're planning a visit. Tap a question and we'll help you get ready."},
 '/giving/':          {'title': 'Giving at Grace',
                       'launcherLabel': 'Questions about giving? Tap here',
                       'intro': "Thanks for your generosity. Here's how giving works at Grace."}}
```

`SCOPES` (L86) is quoted in §3.4.

#### CLI flags

| Flag | Type | Help text |
|---|---|---|
| `--deploy` | store_true | `copy to public/ and ship (default is dry run)` |
| `--min-quiet-minutes N` | int, default 0 | `skip the run if the Sheet was edited less than N minutes ago, so a half-finished edit never ships` |
| `--quiet` | store_true | `machine-readable summary lines only` |

#### Functions

| Line | Function | What it does |
|---|---|---|
| 103 | `say(msg)` | Chatter — suppressed under `--quiet` |
| 109 | `result(**fields)` | Prints the single machine-readable `RESULT …` line; never contains credential material |
| 115 | `warn(msg)` | Appends to `WARNINGS`; non-fatal |
| 120 | `fatal(msg)` | Appends to `FATAL`; collected so one run reports every problem at once |
| 127 | `norm(value)` | Trim — Sheet cells routinely carry stray whitespace |
| 132 | `fold(value)` | Trim + casefold, for case-insensitive comparison |
| 137 | `die(problems)` | Prints the collected fatals and exits **2** |
| 148 | `sheet_modified_minutes_ago()` | Minutes since the Sheet was last edited, via the Drive API — drives the debounce |
| 170 | `open_sheet()` | Authorises with the SA key and opens the spreadsheet; exits with a message if the key is missing |
| 179 | `tabulate(values, header_row)` | Rows below the header as dicts keyed by header name |
| 190 | `read_placement(sh)` | SHOW rows whose URL path is in `PILOT_ROUTES` → route config |
| 224 | `parse_one_link(seg, slug)` | One `Label -> destination` segment → `{label, href}` or None |
| 247 | `parse_links(raw, slug)` | A Primary Action cell → list of links; multiple actions separated |
| 258 | `build(sh)` | Reads ANSWERS + PLACEMENT and assembles the whole `answers.json` document |
| 373 | `validate(doc, page_slugs)` | All content invariants; populates `FATAL`/`WARNINGS` |
| 434 | `dump(doc, path)` | Writes the JSON document |
| 441 | `_without_editor_note(lines, label)` | Drops the `_editorNote` line so a date-only change is not a change |
| 478 | `unified(old_path, new_path, ignore_editor_note)` | Unified text diff |
| 487 | `semantic(old_path, new_doc)` | Field-level semantic diff |
| 518 | `deploy()` | Copies build→public, runs wrangler, then verifies the live md5 **twice**, cache-busted |
| 540 | `main()` | Arg parsing, debounce, diff, deploy/report |

#### `RESULT status=` values

| Value | Where | Meaning |
|---|---|---|
| `quiescence_check_failed` | L561 | Drive API / scope problem — exits **3**, nothing published |
| `debounced` | L565 | Sheet edited inside the quiet window — exits **0**, healthy no-op |
| `nochange` | L587 | Content identical to what is live |
| `deployed` | L596 | Content changed and was shipped |
| `would_change` | L599 | Dry run; content would change |
| `unknown` | workflow L177 | Fallback the workflow substitutes when no `RESULT` line was printed |
| `skipped_duplicate` | workflow L100 | Emitted by the guard job, not by `publish.py` |

#### Exit codes

| Code | Line | Cause |
|---|---|---|
| **0** | 567 and normal return | Success, including `debounced` and `nochange` |
| **2** | 141 (`die`) | Validation refused — nothing written, nothing deployed |
| **3** | 562 | Quiescence check failed |
| *(message)* | 174 | `sys.exit(f'no service-account key at {KEY_PATH} …')` — exits **1** with a string |

#### Deploy verification (L518-539)

```python
subprocess.run(['npx', 'wrangler', 'pages', 'deploy', 'public',
                '--project-name', PAGES_PROJECT, '--branch', 'main'], check=True)
```

then two cache-busted `curl` md5 checks, 3 s apart, against `LIVE_JSON`, plus a
`'Grace' in text` sanity check. **Note it deploys the whole `public` directory** — see §6.

### 4.5 `worker/src/index.js` (9,713 bytes) — grace-assistant-router

**Contract:** `POST { page, tappedId, history, candidateIds }` → **always HTTP 200**
`{ ids: [...] }`.

Two invariants stated in the header comment and enforced in code:
1. Only IDs that arrived in `candidateIds` can be returned — constrained by JSON-schema
   `enum` at decode time *and* filtered again in `filterToApproved()`.
2. It never returns non-200. Every failure path — bad JSON, missing key, API down, timeout,
   refusal, garbage — returns `{ ids: [] }`.

| Constant | Value |
|---|---|
| `ANTHROPIC_API_URL` | `https://api.anthropic.com/v1/messages` |
| `ANTHROPIC_VERSION` | `2023-06-01` |
| **`DEFAULT_MODEL`** | **`claude-haiku-4-5`** (overridable by a `MODEL` env var, which is **not set**) |
| `API_TIMEOUT_MS` | 5000 |
| `MAX_TOKENS` | 256 |
| `MAX_IDS` / `MIN_IDS` | 3 / 2 |
| `MAX_CANDIDATES` | 40 |
| `MAX_HISTORY` | 10 |

Origin allowlist, verbatim:

```javascript
const ALLOWED_ORIGINS = [
  'https://discovergrace.com',
  'https://www.discovergrace.com',
  'https://grace-assistant.pages.dev',
  'https://assistant.discovergrace.ai',
  'https://grace-demo.pages.dev'
];
```

One list feeds two separate concerns: `corsHeaders()` (what a browser may **read**, echoing
the origin back and setting `Vary: Origin`) and `originAllowed()` (whether we **spend** an
API call). **A missing Origin header is rejected**, so a bare `curl` always gets
`{"ids":[]}` — manual testing needs `-H "Origin: https://discovergrace.com"`.

Verified live during this sweep, without spending a call:

```
GET  /                                       -> 200 {"ids":[]}
OPTIONS, Origin: https://discovergrace.com   -> access-control-allow-origin: https://discovergrace.com
OPTIONS, Origin: https://evil.example.com    -> (no ACAO header)
```

Failure behaviour: `catch` logs only `err.name` (`console.log('router fallback:', …)`), never
the key or the request. Non-POST methods return the same empty contract rather than an error.

### 4.6 `worker-clock/src/index.js` (2,783 bytes) — grace-publish-clock

**Contract:** on `scheduled` (cron `17 */2 * * *`) it POSTs a `workflow_dispatch` to
`https://api.github.com/repos/chrisrank01/grace-guest-assistant/actions/workflows/auto-publish.yml/dispatches`
with body `{ref: 'main'}`. On `fetch` (any HTTP request) it does **the same thing** and
returns `{ok, status}` as JSON.

Constants: `OWNER = 'chrisrank01'`, `REPO = 'grace-guest-assistant'`,
`WORKFLOW = 'auto-publish.yml'`.

Failure behaviour: no token, a thrown fetch, or a non-OK response each fire an ntfy alert
titled `Grace clock: dispatch FAILED` at **high** priority with `Tags: rotating_light`. The
alert body carries only the HTTP status and an ISO timestamp — never the token, never the
response text. An alert that itself fails is swallowed.

**Not probed during this inventory:** a bare GET on this Worker fires a real
`workflow_dispatch`. See §6.

### 4.7 `tools/` — six one-off Sheet writers

Every one is marked `NOT part of the publish path`, requires the service account temporarily
promoted to **Editor**, and **defaults to a dry run** (nothing is written without `--apply`).

| File | Bytes | What it did |
|---|---|---|
| `sheet_amend_f.py` | 5,578 | Amendment F — two PLACEMENT URL-path corrections + two new SHOW rows. Widens the strict `ONE_OF_LIST` rule first, because the frozen allowed-set would reject the new paths |
| `sheet_normalize_show.py` | 5,921 | Normalised PLACEMENT `Show / Hide` to `SHOW|HIDE` and applied a strict dropdown; the condition that lived inside the value moved to `Why` |
| `sheet_remap.py` | 9,094 | Fixed 8 F-row answer/question mismatches, added 18 slugs. Rotations resolved against a pre-write snapshot so a 3-cycle cannot clobber its own source |
| `sheet_validation.py` | 3,637 | Strict dropdown on `ANSWERS.Status`, allowed list derived from what is actually present plus `APPROVED` |
| `sheet_validation2.py` | 5,217 | Dropdowns on `ANSWERS.Page` and `PLACEMENT.URL path`; warning-only fence on `ANSWERS.Slug` |
| `sheet_write.py` | 16,435 | Link harvest into 11 cells, 18 draft answers, notes banking. Every cell read first and guarded: links must match expected-old, answers must be EMPTY, notes/FLAGS append never overwrite |

**All six write.** They are historical one-offs from 2026-08-28 and none is wired into any
automation.

### 4.8 Other tracked files

- `smoke_test.py` (863 B) — auth smoke test; prints `client_email`, spreadsheet title,
  worksheet names, ANSWERS row count. Read-only, scope `spreadsheets.readonly`.
- `README.md` (104 B) — two lines: *"Static guided website assistant for discovergrace.com.
  No secrets in this repo."*
- `reports/phase3-widget-build.md` (8,318 B) — the 2026-08-27 widget build report.
- `HANDOFF.md`, `PUBLISHING.md`, `SESSION-2026-08-27.md`, `SESSION-2026-08-28.md` — narrative
  documentation. See §6 for where they have gone stale.

---

## 5. The widget

### 5.1 `public/grace-assistant.js`

| | |
|---|---|
| lines | **936** |
| bytes | 43,293 |
| **md5** | **`bd080ac809a6a05df4e242d7ad54adac`** |

Confirmed byte-identical on both hostnames and in `main` at the time of writing.

### 5.2 `data-` attributes read

| Attribute | Line | Default | Notes |
|---|---|---|---|
| `data-answers` | 24 | `'answers.json'` | Resolved against the **host page**, so the go-live snippet must give it absolutely |
| `data-router` | 37 | `''` | **Empty string = the router is never called.** The enhancement is opt-in per embed |
| `data-route` | 444 | — | Forces a route; falls back to `?ga-route=` then `window.location.pathname` |

### 5.3 Top-level constants

| Line | Constant | Value |
|---|---|---|
| 24 | `ANSWERS_URL` | `data-answers` or `'answers.json'` |
| 31 | `ASSET_BASE` | `new URL('.', script.src).href` — absolute dir of this script; `''` on failure |
| 37 | `ROUTER_URL` | `data-router` or `''` |
| 38 | `ROUTER_TIMEOUT_MS` | `2000` |
| 45 | `HIDE_TAPPED` | `/[?&]ga-hide-tapped=1(?:&|$)/.test(window.location.search)` |
| 51 | `EXHAUSTION_NOTE` | `'That covers everything I can answer here. Want to talk with a real person?'` (PROVISIONAL, hardcoded) |
| 54 | `NAVY` | `'#282E39'` |
| 55 | `ORANGE` | `'#FF5500'` |
| 56 | `CREAM` | `'#FAFAF7'` |
| 57 | `RADIUS` | `'4px'` |
| 59 | `HOME_ID` | `'__home'` |
| 60 | `TALK_PERSON_ID` | `'talk-person'` |
| 80 | `SYSTEM` | `-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif` |
| 81 | `SERIF` | `'quincy-medium', 'quincy-black', 'Times New Roman', serif` |
| 82 | `SANS` | `'greyclif-regular', ` + SYSTEM |
| 83 | `SANS_MED` | `'greycliff-demi', 'greycliff-bold', 'greyclif-regular', ` + SYSTEM |
| 123 | `CROSS_SVG` | The 5-dot monogram, `viewBox="0 0 44 44"` |
| 132 | `CLOSE_SVG` | The X, `viewBox="0 0 24 24"` |
| 144 | `FONT_FACE` | The single `@font-face` for `quincy-medium` |
| 153 | `CSS` | The stylesheet array — 257 lines when joined |

Radius values not covered by `RADIUS`: `.panel` **16px** (a proposed value, flagged in a code
comment), `.chip` and `.pin-btn` **999px**, `.launcher-pill` and the scrollbar thumb 999px,
`.launcher-bug` 50%, `.launcher` wrapper and the mobile `.panel` 0.

`greyclif-regular` is spelled with one `f` deliberately — that is verbatim how Grace's own
CSS registers it. The comment at L65-79 records that one of Grace's five faces
(`greycliff-cf`, from `4619Greycliff-CF.woff2`) is a **trial cut** that reports family
`FSP DEMO - Greycliff CF` and watermarks the apostrophe, which is why the widget must never
name it.

### 5.4 Functions (26)

| Line | Function | Purpose |
|---|---|---|
| 89 | `queryRoute()` | Reads the `?ga-route=` override |
| 94 | `normalize(path)` | Canonicalises a path for matching |
| 102 | `pickRoute(routes, path)` | Path → route config, or nothing |
| 441 | `build(data)` | Constructs the entire widget: host, shadow root, styles, panel, launcher, handlers |
| 542 | `askedBubble(text)` | Renders the guest-side echo bubble |
| 548 | `answerBubble(node)` | Renders the church-side answer, its links and captions |
| 578 | `destinationCaption(link)` | Muted line under each action saying where it actually goes |
| 597 | `renderOptions(ids, atHome, labelOverride, isHomeCard)` | Renders the chip list; applies the `HIDE_TAPPED` filter |
| 643 | `enterExhaustion()` | Flag-gated hand-off to a person when nothing is left to ask |
| 657 | `renderPinned(atHome)` | The fixed two-button row: Back (answer views only) and Talk to a person |
| 672 | `pinButton(label, extraClass, onClick)` | One pinned button |
| 679 | `chip(label, id, ghost)` | One question chip |
| 691 | `resetScroll()` | Returns the card to the top |
| 697 | `updateEdgeFade()` | Bottom fade, only while content remains below the fold |
| 703 | `goHome()` | Back — returns to the starters card at the top |
| 724 | `markPointer()` | Records that the last input was a pointer |
| 725 | `markKeyboard(event)` | Records that the last input was the keyboard |
| 742 | `rankFollowups(tappedId, followups)` | Optional router call to reorder follow-ups |
| 779 | `select(id, opts)` | The core transition; `opts.suppressEcho` drops the guest bubble |
| 829 | `focusFirstOption()` | Keyboard-only focus move |
| 835 | `seed()` | Renders the initial home card |
| 855 | `open()` | Opens the panel |
| 871 | `close()` | Closes it; returns focus only if the last input was the keyboard |
| 910 | `el(tag, className, text)` | Element helper |
| 917 | `start()` | Fetches `answers.json` and calls `build()` |

### 5.5 CSS selectors (86)

```
:host · *, *::before, *::after · .wrap · .launcher · .launcher-pill · .launcher-bug
.launcher:focus · .launcher:focus-visible · .launcher-pill, .launcher-bug
.launcher:active .launcher-bug · .launcher:active .launcher-pill
.launcher:focus-visible .launcher-bug · .launcher:focus-visible .launcher-pill
.launcher-bug svg · .launcher .icon-close · .panel · .panel.is-visible · .panel.is-open
.head · .mark · .mark svg · .head-text · .head-title · .head-sub · .route-heading
.close · .close:active · .close:focus-visible · .close svg · .scroll · .scroll.at-end
.scroll::-webkit-scrollbar · .scroll::-webkit-scrollbar-track
.scroll::-webkit-scrollbar-thumb · .scroll::-webkit-scrollbar-thumb:hover
.feed · .row · .row.from-guest · .row.from-church · .bubble · .from-guest .bubble
.from-church .bubble · .bubble p + p · .bubble a · .bubble a.primary · .bubble a.secondary
.bubble a.primary:active · .bubble a.secondary:active · .bubble a:focus-visible
.links · .link-wrap · .link-caption · .intro · .bubble.is-intro · .options · .options-label
.chip · .chip:active · .chip:focus-visible · .chip .text · .chip .caret · .chip.ghost
.chip.ghost:active · .pinned · .pin-btn · .pin-btn.person · .pin-btn:active
.pin-btn.person:active · .pin-btn:focus-visible · .foot · .restart · .restart:active
.restart:focus-visible · .wrap.is-open .launcher
```

Plus, inside `@media (hover: hover)`: `.launcher:hover .launcher-bug`,
`.launcher:hover .launcher-pill`, `.close:hover`, `.bubble a.primary:hover`,
`.bubble a.secondary:hover`, `.chip:hover`, `.chip.ghost:hover`, `.restart:hover`,
`.pin-btn:hover`, `.pin-btn.person:hover`; and inside
`@media (prefers-reduced-motion: reduce)`: `.panel, .launcher-pill, .launcher-bug, .chip`.

At-rules: `@font-face`, `@media (max-width: 480px)` (×2), `@supports (height: 100dvh)`,
`@media (hover: hover)`, `@media (prefers-reduced-motion: reduce)`.

### 5.6 The `ga-hide-tapped` flag

**How it is read** — L45, query string only, on the **host page** URL:

```javascript
var HIDE_TAPPED = /[?&]ga-hide-tapped=1(?:&|$)/.test(window.location.search);
```

Query-only and hyphenated to match the existing `?ga-route=` idiom. There is no attribute,
cookie or storage form.

**What it changes** (5 call sites, every one written as `HIDE_TAPPED && …`):

| Line | Effect |
|---|---|
| 605 | A tapped question stops rendering as a chip anywhere for the rest of the pageview |
| 615 | When the visible list *and* the starter pool are both empty, the exhaustion note plus the talk-to-a-person card render |
| 623 | Controls whether the options block renders at all when the visible list is empty |
| 787 | Records a tap in the `tapped` map — **except** `talk-person`, which is exempt |
| 801 | Filters the follow-up list, which is also what the router POST now sends |

**What it does not change:** nothing at all with the flag absent. Flag-off rendering is
byte-identical to the pre-experiment widget — re-verified twice during the 2026-09-07/08
design passes by driving the panel to exhaustion under both settings and diffing the shadow
DOM at every step (26 steps flag-off, 8 flag-on, zero mismatches). It touches no
`localStorage`, `sessionStorage` or cookies — state is two closure variables and a reload is
the reset. `Start over` clears both; `Back` clears neither, because Back is navigation, not a
reset.

### 5.7 `public/_headers` verbatim (469 bytes)

```
/*
  X-Robots-Tag: noindex

# The widget is embedded cross-origin by design - the script and this font are
# served from assistant.discovergrace.ai / grace-assistant.pages.dev while the
# page is discovergrace.com or grace-demo.pages.dev. Fonts are ALWAYS fetched in
# CORS mode, whatever the markup says, so without this the browser blocks the
# file and the heading silently falls back to quincy-black with no console error.
/fonts/*
  Access-Control-Allow-Origin: *
```

Cloudflare Pages *also* sends `access-control-allow-origin: *` on static assets by default —
verified live on `answers.json`, which has always been fetched cross-origin without an
explicit rule. The `/fonts/*` rule makes the requirement explicit rather than inherited.

### 5.8 `public/fonts/`

```
36692  QuincyCF-Medium.woff2
```

md5 `fa9c8f9735eeabbdf45a0297405f7aee`. Converted 2026-09-07 from `QuincyCF-Medium.otf`
(61,492 B, md5 `315a28b1b7d5b06dc87f60f086614db5`) out of
`~/Library/Mobile Documents/com~apple~CloudDocs/GraceFonts/Quincy CF v4.1 OTF.zip (Unzipped Files)/`,
using the repo's own `.venv` fontTools 4.63.0 + brotli. Internal name `Quincy CF Medium`,
subfamily `Regular`, OS/2 weight 500, OTTO/CFF outlines, 497 glyphs, designer Connary Fagen,
version 4.100.

Served on both hostnames at `/fonts/QuincyCF-Medium.woff2` with
`content-type: font/woff2`, `access-control-allow-origin: *`, `x-robots-tag: noindex`.
This is the **only** font file the widget ships; every other family is pinned to a face
Grace already registers document-wide.

### 5.9 `public/test.html`

**Yes — it still exists, and it is still live.** 6,176 bytes, tracked in git.

```
https://assistant.discovergrace.ai/test.html -> HTTP 308 -> /test -> HTTP 200, 6176 bytes
(page body still contains the "TEST PAGE" banner; x-robots-tag: noindex is applied)
```

Cloudflare Pages strips the `.html` and 308-redirects, so the harness is reachable at
`/test` on **both** hostnames. It remains an open item on the HANDOFF teardown checklist.

---

## 6. Things you found that this prompt did not ask about

Ordered roughly by how much they would cost someone who did not know them.

### 6.1 A bare GET on the clock Worker triggers a real publish run — unauthenticated, public

`worker-clock/src/index.js` exports a `fetch` handler that calls the same `dispatch(env)` the
cron does:

```javascript
async fetch(request, env) {
  const result = await dispatch(env);
  return new Response(JSON.stringify(result), { … });
}
```

There is no method check, no shared secret, no origin check, and `workers.dev` is
**enabled**. Anyone who learns
`https://grace-publish-clock.relax-tech.workers.dev` can fire an unlimited number of
`workflow_dispatch` events — each one a full Sheet read, a wrangler install and a possible
deploy. The URL is printed in `HANDOFF.md`, which is in a **public** repo.

It is documented as a convenience ("Manual probe … handy for proving the token works"), but
neither HANDOFF nor PUBLISHING notes that it is unauthenticated. Cheapest fixes: require a
header the caller must know, restrict `fetch` to `POST`, or disable the `workers.dev` route
and keep only the cron trigger. **I deliberately did not probe this Worker during this
inventory** for exactly this reason.

### 6.2 A hand deploy ships the whole `public/` directory — this has already caused a live regression

`wrangler pages deploy public` uploads the directory, not a diff. On 2026-09-08 a hand deploy
from a working tree whose `answers.json` was a week stale reverted two of T's published copy
edits (`"make arrival easy"` for `"make arrival simple"`, `"GraceKids"` for `"GraceKids!"`)
and they were live for roughly twenty minutes. It was caught only because the subsequent
`git push` was rejected.

The guard now in use, and worth writing into PUBLISHING.md:

```
git fetch && git diff --quiet origin/main -- public/answers.json
```

The same shape of hazard runs the other way: while a hand-authored widget change sits
uncommitted, the next content publish deploys `main`'s copy of `public/` and silently reverts
it. `publish.py` only calls `deploy()` when `answers.json` actually changed, so the revert
waits for T's next Sheet edit rather than the next tick — which makes it *less* likely to be
noticed, not more.

### 6.3 The model id in HANDOFF does not match the code

HANDOFF §1 says the router uses `claude-haiku-4-5-20251001`. `worker/src/index.js` L28 sets
`DEFAULT_MODEL = 'claude-haiku-4-5'` and no `MODEL` env var is set on the Worker (confirmed:
its only binding is `ANTHROPIC_API_KEY`). The alias, not the dated snapshot, is what runs —
so the model **can move under the Worker** when Anthropic repoints the alias. That is a real
behavioural difference from what the documentation promises, and worth a deliberate decision
either way.

### 6.4 The Sheet's real name is not the name in the docs

Every document says **grace-assistant-corpus**. The file is actually titled
**`grace-assistant-corpus-2026-08-27`**. The fileId is correct everywhere, so nothing breaks —
but anyone searching Drive by name will not find it.

### 6.5 The incident log's arithmetic is wrong, and the two docs disagree

HANDOFF §6 says the GitHub scheduler missed **"nine consecutive missed ticks"** over
**16 hours**. PUBLISHING.md L21 and the workflow's own header comment both say **7
consecutive ticks over 16 hours**. At a 2-hour cadence, 16 hours cannot contain nine ticks —
eight is the ceiling. HANDOFF is the wrong one. Minor, but it is the flagship lesson in the
incident log and it should not be the number that fails a sanity check.

### 6.6 HANDOFF's "Known gap" was closed and never updated

HANDOFF §1 still reads: *"a clock that never fires produces no failed run and therefore no
alert … A 'no successful publish in N hours' check is the missing piece"*, and the teardown
checklist still carries *"Consider a 'no successful publish in N hours' watchdog"*. Commit
`0f337f5` added the daily min-priority heartbeat at hour 12 UTC precisely to close this. The
gap is now *narrowed* rather than fully closed — the heartbeat proves liveness once a day,
and its absence is the signal — but the docs describe a state that no longer exists.

### 6.7 HANDOFF's file list is out of date

*"Serves three files plus `_headers`"* — the origin now serves **four** files plus `_headers`
plus a `fonts/` directory: `grace-assistant.js`, `answers.json`, `test.html`,
`fonts/QuincyCF-Medium.woff2`. The widget also no longer "ships no fonts", which that section
states explicitly and which a code comment inside the widget used to repeat.

### 6.8 A live Anthropic API key sits in plaintext at `worker/.dev.vars`

127 bytes, one key: `ANTHROPIC_API_KEY`. Correctly gitignored (`.gitignore:16` → `.dev.vars*`)
and confirmed untracked. But the rotation checklist in HANDOFF §5 names only the Worker
secret and the terminal-scrollback/Vim-swap exposures — it does not mention that a working
copy is on this laptop's disk. When the key is rotated, this file has to be updated or
deleted too, or local `wrangler dev` will silently keep using a dead key.

### 6.9 Nothing protects `main`, and CI deploys from it

No branch protection, no rulesets, `allowed_actions: all`, and the repo is **public**. A
force-push to `main` is both possible and directly load-bearing: the next auto-publish
checks out `main` and deploys its `public/` to production.

### 6.10 The `Source` column in Pages deployment lists is not trustworthy

`a487bddd` and `cc05d33e` both report source `a17667a`, but only one carries the correct
`answers.json` — deployments from a dirty tree inherit the last commit's SHA. When choosing a
rollback target, verify by md5 of the served file, never by that column. (Concretely:
`a487bddd` is the deployment carrying the stale content from §6.2 and must **not** be a
rollback target.)

### 6.11 Only 2 of 17 SHOW rows are actually shipped

PLACEMENT has **17** rows marked SHOW, but `PILOT_ROUTES` is `['/plan-your-visit/', '/giving/']`,
so `answers.json` carries two routes and 14 questions out of 70 ANSWERS rows. That is
deliberate pilot scoping, but the Sheet gives no hint of it — a content editor looking at 17
SHOW rows would reasonably expect 17 live pages. Adding a route needs a **code** change
(`PILOT_ROUTES` + `ROUTE_META_FALLBACK`), which contradicts the spirit of the default-hide
contract described as "a content change, not a code change".

### 6.12 The pilot exit has not happened, and cannot yet

`SHIP_STATUSES = {'DRAFT', 'APPROVED'}` and the Sheet contains **48 DRAFT, 22 HOLD, and zero
APPROVED**. Flipping the constant today would ship nothing and fail validation loudly — which
is the documented, correct behaviour, but it means the mandatory pilot-exit step is blocked
on T's approval pass and nothing in the system will remind anyone.

### 6.13 Worker compatibility dates are 20 months behind the Pages projects

Both Workers pin `compatibility_date = "2025-01-01"`; both Pages projects use `2026-08-27`.
Not a bug — pinning is the point — but it is an inconsistency someone will trip over, and
2025-01-01 predates runtime behaviour the code may otherwise be assumed to have.

### 6.14 Neither Worker has observability enabled

`observability: null` and `logpush: false` on both. The router deliberately logs almost
nothing (`console.log('router fallback:', err.name)`), so when it degrades there is no
retained record anywhere of how often or why. The design treats silent degradation as a
feature, which it is for the guest — but it also means nobody can answer "how often does the
ranking call fail?" after the fact.

### 6.15 The account is not Grace-only

`relaxtech.us` is a second zone on the same Cloudflare account, and the account, the OAuth
token, the workers.dev subdomain (`relax-tech`) and the Sheet's owner are all
`chris@relax-tech.com`. Both Worker public URLs are permanently branded
`*.relax-tech.workers.dev`, which no amount of ownership transfer changes — moving the
Workers to Grace means new URLs, and therefore a widget change (`data-router`) and an origin
allowlist change.

### 6.16 `grace-demo` has not been redeployed in a week and holds a stale widget copy

Its five most recent deployments are all `1452704`, all one week old. That is fine by design —
HANDOFF notes the demo loads the widget from `grace-assistant.pages.dev`, so content and
widget changes reach it without a demo redeploy. Worth stating explicitly, because a reader
seeing a week-old deployment could reasonably conclude the demo is showing week-old work. It
is not; it is showing today's widget inside a week-old page clone.

### 6.17 Small things

- **`.gitignore` has a redundant line.** Line 2 `.dev.vars` is fully covered by line 16
  `.dev.vars*`. Harmless; line 2 is the pre-incident pattern that failed to catch the swap
  file.
- **`GRACE-WIDGET-BUILD-STATE-2026-08-27.md`** has been untracked for eleven days and appears
  in every `git status`. It is superseded by the tracked `SESSION-2026-08-27.md`. Track it or
  delete it.
- **`build/` is gitignored** but is `publish.py`'s first write target (`OUT_BUILD`). A fresh
  clone has no `build/` directory; `publish.py` creates it, so this is fine — noted only
  because "the file the validator writes is not in the repo" surprises people.
- **`smoke_test.py` requests narrower scopes than `publish.py`** (`spreadsheets.readonly`
  only, no Drive). It therefore cannot exercise the debounce path, so a passing smoke test
  does not prove the quiescence check will work.
- **`LIVE_URL` in `publish.py` is defined but never used** — only `LIVE_JSON` is verified
  after deploy. The widget's own md5 is never checked by the pipeline.
- **The demo Access team domain is `rapid-pond-2632`**, which appears nowhere in any
  documentation. If the Zero Trust dashboard is ever hard to locate, that is the string to
  search for.
