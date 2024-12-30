-- upgrade --
ALTER TABLE "regime" ADD "template" VARCHAR(64);
ALTER TABLE "special" ADD "template" VARCHAR(64);
ALTER TABLE "special" ALTER COLUMN "start_date" DROP NOT NULL;
ALTER TABLE "special" ALTER COLUMN "end_date" DROP NOT NULL;

WITH shiny_id AS (
    INSERT INTO "special" (name, catch_phrase, rarity, emoji, background, template) VALUES
    ('Shiny', '**It''s a shiny countryball!**', 0.00048828125,
    '✨', '/ballsdex/core/image_generator/src/shiny.png', 'shiny')
    RETURNING id);
UPDATE "ballinstance" SET "special_id" = shiny_id WHERE "shiny" = true;

ALTER TABLE "ballinstance" DROP COLUMN "shiny";
-- downgrade --
ALTER TABLE "ballinstance" ADD "shiny" BOOL NOT NULL  DEFAULT False;

UPDATE "ballinstance" SET "shiny" = true
FROM "special" s WHERE s.id = "special_id"
AND s.name = 'Shiny' AND s.background = '/ballsdex/core/image_generator/src/shiny.png';

DELETE FROM "special" WHERE
    name = 'Shiny' AND background = '/ballsdex/core/image_generator/src/shiny.png';

ALTER TABLE "regime" DROP COLUMN "template";
ALTER TABLE "special" DROP COLUMN "template";
ALTER TABLE "special" ALTER COLUMN "start_date" SET NOT NULL;
ALTER TABLE "special" ALTER COLUMN "end_date" SET NOT NULL;
