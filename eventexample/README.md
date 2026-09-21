# Event pass examples

Each JSON file here describes a whole event pass (its tiers, quests and rewards) that the
`load_event_pass` command builds in one go, instead of clicking it together in the admin.

- `birthday_voyage.json`: the first anniversary event, October 9 to 18, 2026.
- `halloween_2026.json`: one tier of five Thriller Bark quests, October 25 to November 1, 2026. The
  Halloween 2026 special has a rarity of 0: raise it for the event, or "Haunted Ship" can't be done.

## Loading an event

The admin panel container doesn't have this folder, so the file is copied into it first. From the
folder of the bot (where `docker-compose.yml` is), once the code is deployed:

```bash
# 1. copy the file into the admin panel container
docker compose cp eventexample/birthday_voyage.json admin-panel:/tmp/birthday_voyage.json

# 2. check it: every treasure, special, pack and craft type must exist, nothing is saved
docker compose exec admin-panel python3 -m django load_event_pass /tmp/birthday_voyage.json --dry-run

# 3. load it for real
docker compose exec admin-panel python3 -m django load_event_pass /tmp/birthday_voyage.json
```

On Linux, steps 1 and 3 can be one command:
`docker compose exec -T admin-panel python3 -m django load_event_pass - < eventexample/birthday_voyage.json`

The pass is created as a **draft**: only staff see it in `/pass view`, and nothing progresses. Check
it in Discord and in the admin (Event passes), then publish it by setting its status to **Active**.

## Fixing it before launch

Edit the file and load it again (steps 1 to 3): the draft is updated in place, nothing is duplicated.

- If anything in the file is wrong (a misspelled treasure, a setting a quest type doesn't use...),
  every mistake is listed at once and **nothing** is saved.
- Only a draft can be reloaded. Once the pass is active, players may be on it: change it in the
  admin, or move it back to draft first.
- Quests or tiers removed from the file are not deleted from the pass: delete them in the admin.

For the Birthday Voyage specifically:

- `"token": "venustoken"` is a placeholder: put the name of the real Birthday token and reload.
- "The Last Present" counts any Craft for now: once the token frame collector exists, add
  `"collector": "<its name>"` to that quest and reload, or set it in the admin.

## File format

Everything is matched **by name**: treasures by their name in the Treasures section, specials,
packs (`"Gold Pack"` is enough for "Gold Pack 🥇"), craft types (`"Elemental"`, `"Tier 1"`,
`"Craft"`), collectors, merchant items and groups. Dates always carry a timezone, and the bot runs
in UTC: `"2026-10-09T00:01:00Z"`.

### The pass

| Key | Meaning |
| --- | --- |
| `name` | Name of the pass, how it is found again when reloading |
| `emoji`, `description`, `colour` | Look of the pass (`"#FDDF28"`) |
| `starts_at`, `ends_at`, `claim_until` | Dates. `claim_until` is optional |
| `token` | The treasure given by `"tokens"` in the rewards |
| `card_special` | The special put on every card given as a reward (`"Birthday"`) |
| `final_reward`, `final_message` | Given once every tier is finished |
| `main_server_id`, `main_server_only`, `position`, `notes` | Optional, as in the admin |
| `tiers` | The tiers, in order |

### A tier

| Key | Meaning |
| --- | --- |
| `name`, `emoji`, `description`, `locked_message` | As in the admin |
| `reward` | Given when the tier is finished: every mandatory quest completed |
| `requirements` | What opens it: `"finish_previous"`, `{"date": "…"}`, `{"quests_count": 12}`, `{"berries": 5000}`, `{"own": {"count": 10, "ball": "…"}}`, `{"quests": ["Quest name", …]}`, `"previous_tier"` |
| `unlock_logic` | `"all"` (default) or `"any"` of the requirements |
| `quests` | The quests, in order |

### A quest

| Key | Meaning |
| --- | --- |
| `name`, `emoji`, `description` | An empty description shows the goal generated from the settings |
| `type` | `catch`, `obtain`, `command`, `trade`, `trade_treasures`, `give_treasures`, `friend`, `battle_win`, `give_currency`, `receive_currency`, `catch_currency`, `spend_currency`, `craft`, `pack_buy`, `merchant_buy`, `shop_buy`, `sell`, `auction_create`, `auction_bid`, `auction_won` |
| `goal`, `measure` | How much is needed (default 1). `"measure": "amount"` adds berries up instead of counting |
| `mandatory`, `hidden` | Needed to finish the tier / secret until completed |
| `reset` | `"none"` (default), `"daily"` or `"weekly"` |
| `claim_required`, `announce`, `completion_message` | As in the admin |
| `starts_at`, `ends_at`, `enabled`, `notes` | Optional |
| filters | `ball`, `special`, `any_special`, `group`, `min_rarity`, `max_rarity`, `min_attack_bonus`, `min_health_bonus`, `hex_contains`, `max_catch_seconds`, `main_server_only`, `partner` (Discord ID), `min_currency`, `must_receive_treasure`, `in_one_trade`, `command` (`"pack shop"`), `item` (pack), `merchant_item`, `collector`, `craft_type`. Only the ones the type uses are accepted |
| `reward` | `{"cards": ["Alvida"], "tokens": 2, "berries": 800}`, any mix of the three |

Rarity is the value of the treasure, lower is rarer: `"max_rarity": 60` means T60 or rarer.
