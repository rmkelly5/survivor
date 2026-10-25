from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase

from .models import Game, Team
from .views import AddPickView


class DisplaySpreadTests(SimpleTestCase):
    def matchup(self, **odds):
        matchup = dict(home=object(), away=object(), **odds)
        AddPickView._add_display_spreads(matchup)
        return matchup

    def test_favorite_only_spread_displays_both_sides(self):
        for favorite, underdog in (('home', 'away'), ('away', 'home')):
            for spread in (Decimal('5.50'), Decimal('-5.50')):
                with self.subTest(favorite=favorite, spread=spread):
                    matchup = self.matchup(**{
                        f'{favorite}_is_favorite': True,
                        f'{favorite}_spread': spread,
                        f'{underdog}_spread': None,
                    })
                    self.assertEqual(matchup[f'{favorite}_display_spread'], '-5.5')
                    self.assertEqual(matchup[f'{underdog}_display_spread'], '+5.5')
                    self.assertEqual(matchup[f'{favorite}_spread'], spread)
                    self.assertIsNone(matchup[f'{underdog}_spread'])

    def test_explicit_underdog_spread_and_whole_numbers(self):
        matchup = self.matchup(home_spread=Decimal('10.00'), home_is_favorite=False)
        self.assertEqual(matchup['home_display_spread'], '+10')

    def test_missing_odds_are_not_inferred_from_moneyline(self):
        matchup = self.matchup(home_moneyline=-200, away_moneyline=150)
        self.assertIsNone(matchup['home_display_spread'])
        self.assertIsNone(matchup['away_display_spread'])

    def test_pickem_and_missing_opponent(self):
        matchup = self.matchup(home_spread=Decimal('0.00'))
        self.assertEqual(matchup['home_display_spread'], '0')
        matchup['away'] = None
        matchup['home_is_favorite'] = True
        matchup['home_spread'] = Decimal('7')
        AddPickView._add_display_spreads(matchup)
        self.assertIsNone(matchup['away_display_spread'])


class PickPageOddsTests(TestCase):
    def test_game_and_team_fallback_show_spread_and_moneyline_for_both_sides(self):
        home = Team.objects.create(
            team_name='Bills', current_week=1, is_home=True,
            opponent='Dolphins', spread=Decimal('5.5'),
            is_favorite=True, moneyline=-230,
        )
        away = Team.objects.create(
            team_name='Dolphins', current_week=1, is_home=False,
            opponent='Bills', is_favorite=False, moneyline=190,
        )
        game = Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=1,
            home_team=home, away_team=away,
            home_spread=Decimal('5.5'), home_is_favorite=True,
            home_moneyline=-230, away_moneyline=190,
        )
        self.client.force_login(User.objects.create_user(username='odds-viewer'))
        for source in ('game', 'team fallback'):
            with self.subTest(source=source):
                with patch.object(AddPickView, '_get_current_nfl_week', return_value=1):
                    response = self.client.get('/add_pick/?week=1')
                self.assertEqual(response.status_code, 200)
                self.assertContains(response, 'title="Point spread">+5.5</span>')
                self.assertContains(response, 'title="Point spread">-5.5</span>')
                self.assertContains(response, '>+190</span>')
                self.assertContains(response, '>-230</span>')
                if source == 'game':
                    game.delete()
