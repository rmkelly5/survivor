import datetime
import io
from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from .models import Game, Team


def feed_game(home, away, kickoff, home_spread, home_moneyline):
    return {
        'home_team': home,
        'away_team': away,
        'commence_time': kickoff.isoformat(),
        'bookmakers': [{
            'key': 'draftkings',
            'title': 'DraftKings',
            'markets': [
                {
                    'key': 'spreads',
                    'outcomes': [
                        {'name': home, 'point': -home_spread},
                        {'name': away, 'point': home_spread},
                    ],
                },
                {
                    'key': 'h2h',
                    'outcomes': [
                        {'name': home, 'price': home_moneyline},
                        {'name': away, 'price': 200},
                    ],
                },
            ],
        }],
    }


class OddsRefreshAfterKickoffTests(TestCase):
    def setUp(self):
        self.thursday = timezone.now() - datetime.timedelta(days=3)
        self.sunday = timezone.now() + datetime.timedelta(hours=6)
        self.bills = Team.objects.create(
            team_name='Bills', opponent='Dolphins', game_time=self.thursday,
            spread=Decimal('7.5'), moneyline=-300, is_favorite=True,
            is_home=True, current_week=5,
        )
        self.dolphins = Team.objects.create(
            team_name='Dolphins', opponent='Bills', game_time=self.thursday,
            moneyline=240, is_favorite=False, is_home=False, current_week=5,
        )
        self.chiefs = Team.objects.create(team_name='Chiefs')
        self.raiders = Team.objects.create(team_name='Raiders')
        self.played = Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=5,
            home_team=self.bills, away_team=self.dolphins, game_time=self.thursday,
            home_spread=Decimal('7.5'), home_moneyline=-300,
            home_is_favorite=True, away_moneyline=240,
        )
        self.unstarted = Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=5,
            home_team=self.chiefs, away_team=self.raiders, game_time=self.sunday,
            home_spread=Decimal('3.5'), home_moneyline=-160,
            home_is_favorite=True,
        )
        self.schedule = {
            ('Bills', 'Dolphins'): self.thursday,
            ('Chiefs', 'Raiders'): self.sunday,
        }

    def refresh(self, get_odds, get_schedule, games):
        get_schedule.return_value = self.schedule
        get_odds.return_value.headers = {}
        get_odds.return_value.json.return_value = games
        output = io.StringIO()
        call_command(
            'fetch_nfl_odds', year=settings.NFL_SEASON_YEAR, week=5, stdout=output,
        )
        return output.getvalue()

    def assert_played_odds_unchanged(self):
        self.played.refresh_from_db()
        self.bills.refresh_from_db()
        self.dolphins.refresh_from_db()
        self.assertEqual(self.played.home_spread, Decimal('7.5'))
        self.assertEqual(self.played.home_moneyline, -300)
        self.assertTrue(self.played.home_is_favorite)
        self.assertEqual(self.played.away_moneyline, 240)
        self.assertEqual(self.bills.spread, Decimal('7.5'))
        self.assertEqual(self.bills.moneyline, -300)
        self.assertTrue(self.bills.is_favorite)
        self.assertEqual(self.bills.opponent, 'Dolphins')
        self.assertEqual(self.bills.game_time, self.thursday)
        self.assertEqual(self.bills.current_week, 5)
        self.assertEqual(self.dolphins.moneyline, 240)
        self.assertEqual(self.dolphins.current_week, 5)

    @patch.dict('os.environ', {'ODDS_API_KEY': 'test-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups')
    @patch('survivorPool.management.commands.fetch_nfl_odds.requests.get')
    def test_sunday_refresh_skips_played_game_and_updates_unstarted_game(
        self, get_odds, get_schedule,
    ):
        output = self.refresh(get_odds, get_schedule, [
            feed_game(
                'Buffalo Bills', 'Miami Dolphins', self.thursday,
                home_spread=30.5, home_moneyline=-9999,
            ),
            feed_game(
                'Kansas City Chiefs', 'Las Vegas Raiders', self.sunday,
                home_spread=9.5, home_moneyline=-400,
            ),
        ])

        self.assert_played_odds_unchanged()
        self.unstarted.refresh_from_db()
        self.chiefs.refresh_from_db()
        self.assertEqual(self.unstarted.home_spread, Decimal('9.5'))
        self.assertEqual(self.unstarted.home_moneyline, -400)
        self.assertEqual(self.chiefs.spread, Decimal('9.5'))
        self.assertEqual(self.chiefs.moneyline, -400)
        self.assertIn('Preserved pre-kickoff odds: Dolphins @ Bills', output)
        self.assertIn('Updated 2 teams (1 matchups), Skipped: 1', output)

    @patch.dict('os.environ', {'ODDS_API_KEY': 'test-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups')
    @patch('survivorPool.management.commands.fetch_nfl_odds.requests.get')
    def test_missing_played_game_in_feed_does_not_clear_thursday_team_odds(
        self, get_odds, get_schedule,
    ):
        self.refresh(get_odds, get_schedule, [
            feed_game(
                'Kansas City Chiefs', 'Las Vegas Raiders', self.sunday,
                home_spread=9.5, home_moneyline=-400,
            ),
        ])
        self.assert_played_odds_unchanged()

    @patch.dict('os.environ', {'ODDS_API_KEY': 'test-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups')
    @patch('survivorPool.management.commands.fetch_nfl_odds.requests.get')
    def test_stored_past_kickoff_protects_game_if_feed_claims_future_kickoff(
        self, get_odds, get_schedule,
    ):
        self.schedule[('Bills', 'Dolphins')] = self.sunday
        output = self.refresh(get_odds, get_schedule, [
            feed_game(
                'Buffalo Bills', 'Miami Dolphins', self.sunday,
                home_spread=30.5, home_moneyline=-9999,
            ),
        ])
        self.assert_played_odds_unchanged()
        self.assertIn('Preserved pre-kickoff odds', output)

    @patch.dict('os.environ', {'ODDS_API_KEY': 'test-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups')
    @patch('survivorPool.management.commands.fetch_nfl_odds.requests.get')
    def test_schedule_past_kickoff_protects_game_without_existing_record(
        self, get_odds, get_schedule,
    ):
        self.played.delete()
        self.refresh(get_odds, get_schedule, [
            feed_game(
                'Buffalo Bills', 'Miami Dolphins', self.thursday,
                home_spread=30.5, home_moneyline=-9999,
            ),
        ])
        self.bills.refresh_from_db()
        self.assertEqual(self.bills.spread, Decimal('7.5'))
        self.assertEqual(self.bills.moneyline, -300)
        self.assertFalse(
            Game.objects.filter(
                season_year=settings.NFL_SEASON_YEAR,
                week=5, home_team=self.bills, away_team=self.dolphins,
            ).exists()
        )

    @patch.dict('os.environ', {'ODDS_API_KEY': 'test-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups')
    @patch('survivorPool.management.commands.fetch_nfl_odds.requests.get')
    def test_staff_refresh_uses_the_same_protection(self, get_odds, get_schedule):
        staff = User.objects.create_user(username='staff', is_staff=True)
        self.client.force_login(staff)
        get_schedule.return_value = self.schedule
        get_odds.return_value.headers = {}
        get_odds.return_value.json.return_value = [
            feed_game(
                'Buffalo Bills', 'Miami Dolphins', self.thursday,
                home_spread=30.5, home_moneyline=-9999,
            ),
            feed_game(
                'Kansas City Chiefs', 'Las Vegas Raiders', self.sunday,
                home_spread=9.5, home_moneyline=-400,
            ),
        ]
        response = self.client.post(
            '/league-operations/', {'action': 'odds', 'week': '5'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Preserved pre-kickoff odds')
        self.assertContains(response, 'unstarted games only')
        self.assert_played_odds_unchanged()
        self.unstarted.refresh_from_db()
        self.assertEqual(self.unstarted.home_spread, Decimal('9.5'))
