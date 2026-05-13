CREATE TABLE player_id_mapping (
  afl_official_id   VARCHAR(10),
  player_id       VARCHAR(100) NOT NULL REFERENCES player(id),
  year           INTEGER NOT NULL,
  created_at     TIMESTAMP DEFAULT NOW(),
  updated_at    TIMESTAMP DEFAULT NOW(),

  PRIMARY KEY (player_id, year),
  UNIQUE(afl_official_id, year)
);