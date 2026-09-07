# Survivor Pool Season Runbook

This project uses a shared Neon database, so management commands run from the
workspace update the data used by both development and production.

## Start a new season

1. Confirm the season settings in `survivor/settings.py`:
   - `NFL_SEASON_YEAR`
   - `NFL_SEASON_START_DATE`
2. Confirm the `ODDS_API_KEY` secret is available.
3. Apply migrations:

   ```bash
   python manage.py migrate
   ```

4. Remove prior-season Picks and stale matchup data only after confirming that
   the historical data is no longer needed. Keep user and team records.
5. Load the official schedule for the opening week:

   ```bash
   python manage.py fetch_nfl_schedule --year 2026 --week 1
   ```

6. Add current kickoff times and betting lines:

   ```bash
   python manage.py fetch_nfl_odds --year 2026 --week 1
   ```

7. Verify the load:

   ```bash
   python manage.py shell -c "from survivorPool.models import Game, Team; print('Games:', Game.objects.filter(season_year=2026, week=1).count()); print('Teams:', Team.objects.filter(current_week=1).count())"
   ```

   A normal NFL week should show 16 games and 32 teams. Holiday or bye-week
   schedules can contain fewer games.

8. Sign in and confirm the Make a Pick page shows each matchup once with the
   correct home team, away team, and kickoff time.

## Weekly procedure

Run these commands with the new week number:

```bash
python manage.py fetch_nfl_schedule --year 2026 --week WEEK
python manage.py fetch_nfl_odds --year 2026 --week WEEK
```

Then verify the Game and Team counts for that week and review the Make a Pick
page. Both commands are safe to rerun: existing schedule records are updated,
and the selected week's team matchup fields are refreshed before odds are
loaded.

## After games finish

Update pick outcomes for the completed week:

```bash
python manage.py fetch_nfl_winners --week WEEK
```

Review the League Picks and Leaderboard pages after the command completes.

## Important safeguards

- Never run a cleanup command without first counting the affected records.
- Picks are permanent league history once the season begins; do not clear them
  as part of the normal weekly process.
- Do not delete user or team records during a season reset.
- The Odds API has a request quota. One odds refresh is normally sufficient
  unless lines or kickoff times changed.
- If schedule and odds counts differ, stop and inspect the Make a Pick page
  before opening picks.