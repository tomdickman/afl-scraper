CREATE TABLE venue (
  id           VARCHAR(100) PRIMARY KEY,
  name         VARCHAR(255) UNIQUE NOT NULL,
  city         VARCHAR(255) NOT NULL,
  state        VARCHAR(255) NOT NULL,
  country      VARCHAR(255) NOT NULL,
  latitude     FLOAT NOT NULL,
  longitude    FLOAT NOT NULL
);
