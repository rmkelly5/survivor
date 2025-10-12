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

    def add_arguments(self, parser):
        parser.add_argument(
            '--week',
            type=int,
            help='Specific week number to fetch (optional, defaults to current week)',
        )

    def handle(self, *args, **kwargs):
        current_year = datetime.now().year
        season_start_date = datetime(2025, 9, 5).date()
        
        # Use specified week or calculate current week
        week = kwargs.get('week')
        if week is None:
            current_week = get_current_nfl_week(season_start_date)
        else:
            current_week = week

        results = get_nfl_weekly_winners(current_year, current_week)

        if current_week == 0:
            self.stdout.write(self.style.WARNING("NFL regular season hasn't started yet."))
            return

        wins_updated = 0
        losses_updated = 0
        
        for result in results:
            # Extract team nickname (last word) from full ESPN name
            # e.g., "Philadelphia Eagles" -> "Eagles"
            winner_full_name = result["winner"]
            loser_full_name = result["loser"]
            
            winner_nickname = winner_full_name.split()[-1]
            loser_nickname = loser_full_name.split()[-1]
            
            # Update winning team picks to is_win=True
            try:
                winning_team = Team.objects.get(team_name=winner_nickname)
                wins_count = Pick.objects.filter(
                    team=winning_team,
                    week=current_week
                ).update(is_win=True)
                wins_updated += wins_count
                
            except Team.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Winning team '{winner_nickname}' (from '{winner_full_name}') not found in database"))
            
            # Update losing team picks to is_win=False
            try:
                losing_team = Team.objects.get(team_name=loser_nickname)
                losses_count = Pick.objects.filter(
                    team=losing_team,
                    week=current_week
                ).update(is_win=False)
                losses_updated += losses_count
                
            except Team.DoesNotExist:
                self.stdout.write(self.style.WARNING(f"Losing team '{loser_nickname}' (from '{loser_full_name}') not found in database"))

        self.stdout.write(self.style.SUCCESS(
            f"Week {current_week} results: {wins_updated} picks marked as WINS, {losses_updated} picks marked as LOSSES"
        ))
