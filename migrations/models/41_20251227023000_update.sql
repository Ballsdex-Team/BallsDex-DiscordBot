-- upgrade --
-- Ensure coins and new bonuses exist
ALTER TABLE "player" ADD COLUMN IF NOT EXISTS "coins" INT NOT NULL DEFAULT 0;
ALTER TABLE "ballinstance" ADD COLUMN IF NOT EXISTS "defense_bonus" INT NOT NULL DEFAULT 0;
ALTER TABLE "ballinstance" ADD COLUMN IF NOT EXISTS "shiny" BOOL NOT NULL DEFAULT FALSE;

-- downgrade --
ALTER TABLE "ballinstance" DROP COLUMN IF EXISTS "shiny";
ALTER TABLE "ballinstance" DROP COLUMN IF EXISTS "defense_bonus";
ALTER TABLE "player" DROP COLUMN IF EXISTS "coins";
