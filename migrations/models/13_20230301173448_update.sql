-- upgrade --
ALTER TABLE "ballinstance" DROP COLUMN "count";
-- downgrade --
ALTER TABLE "ballinstance" ADD "count" INT NOT NULL;
