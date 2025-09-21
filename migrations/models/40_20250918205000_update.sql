-- upgrade --
-- Safeguard: add coins column if it somehow was missed but model expects it
ALTER TABLE "player" ADD COLUMN IF NOT EXISTS "coins" INT NOT NULL DEFAULT 0;

-- downgrade --
ALTER TABLE "player" DROP COLUMN IF EXISTS "coins";
