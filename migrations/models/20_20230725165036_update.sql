-- upgrade --
ALTER TABLE "ball" ADD "economy_id" INT;
ALTER TABLE "ball" ADD "regime_id" INT; -- Add NOT NULL after we filled the table --
CREATE TABLE IF NOT EXISTS "economy" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(64) NOT NULL,
    "icon" VARCHAR(200) NOT NULL
);
COMMENT ON COLUMN "ball"."economy_id" IS 'Economical regime of this country';
COMMENT ON COLUMN "ball"."regime_id" IS 'Political regime of this country';
COMMENT ON COLUMN "economy"."icon" IS '512x512 PNG image';;
CREATE TABLE IF NOT EXISTS "regime" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "name" VARCHAR(64) NOT NULL,
    "background" VARCHAR(200) NOT NULL
);
COMMENT ON COLUMN "regime"."background" IS '1428x2000 PNG image';;
ALTER TABLE "special" ADD "background" VARCHAR(200);
UPDATE "special" SET "background" = "democracy_card";
ALTER TABLE "special" DROP COLUMN "democracy_card";
ALTER TABLE "special" DROP COLUMN "union_card";
ALTER TABLE "special" DROP COLUMN "dictatorship_card";
ALTER TABLE "ball" ADD CONSTRAINT "fk_ball_regime_d7fd92a9" FOREIGN KEY ("regime_id") REFERENCES "regime" ("id") ON DELETE CASCADE;
ALTER TABLE "ball" ADD CONSTRAINT "fk_ball_economy_cfe9c5c3" FOREIGN KEY ("economy_id") REFERENCES "economy" ("id") ON DELETE SET NULL;
INSERT INTO "economy" ("name", "icon") VALUES
    ('Capitalist', '/ballsdex/core/image_generator/src/capitalist.png'),
    ('Communist', '/ballsdex/core/image_generator/src/communist.png');
INSERT INTO "regime" ("name", "background") VALUES
    ('Democracy', '/ballsdex/core/image_generator/src/democracy.png'),
    ('Dictatorship', '/ballsdex/core/image_generator/src/dictatorship.png'),
    ('Union', '/ballsdex/core/image_generator/src/union.png');
UPDATE "ball" SET "economy_id" = "economy" WHERE "economy" != 3;
UPDATE "ball" SET "economy_id" = null WHERE "economy" = 3;
UPDATE "ball" SET "regime_id" = "regime";
ALTER TABLE "ball" ALTER COLUMN "regime_id" SET NOT NULL; -- Table filled, now we can put non-nullable constraint --
ALTER TABLE "ball" DROP COLUMN "economy";
ALTER TABLE "ball" DROP COLUMN "regime";
-- downgrade --
ALTER TABLE "ball" DROP CONSTRAINT "fk_ball_economy_cfe9c5c3";
ALTER TABLE "ball" DROP CONSTRAINT "fk_ball_regime_d7fd92a9";
ALTER TABLE "ball" ADD "regime" SMALLINT;
ALTER TABLE "ball" ADD "economy" SMALLINT;
UPDATE "ball" SET "regime" = "regime_id";
UPDATE "ball" SET "economy" = "economy_id";
ALTER TABLE "ball" DROP COLUMN "economy_id";
ALTER TABLE "ball" DROP COLUMN "regime_id";
ALTER TABLE "special" ADD "democracy_card" VARCHAR(200);
ALTER TABLE "special" ADD "union_card" VARCHAR(200);
ALTER TABLE "special" ADD "dictatorship_card" VARCHAR(200);
ALTER TABLE "special" DROP COLUMN "background";
DROP TABLE IF EXISTS "economy";
DROP TABLE IF EXISTS "regime";
ALTER TABLE "ball" ALTER COLUMN "regime" SET NOT NULL;
ALTER TABLE "ball" ALTER COLUMN "regime" SET NOT NULL;
