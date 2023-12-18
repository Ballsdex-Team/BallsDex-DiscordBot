-- upgrade --
ALTER TABLE "special" ADD "enabled" BOOL NOT NULL  DEFAULT True;
-- downgrade --
ALTER TABLE "special" DROP COLUMN "enabled";
