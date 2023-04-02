-- upgrade --
ALTER TABLE "player" ADD "donation_policy" SMALLINT NOT NULL  DEFAULT 1;
-- downgrade --
ALTER TABLE "player" DROP COLUMN "donation_policy";
