-- upgrade --
ALTER TABLE "blacklistedid" ADD "date" TIMESTAMPTZ   DEFAULT CURRENT_TIMESTAMP;
-- downgrade --
ALTER TABLE "blacklistedid" DROP COLUMN "date";
