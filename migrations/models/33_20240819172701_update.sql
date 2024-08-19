-- upgrade --
CREATE TABLE IF NOT EXISTS "friendship" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "player1" INTEGER NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "player2" INTEGER NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "since" TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
-- downgrade --
DROP TABLE IF EXISTS "friendship";