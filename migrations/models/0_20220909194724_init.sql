-- upgrade --
CREATE TABLE IF NOT EXISTS "ball" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "country" VARCHAR(48) NOT NULL UNIQUE,
    "regime" SMALLINT NOT NULL  /* Political regime of this country */,
    "economy" SMALLINT NOT NULL  /* Economical regime of this country */,
    "health" INT NOT NULL  /* Ball health stat */,
    "attack" INT NOT NULL  /* Ball attack stat */,
    "rarity" REAL NOT NULL  /* Rarity of this ball */,
    "emoji_id" INT NOT NULL  /* Emoji ID for this ball */,
    "wild_card" VARCHAR(200) NOT NULL  /* Image used when a new ball spawns in the wild */,
    "collection_card" VARCHAR(200) NOT NULL  /* Image used when displaying balls */,
    "credits" VARCHAR(64) NOT NULL  /* Author of the collection artwork */,
    "capacity_name" VARCHAR(64) NOT NULL  /* Name of the countryball's capacity */,
    "capacity_description" VARCHAR(256) NOT NULL  /* Description of the countryball's capacity */,
    "capacity_logic" JSON NOT NULL  /* Effect of this capacity */
);
CREATE TABLE IF NOT EXISTS "guildconfig" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "guild_id" INT NOT NULL UNIQUE /* Discord guild ID */,
    "spawn_channel" INT   /* Discord channel ID where balls will spawn */,
    "enabled" INT NOT NULL  DEFAULT 1 /* Whether the bot will spawn countryballs in this guild */
);
CREATE TABLE IF NOT EXISTS "player" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "discord_id" INT NOT NULL UNIQUE /* Discord user ID */
);
CREATE TABLE IF NOT EXISTS "ballinstance" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "count" INT NOT NULL,
    "catch_date" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP,
    "special" INT NOT NULL  DEFAULT 0 /* Defines rare instances, like a shiny */,
    "health_bonus" INT NOT NULL  DEFAULT 0,
    "attack_bonus" INT NOT NULL  DEFAULT 0,
    "ball_id" INT NOT NULL REFERENCES "ball" ("id") ON DELETE CASCADE,
    "player_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    "trade_player_id" INT NOT NULL REFERENCES "player" ("id") ON DELETE CASCADE,
    CONSTRAINT "uid_ballinstanc_player__f154f9" UNIQUE ("player_id", "id")
);
CREATE TABLE IF NOT EXISTS "user" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "username" VARCHAR(50) NOT NULL UNIQUE,
    "password" VARCHAR(200) NOT NULL,
    "last_login" TIMESTAMP NOT NULL  /* Last Login */,
    "avatar" VARCHAR(200) NOT NULL  DEFAULT '',
    "intro" TEXT NOT NULL,
    "created_at" TIMESTAMP NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS "aerich" (
    "id" INTEGER PRIMARY KEY AUTOINCREMENT NOT NULL,
    "version" VARCHAR(255) NOT NULL,
    "app" VARCHAR(100) NOT NULL,
    "content" JSON NOT NULL
);
