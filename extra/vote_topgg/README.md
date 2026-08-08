# vote-topgg

Adds a `/vote` command and rewards players with a random countryball (with a small chance of an
active special) when they vote for the bot on Top.gg — verified through Top.gg's official
webhook (v1, HMAC-SHA256 signed), not just by running the command.

## Setup

1. Enable this package in `config/extra.toml`:
   ```toml
   [[ballsdex.packages]]
   location = "/code/extra/vote_topgg"  # or a git URL once published
   path = "vote_app"
   enabled = true
   editable = true  # local development only
   ```
2. In the admin panel, go to **Vote app → Vote settings** and set:
   - `webhook_secret` — must match the secret you configure on Top.gg's webhook page.
   - `webhook_port` — the port this package's webhook server listens on (default `15261`). Must
     be reachable from Top.gg, so expose/proxy it (see below).
   - `min_rarity` / `max_rarity` / `special_chance` — reward tuning.
3. On your bot's Top.gg project dashboard → Webhooks: point the URL at
   `http://<your public host>:<webhook_port>/webhook/topgg` with the same secret.
4. Restart the bot so it picks up the new settings and starts the webhook server.

The webhook server runs inside the bot process (same pattern as the built-in Prometheus metrics
server), not the admin panel — it needs its own exposed port.
