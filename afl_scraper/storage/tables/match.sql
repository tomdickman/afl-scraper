CREATE TABLE IF NOT EXISTS match (
  id           VARCHAR(50) PRIMARY KEY,
  venue        VARCHAR(100) NOT NULL,
  year         INT NOT NULL,
  roundnumber  VARCHAR(10) NOT NULL,
  hometeam     VARCHAR(50) NOT NULL,
  awayteam     VARCHAR(50) NOT NULL,
  matchdate    TIMESTAMPTZ NOT NULL,
  homegoals    INT NOT NULL,
  homebehinds  INT NOT NULL,
  awaygoals    INT NOT NULL,
  awaybehinds  INT NOT NULL,
  FOREIGN KEY (venue) REFERENCES venue(id),
  FOREIGN KEY (hometeam) REFERENCES team(id),
  FOREIGN KEY (awayteam) REFERENCES team(id)
);
