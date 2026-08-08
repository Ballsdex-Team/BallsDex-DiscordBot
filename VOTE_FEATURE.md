# Vote rewards (Top.gg)

Adds a `/vote` command and a Top.gg vote webhook that rewards players with a random countryball
(with a small chance of an active special) when they actually vote for the bot — not just for
running the command.

## Review feedback addressed

An earlier version of this PR added models/migrations directly to the core `bd_models` and
`settings` apps, added the cog under `ballsdex/packages/`, hand-rolled the Top.gg webhook
signature check, and stored an interaction token per player just to notify them. All four points
raised in review are fixed:

1. **No more migrations on `bd_models`/`settings`.** Those numbering collisions with upstream
   were the real risk. The whole feature is now a self-contained **custom package** under
   `extra/vote_topgg/`, with its own Django app (`vote_app`) and its own migration sequence
   (`0001_initial.py`, ...) that can never collide with core app migrations.
2. **Follows the [custom package guide](https://wiki.ballsdex.com/dev/custom-package/)** —
   `extra/vote_topgg/pyproject.toml`, `vote_app/apps.py` with `dpy_package`, `vote_app/vote_ext/`
   for the discord.py side, same structure as the guide's example.
3. **Uses the official Top.gg SDK** (`topggpy`, from
   [Top-gg-Community/python-sdk](https://github.com/Top-gg-Community/python-sdk)) for signature
   verification and payload parsing, instead of hand-rolled HMAC code.
4. **`VoteInteraction` is gone.** The reward notification is now a plain DM sent from the bot
   process (`user.send(...)`) instead of an ephemeral follow-up tied to a stored interaction
   token — no per-player row needed just to remember how to reply to them.

## How it works now

- `/vote` (`extra/vote_topgg/vote_app/vote_ext/cog.py`) sends an ephemeral embed with a link to
  vote. It does not grant anything — clicking it and voting are two different things, and only
  Top.gg knows for sure that a vote happened.
- The Top.gg SDK's `topgg.Webhooks` runs its own small web server **inside the bot process**
  (`extra/vote_topgg/vote_app/vote_ext/webhook.py`), the same pattern already used for the
  built-in Prometheus metrics server (`ballsdex/core/metrics.py`). It listens on its own port
  (`VoteSettings.webhook_port`, default `15261`), verifies Top.gg's `x-topgg-signature` header
  (HMAC-SHA256, v1 scheme) via the SDK, and only reacts to genuine `vote.create` events.
- On a verified vote: get-or-create the `Player`, skip if they were already rewarded in the last
  12h (Top.gg's own vote cooldown — also guards against a redelivered webhook), pick a random
  `Ball` in the configured rarity range (weighted the same way spawns are), roll a chance for an
  active `Special`, create the `BallInstance`, and DM the player the result with the rendered
  card. A `VoteRecord` is kept either way, for the 12h check and as an audit trail (read-only in
  the admin).
- nginx (`bd-nginx.conf`) forwards `/webhook/topgg` to the bot container instead of the admin
  panel, since that's now where the webhook server lives. The bot container joins the `nginx`
  docker network for this (`docker-compose.yml`).

## Setup

**1. Enable the package** — not committed, this is per-deployment config. Create
`config/extra.toml`:
```toml
[[ballsdex.packages]]
location = "/code/extra/vote_topgg"   # or a git URL once this package is published on its own
path = "vote_app"
enabled = true
editable = true                        # local development only, omit for a real install
```
Rebuild so it gets installed (`docker compose build`), then run migrations
(`docker compose run --rm migration python3 -m django migrate`).

**2. Admin panel** — a new **Vote app** section appears with two models:
| Setting | What it does |
|---|---|
| `vote_url` | Link shown by `/vote`. Pre-filled with the bot's Top.gg page. |
| `webhook_secret` | Shared secret used to verify incoming webhooks. **Leave empty and the webhook server stays disabled** — nothing else works until this is set. |
| `webhook_port` | Port the webhook server listens on (default `15261`). |
| `min_rarity` / `max_rarity` | Rarity range the reward ball is picked from. |
| `special_chance` | 0–1 chance the reward is a currently-active special instead of a plain ball. |

`Vote records` (read-only) shows the history of processed votes and their rewards.

**3. Top.gg dashboard** — on your bot's project page → Webhooks:
1. Set the endpoint URL to `<your public host>/webhook/topgg` (same domain as the admin panel,
   nginx routes it to the bot automatically — see "How it works" above).
2. Set a secret and paste the **same** value into `webhook_secret` in the admin panel.
3. Restart the bot so it picks up the settings and starts the webhook server.

⚠️ This only works once the host is reachable from the public internet — Top.gg cannot reach
`localhost`. For local testing without a public deploy, tunnel it (e.g.
`cloudflared tunnel --url http://localhost:8000`) and use the tunnel's URL instead.

## Files touched

- `extra/vote_topgg/` (new) — the whole package: `pyproject.toml`, `README.md`,
  `vote_app/{apps,models,admin}.py`, `vote_app/migrations/0001_initial.py`,
  `vote_app/vote_ext/{cog,webhook}.py`.
- `bd-nginx.conf` — added the `/webhook/topgg` → bot route.
- `docker-compose.yml` — `bot` service joins the `nginx` network.

Nothing in `bd_models`, `settings`, or `ballsdex/` was touched by this version of the feature.

## Unrelated fixes bundled from the same session

Two pre-existing bugs unrelated to this feature were also fixed while getting the project running
locally, and may show up in the same diff:
- `docker-compose.yml`: `build` context for `bot`/`admin-panel`/`migration`/`proxy` pointed to a
  stale absolute path from another machine, breaking `docker compose build` for anyone else.
  Changed to `.`.
- `currency_app/migrations/0007_auto_20260704_1511.py`: a data migration referenced the
  `settings` app's `Settings` model via `apps.get_model` without declaring a migration dependency
  on it, so it could run before `settings`'s migrations depending on graph ordering, raising
  `LookupError: No installed app with label 'settings'`. Added the missing `dependencies` entries.
