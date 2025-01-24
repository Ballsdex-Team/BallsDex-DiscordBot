-- upgrade --
DROP TABLE IF EXISTS "user";
-- downgrade --
CREATE TABLE IF NOT EXISTS "user" (
    "id" SERIAL NOT NULL PRIMARY KEY,
    "username" VARCHAR(50) NOT NULL UNIQUE,
    "password" VARCHAR(200) NOT NULL,
    "last_login" TIMESTAMPTZ NOT NULL,
    "avatar" VARCHAR(200) NOT NULL  DEFAULT '',
    "intro" TEXT NOT NULL,
    "created_at" TIMESTAMPTZ NOT NULL  DEFAULT CURRENT_TIMESTAMP
);
COMMENT ON COLUMN "user"."last_login" IS 'Last Login';
