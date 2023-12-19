-- upgrade --
ALTER TABLE "special" ADD "hidden" BOOL NOT NULL  DEFAULT False;
-- downgrade --
ALTER TABLE "special" DROP COLUMN "hidden";
