-- upgrade --
ALTER TABLE "ball" ADD "created_at" TIMESTAMPTZ   DEFAULT CURRENT_TIMESTAMP;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "created_at";
