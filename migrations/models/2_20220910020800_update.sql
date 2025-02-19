-- upgrade --
ALTER TABLE "ballinstance" ALTER COLUMN "trade_player_id" DROP NOT NULL;
-- downgrade --
ALTER TABLE "ballinstance" ALTER COLUMN "trade_player_id" SET NOT NULL;
