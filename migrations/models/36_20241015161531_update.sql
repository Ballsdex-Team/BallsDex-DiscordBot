-- upgrade --
ALTER TABLE "player" ADD "coins" INT NOT NULL  DEFAULT 0;
ALTER TABLE "trade" ADD "player1_coins" INT NOT NULL  DEFAULT 0;
ALTER TABLE "trade" ADD "player2_coins" INT NOT NULL  DEFAULT 0;
-- downgrade --
ALTER TABLE "trade" DROP COLUMN "player1_coins";
ALTER TABLE "trade" DROP COLUMN "player2_coins";
ALTER TABLE "player" DROP COLUMN "coins";
