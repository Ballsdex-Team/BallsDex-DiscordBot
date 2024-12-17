-- upgrade --
ALTER TABLE "special" ADD "credits" VARCHAR(64);
-- downgrade --
ALTER TABLE "special" DROP COLUMN "credits";
