CREATE VIEW player_game_stats_with_career_number AS
SELECT
  player_stats.*,
  game.start_date,
  game.year,
  game.round,
  ROW_NUMBER() OVER (
    PARTITION BY player_stats.player_id
    ORDER BY game.start_date, game.id
  ) AS career_game_number
FROM player_game_stats AS player_stats
JOIN game ON game.id = player_stats.game_id;
