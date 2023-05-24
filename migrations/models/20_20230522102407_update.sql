-- upgrade --
CREATE TABLE IF NOT EXISTS "trade" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "time" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);;
CREATE TABLE IF NOT EXISTS "tradeoffer" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "ball_id" INT NOT NULL REFERENCES "ballinstance" ("id") ON DELETE CASCADE,
    "player_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "trade_id" INT NOT NULL REFERENCES "trade" ("id") ON DELETE CASCADE
);;
DROP TABLE IF EXISTS "blacklistedguild";
-- downgrade --
DROP TABLE IF EXISTS "trade";
DROP TABLE IF EXISTS "tradeoffer";
