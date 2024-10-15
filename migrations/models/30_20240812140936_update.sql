-- upgrade --
CREATE TABLE IF NOT EXISTS "blacklisthistory" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "discord_id" BIGINT NOT NULL,
    "moderator_id" BIGINT NOT NULL,
    "reason" TEXT,
    "date" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "id_type" VARCHAR(64) NOT NULL  DEFAULT 'user',
    "action_type" VARCHAR(64) NOT NULL  DEFAULT 'blacklist'
);
COMMENT ON COLUMN "blacklisthistory"."discord_id" IS 'Discord ID';
COMMENT ON COLUMN "blacklisthistory"."moderator_id" IS 'Discord Moderator ID';;
ALTER TABLE "blacklistedguild" ADD "moderator_id" BIGINT;
ALTER TABLE "blacklistedid" ADD "moderator_id" BIGINT;
-- downgrade --
ALTER TABLE "blacklistedid" DROP COLUMN "moderator_id";
ALTER TABLE "blacklistedguild" DROP COLUMN "moderator_id";
DROP TABLE IF EXISTS "blacklisthistory";
