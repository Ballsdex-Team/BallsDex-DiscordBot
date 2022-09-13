-- upgrade --
ALTER TABLE "ball" ADD "enabled" BOOL NOT NULL  DEFAULT True;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "enabled";
