-- upgrade --
ALTER TABLE "ballinstance" ADD "server_id" BIGINT;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "spawn_time";
