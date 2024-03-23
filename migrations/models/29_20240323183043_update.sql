-- upgrade --
ALTER TABLE "player" ADD "developer" BOOL NOT NULL  DEFAULT False;
-- downgrade --
ALTER TABLE "player" DROP COLUMN "developer";
