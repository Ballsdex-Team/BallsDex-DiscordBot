-- upgrade --
ALTER TABLE "ballinstance" ADD "locked" TIMESTAMPTZ;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "locked";
