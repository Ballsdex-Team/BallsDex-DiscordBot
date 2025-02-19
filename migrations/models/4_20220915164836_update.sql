-- upgrade --
ALTER TABLE "ballinstance" ADD "favorite" BOOL NOT NULL  DEFAULT False;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "favorite";
