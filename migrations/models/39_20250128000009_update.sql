-- upgrade --
ALTER TABLE "ball" RENAME COLUMN "capacity_description" TO "ability_description";
ALTER TABLE "ball" RENAME COLUMN "capacity_name" TO "ability_name";
ALTER TABLE "ball" RENAME COLUMN "capacity_logic" TO "ability_logic";
-- downgrade --
ALTER TABLE "ball" RENAME COLUMN "ability_description" TO "capacity_description";
ALTER TABLE "ball" RENAME COLUMN "ability_name" TO "capacity_name";
ALTER TABLE "ball" RENAME COLUMN "ability_logic" TO "capacity_logic";
