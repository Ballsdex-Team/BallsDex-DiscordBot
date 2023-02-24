-- upgrade --
ALTER TABLE "ball" ADD "catch_names" TEXT;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "catch_names";
