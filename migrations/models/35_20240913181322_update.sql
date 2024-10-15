-- upgrade --
ALTER TABLE "player" ADD "friend_policy" SMALLINT NOT NULL  DEFAULT 1;
-- downgrade --
ALTER TABLE "player" DROP COLUMN "friend_policy";
