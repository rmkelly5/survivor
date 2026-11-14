from datetime import timedelta
from unittest.mock import patch

from django.conf import settings
from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Game, Pick, Team


class PickDistributionTests(TestCase):
    def setUp(self):
        self.viewer = User.objects.create_user(username='distribution-viewer')
        self.client.force_login(self.viewer)
        self.bills = Team.objects.create(team_name='Bills')
        self.chiefs = Team.objects.create(team_name='Chiefs')
        self.dolphins = Team.objects.create(team_name='Dolphins')
        self.eagles = Team.objects.create(team_name='Eagles')
        opponent = Team.objects.create(team_name='Raiders')
        for team, kickoff in (
            (self.bills, timezone.now() - timedelta(hours=1)),
            (self.chiefs, timezone.now() - timedelta(hours=1)),
            (self.dolphins, timezone.now() + timedelta(hours=1)),
        ):
            Game.objects.create(
                season_year=settings.NFL_SEASON_YEAR, week=3,
                home_team=team, away_team=opponent, game_time=kickoff,
            )
        self.add_pick('player-one', self.bills)
        self.add_pick('player-two', self.bills)
        self.add_pick('player-three', self.chiefs)
        self.hidden = self.add_pick('player-four', self.dolphins)
        self.add_pick('player-five', self.eagles, missed_deadline=True, is_win=False)
        # This player exists on the board but hasn't made a week-three pick.
        self.add_pick('player-six', self.eagles, week=4, is_win=True)

    def add_pick(self, username, team, week=3, **kwargs):
        return Pick.objects.create(
            user_name=User.objects.create_user(username=username),
            team=team, week=week, **kwargs,
        )

    def page(self, week=3):
        with patch('survivorPool.views.get_current_nfl_week', return_value=3):
            return self.client.get(reverse('allPicks'), {'week': week})

    def test_counts_use_selected_week_and_preserve_full_grid_without_cards(self):
        response = self.page()
        self.assertEqual(response.status_code, 200)
        distribution = response.context['pick_distribution']
        self.assertEqual(distribution['teams'], [
            {'team': 'Bills', 'count': 2, 'bar_percent': 100},
            {'team': 'Chiefs', 'count': 1, 'bar_percent': 50},
        ])
        self.assertEqual(distribution['revealed_count'], 3)
        self.assertEqual(distribution['unrevealed_count'], 2)
        self.assertEqual(distribution['missed_count'], 1)
        self.assertEqual(distribution['total_count'], 6)
        self.assertEqual(
            distribution['revealed_count'] + distribution['unrevealed_count']
            + distribution['missed_count'], distribution['total_count'],
        )
        self.assertContains(response, 'Pick distribution')
        self.assertContains(response, 'Full Pick Grid')
        self.assertContains(response, 'class="picks-table"')
        self.assertNotContains(response, 'week-summary-panel')
        self.assertNotContains(response, 'week-summary-card')
        self.assertContains(response, 'style="width: 50%;"')
        self.assertContains(response, 'Selections reveal at kickoff.')
        self.assertNotContains(response, 'Dolphins')
        self.assertEqual(self.page(4).context['pick_distribution']['teams'], [
            {'team': 'Eagles', 'count': 1, 'bar_percent': 100},
        ])

    def test_hidden_pick_is_revealed_only_at_its_own_kickoff(self):
        initial = self.page().context['pick_distribution']
        self.assertNotIn('Dolphins', [row['team'] for row in initial['teams']])
        Game.objects.filter(home_team=self.dolphins).update(
            game_time=timezone.now() - timedelta(seconds=1),
        )
        revealed = self.page().context['pick_distribution']
        self.assertEqual(revealed['revealed_count'], 4)
        self.assertEqual(revealed['unrevealed_count'], 1)
        self.assertEqual([row['team'] for row in revealed['teams']],
                         ['Bills', 'Chiefs', 'Dolphins'])

    def test_no_revealed_picks_renders_empty_state_without_team_leaks(self):
        Game.objects.all().update(game_time=timezone.now() + timedelta(days=1))
        response = self.page()
        self.assertEqual(response.context['pick_distribution']['teams'], [])
        self.assertContains(response, 'No team picks have been revealed for this week yet.')
        self.assertNotContains(response, 'Dolphins')
        self.assertNotContains(response, 'Bills')
        self.assertNotContains(response, 'Chiefs')

    def test_no_picks_has_zero_totals_and_no_division_by_zero(self):
        Pick.objects.all().delete()
        response = self.page()
        self.assertEqual(response.context['pick_distribution'], {
            'teams': [], 'revealed_count': 0, 'unrevealed_count': 0,
            'missed_count': 0, 'total_count': 0,
        })

    def test_anonymous_page_does_not_render_distribution(self):
        self.client.logout()
        response = self.page()
        self.assertEqual(response.status_code, 302)
        self.assertIn('/members/login/', response['Location'])
        self.assertNotContains(response, 'id="pick-distribution-title"', status_code=302)
        self.assertNotContains(response, 'Dolphins', status_code=302)
