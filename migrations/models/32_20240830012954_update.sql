-- upgrade --
ALTER TABLE "guildconfig" ADD "silent" BOOL NOT NULL  DEFAULT False;
-- downgrade --
ALTER TABLE "guildconfig" DROP COLUMN "silent";