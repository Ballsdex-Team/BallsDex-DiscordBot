-- upgrade --
ALTER TABLE "special" ADD "emoji" VARCHAR(20);
-- downgrade --
ALTER TABLE "special" DROP COLUMN "emoji";
