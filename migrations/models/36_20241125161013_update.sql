-- upgrade --
ALTER TABLE "ballinstance" ADD "deleted" BOOL NOT NULL  DEFAULT False;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "deleted";