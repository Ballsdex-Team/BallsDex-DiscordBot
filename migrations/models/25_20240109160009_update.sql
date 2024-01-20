-- upgrade --
ALTER TABLE "ball" ADD "created_at" TIMESTAMPTZ   DEFAULT CURRENT_TIMESTAMP;
UPDATE ball b
SET created_at = (
  SELECT inst.catch_date
  FROM ballinstance inst
  WHERE inst.ball_id = b.id
  ORDER BY inst.catch_date ASC
  LIMIT 1
);
-- downgrade --
ALTER TABLE "ball" DROP COLUMN "created_at";
