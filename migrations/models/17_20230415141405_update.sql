-- upgrade --
ALTER TABLE "special" ADD "emoji" VARCHAR(40) NOT NULL;
-- downgrade --
ALTER TABLE "special" DROP COLUMN "emoji";
