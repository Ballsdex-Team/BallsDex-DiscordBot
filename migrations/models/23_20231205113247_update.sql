-- upgrade --
ALTER TABLE "ballinstance" ADD "tradeable" BOOL NOT NULL  DEFAULT True;
ALTER TABLE "special" ADD "tradeable" BOOL NOT NULL  DEFAULT True;
-- downgrade --
ALTER TABLE "special" DROP COLUMN "tradeable";
ALTER TABLE "ballinstance" DROP COLUMN "tradeable";
