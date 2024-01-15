-- upgrade --
ALTER TABLE "ball" ADD "created_at" TIMESTAMPTZ   DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE "player" ADD "privacy_policy" SMALLINT NOT NULL  DEFAULT 2;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "created_at";
ALTER TABLE "player" DROP COLUMN "privacy_policy";
