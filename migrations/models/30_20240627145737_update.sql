-- upgrade --
ALTER TABLE "player" ADD "coins" INT NOT NULL  DEFAULT 0;
-- downgrade --
ALTER TABLE "player" DROP COLUMN "coins";
