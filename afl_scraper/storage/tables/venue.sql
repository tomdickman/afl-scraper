CREATE TABLE IF NOT EXISTS venue (
  id           VARCHAR(100) PRIMARY KEY,
  name         VARCHAR(255) UNIQUE NOT NULL,
  city         VARCHAR(255) NOT NULL,
  state        VARCHAR(255) NOT NULL,
  country      VARCHAR(255) NOT NULL,
  latitude     FLOAT NOT NULL,
  longitude    FLOAT NOT NULL
);

INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Adelaide Oval', 'Adelaide Oval', 'Adelaide', 'South Australia', 'Australia', -34.915556, 138.596111);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Bellerive Oval', 'Blundstone Arena', 'Hobart', 'Tasmania', 'Australia', -42.87722, 147.37387);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Blacktown', 'Blacktown International Sports Park', 'Sydney', 'New South Wales', 'Australia', -33.76926, 150.85819);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Carrara', 'Heritage Bank Stadium', 'Gold Coast', 'Queensland', 'Australia', -28.00633, 153.36704);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Cazaly''s Stadium', 'Cazaly''s Stadium', 'Cairns', 'Queensland', 'Australia', -16.93574, 145.74895);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Docklands', 'Marvel Stadium', 'Melbourne', 'Victoria', 'Australia', -37.816667, 144.94768);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Eureka Stadium', 'Mars Stadium', 'Ballarat', 'Victoria', 'Australia', -37.538340, 143.848015);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Football Park', 'Football Park', 'Adelaide', 'South Australia', 'Australia', -34.879837, 138.495317);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Gabba', 'The Gabba', 'Brisbane', 'Queensland', 'Australia', -27.48539, 153.03827);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Jiangwan Stadium', 'Jiangwan Stadium', 'Shanghai', 'Shanghai', 'China', 31.306607, 121.515530);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Kardinia Park', 'GMHBA Stadium', 'Geelong', 'Victoria', 'Australia', -38.158006, 144.354544);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('M.C.G.', 'Melbourne Cricket Ground', 'Melbourne', 'Victoria', 'Australia', -37.82056, 144.98389);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Manuka Oval', 'Manuka Oval', 'Canberra', 'Australian Capital Territory', 'Australia', -35.318159, 149.134522);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Marrara Oval', 'TIO Stadium', 'Darwin', 'Northern Territory', 'Australia', -12.399114, 130.887141);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Norwood Oval', 'Norwood Oval', 'Adelaide', 'South Australia', 'Australia', -34.919857, 138.630618);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Perth Stadium', 'Optus Stadium', 'Perth', 'Western Australia', 'Australia', -31.951155, 115.889035);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Riverway Stadium', 'Riverway Stadium', 'Townsville', 'Queensland', 'Australia', -19.317660, 146.732029);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('S.C.G.', 'Sydney Cricket Ground', 'Sydney', 'New South Wales', 'Australia', -33.891584, 151.224816);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Stadium Australia', 'Accor Stadium', 'Sydney', 'New South Wales', 'Australia', -33.846981, 151.063349);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Subiaco', 'Subiaco Oval', 'Perth', 'Western Australia', 'Australia', -31.944596, 115.830015);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Summit Sports Park', 'Summit Sports Park', 'Mount Barker Summit', 'South Australia', 'Australia', -19.317660, 146.732029);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Sydney Showground', 'Sydney Showground Stadium', 'Sydney', 'New South Wales', 'Australia', -33.843005, 151.067731);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Traeger Park', 'TIO Traeger Park', 'Alice Springs', 'Northern Territory', 'Australia', -23.709149, 133.8748802);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('Wellington', 'Westpac Stadium', 'Wellington', 'Wellington', 'New Zealand', -41.272941, 174.785780);
INSERT INTO venue (id, name, city, state, country, latitude, longitude) VALUES ('York Park', 'University of Tasmania Stadium', 'Launceston', 'Tasmania', 'Australia', -41.425945, 147.139080);
