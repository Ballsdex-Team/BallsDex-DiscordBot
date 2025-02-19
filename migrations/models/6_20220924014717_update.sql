-- upgrade --
ALTER TABLE "ball" ADD "short_name" VARCHAR(12);
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "short_name";
