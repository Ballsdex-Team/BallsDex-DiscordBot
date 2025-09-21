# BallsDex Manual Test Guide

This document provides structured manual verification steps for the restored commands and the new coin economy.

## 1. Database & Migration Sanity

Purpose: Ensure the `coins` column exists and migrations are in a consistent state.

Steps:
1. Start services:
   - `docker compose up --build`
2. If startup errors with `UndefinedColumnError: coins`:
   - Confirm migration 39 & 40 files exist in `migrations/models/`.
   - Enter DB container: `docker exec -it <postgres-container> psql -U postgres -d <db>`
   - Inspect table: `\d player` → Expect column `coins integer not null default 0`.
   - If missing: run `ALTER TABLE player ADD COLUMN coins INT NOT NULL DEFAULT 0;` then restart bot container.
3. OPTIONAL: View Aerich versions table (name may vary: `aerich`): `SELECT * FROM aerich;` – ensure latest migrations listed.

Pass Criteria:
- Bot starts with no migration exceptions.
- Selecting from `player` including `coins` succeeds.

---
## 2. `/balls collection` Command

Goal: Validate counts, uniqueness, and % completion.

Preconditions:
- Have at least one player with several `BallInstance` rows.
- Some spawnable/enabled balls exist.

Steps:
1. Run `/balls collection` for yourself.
2. Note displayed values: unique owned, total instances, completion %.
3. Obtain a new ball (spawn / manual DB insert) that is a duplicate of an existing one.
4. Re-run command: unique should stay same, total instances increase.
5. Obtain a new ball that is a new unique: unique and total instances both increase; completion % changes.
6. Run as a brand new user: all zero, no errors.

Edge Cases:
- All spawnable collected → 100%.
- No spawnable balls (dev DB) → expect 0% without division error.

Pass Criteria:
- No tracebacks.
- Percent shown is (unique_owned / total_spawnable) * 100 (rounded as implemented).

Failure Clues:
- KeyError or division-by-zero.
- Unique count increments on duplicate acquisition.

---
## 3. `/balls compare` Command

Goal: Verify comparative statistics between two players.

Steps:
1. Select two users A & B with overlapping but not identical collections.
2. Run `/balls compare A B`.
3. Confirm both users’ counts display and overlap (or delta) section accurate.
4. Reverse order: `/balls compare B A` – symmetry of numeric stats.
5. Compare user with themselves (if allowed) – either handled gracefully or blocked with message.
6. Compare with a user having zero balls – output should reflect zero for that user; no crash.

Edge Cases:
- Very large overlap list (should truncate or summarize if implemented).
- Privacy settings (if active) – ensure respect or at least no unhandled exception.

Pass Criteria:
- Stats align with manual DB queries (spot check counts: `SELECT COUNT(DISTINCT ball_id) ...`).

Failure Clues:
- ORM OperationalError referencing `coins` (indicates unresolved migration ordering).
- Embed too large error.

---
## 4. `/balls info` vs `/missingball info`

Purpose: Distinguish owned instance detail vs general ball definition info.

Steps:
1. Use `/balls info` selecting an owned instance → Expect instance-level details (e.g., unique ID, maybe acquisition time, special flags).
2. Use `/missingball info <name_of_owned_ball>` → Should show generic stats (rarity, description) but not instance-specific metadata.
3. Use `/missingball info <ball_you_do_not_own>` → Should still show generic info.
4. Query a disabled ball (if any) – confirm either hidden or gracefully displayed depending on design.
5. Provide a non-existent name → Expect a clear “not found” style response.

Pass Criteria:
- No `DoesNotExist` traceback; errors handled user-facing.

Failure Clues:
- `/balls info` allows selecting unowned instance.
- `/missingball info` returns instance-only fields (leak of design separation).

---
## 5. Shop & Coin Economy

### 5.1 Balance Initialization
1. New user runs `/shop balance` → Player auto-created with 0 coins.
2. `/player info` also displays coin line.

### 5.2 Manual Funding (until natural earning exists)
- In DB: `UPDATE player SET coins=2500 WHERE discord_id=<id>;`.

### 5.3 Viewing Shop
- `/shop view` displays all seven items (Basic I/II/III, Deluxe, Premium, Big Box, Coin Pack) with prices and tier exclusions.

### 5.4 Purchasing Boxes
1. Buy Basic Box I (cost 500) – balance reduces; message lists 3 new balls (IDs or names).
2. Buy Premium Box (cost 1250) – 7 new balls; none from excluded tiers (T1–T12).
3. Capture each new `BallInstance` count: `SELECT COUNT(*) FROM ballinstance WHERE owner_id=<player_id>;` before/after.

### 5.5 Coin Pack
1. Buy Coin Pack (1000) – message: gained X coins (100–2000) – net balance = previous - 1000 + X.
2. Confirm DB value matches message.

### 5.6 Insufficient Funds
1. Attempt a purchase with balance below price – expect error message, no negative balance.

### 5.7 Tier Exclusion Validation
1. Query tier mapping (optional debug) or approximate by rarity order.
2. Open multiple Basic Box I boxes – confirm none of first 19 tiers appear (if rule excludes T1–T19) – adjust if design changes.

### 5.8 Concurrency (Manual Approx)
1. Open two purchase modals quickly with just enough coins for one purchase.
2. Expect one success, one failure due to refreshed balance.

Pass Criteria:
- Every successful purchase deducts exact price first (except coin pack which then adds reward).
- No negative coin values.

Failure Clues:
- `OperationalError: column "coins" does not exist` (migration mismatch still present).
- Purchase success with unchanged coin balance.

---
## 6. Troubleshooting Matrix

| Symptom | Likely Cause | Resolution |
|---------|--------------|------------|
| UndefinedColumnError coins | Migration 39 skipped; 40 not applied | Apply migrations; manual ALTER; restart bot |
| Empty rewards / crash in shop | All eligible tiers excluded | Add fallback: choose full pool minus disabled |
| Duplicate coin deduction | Interaction double-submit | Add idempotency check (store purchase interaction ID) |
| Slow collection/compare | Large joins or missing index on `BallInstance.owner_id` | Add index if not present |
| Tier mapping inconsistent | Rarity values mutated post-start | Recompute or cache invalidation hook |

---
## 7. Suggested Enhancements (Not Yet Implemented)
- Atomic coin updates with single SQL `UPDATE ... WHERE coins >= price RETURNING coins`.
- Admin command: `/admin addcoins <user> <amount>` (role-locked).
- Weighted selection inside a tier by rarity (currently uniform within tier).
- Fallback if eligible set empty (prevent user confusion).
- Add automated tests (PyTest + async Tortoise setup) for economy flows.

---
## 8. Quick Reference Commands
```
# Start stack
docker compose up --build

# Psql into DB
docker exec -it <postgres-container> psql -U postgres -d <db>

# Inspect player schema
\d player

# Sample count checks
SELECT COUNT(*) FROM ballinstance WHERE owner_id=<player_id>;
SELECT COUNT(DISTINCT ball_id) FROM ballinstance WHERE owner_id=<player_id>;
```

---
## 9. Exit Criteria
All sections pass without unhandled exceptions, coin balances reconcile after each purchase, and collection/compare outputs match DB truth.

If any section fails, annotate the failure, collect logs, and address before marking deployment ready.
