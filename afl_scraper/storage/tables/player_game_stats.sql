CREATE TABLE player_game_stats (
  player_id                 VARCHAR(100) NOT NULL REFERENCES player(id),
  team                      VARCHAR(50) NOT NULL REFERENCES team(id),
  jumper_number             INT NOT NULL,
  kicks                     INT NOT NULL,
  marks                     INT NOT NULL,
  handballs                 INT NOT NULL,
  goals                     INT NOT NULL,
  behinds                   INT NOT NULL,
  hitouts                   INT NOT NULL,
  tackles                   INT NOT NULL,
  rebound_50s               INT,
  inside_50s                INT,
  clearances                INT,
  clangers                  INT,
  free_kicks_for            INT,
  free_kicks_against        INT,
  contested_possessions     INT,
  uncontested_possessions   INT,
  contested_marks           INT,
  marks_inside_50           INT,
  one_percenters            INT,
  bounces                   INT,
  goal_assists              INT,
  time_on_ground_percent    NUMERIC(5,2),
  fantasy_points            INT,
  game_id                   INT NOT NULL REFERENCES game(id),
  PRIMARY KEY (player_id, game_id),
  CHECK (time_on_ground_percent BETWEEN 0 AND 100),
  CHECK (
    kicks >= 0 AND
    marks >= 0 AND
    handballs >= 0 AND
    goals >= 0 AND
    behinds >= 0 AND
    hitouts >= 0 AND
    tackles >= 0 AND
    rebound_50s >= 0 AND
    inside_50s >= 0 AND
    clearances >= 0 AND
    clangers >= 0 AND
    free_kicks_for >= 0 AND
    free_kicks_against >= 0 AND
    contested_possessions >= 0 AND
    uncontested_possessions >= 0 AND
    contested_marks >= 0 AND
    marks_inside_50 >= 0 AND
    one_percenters >= 0 AND
    bounces >= 0 AND
    goal_assists >= 0 AND
    fantasy_points >= 0
  )
);
