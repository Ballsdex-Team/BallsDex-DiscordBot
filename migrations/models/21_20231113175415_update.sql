-- upgrade --
ALTER TABLE "ballinstance" ADD "server_id" BIGINT;
ALTER TABLE "ballinstance" ADD "spawn_time" TIMESTAMPTZ;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "server_id";
ALTER TABLE "ballinstance" DROP COLUMN "spawn_time";
