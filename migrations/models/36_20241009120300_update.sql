-- upgrade --
ALTER TABLE "special" ALTER COLUMN "start_date" DROP NOT NULL;
ALTER TABLE "special" ALTER COLUMN "end_date" DROP NOT NULL;

WITH shiny_id AS (
    INSERT INTO "special" (name, catch_phrase, rarity, emoji, background) VALUES
    ('Shiny', '**It''s a shiny countryball!**', 0.00048828125,
    '✨', '/ballsdex/core/image_generator/src/shiny.png')
    RETURNING id)
UPDATE "ballinstance" SET "special_id" = (SELECT id FROM shiny_id) WHERE "shiny" = true;

ALTER TABLE "ballinstance" DROP COLUMN "shiny";
-- downgrade --
ALTER TABLE "ballinstance" ADD "shiny" BOOL NOT NULL  DEFAULT False;

UPDATE "ballinstance" SET "shiny" = true
FROM "special" s
WHERE s.id = special_id
AND s.background = '/ballsdex/core/image_generator/src/shiny.png';

DELETE FROM "special" WHERE
background = '/ballsdex/core/image_generator/src/shiny.png';

ALTER TABLE "special" ALTER COLUMN "start_date" SET NOT NULL;
ALTER TABLE "special" ALTER COLUMN "end_date" SET NOT NULL;
