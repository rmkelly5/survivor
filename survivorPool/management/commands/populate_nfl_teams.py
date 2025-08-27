from django.core.management.base import BaseCommand
from survivorPool.models import Team  

class Command(BaseCommand):
    help = 'Populates the Team model with all NFL team names (team names only, no city/state)'

    def handle(self, *args, **options):
        nfl_teams = [
            "49ers", "Bears", "Bengals", "Bills", "Broncos", "Browns", "Buccaneers", "Cardinals",
            "Chargers", "Chiefs", "Colts", "Commanders", "Cowboys", "Dolphins", "Eagles", "Falcons",
            "Giants", "Jaguars", "Jets", "Lions", "Packers", "Panthers", "Patriots", "Raiders",
            "Rams", "Ravens", "Saints", "Seahawks", "Steelers", "Texans", "Titans", "Vikings"
        ]

        created_count = 0
        for team_name in nfl_teams:
            team, created = Team.objects.get_or_create(team_name=team_name)
            if created:
                created_count += 1

        self.stdout.write(self.style.SUCCESS(
            f"Successfully ensured {len(nfl_teams)} teams exist. {created_count} were newly created."
        ))