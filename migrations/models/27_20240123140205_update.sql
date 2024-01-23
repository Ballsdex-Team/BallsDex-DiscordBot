-- upgrade --
ALTER TABLE "ballinstance" ADD "extra_data" JSONB NOT NULL DEFAULT '{}'::JSONB;
-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN "extra_data";
