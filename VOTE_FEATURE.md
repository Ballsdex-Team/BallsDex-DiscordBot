# Vote rewards (Top.gg)

Adds a `/vote` command and a Top.gg vote webhook that rewards players with a random countryball
(with a small chance of an active special) when they actually vote for the bot — not just for
running the command.

## Admin panel setup

Go to **Settings → Settings → Vote rewards (Top.gg)** in the admin panel and fill in:

| Field | What it does |
|---|---|
| `vote_url` | Link shown by `/vote`. Pre-filled with the bot's Top.gg page. |
| `vote_webhook_secret` | Shared secret used to verify incoming webhooks. **Leave empty and the `/webhook/topgg` endpoint stays disabled** — nothing else works until this is set. |
| `vote_min_rarity` / `vote_max_rarity` | Rarity range the reward ball is picked from (same field as regular balls, weighted the same way spawns are). |
| `vote_special_chance` | 0–1 chance that the reward is a currently-active special instead of a plain ball. |

Then, on your bot's **Top.gg project dashboard → Webhooks**:

1. Set the endpoint URL to `<your admin panel's public base URL>/webhook/topgg`
   (same domain as the admin panel — see `Settings.site_base_url` — just with this path appended).
2. Set a secret and paste the **same** value into `vote_webhook_secret` above.

That's it — no other config or deploy step needed, the endpoint is wired in automatically.

⚠️ This only works once the admin panel is reachable from the public internet over the URL you
give Top.gg. It cannot reach `localhost`; for local testing without a public deploy, tunnel it
(e.g. `cloudflared tunnel --url http://localhost:8000`) and use the tunnel's URL in the Top.gg
dashboard instead.

## What was added, and why

### The core problem

Nothing about voting existed in the codebase before (`topgg`/`vote` search returns nothing). It
also needed to solve one thing by design: **a reward must only be granted for a real vote**, not
for merely running `/vote` — so the command itself never grants anything; it just links out. The
actual reward is entirely driven by Top.gg's server-to-server webhook, which only fires once a
vote is genuinely recorded on their end.

### New/changed files

**`ballsdex/packages/vote/` (new)** — `cog.py`, `__init__.py`
The `/vote` command. Sends an ephemeral embed with a link button to `settings.vote_url`, and
records a `VoteInteraction` (see below) so a later webhook call can find its way back to this
specific interaction. Registered in `DEFAULT_PACKAGES` in `ballsdex/core/bot.py`.

**`admin_panel/settings/views.py` (new)** — `topgg_webhook`
The actual webhook receiver. Runs in the Django admin panel process (not the bot), because that's
the process already exposed to the internet (via nginx) and it can touch the same database
directly with the async ORM — no need to add new bot-side network exposure. Flow per request:

