-- upgrade --
ALTER TABLE "blacklistedid" RENAME COLUMN "discord_id" TO "id";
ALTER TABLE "blacklistedid" ADD "discord_id" BIGINT NOT NULL UNIQUE;
-- downgrade --
ALTER TABLE "blacklistedid" RENAME COLUMN "id" TO "discord_id";
ALTER TABLE "blacklistedid" DROP COLUMN "discord_id";
