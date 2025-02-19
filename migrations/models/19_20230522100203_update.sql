-- upgrade --
CREATE TABLE IF NOT EXISTS "blacklistedguild" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "discord_id" BIGINT NOT NULL UNIQUE,
    "reason" TEXT,
    "date" TIMESTAMPTZ   DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON COLUMN "blacklistedguild"."discord_id" IS 'Discord Guild ID';
-- downgrade --
DROP TABLE IF EXISTS "blacklistedguild";
