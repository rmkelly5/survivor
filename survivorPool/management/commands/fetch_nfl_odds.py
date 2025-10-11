from django.core.management.base import BaseCommand
from survivorPool.models import Team
import requests
from datetime import datetime
import os
import pytz

class Command(BaseCommand):
    help = 'Fetches NFL matchups and betting odds from The Odds API and updates Team records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--week',
            type=int,
            help='NFL week number to fetch odds for',
        )

    def handle(self, *args, **options):
        api_key = os.environ.get('ODDS_API_KEY')
        
        if not api_key:
            self.stdout.write(
                self.style.ERROR('ODDS_API_KEY not found in environment variables.')
            )
            self.stdout.write(
                'Please set ODDS_API_KEY in Replit Secrets with your API key from https://the-odds-api.com/'
            )
            return
        
        week = options.get('week')
        if not week:
            self.stdout.write(self.style.ERROR('Please specify a week number with --week'))
            return

        url = 'https://api.the-odds-api.com/v4/sports/americanfootball_nfl/odds'
        params = {
            'apiKey': api_key,
            'regions': 'us',
            'markets': 'h2h,spreads',
            'oddsFormat': 'american'
        }
        
        try:
            self.stdout.write('Fetching NFL odds from The Odds API...')
            response = requests.get(url, params=params)
            response.raise_for_status()
            
            remaining_requests = response.headers.get('x-requests-remaining')
            if remaining_requests:
                self.stdout.write(f'API requests remaining: {remaining_requests}')
            
            games = response.json()
            self.stdout.write(f'Found {len(games)} games')
            
            updated_count = 0
            skipped_count = 0
            
            # Get current time in EST
            est_tz = pytz.timezone('US/Eastern')
            current_time_est = datetime.now(est_tz)
            
            for game in games:
                home_team_name = self.extract_team_nickname(game['home_team'])
                away_team_name = self.extract_team_nickname(game['away_team'])
                
                try:
                    home_team = Team.objects.get(team_name__iexact=home_team_name)
                    away_team = Team.objects.get(team_name__iexact=away_team_name)
                except Team.DoesNotExist:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Team not found: {home_team_name} or {away_team_name} - Skipping'
                        )
                    )
                    skipped_count += 1
                    continue
                
                # Parse game time and convert to EST
                commence_time_utc = datetime.fromisoformat(game['commence_time'].replace('Z', '+00:00'))
                commence_time = commence_time_utc.astimezone(est_tz)
                
                # Skip games that already happened
                if commence_time < current_time_est:
                    self.stdout.write(
                        self.style.WARNING(
                            f'Skipping past game: {away_team_name} @ {home_team_name} '
                            f'({commence_time.strftime("%a %I:%M %p")} EST)'
                        )
                    )
                    skipped_count += 1
                    continue
                
                spread = None
                home_is_favorite = False
                moneyline_home = None
                moneyline_away = None
                
                if game.get('bookmakers'):
                    bookmaker = game['bookmakers'][0]
                    
                    spread_market = next((m for m in bookmaker['markets'] if m['key'] == 'spreads'), None)
                    if spread_market:
                        for outcome in spread_market['outcomes']:
                            if outcome['name'] == game['home_team']:
                                home_spread = outcome.get('point', 0)
                                if home_spread < 0:
                                    home_is_favorite = True
                                    spread = abs(home_spread)
                            elif outcome['name'] == game['away_team']:
                                away_spread = outcome.get('point', 0)
                                if away_spread < 0:
                                    spread = abs(away_spread)
                    
                    h2h_market = next((m for m in bookmaker['markets'] if m['key'] == 'h2h'), None)
                    if h2h_market:
                        for outcome in h2h_market['outcomes']:
                            if outcome['name'] == game['home_team']:
                                moneyline_home = outcome['price']
                            elif outcome['name'] == game['away_team']:
                                moneyline_away = outcome['price']
                
                home_team.opponent = away_team_name
                home_team.game_time = commence_time
                home_team.spread = spread if home_is_favorite else None
                home_team.moneyline = moneyline_home
                home_team.is_home = True
                home_team.current_week = week
                home_team.is_favorite = home_is_favorite
                home_team.save()
                
                away_team.opponent = home_team_name
                away_team.game_time = commence_time
                away_team.spread = spread if not home_is_favorite else None
                away_team.moneyline = moneyline_away
                away_team.is_home = False
                away_team.current_week = week
                away_team.is_favorite = not home_is_favorite
                away_team.save()
                
                updated_count += 1
                favorite_symbol = "⭐" if home_is_favorite else ""
                game_time_str = commence_time.strftime("%a %I:%M %p EST")
                self.stdout.write(
                    self.style.SUCCESS(
                        f'Updated: {away_team_name} @ {home_team_name} {favorite_symbol} - {game_time_str} (Week {week})'
                    )
                )
            
            self.stdout.write(
                self.style.SUCCESS(
                    f'\nCompleted! Updated {updated_count * 2} teams ({updated_count} matchups), Skipped: {skipped_count}'
                )
            )
            
        except requests.RequestException as e:
            self.stdout.write(
                self.style.ERROR(f'Error fetching data from The Odds API: {str(e)}')
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Error: {str(e)}')
            )

    def extract_team_nickname(self, full_name):
        """Extract team nickname from full name (e.g., 'Kansas City Chiefs' -> 'Chiefs')"""
        return full_name.split()[-1]
