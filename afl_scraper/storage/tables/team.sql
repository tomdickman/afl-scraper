CREATE TABLE IF NOT EXISTS team (
  id       VARCHAR(50) PRIMARY KEY,
  club     VARCHAR(100) UNIQUE NOT NULL,
  mascot   VARCHAR(100) UNIQUE NOT NULL
);

INSERT INTO team (id, club, mascot) VALUES ('Adelaide', 'Adelaide', 'Crows');
INSERT INTO team (id, club, mascot) VALUES ('Brisbane Lions', 'Brisbane', 'Lions');
INSERT INTO team (id, club, mascot) VALUES ('Carlton', 'Carlton', 'Blues');
INSERT INTO team (id, club, mascot) VALUES ('Collingwood', 'Collingwood', 'Magpies');
INSERT INTO team (id, club, mascot) VALUES ('Essendon', 'Essendon', 'Bombers');
INSERT INTO team (id, club, mascot) VALUES ('Fremantle', 'Fremantle', 'Dockers');
INSERT INTO team (id, club, mascot) VALUES ('Geelong', 'Geelong', 'Cats');
INSERT INTO team (id, club, mascot) VALUES ('Gold Coast', 'Gold Coast', 'Suns');
INSERT INTO team (id, club, mascot) VALUES ('Greater Western Sydney', 'Greater Western Sydney', 'Giants');
INSERT INTO team (id, club, mascot) VALUES ('Hawthorn', 'Hawthorn', 'Hawks');
INSERT INTO team (id, club, mascot) VALUES ('Melbourne', 'Melbourne', 'Demons');
INSERT INTO team (id, club, mascot) VALUES ('North Melbourne', 'North Melbourne', 'Kangaroos');
INSERT INTO team (id, club, mascot) VALUES ('Port Adelaide', 'Port Adelaide', 'Power');
INSERT INTO team (id, club, mascot) VALUES ('Richmond', 'Richmond', 'Tigers');
INSERT INTO team (id, club, mascot) VALUES ('St Kilda', 'St Kilda', 'Saints');
INSERT INTO team (id, club, mascot) VALUES ('Sydney', 'Sydney', 'Swans');
INSERT INTO team (id, club, mascot) VALUES ('West Coast', 'West Coast', 'Eagles');
INSERT INTO team (id, club, mascot) VALUES ('Western Bulldogs', 'Western Bulldogs', 'Bulldogs');
