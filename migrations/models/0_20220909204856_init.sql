-- upgrade --
CREATE TABLE IF NOT EXISTS "ball" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "country" VARCHAR(48) NOT NULL UNIQUE,
    "regime" SMALLINT NOT NULL,
    "economy" SMALLINT NOT NULL,
    "health" INT NOT NULL,
    "attack" INT NOT NULL,
    "rarity" DOUBLE PRECISION NOT NULL,
    "emoji_id" INT NOT NULL,
    "wild_card" VARCHAR(200) NOT NULL,
    "collection_card" VARCHAR(200) NOT NULL,
    "credits" VARCHAR(64) NOT NULL,
    "capacity_name" VARCHAR(64) NOT NULL,
    "capacity_description" VARCHAR(256) NOT NULL,
    "capacity_logic" JSONB NOT NULL
);
COMMENT ON COLUMN "ball"."regime" IS 'Political regime of this country';
COMMENT ON COLUMN "ball"."economy" IS 'Economical regime of this country';
COMMENT ON COLUMN "ball"."health" IS 'Ball health stat';
COMMENT ON COLUMN "ball"."attack" IS 'Ball attack stat';
COMMENT ON COLUMN "ball"."rarity" IS 'Rarity of this ball';
COMMENT ON COLUMN "ball"."emoji_id" IS 'Emoji ID for this ball';
COMMENT ON COLUMN "ball"."wild_card" IS 'Image used when a new ball spawns in the wild';
COMMENT ON COLUMN "ball"."collection_card" IS 'Image used when displaying balls';
COMMENT ON COLUMN "ball"."credits" IS 'Author of the collection artwork';
COMMENT ON COLUMN "ball"."capacity_name" IS 'Name of the countryball''s capacity';
COMMENT ON COLUMN "ball"."capacity_description" IS 'Description of the countryball''s capacity';
COMMENT ON COLUMN "ball"."capacity_logic" IS 'Effect of this capacity';
CREATE TABLE IF NOT EXISTS "guildconfig" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "guild_id" INT NOT NULL UNIQUE,
    "spawn_channel" INT,
    "enabled" BOOL NOT NULL  DEFAULT True
);
COMMENT ON COLUMN "guildconfig"."guild_id" IS 'Discord guild ID';
COMMENT ON COLUMN "guildconfig"."spawn_channel" IS 'Discord channel ID where balls will spawn';
COMMENT ON COLUMN "guildconfig"."enabled" IS 'Whether the bot will spawn countryballs in this guild';
CREATE TABLE IF NOT EXISTS "player" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "discord_id" INT NOT NULL UNIQUE
);
COMMENT ON COLUMN "player"."discord_id" IS 'Discord user ID';
CREATE TABLE IF NOT EXISTS "ballinstance" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "count" INT NOT NULL,
    "catch_date" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "special" INT NOT NULL  DEFAULT 0,
    "health_bonus" INT NOT NULL  DEFAULT 0,
    "attack_bonus" INT NOT NULL  DEFAULT 0,
    "ball_id" INT NOT NULL REFERENCES "ball" ("id") ON DELETE CASCADE,
    "player_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "trade_player_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_ballinstanc_player__f154f9" UNIQUE ("player_id", "id")
);
COMMENT ON COLUMN "ballinstance"."special" IS 'Defines rare instances, like a shiny';
CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "username" VARCHAR(50) NOT NULL UNIQUE,
    "password" VARCHAR(200) NOT NULL,
    "last_login" TIMESTAMPTZ NOT NULL,
    "avatar" VARCHAR(200) NOT NULL  DEFAULT '',
    "intro" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON COLUMN "user"."last_login" IS 'Last Login';
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSONB NOT NULL
);
