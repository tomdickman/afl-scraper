CREATE TABLE game_source_identity (
  source            VARCHAR(50) NOT NULL,
  source_match_id   VARCHAR(100) NOT NULL,
  game_id           INTEGER NOT NULL REFERENCES game(id) ON DELETE CASCADE,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (source, source_match_id),
  CHECK (source <> ''),
  CHECK (source_match_id <> '')
);

CREATE INDEX ix_game_source_identity_game
  ON game_source_identity (game_id);
