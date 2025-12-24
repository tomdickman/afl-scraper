CREATE TABLE player (
  id           VARCHAR(100) PRIMARY KEY,
  givenname    VARCHAR(255) NOT NULL,
  familyname   VARCHAR(255) NOT NULL,
  birthdate    DATE NOT NULL
);
