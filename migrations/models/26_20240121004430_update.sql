-- upgrade --
ALTER TABLE "player" ADD "privacy_policy" SMALLINT NOT NULL  DEFAULT 2;
-- downgrade --
ALTER TABLE "player" DROP COLUMN "privacy_policy";
