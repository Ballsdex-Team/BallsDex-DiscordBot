-- upgrade --
ALTER TABLE "blacklistedid" ADD "reason" TEXT;
-- downgrade --
ALTER TABLE "blacklistedid" DROP COLUMN "reason";
