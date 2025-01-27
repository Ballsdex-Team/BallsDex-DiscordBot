-- upgrade --
ALTER TABLE "blacklistedguild" ADD "expiry_date" TIMESTAMPTZ;
ALTER TABLE "blacklistedid" ADD "expiry_date" TIMESTAMPTZ;
-- downgrade --
ALTER TABLE "blacklistedid" DROP COLUMN "expiry_date";
ALTER TABLE "blacklistedguild" DROP COLUMN "expiry_date";
