# FootballDex Bot - Testing Guide

## Prerequisites

1. Bot is running with:
```bash
BALLSDEXBOT_DB_URL="postgres://ballsdex@localhost:5432/ballsdex" python3 -m ballsdex --dev --debug
```

2. You have admin permissions in your Discord server

---

## Pack System Commands

### Admin Commands (requires admin role)

| Command | Description | Example |
|---------|-------------|---------|
| `/admin packs give` | Give packs to a user | `/admin packs give @user common 5` |
| `/admin packs view` | View a user's packs | `/admin packs view @user` |
| `/admin packs remove` | Remove packs from user | `/admin packs remove @user rare 2` |

### User Commands

| Command | Description | Example |
|---------|-------------|---------|
| `/packs` | View your pack inventory | `/packs` |
| `/open` | Open a pack | `/open common` |

---

## Testing Steps

### 1. Give Yourself Packs
```
/admin packs give @YourName common 3
/admin packs give @YourName rare 2
/admin packs give @YourName epic 1
```

### 2. Check Pack Inventory
```
/packs
```
You should see: 3 common, 2 rare, 1 epic

### 3. Open Packs
```
/open common
```
- Should show players received with rarity colors
- Players auto-added to collection

### 4. View Collection
```
/players list
```
Should show newly obtained players

---

## Pack Rarity Weights

| Pack Type | Players | Common | Rare | Epic | Legendary |
|-----------|---------|--------|------|------|-----------|
| Common | 3 | 70% | 20% | 8% | 2% |
| Rare | 5 | 40% | 35% | 20% | 5% |
| Epic | 7 | 20% | 30% | 40% | 10% |

---

## Troubleshooting

**"No players available" error**: 
- Add players to database via admin panel (http://localhost:8000)
- Set `rarity_tier` field to: common, rare, epic, or legendary

**Pack commands not showing**:
- Restart bot to sync commands
- Check bot has correct permissions in server
