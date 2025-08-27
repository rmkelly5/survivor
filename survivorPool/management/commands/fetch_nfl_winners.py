# your_app/management/commands/fetch_nfl_winners.py

from django.core.management.base import BaseCommand
from survivorPool.tasks.nfl import get_nfl_weekly_winners
from datetime import datetime
from survivorPool.models import GameResult  # assuming you have this model


def get_current_nfl_week(season_start_date):
    today = datetime.now().date()
    if today < season_start_date:
        return 0  # preseason or offseason
    delta = today - season_start_date
    week = delta.days // 7 + 1
    return min(week, 18)  # limit to 18 weeks

class Command(BaseCommand):
    help = 'Fetch and store NFL game winners'

    def handle(self, *args, **kwargs):
        current_year = datetime.now().year
        # current_week = 18  # Or use logic to calculate current week dynamically
        season_start_date = datetime(2025, 9, 5).date()
        current_week = get_current_nfl_week(season_start_date)

        results = get_nfl_weekly_winners(current_year, current_week)

        if current_week == 0:
            self.stdout.write(self.style.WARNING("NFL regular season hasn't started yet."))
            return

        for result in results:
            GameResult.objects.update_or_create(
                winner=result["winner"],
                loser=result["loser"],
                defaults={
                    "winner_score": result["score"],
                    "loser_score": result["loser_score"],
                    "game_date": result["game_date"],
                }
            )

        self.stdout.write(self.style.SUCCESS(f"Saved {len(results)} game results for Week {current_week}"))
