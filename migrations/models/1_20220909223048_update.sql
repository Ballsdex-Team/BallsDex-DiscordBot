-- upgrade --
ALTER TABLE "ball" ALTER COLUMN "emoji_id" TYPE BIGINT USING "emoji_id"::BIGINT;
ALTER TABLE "guildconfig" ALTER COLUMN "spawn_channel" TYPE BIGINT USING "spawn_channel"::BIGINT;
ALTER TABLE "guildconfig" ALTER COLUMN "guild_id" TYPE BIGINT USING "guild_id"::BIGINT;
ALTER TABLE "player" ALTER COLUMN "discord_id" TYPE BIGINT USING "discord_id"::BIGINT;
-- downgrade --
ALTER TABLE "ball" ALTER COLUMN "emoji_id" TYPE INT USING "emoji_id"::INT;
ALTER TABLE "player" ALTER COLUMN "discord_id" TYPE INT USING "discord_id"::INT;
ALTER TABLE "guildconfig" ALTER COLUMN "spawn_channel" TYPE INT USING "spawn_channel"::INT;
ALTER TABLE "guildconfig" ALTER COLUMN "guild_id" TYPE INT USING "guild_id"::INT;
