-- upgrade --
ALTER TABLE "player" ADD "mention_policy" SMALLINT NOT NULL  DEFAULT 1;
-- downgrade --
ALTER TABLE "player" DROP COLUMN "mention_policy";