1. Verify `x-topgg-signature` (Top.gg's **v1** scheme: header is
   `t=<unix ts>,v1=<hex hmac-sha256 of "{ts}.{raw body}">`, checked with `hmac.compare_digest`
   and a 5-minute timestamp tolerance). Confirmed against the current
   [docs.top.gg webhooks docs](https://docs.top.gg/webhooks/overview) — Top.gg's *legacy* (v0)
   scheme uses a plain `Authorization` header instead, which is what an early version of this
   code mistakenly implemented; this was caught and fixed before merging.
2. Parse `data.user.platform_id` (the voter's Discord ID) and `type` (`vote.create` vs
   `webhook.test`, the latter is Top.gg's dashboard test ping — acknowledged with 200, no reward).
3. Get-or-create the `Player`, check the last `VoteRecord` for that player isn't < 12h old
   (Top.gg's own vote cooldown — defends against a webhook being delivered more than once for the
   same vote).
4. Pick a random `Ball` in `[vote_min_rarity, vote_max_rarity]`, weighted by rarity, same
   mechanic as `Ball.get_random_countryball` elsewhere. Roll `vote_special_chance` for whether to
   also attach a currently-active `Special` (same date-window logic as
   `countryball.get_random_special`, reimplemented against the DB here since this process has no
   bot-side in-memory cache).
5. Create the `BallInstance` — the reward exists in the player's inventory at this point,
   regardless of whether the notification below succeeds.
6. Call `_send_ephemeral_reward` to notify the player privately (see next section).
7. Record a `VoteRecord` either way (even with no reward, e.g. if no ball matched the rarity
   range) so the 12h dedup in step 3 still works next time.

**Why an ephemeral follow-up instead of a channel announcement or a DM?**
That's what was asked for: a message only the voter can see. A true Discord "ephemeral" message
only exists as a response to an interaction — there's no way to push one out of nowhere. The
`/vote` command's own interaction token is reused for this: Discord's
`POST /webhooks/{application_id}/{token}` endpoint accepts follow-up messages for **15 minutes**
after the original interaction, using just the token (no bot auth needed), and `flags: 64` makes
it ephemeral. So `/vote` stores `(discord_id, application_id, token)` in `VoteInteraction`, and the
webhook looks it up by `discord_id` when the reward is granted. If the player voted more than 15
minutes after running `/vote` (or never ran it), sending is skipped — the reward is still granted,
just silently, and they'll find it browsing their collection. This is a hard Discord API
limitation, not a bug: there's no way around the 15-minute window without a fundamentally
different flow (e.g. a persistent "claim" button), which wasn't in scope here.

**`admin_panel/bd_models/models.py`** — two new models
- `VoteRecord(player, voted_at, reward)`: audit trail of every processed vote webhook, also used
  for the 12h dedup check above. Read-only in the admin (`bd_models/admin/vote.py`) — it's a
  tracker, not something to hand-edit.
- `VoteInteraction(discord_id, application_id, token, created_at)`: the short-lived "ticket"
  described above. One row per player (upserted on each `/vote`), deleted once consumed by the
  webhook (success or failure — it's single-use either way).

**`admin_panel/settings/models.py` / `admin.py`** — `Settings` fields
Added `vote_url`, `vote_webhook_secret`, `vote_min_rarity`, `vote_max_rarity`,
`vote_special_chance` to the existing global settings singleton (same pattern as the currency or
spawn-chance fields already there), plus a `vote_min_rarity <= vote_max_rarity` check constraint
mirroring the existing `spawn_chance_min_lt_max` one. Surfaced in the admin under a new
"Vote rewards (Top.gg)" fieldset.

**`admin_panel/settings/apps.py` / `urls.py` (new)**
`SettingsConfig.url_prefix = "webhook/"` opts this app into the admin panel's existing
per-app URL auto-inclusion mechanism (`admin_panel/urls.py` already loops over
`apps.get_app_configs()` for any `url_prefix`, previously unused by any app). `urls.py` just maps
`topgg` to the view above, giving the final path `/webhook/topgg`.

**Migrations**
`bd_models/migrations/0018_voterecord.py`, `0019_voteinteraction.py`, and
`settings/migrations/0008_settings_vote_max_rarity_settings_vote_min_rarity_and_more.py`
(the settings one was squashed from a few iterations made during development — verified locally
against a fresh DB to produce the same schema).

### Unrelated fixes bundled from the same session

Two pre-existing bugs unrelated to this feature were also fixed while getting the project running
locally, and may show up in the same diff:
- `docker-compose.yml`: `build` context for `bot`/`admin-panel`/`migration`/`proxy` pointed to a
  stale absolute path from another machine, breaking `docker compose build` for anyone else.
  Changed to `.`.
- `currency_app/migrations/0007_auto_20260704_1511.py`: a data migration referenced the
  `settings` app's `Settings` model via `apps.get_model` without declaring a migration dependency
  on it, so it could run before `settings`'s migrations depending on graph ordering, raising
  `LookupError: No installed app with label 'settings'`. Added the missing `dependencies` entries.
