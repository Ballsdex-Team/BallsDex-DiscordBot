-- upgrade --
ALTER TABLE "ball" ADD "tradeable" BOOL NOT NULL  DEFAULT True;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "tradeable";
