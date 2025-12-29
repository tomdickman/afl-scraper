CREATE TABLE game (
  id INT PRIMARY KEY CHECK (id > 0),
  venue VARCHAR(100) NOT NULL REFERENCES venue(id),
  start_date TIMESTAMPTZ NOT NULL,
  year INT GENERATED ALWAYS AS (
    EXTRACT(YEAR FROM start_date AT TIME ZONE 'UTC')
  ) STORED,
  round VARCHAR(20) NOT NULL,
  home_team VARCHAR(50) NOT NULL REFERENCES team(id),
  away_team VARCHAR(50) NOT NULL REFERENCES team(id),
  home_goals INT NOT NULL CHECK (home_goals >= 0),
  home_behinds INT NOT NULL CHECK (home_behinds >= 0),
  away_goals INT NOT NULL CHECK (away_goals >= 0),
  away_behinds INT NOT NULL CHECK (away_behinds >= 0),
  CHECK (home_team <> away_team)
);
