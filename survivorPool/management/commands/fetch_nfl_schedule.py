from datetime import datetime
import re

import requests
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from survivorPool.models import Game, Team


NFL_WEEK_URL = 'https://www.nfl.com/schedules/{year}/by-week/reg-{week:02d}'
GAME_PATTERN = re.compile(
    r'"homeTeam":\{"id":"[^"]+","currentLogo":"[^"]+","fullName":"(?P<home>[^"]+)"\},'
    r'"awayTeam":\{"id":"[^"]+","currentLogo":"[^"]+","fullName":"(?P<away>[^"]+)"\}'
    r'.*?"time":"(?P<time>[^"]+)".*?"season":(?P<season>\d+).*?"week":(?P<week>\d+)',
    re.S,
)
GAME_LINK_PATTERN = re.compile(
    r'href="/games/(?P<away>[a-z0-9-]+)-at-(?P<home>[a-z0-9-]+)-'
    r'(?P<year>\d{4})-reg-(?P<week>\d+)"'
)
TEAM_SLUGS = {
    '49ers': '49ers',
    'bears': 'Bears',
    'bengals': 'Bengals',
    'bills': 'Bills',
    'broncos': 'Broncos',
    'browns': 'Browns',
    'buccaneers': 'Buccaneers',
    'cardinals': 'Cardinals',
    'chargers': 'Chargers',
    'chiefs': 'Chiefs',
    'colts': 'Colts',
    'commanders': 'Commanders',
    'cowboys': 'Cowboys',
    'dolphins': 'Dolphins',
    'eagles': 'Eagles',
    'falcons': 'Falcons',
    'giants': 'Giants',
    'jaguars': 'Jaguars',
    'jets': 'Jets',
    'lions': 'Lions',
    'packers': 'Packers',
    'panthers': 'Panthers',
    'patriots': 'Patriots',
    'raiders': 'Raiders',
    'rams': 'Rams',
    'ravens': 'Ravens',
    'saints': 'Saints',
    'seahawks': 'Seahawks',
    'steelers': 'Steelers',
    'texans': 'Texans',
    'titans': 'Titans',
    'vikings': 'Vikings',
}


def extract_team_nickname(full_name):
    return full_name.split()[-1]


def parse_nfl_week_schedule(html, year, week):
    text = html.replace('\\"', '"').replace('\\u0026', '&')
    games_by_matchup = {}

    for match in GAME_PATTERN.finditer(text):
        game_year = int(match.group('season'))
        game_week = int(match.group('week'))
        if game_year != year or game_week != week:
            continue

        game_time = datetime.fromisoformat(match.group('time').replace('Z', '+00:00'))
        away = extract_team_nickname(match.group('away'))
        home = extract_team_nickname(match.group('home'))
        games_by_matchup[(away, home)] = {
            'home': extract_team_nickname(match.group('home')),
            'away': extract_team_nickname(match.group('away')),
            'game_time': game_time.astimezone(timezone.get_current_timezone()),
        }

    for match in GAME_LINK_PATTERN.finditer(text):
        game_year = int(match.group('year'))
        game_week = int(match.group('week'))
        if game_year != year or game_week != week:
            continue

        away = TEAM_SLUGS.get(match.group('away'))
        home = TEAM_SLUGS.get(match.group('home'))
        if not away or not home:
            continue

        games_by_matchup.setdefault((away, home), {
            'home': home,
            'away': away,
            'game_time': None,
        })

    return list(games_by_matchup.values())


class Command(BaseCommand):
    help = 'Fetch the NFL regular-season schedule from NFL.com and store it as Game records'

    def add_arguments(self, parser):
        parser.add_argument(
            '--year',
            type=int,
            default=settings.NFL_SEASON_YEAR,
            help='NFL season year to fetch',
        )
        parser.add_argument(
            '--week',
            type=int,
            help='Optional week number to fetch. Defaults to all regular-season weeks.',
        )

    def handle(self, *args, **options):
        year = options['year']
        weeks = [options['week']] if options.get('week') else range(1, 19)

        created_count = 0
        updated_count = 0

        for week in weeks:
            url = NFL_WEEK_URL.format(year=year, week=week)
            response = requests.get(url, timeout=20)
            response.raise_for_status()

            games = parse_nfl_week_schedule(response.text, year, week)
            if not games:
                self.stdout.write(
                    self.style.WARNING(f'Week {week}: no {year} games found at {url}')
                )
                continue

            for game in games:
                home_team, _ = Team.objects.get_or_create(team_name=game['home'])
                away_team, _ = Team.objects.get_or_create(team_name=game['away'])

                _, created = Game.objects.update_or_create(
                    season_year=year,
                    week=week,
                    home_team=home_team,
                    away_team=away_team,
                    defaults={'game_time': game['game_time']},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

            self.stdout.write(
                self.style.SUCCESS(
                    f'Week {week}: synced {len(games)} scheduled games for {year}'
                )
            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Completed schedule sync: {created_count} created, {updated_count} updated'
            )
        )
