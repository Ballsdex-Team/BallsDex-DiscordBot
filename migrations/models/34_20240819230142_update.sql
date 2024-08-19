-- upgrade --
CREATE TABLE IF NOT EXISTS "block" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "player1" INTEGER NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "player2" INTEGER NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE
);
-- downgrade --
DROP TABLE IF EXISTS "block";
