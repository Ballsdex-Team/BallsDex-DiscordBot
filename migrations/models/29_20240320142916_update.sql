-- upgrade --
ALTER TABLE "ballinstance" ADD "spawned_time" TIMESTAMPTZ;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "spawned_time";
