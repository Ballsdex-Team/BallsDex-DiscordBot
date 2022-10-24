-- upgrade --
ALTER TABLE "ballinstance" DROP CONSTRAINT "ballinstance_trade_player_id_fkey";
ALTER TABLE "ballinstance" ADD CONSTRAINT "fk_ballinst_player_6b1aca0e" FOREIGN KEY ("trade_player_id") REFERENCES "player" ("id") ON DELETE SET NULL;
-- downgrade --
ALTER TABLE "ballinstance" DROP CONSTRAINT "fk_ballinst_player_6b1aca0e";
ALTER TABLE "ballinstance" ADD CONSTRAINT "ballinstance_trade_player_id_fkey" FOREIGN KEY ("trade_player_id") REFERENCES "player" ("id") ON DELETE CASCADE;
