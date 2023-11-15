-- upgrade --
CREATE TABLE IF NOT EXISTS "trade" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "date" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "player1_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "player2_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE
);;
CREATE TABLE IF NOT EXISTS "tradeobject" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "ballinstance_id" INT NOT NULL REFERENCES "ballinstance" ("id") ON DELETE CASCADE,
    "player_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "trade_id" INT NOT NULL REFERENCES "trade" ("id") ON DELETE CASCADE
);-- downgrade --
DROP TABLE IF EXISTS "trade";
DROP TABLE IF EXISTS "tradeobject";
