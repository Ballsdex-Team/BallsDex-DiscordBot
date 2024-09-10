-- upgrade --
ALTER TABLE "ball" ADD "translations" TEXT;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "translations";
