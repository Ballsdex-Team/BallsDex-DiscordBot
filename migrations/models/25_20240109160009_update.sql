-- upgrade --
ALTER TABLE "ball" ADD "created_at" TIMESTAMPTZ   DEFAULT CURRENT_TIMESTAMP;
UPDATE ball b
SET created_at = bi.catch_date
FROM (
  SELECT ball_id, MIN(catch_date) AS catch_date
  FROM ballinstance
  GROUP BY ball_id
) AS bi
WHERE b.id = bi.ball_id;
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "created_at";
