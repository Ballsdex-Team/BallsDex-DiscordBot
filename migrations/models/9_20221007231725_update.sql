-- upgrade --
ALTER TABLE "ballinstance" ADD "special_id" INT;
CREATE TABLE IF NOT EXISTS "special" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(64) NOT NULL,
    "catch_phrase" VARCHAR(128),
    "start_date" TIMESTAMPTZ NOT NULL,
    "end_date" TIMESTAMPTZ NOT NULL,
    "rarity" DOUBLE PRECISION NOT NULL,
    "democracy_card" VARCHAR(200) NOT NULL,
    "dictatorship_card" VARCHAR(200) NOT NULL,
    "union_card" VARCHAR(200) NOT NULL
);
COMMENT ON COLUMN "special"."catch_phrase" IS 'Sentence sent in bonus when someone catches a special card';
COMMENT ON COLUMN "special"."rarity" IS 'Value between 0 and 1, chances of using this special background.';;
ALTER TABLE "ballinstance" ADD CONSTRAINT "fk_ballinst_special_25656e1a" FOREIGN KEY ("special_id") REFERENCES "special" ("id") ON DELETE SET NULL;
-- downgrade --
ALTER TABLE "ballinstance" DROP CONSTRAINT "fk_ballinst_special_25656e1a";
ALTER TABLE "ballinstance" DROP COLUMN "special_id";
DROP TABLE IF EXISTS "special";
