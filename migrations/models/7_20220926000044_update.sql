-- upgrade --
CREATE TABLE IF NOT EXISTS "blacklistedid" (
    "discord_id" BIGSERIAL NOT NULL PRIMARY KEY
);
COMMENT ON COLUMN "blacklistedid"."discord_id" IS 'Discord user ID';
-- downgrade --
DROP TABLE IF EXISTS "blacklistedid";
