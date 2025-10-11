# your_app/management/commands/fetch_nfl_winners.py

from django.core.management.base import BaseCommand
from survivorPool.tasks.nfl import get_nfl_weekly_winners
from datetime import datetime
from survivorPool.models import Pick, Team


def get_current_nfl_week(season_start_date):
    today = datetime.now().date()
    if today < season_start_date:
        return 0  # preseason or offseason
    delta = today - season_start_date
    week = delta.days // 7 + 1
    return min(week, 18)  # limit to 18 weeks

class Command(BaseCommand):
    help = 'Fetch NFL game winners and update Pick model'

    def handle(self, *args, **kwargs):
        current_year = datetime.now().year
        season_start_date = datetime(2025, 9, 5).date()
        current_week = get_current_nfl_week(season_start_date)

        results = get_nfl_weekly_winners(current_year, current_week)

        if current_week == 0:
            self.stdout.write(self.style.WARNING("NFL regular season hasn't started yet."))
            return

        updated_count = 0
        for result in results:
            winner_team_name = result["winner"]
            
            # Find the winning team
            try:
                winning_team = Team.objects.get(team_name=winner_team_name)
                
                # Update all picks for this team in this week to is_win=True
                picks_updated = Pick.objects.filter(
                    team=winning_team,
                    week=current_week
                ).update(is_win=True)
                
                updated_count += picks_updated
                
            except Team.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Team '{winner_team_name}' not found in database"))
                continue

        self.stdout.write(self.style.SUCCESS(f"Updated {updated_count} picks as wins for Week {current_week}"))
