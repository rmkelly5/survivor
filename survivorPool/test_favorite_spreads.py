from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from .models import Game, Pick, Team
from .utils import build_leaderboard_rows, select_biggest_spread_favorites
from .views import AddPickView


class FavoriteSpreadSelectionTests(SimpleTestCase):
    def test_largest_spread_wins_even_when_moneyline_disagrees(self):
        candidates = [
            dict(team_id=1, spread=Decimal('7.5'), is_favorite=True, moneyline=-500),
            dict(team_id=2, spread=Decimal('10.5'), is_favorite=True, moneyline=-250),
        ]
        self.assertEqual(select_biggest_spread_favorites(candidates), [candidates[1]])

    def test_all_tied_favorites_include_signed_and_unsigned_spreads(self):
        candidates = [
            dict(team_id=1, spread=Decimal('10.5'), is_favorite=True),
            dict(team_id=2, spread=Decimal('-10.5'), is_favorite=True),
            dict(team_id=3, spread=Decimal('7.5'), is_favorite=True),
        ]
        self.assertEqual(select_biggest_spread_favorites(candidates), candidates[:2])

    def test_underdogs_missing_spreads_and_pickem_are_excluded(self):
        candidates = [
            dict(team_id=1, spread=14, is_favorite=False),
            dict(team_id=2, spread=None, is_favorite=True, moneyline=-1000),
            dict(team_id=3, spread=0, is_favorite=True),
        ]
        self.assertEqual(select_biggest_spread_favorites(candidates), [])
        self.assertEqual(select_biggest_spread_favorites([]), [])


class FavoriteSpreadIntegrationTests(TestCase):
    def setUp(self):
        self.bills = Team.objects.create(team_name='Bills')
        self.dolphins = Team.objects.create(team_name='Dolphins')
        self.chiefs = Team.objects.create(team_name='Chiefs')
        self.raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=1,
            home_team=self.bills, away_team=self.dolphins,
            home_spread=7.5, home_is_favorite=True, home_moneyline=-500,
        )
        Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=1,
            home_team=self.chiefs, away_team=self.raiders,
            away_spread=10.5, away_is_favorite=True, away_moneyline=None,
        )
        self.user = User.objects.create_user(username='spread-player')

    def test_pick_page_shows_away_favorite_spread_without_moneyline(self):
        self.client.force_login(self.user)
        with patch.object(AddPickView, '_get_current_nfl_week', return_value=1):
            response = self.client.get('/add_pick/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [row['team'] for row in response.context['biggest_favorites']],
            [self.raiders],
        )
        self.assertContains(response, 'Largest point spread')
        self.assertContains(response, '−10.5 points')

    def test_loss_fees_follow_spread_not_moneyline(self):
        other = User.objects.create_user(username='moneyline-player')
        Pick.objects.create(user_name=self.user, team=self.raiders, week=1, is_win=False)
        Pick.objects.create(user_name=other, team=self.bills, week=1, is_win=False)
        rows = {row['username']: row for row in build_leaderboard_rows()}
        self.assertEqual(rows[self.user.username]['pot_contribution'], Decimal('75'))
        self.assertEqual(rows[other.username]['pot_contribution'], Decimal('60'))

    def test_favorite_selection_is_specific_to_week_and_season(self):
        Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=2,
            home_team=self.bills, away_team=self.dolphins,
            home_spread=20, home_is_favorite=True,
        )
        Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR - 1, week=1,
            home_team=self.bills, away_team=self.dolphins,
            home_spread=30, home_is_favorite=True,
        )
        Pick.objects.create(user_name=self.user, team=self.raiders, week=1, is_win=False)
        rows = {row['username']: row for row in build_leaderboard_rows()}
        self.assertEqual(rows[self.user.username]['favorite_loss_count'], 1)

    def test_manual_overrides_and_missed_picks_remain_authoritative(self):
        Pick.objects.create(
            user_name=self.user, team=self.raiders, week=1, is_win=False,
            imported_result=True, favorite_loss_override=False,
        )
        other = User.objects.create_user(username='override-player')
        Pick.objects.create(
            user_name=other, team=self.bills, week=1, is_win=False,
            imported_result=True, favorite_loss_override=True,
        )
        missed = User.objects.create_user(username='missed-player')
        Pick.objects.create(
            user_name=missed, team=self.raiders, week=1, is_win=False,
            missed_deadline=True,
        )
        rows = {row['username']: row for row in build_leaderboard_rows()}
        self.assertEqual(rows[self.user.username]['pot_contribution'], Decimal('60'))
        self.assertEqual(rows[other.username]['pot_contribution'], Decimal('75'))
        self.assertEqual(rows[missed.username]['pot_contribution'], Decimal('60'))
