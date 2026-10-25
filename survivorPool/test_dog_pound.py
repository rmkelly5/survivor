from decimal import Decimal
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Game, Team
from .views import AddPickView


class DogPoundSelectionTests(SimpleTestCase):
    def test_home_and_away_underdogs_include_exactly_five_and_signed_lines(self):
        for side, opponent in (('home', 'away'), ('away', 'home')):
            for spread in (Decimal('5'), Decimal('-5.5'), Decimal('10')):
                with self.subTest(side=side, spread=spread):
                    dog = object()
                    matchup = {
                        side: dog, opponent: object(),
                        f'{opponent}_is_favorite': True,
                        f'{opponent}_spread': spread,
                        f'{side}_spread': None,
                        f'{side}_started': True,
                        f'{side}_picked': True,
                    }
                    result = AddPickView._get_dog_pound([matchup])
                    self.assertEqual(len(result), 1)
                    self.assertIs(result[0]['team'], dog)
                    self.assertTrue(result[0]['display_spread'].startswith('+'))
                    self.assertTrue(result[0]['started'])
                    self.assertTrue(result[0]['picked'])

    def test_small_missing_and_unmarked_spreads_are_excluded(self):
        for spread, favorite in ((Decimal('4.5'), True), (None, True),
                                 (Decimal('0'), True), (Decimal('7'), False)):
            with self.subTest(spread=spread, favorite=favorite):
                matchup = dict(
                    home=object(), away=object(), home_spread=spread,
                    home_is_favorite=favorite, away_moneyline=500,
                )
                self.assertEqual(AddPickView._get_dog_pound([matchup]), [])
        self.assertEqual(AddPickView._get_dog_pound([]), [])
        self.assertEqual(AddPickView._get_dog_pound([dict(
            home=object(), away=None, home_is_favorite=True, home_spread=7,
        )]), [])


class DogPoundPageTests(TestCase):
    def setUp(self):
        self.home = Team.objects.create(
            team_name='Bills', current_week=1, is_home=True, opponent='Dolphins',
            is_favorite=True, spread=Decimal('5.5'), moneyline=-230,
        )
        self.away = Team.objects.create(
            team_name='Dolphins', current_week=1, is_home=False, opponent='Bills',
            moneyline=190,
        )
        self.game = Game.objects.create(
            season_year=settings.NFL_SEASON_YEAR, week=1,
            home_team=self.home, away_team=self.away,
            home_is_favorite=True, home_spread=Decimal('5.5'),
            home_moneyline=-230, away_moneyline=190,
        )
        self.client.force_login(User.objects.create_user(username='dog-pound-player'))

    def get_page(self, week=1):
        with patch.object(AddPickView, '_get_current_nfl_week', return_value=1):
            return self.client.get(reverse('add_pick'), {'week': week})

    def test_section_uses_display_week_and_lists_only_qualifying_teams(self):
        response = self.get_page()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [dog['team'] for dog in response.context['dog_pound']], [self.away],
        )
        self.assertContains(response, 'Dog Pound')
        self.assertContains(response, '<details class="dog-pound">')
        self.assertNotContains(response, '<details class="dog-pound" open')
        self.assertContains(response, '<summary class="dog-pound-summary">')
        self.assertContains(response, '+5.5')
        self.assertContains(response, '+190')
        content = response.content.decode()
        self.assertLess(content.index('biggest-favorite-banner'), content.index('Dog Pound'))
        self.assertEqual(self.get_page(week=2).context['dog_pound'], [])

    def test_team_fallback_matches_saved_game_selection(self):
        self.game.delete()
        response = self.get_page()
        self.assertEqual(
            [dog['team'] for dog in response.context['dog_pound']], [self.away],
        )

    def test_no_qualifying_teams_still_renders_section(self):
        self.game.home_spread = Decimal('4.5')
        self.game.save(update_fields=['home_spread'])
        response = self.get_page()
        self.assertEqual(response.context['dog_pound'], [])
        self.assertContains(response, 'Dog Pound')
        self.assertContains(response, 'No teams qualify as 5+ point underdogs this week.')
