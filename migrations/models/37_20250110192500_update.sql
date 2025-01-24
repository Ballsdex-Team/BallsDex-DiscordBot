-- upgrade --
CREATE INDEX "idx_ballinstanc_ball_id_0752b7" ON "ballinstance" ("ball_id");
CREATE INDEX "idx_ballinstanc_player__4a2d71" ON "ballinstance" ("player_id");
CREATE INDEX "idx_ballinstanc_special_f3f7e1" ON "ballinstance" ("special_id");
CREATE INDEX "idx_trade_player1_35694c" ON "trade" ("player1_id");
CREATE INDEX "idx_trade_player2_5abb89" ON "trade" ("player2_id");
CREATE INDEX "idx_tradeobject_player__04bc1c" ON "tradeobject" ("player_id");
CREATE INDEX "idx_tradeobject_trade_i_255bae" ON "tradeobject" ("trade_id");
CREATE INDEX "idx_tradeobject_ballins_49034b" ON "tradeobject" ("ballinstance_id");
-- downgrade --
DROP INDEX "idx_ballinstanc_special_f3f7e1";
DROP INDEX "idx_ballinstanc_player__4a2d71";
DROP INDEX "idx_ballinstanc_ball_id_0752b7";
DROP INDEX "idx_tradeobject_ballins_49034b";
DROP INDEX "idx_tradeobject_trade_i_255bae";
DROP INDEX "idx_tradeobject_player__04bc1c";
DROP INDEX "idx_trade_player2_5abb89";
DROP INDEX "idx_trade_player1_35694c";
