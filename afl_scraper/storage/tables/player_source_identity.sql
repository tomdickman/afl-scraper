CREATE TABLE player_source_identity (
  source             VARCHAR(50) NOT NULL,
  source_player_id   VARCHAR(100) NOT NULL,
  year               INTEGER NOT NULL,
  player_id          VARCHAR(100) NOT NULL REFERENCES player(id),
  created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),

  PRIMARY KEY (source, source_player_id, year),
  UNIQUE (source, player_id, year),
  CHECK (source <> ''),
  CHECK (source_player_id <> '')
);

CREATE INDEX ix_player_source_identity_player
  ON player_source_identity (player_id);
