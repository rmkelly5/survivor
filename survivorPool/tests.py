from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from django.utils import timezone
import datetime
from unittest.mock import patch

from .forms import PostForm
from .management.commands.fetch_nfl_odds import choose_bookmaker
from .models import ChatMessage, Game, Pick, Team, WeekLockRun
from .utils import all_week_games_started, build_leaderboard_rows, build_picks_grid
from .views import AddPickView


class HomeViewTests(TestCase):
    def test_picks_are_displayed_newest_week_first_not_submission_order(self):
        user = User.objects.create_user(username='player')
        other_user = User.objects.create_user(username='other')
        team = Team.objects.create(team_name='Bills')
        for week in (3, 1, 2):
            Pick.objects.create(user_name=user, team=team, week=week)
        Pick.objects.create(user_name=other_user, team=team, week=4)
        self.client.force_login(user)

        response = self.client.get('/')

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [pick.week for pick in response.context['object_list']],
            [3, 2, 1],
        )


class AddPickViewTests(TestCase):
    def test_display_week_does_not_jump_to_future_loaded_week(self):
        user = User.objects.create_user(username='miscia')
        cardinals = Team.objects.create(team_name='Cardinals', current_week=1)
        Team.objects.create(team_name='Bills', current_week=7)
        Pick.objects.create(user_name=user, team=cardinals, week=1, is_win=True)

        request = RequestFactory().get('/add_pick/')
        request.user = user
        view = AddPickView()
        view.request = request

        with patch.object(view, '_get_current_nfl_week', return_value=4):
            self.assertEqual(view._get_display_week(), 4)

    def test_query_param_week_takes_precedence(self):
        Team.objects.create(team_name='Bills', current_week=7)

        request = RequestFactory().get('/add_pick/?week=3')
        request.user = AnonymousUser()
        view = AddPickView()
        view.request = request

        self.assertEqual(view._get_display_week(), 3)

    def test_add_pick_page_defaults_to_current_week(self):
        user = User.objects.create_user(username='miscia', password='password')
        self.client.force_login(user)
        with patch.object(AddPickView, '_get_current_nfl_week', return_value=4):
            response = self.client.get('/add_pick/')
        self.assertEqual(response.context['display_week'], 4)
        self.assertEqual(response.context['current_week'], 4)

    def test_display_week_does_not_fall_back_to_past_loaded_week(self):
        user = User.objects.create_user(username='miscia')
        cardinals = Team.objects.create(team_name='Cardinals')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Game.objects.create(season_year=2026, week=1, home_team=cardinals, away_team=bills)
        Game.objects.create(season_year=2026, week=2, home_team=dolphins, away_team=bills)
        Pick.objects.create(user_name=user, team=cardinals, week=1, is_win=True)

        request = RequestFactory().get('/add_pick/')
        request.user = user
        view = AddPickView()
        view.request = request

        with patch.object(view, '_get_current_nfl_week', return_value=4):
            self.assertEqual(view._get_display_week(), 4)

    def test_biggest_favorite_uses_lowest_moneyline(self):
        view = AddPickView()
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        favorites = view._get_biggest_favorites([
            {
                'home': bills,
                'home_logo': 'bills.png',
                'home_moneyline': -240,
                'away': dolphins,
                'away_logo': 'dolphins.png',
                'away_moneyline': 190,
            },
        ])

        self.assertEqual(
            [(favorite['team'], favorite['moneyline']) for favorite in favorites],
            [(bills, -240)],
        )

    def test_biggest_favorite_includes_all_tied_teams(self):
        view = AddPickView()
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        favorites = view._get_biggest_favorites([
            {
                'home': bills,
                'home_logo': '',
                'home_moneyline': -300,
                'away': dolphins,
                'away_logo': '',
                'away_moneyline': 240,
            },
            {
                'home': chiefs,
                'home_logo': '',
                'home_moneyline': -300,
                'away': raiders,
                'away_logo': '',
                'away_moneyline': 250,
            },
        ])

        self.assertEqual(
            [favorite['team'] for favorite in favorites],
            [bills, chiefs],
        )

    def test_biggest_favorite_is_empty_without_moneylines(self):
        view = AddPickView()
        bills = Team.objects.create(team_name='Bills')

        self.assertEqual(
            view._get_biggest_favorites([
                {
                    'home': bills,
                    'home_logo': '',
                    'home_moneyline': None,
                    'away': None,
                    'away_logo': '',
                    'away_moneyline': None,
                },
            ]),
            [],
        )

    def test_missing_pick_explains_when_no_eligible_team_remains(self):
        user = User.objects.create_user(username='miscia', password='password')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Pick.objects.create(user_name=user, team=chiefs, week=1)
        Pick.objects.create(user_name=user, team=raiders, week=2)
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() - datetime.timedelta(minutes=1),
        )
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() + datetime.timedelta(hours=3),
        )
        self.client.login(username='miscia', password='password')

        response = self.client.get('/add_pick/?week=3')

        self.assertFalse(response.context['has_available_team'])
        self.assertContains(response, 'No teams are available for this week.')


class PostFormTests(TestCase):
    def test_team_queryset_is_limited_to_selected_week(self):
        user = User.objects.create_user(username='miscia')
        Team.objects.create(team_name='Bills', current_week=7)
        Team.objects.create(team_name='Rams', current_week=8)

        form = PostForm(user=user, initial={'week': 7})

        self.assertQuerySetEqual(
            form.fields['team'].queryset.order_by('team_name'),
            ['Bills'],
            transform=lambda team: team.team_name,
        )

    def test_team_queryset_uses_game_schedule_when_loaded(self):
        user = User.objects.create_user(username='miscia')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        rams = Team.objects.create(team_name='Rams')
        Game.objects.create(season_year=2026, week=1, home_team=bills, away_team=dolphins)
        Game.objects.create(season_year=2026, week=2, home_team=rams, away_team=dolphins)

        form = PostForm(user=user, initial={'week': 1})

        self.assertQuerySetEqual(
            form.fields['team'].queryset.order_by('team_name'),
            ['Bills', 'Dolphins'],
            transform=lambda team: team.team_name,
        )

    def test_form_rejects_team_from_a_different_week(self):
        user = User.objects.create_user(username='miscia')
        Team.objects.create(team_name='Bills', current_week=7)
        rams = Team.objects.create(team_name='Rams', current_week=8)

        form = PostForm(
            data={'team': rams.id, 'week': 7, 'user_name': user.id},
            user=user,
        )

        self.assertFalse(form.is_valid())

        self.assertIn('Select a valid choice', str(form.errors))

    def test_no_pick_auto_loss_does_not_block_future_choices(self):
        user = User.objects.create_user(username='miscia')
        no_pick = Team.objects.create(team_name='No Pick')
        bills = Team.objects.create(team_name='Bills', current_week=2)
        Pick.objects.create(
            user_name=user,
            team=no_pick,
            week=1,
            is_win=False,
            missed_deadline=True,
        )

        form = PostForm(user=user, initial={'week': 2})

        self.assertIn(bills, form.fields['team'].queryset)

    def test_started_game_is_closed_while_later_game_remains_available(self):
        user = User.objects.create_user(username='miscia')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() - datetime.timedelta(minutes=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() + datetime.timedelta(hours=3),
        )

        started = PostForm(data={'team': bills.id, 'week': 1}, user=user)
        later = PostForm(data={'team': chiefs.id, 'week': 1}, user=user)

        self.assertFalse(started.is_valid())
        self.assertIn('game has already started', str(started.errors))
        self.assertTrue(later.is_valid(), later.errors)


class AddPickSecurityTests(TestCase):
    def test_post_uses_logged_in_user_not_hidden_user_field(self):
        user = User.objects.create_user(username='miscia', password='password')
        other_user = User.objects.create_user(username='other')
        team = Team.objects.create(team_name='Bills', current_week=7)

        self.client.login(username='miscia', password='password')

        response = self.client.post(
            '/add_pick/',
            {'team': team.id, 'week': 7, 'user_name': other_user.id},
        )

        self.assertRedirects(response, '/', fetch_redirect_response=False)
        pick = Pick.objects.get()
        self.assertEqual(pick.user_name, user)

    def test_make_pick_page_updates_existing_week_pick_before_kickoff(self):
        user = User.objects.create_user(username='miscia', password='password')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() + datetime.timedelta(hours=3),
        )
        pick = Pick.objects.create(user_name=user, team=bills, week=1)
        self.client.login(username='miscia', password='password')

        response = self.client.post(
            '/add_pick/',
            {'team': chiefs.id, 'week': 1, 'user_name': user.id},
        )

        self.assertRedirects(response, '/', fetch_redirect_response=False)
        self.assertEqual(Pick.objects.filter(user_name=user, week=1).count(), 1)
        pick.refresh_from_db()
        self.assertEqual(pick.team, chiefs)

    def test_make_pick_page_cannot_switch_after_selected_game_starts(self):
        user = User.objects.create_user(username='miscia', password='password')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() - datetime.timedelta(minutes=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() + datetime.timedelta(hours=3),
        )
        pick = Pick.objects.create(user_name=user, team=bills, week=1)
        self.client.login(username='miscia', password='password')

        response = self.client.post(
            '/add_pick/',
            {'team': chiefs.id, 'week': 1, 'user_name': user.id},
        )

        self.assertEqual(response.status_code, 200)
        pick.refresh_from_db()
        self.assertEqual(pick.team, bills)
        self.assertContains(response, "game has started")

    def test_pick_crud_is_owner_only(self):
        owner = User.objects.create_user(username='owner', password='password')
        other = User.objects.create_user(username='other', password='password')
        team = Team.objects.create(team_name='Bills')
        pick = Pick.objects.create(user_name=owner, team=team, week=1)

        self.client.login(username='other', password='password')

        for path in [
            f'/pick_details/{pick.pk}',
            f'/pick/edit/{pick.pk}',
            f'/pick/delete/{pick.pk}',
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 404)

    def test_pick_crud_requires_login(self):
        owner = User.objects.create_user(username='owner')
        team = Team.objects.create(team_name='Bills')
        pick = Pick.objects.create(user_name=owner, team=team, week=1)

        for path in [
            f'/pick_details/{pick.pk}',
            f'/pick/edit/{pick.pk}',
            f'/pick/delete/{pick.pk}',
        ]:
            response = self.client.get(path)
            self.assertEqual(response.status_code, 302)

    def test_pick_can_be_changed_until_selected_game_starts(self):
        user = User.objects.create_user(username='owner', password='password')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() + datetime.timedelta(hours=3),
        )
        pick = Pick.objects.create(user_name=user, team=bills, week=1)
        self.client.login(username='owner', password='password')

        response = self.client.post(f'/pick/edit/{pick.pk}', {'team': chiefs.id})

        self.assertRedirects(response, '/', fetch_redirect_response=False)
        pick.refresh_from_db()
        self.assertEqual(pick.team, chiefs)

    def test_pick_cannot_be_changed_after_selected_game_starts(self):
        user = User.objects.create_user(username='owner', password='password')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() - datetime.timedelta(minutes=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() + datetime.timedelta(hours=3),
        )
        pick = Pick.objects.create(user_name=user, team=bills, week=1)
        self.client.login(username='owner', password='password')

        response = self.client.post(f'/pick/edit/{pick.pk}', {'team': chiefs.id})

        self.assertEqual(response.status_code, 200)
        pick.refresh_from_db()
        self.assertEqual(pick.team, bills)
        self.assertContains(response, "game has started")

    def test_pick_cannot_be_changed_to_team_whose_game_has_started(self):
        user = User.objects.create_user(username='owner', password='password')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() - datetime.timedelta(minutes=1),
        )
        pick = Pick.objects.create(user_name=user, team=bills, week=1)
        self.client.login(username='owner', password='password')

        response = self.client.post(f'/pick/edit/{pick.pk}', {'team': chiefs.id})

        self.assertEqual(response.status_code, 200)
        pick.refresh_from_db()
        self.assertEqual(pick.team, bills)
        self.assertContains(response, "game has already started")


class BaseNavigationTests(TestCase):
    def test_superuser_sees_admin_console_link(self):
        User.objects.create_superuser(
            username='admin',
            password='password',
        )
        self.client.login(username='admin', password='password')

        response = self.client.get('/')

        self.assertContains(response, 'Admin Console')
        self.assertContains(response, 'href="/admin/"')
        self.assertContains(response, 'Admin Console')

    def test_regular_user_does_not_see_admin_console_link(self):
        User.objects.create_user(
            username='player',
            password='password',
        )
        self.client.login(username='player', password='password')

        response = self.client.get('/')

        self.assertNotContains(response, 'Admin Console')
        self.assertNotContains(response, 'nav-link-admin')
        self.assertNotContains(response, 'League Operations')

    def test_staff_user_can_open_league_operations(self):
        User.objects.create_user(
            username='operator',
            password='password',
            is_staff=True,
        )
        self.client.login(username='operator', password='password')

        response = self.client.get('/league-operations/?week=1')

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'League operations')
        self.assertContains(response, 'Week 1')

    def test_regular_user_cannot_open_league_operations(self):
        User.objects.create_user(username='player', password='password')
        self.client.login(username='player', password='password')

        response = self.client.get('/league-operations/')

        self.assertEqual(response.status_code, 302)

    @patch('survivorPool.views.call_command')
    def test_staff_operation_runs_selected_command_with_validated_week(self, command):
        User.objects.create_user(
            username='operator',
            password='password',
            is_staff=True,
        )
        self.client.login(username='operator', password='password')

        response = self.client.post(
            '/league-operations/',
            {'action': 'schedule', 'week': '2'},
        )

        self.assertEqual(response.status_code, 200)
        command.assert_called_once()
        args, kwargs = command.call_args
        self.assertEqual(args[0], 'fetch_nfl_schedule')
        self.assertEqual(kwargs['week'], 2)
        self.assertEqual(kwargs['year'], 2026)

    @patch('survivorPool.views.call_command')
    def test_post_results_runs_combined_finalization_command(self, command):
        User.objects.create_user(
            username='operator',
            password='password',
            is_staff=True,
        )
        self.client.login(username='operator', password='password')

        response = self.client.post(
            '/league-operations/',
            {'action': 'results', 'week': '1'},
        )

        self.assertEqual(response.status_code, 200)
        args, kwargs = command.call_args
        self.assertEqual(args[0], 'post_week_results')
        self.assertEqual(kwargs['week'], 1)

    def test_pot_is_removed_from_navigation_and_redirects_to_leaderboard(self):
        User.objects.create_user(
            username='player',
            password='password',
        )
        self.client.login(username='player', password='password')

        response = self.client.get('/')
        self.assertNotContains(response, 'href="/pot/"')

        response = self.client.get('/pot/')
        self.assertRedirects(
            response,
            '/league_leaderboard/',
            fetch_redirect_response=False,
        )


class UtilsTests(TestCase):
    def test_bookmaker_priority_falls_back_to_any_returned_book(self):
        other = {'key': 'betrivers', 'title': 'BetRivers'}
        draftkings = {'key': 'draftkings', 'title': 'DraftKings'}
        fanduel = {'key': 'fanduel', 'title': 'FanDuel'}
        betmgm = {'key': 'betmgm', 'title': 'BetMGM'}

        self.assertIs(choose_bookmaker([other, fanduel, draftkings]), draftkings)
        self.assertIs(choose_bookmaker([other, betmgm, fanduel]), fanduel)
        self.assertIs(choose_bookmaker([other]), other)

    def test_week_is_final_only_after_every_game_starts(self):
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        chiefs = Team.objects.create(team_name='Chiefs')
        raiders = Team.objects.create(team_name='Raiders')
        later = Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chiefs,
            away_team=raiders,
            game_time=timezone.now() - datetime.timedelta(hours=1),
        )

        self.assertFalse(all_week_games_started(1))
        later.game_time = timezone.now() - datetime.timedelta(minutes=1)
        later.save(update_fields=['game_time'])
        self.assertTrue(all_week_games_started(1))

    def test_build_picks_grid_without_pandas(self):
        user = User.objects.create_user(username='alice')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=user, team=team, week=1, is_win=True)

        grid = build_picks_grid(max_week=1)
        self.assertEqual(grid['players'], ['alice'])
        self.assertEqual(grid['pick_lookup'][(1, 'alice')]['team'], 'Bills')
        self.assertEqual(grid['pick_lookup'][(1, 'alice')]['status'], 'WIN')

    def test_build_picks_grid_hides_no_pick_team_for_missed_deadline(self):
        user = User.objects.create_user(username='alice')
        no_pick = Team.objects.create(team_name='No Pick')
        Pick.objects.create(
            user_name=user,
            team=no_pick,
            week=1,
            is_win=False,
            missed_deadline=True,
        )

        grid = build_picks_grid(max_week=1)

        self.assertEqual(grid['pick_lookup'][(1, 'alice')]['team'], '')
        self.assertEqual(grid['pick_lookup'][(1, 'alice')]['status'], 'LOSS')
        self.assertTrue(grid['pick_lookup'][(1, 'alice')]['missed_deadline'])

    def test_build_picks_grid_hides_pick_until_selected_team_kicks_off(self):
        user = User.objects.create_user(username='alice')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )
        Pick.objects.create(user_name=user, team=bills, week=3)

        grid = build_picks_grid(max_week=3)

        self.assertEqual(grid['pick_lookup'][(3, 'alice')]['team'], '')
        self.assertEqual(grid['pick_lookup'][(3, 'alice')]['status'], '')

    def test_build_picks_grid_reveals_pick_after_selected_team_kicks_off(self):
        user = User.objects.create_user(username='alice')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() - datetime.timedelta(minutes=1),
        )
        Pick.objects.create(user_name=user, team=bills, week=3)

        grid = build_picks_grid(max_week=3)

        self.assertEqual(grid['pick_lookup'][(3, 'alice')]['team'], 'Bills')
        self.assertEqual(grid['pick_lookup'][(3, 'alice')]['status'], 'TBD')

    def test_leaderboard_includes_staff_and_superusers(self):
        User.objects.create_superuser(username='admin', password='password')
        player = User.objects.create_user(username='player')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=player, team=team, week=1, is_win=True)

        rows = build_leaderboard_rows()

        self.assertEqual(
            [row['username'] for row in rows],
            ['player', 'admin'],
        )

    def test_biggest_favorite_loss_adds_twenty_five_to_pot(self):
        favorite_player = User.objects.create_user(username='favorite-player')
        regular_player = User.objects.create_user(username='regular-player')
        cofavorite_player = User.objects.create_user(username='cofavorite-player')
        chargers = Team.objects.create(team_name='Chargers')
        raiders = Team.objects.create(team_name='Raiders')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=chargers,
            away_team=raiders,
            home_moneyline=-300,
            away_moneyline=250,
        )
        Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            home_moneyline=-300,
            away_moneyline=240,
        )
        Pick.objects.create(
            user_name=favorite_player,
            team=chargers,
            week=1,
            is_win=False,
        )
        Pick.objects.create(
            user_name=cofavorite_player,
            team=bills,
            week=1,
            is_win=False,
        )
        Pick.objects.create(
            user_name=regular_player,
            team=raiders,
            week=1,
            is_win=False,
        )

        rows = {
            row['username']: row
            for row in build_leaderboard_rows()
        }

        self.assertEqual(rows['favorite-player']['favorite_loss_count'], 1)
        self.assertEqual(rows['favorite-player']['standard_loss_count'], 0)
        self.assertEqual(rows['favorite-player']['pot_contribution'], 75)
        self.assertEqual(rows['cofavorite-player']['favorite_loss_count'], 1)
        self.assertEqual(rows['cofavorite-player']['pot_contribution'], 75)
        self.assertEqual(rows['regular-player']['favorite_loss_count'], 0)
        self.assertEqual(rows['regular-player']['standard_loss_count'], 1)
        self.assertEqual(rows['regular-player']['pot_contribution'], 60)


class OddsCommandTests(TestCase):
    @patch.dict('os.environ', {'ODDS_API_KEY': 'test-key'})
    @patch('survivorPool.management.commands.fetch_nfl_odds.get_espn_week_matchups')
    @patch('survivorPool.management.commands.fetch_nfl_odds.requests.get')
    def test_empty_bookmaker_response_preserves_existing_odds(self, get_odds, get_schedule):
        kickoff = timezone.now() + datetime.timedelta(days=1)
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        game = Game.objects.create(
            season_year=2026,
            week=1,
            home_team=bills,
            away_team=dolphins,
            game_time=kickoff,
            home_spread=3.5,
            home_moneyline=-180,
            away_moneyline=155,
            home_is_favorite=True,
        )
        get_schedule.return_value = {('Bills', 'Dolphins'): kickoff}
        get_odds.return_value.headers = {}
        get_odds.return_value.json.return_value = [{
            'home_team': 'Buffalo Bills',
            'away_team': 'Miami Dolphins',
            'commence_time': kickoff.isoformat(),
            'bookmakers': [],
        }]

        call_command('fetch_nfl_odds', '--year=2026', '--week=1')

        game.refresh_from_db()
        self.assertEqual(game.home_moneyline, -180)
        self.assertEqual(game.away_moneyline, 155)
        self.assertEqual(game.home_spread, 3.5)


class LockWeekCommandTests(TestCase):
    def test_week_cannot_finalize_while_a_game_is_still_available(self):
        user = User.objects.create_user(username='late')
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Pick.objects.create(user_name=user, team=bills, week=1, is_win=True)
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )

        call_command('lock_week_and_post_chat', '--week=3')

        self.assertFalse(WeekLockRun.objects.filter(week=3).exists())
        self.assertFalse(Pick.objects.filter(user_name=user, week=3).exists())

    def test_lock_week_posts_chat_and_auto_loss(self):
        user = User.objects.create_user(username='late')
        stranger = User.objects.create_user(username='stranger')
        admin = User.objects.create_superuser(username='admin', password='password')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=user, team=team, week=1, is_win=True)
        Pick.objects.create(user_name=admin, team=team, week=1, is_win=True)

        call_command('lock_week_and_post_chat', '--week=3', '--force')

        pick = Pick.objects.get(user_name=user, week=3)
        self.assertFalse(pick.is_win)
        self.assertTrue(pick.missed_deadline)
        self.assertTrue(
            Pick.objects.filter(
                user_name=admin,
                week=3,
                missed_deadline=True,
            ).exists()
        )
        stranger_pick = Pick.objects.get(user_name=stranger, week=3)
        self.assertFalse(stranger_pick.is_win)
        self.assertTrue(stranger_pick.missed_deadline)
        self.assertTrue(WeekLockRun.objects.filter(week=3).exists())
        msg = ChatMessage.objects.get(message_type=ChatMessage.MESSAGE_WEEKLY_LOCK)
        self.assertIn('Week 3', msg.body)
        self.assertIn('late', msg.body)
        self.assertIn('Shame corner', msg.body)

    def test_force_lock_is_idempotent_for_chat_and_missed_picks(self):
        user = User.objects.create_user(username='late')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=user, team=team, week=1, is_win=True)

        call_command('lock_week_and_post_chat', '--week=3', '--force')
        call_command('lock_week_and_post_chat', '--week=3', '--force')

        self.assertEqual(Pick.objects.filter(user_name=user, week=3, missed_deadline=True).count(), 1)
        self.assertEqual(ChatMessage.objects.filter(message_type=ChatMessage.MESSAGE_WEEKLY_LOCK, week=3).count(), 1)


class WinnersCommandTests(TestCase):
    @patch('survivorPool.management.commands.fetch_nfl_winners.get_current_nfl_week', return_value=0)
    @patch('survivorPool.management.commands.fetch_nfl_winners.get_nfl_weekly_winners')
    def test_preseason_is_a_noop(self, get_winners, get_week):
        call_command('fetch_nfl_winners')
        get_winners.assert_not_called()

    @patch('survivorPool.management.commands.fetch_nfl_winners.get_nfl_weekly_winners')
    def test_finalized_week_scores_picks_without_changing_other_weeks(self, get_winners):
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        user = User.objects.create_user(username='scored')
        winner = Pick.objects.create(user_name=user, team=bills, week=3)
        loser = Pick.objects.create(user_name=User.objects.create_user(username='loser'), team=dolphins, week=3)
        later = Pick.objects.create(user_name=user, team=dolphins, week=4)
        Game.objects.create(season_year=2026, week=3, home_team=bills,
                            away_team=dolphins, game_time=timezone.now() - datetime.timedelta(hours=4))
        WeekLockRun.objects.create(season_year=2026, week=3)
        get_winners.return_value = [{'winner': 'Buffalo Bills', 'loser': 'Miami Dolphins'}]

        call_command('fetch_nfl_winners', week=3)

        get_winners.assert_called_once_with(2026, 3)
        winner.refresh_from_db()
        loser.refresh_from_db()
        later.refresh_from_db()
        self.assertIs(winner.is_win, True)
        self.assertIs(loser.is_win, False)
        self.assertIsNone(later.is_win)

    @patch('survivorPool.management.commands.fetch_nfl_winners.get_nfl_weekly_winners')
    def test_results_require_finalization(self, get_winners):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() - datetime.timedelta(hours=1),
        )

        with self.assertRaisesRegex(CommandError, 'must be finalized'):
            call_command('fetch_nfl_winners', '--week=3')
        get_winners.assert_not_called()

    @patch('survivorPool.management.commands.fetch_nfl_winners.get_nfl_weekly_winners', return_value=[])
    def test_results_require_all_games_to_have_started(self, get_winners):
        from django.core.management import call_command
        from django.core.management.base import CommandError

        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        Game.objects.create(
            season_year=2026,
            week=3,
            home_team=bills,
            away_team=dolphins,
            game_time=timezone.now() + datetime.timedelta(hours=1),
        )
        WeekLockRun.objects.create(season_year=2026, week=3)

        with self.assertRaisesRegex(CommandError, 'still has games available'):
            call_command('fetch_nfl_winners', '--week=3')
        get_winners.assert_not_called()


class PostWeekResultsCommandTests(TestCase):
    @patch('survivorPool.management.commands.fetch_nfl_winners.get_nfl_weekly_winners')
    def test_combined_command_finalizes_and_scores_with_guards_enabled(self, winners):
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        picker = User.objects.create_user(username='picker')
        absent = User.objects.create_user(username='absent')
        pick = Pick.objects.create(user_name=picker, team=bills, week=3)
        Game.objects.create(season_year=2026, week=3, home_team=bills,
                            away_team=dolphins, game_time=timezone.now() - datetime.timedelta(hours=4))
        winners.return_value = [{'winner': 'Buffalo Bills', 'loser': 'Miami Dolphins'}]

        # Exercise the actual nested commands, not just their invocation order.
        call_command('post_week_results', week=3)
        call_command('post_week_results', week=3)

        pick.refresh_from_db()
        self.assertIs(pick.is_win, True)
        missed = Pick.objects.get(user_name=absent, week=3)
        self.assertTrue(missed.missed_deadline)
        self.assertIs(missed.is_win, False)
        self.assertEqual(WeekLockRun.objects.filter(season_year=2026, week=3).count(), 1)
        self.assertEqual(ChatMessage.objects.filter(message_type=ChatMessage.MESSAGE_WEEKLY_LOCK, week=3).count(), 1)

    @patch('survivorPool.management.commands.post_week_results.call_command')
    @patch(
        'survivorPool.management.commands.post_week_results.all_week_games_started',
        return_value=True,
    )
    def test_post_results_finalizes_before_fetching_winners(self, games_started, command):
        call_command('post_week_results', '--week=1')

        self.assertEqual(command.call_count, 2)
        self.assertEqual(command.call_args_list[0].args[0], 'lock_week_and_post_chat')
        self.assertTrue(command.call_args_list[0].kwargs['force'])
        self.assertEqual(command.call_args_list[1].args[0], 'fetch_nfl_winners')

    @patch('survivorPool.management.commands.post_week_results.call_command')
    @patch(
        'survivorPool.management.commands.post_week_results.all_week_games_started',
        return_value=False,
    )
    def test_post_results_refuses_while_games_are_available(self, games_started, command):
        with self.assertRaisesMessage(
            Exception,
            'Week 1 still has games available',
        ):
            call_command('post_week_results', '--week=1')

        command.assert_not_called()


class ChatViewTests(TestCase):
    def test_chat_api_returns_timestamp_with_timezone(self):
        user = User.objects.create_user(username='chatter', password='password')
        ChatMessage.objects.create(author=user, body='hello')
        self.client.login(username='chatter', password='password')

        timestamp = self.client.get('/chat/poll/').json()['messages'][0]['created_at']

        self.assertIsNotNone(datetime.datetime.fromisoformat(timestamp).utcoffset())

    def test_chat_poll_without_after_is_capped(self):
        user = User.objects.create_user(username='chatter', password='password')
        for i in range(205):
            ChatMessage.objects.create(author=user, body=f'message {i}')

        self.client.login(username='chatter', password='password')
        response = self.client.get('/chat/poll/')

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload['messages']), 200)
        self.assertEqual(payload['messages'][0]['body'], 'message 5')


class LeagueUsabilityTests(TestCase):
    def test_board_preserves_pick_privacy_until_kickoff(self):
        bills = Team.objects.create(team_name='Bills')
        dolphins = Team.objects.create(team_name='Dolphins')
        other = User.objects.create_user(username='private_picker')
        game = Game.objects.create(season_year=2026, week=3, home_team=bills,
                                   away_team=dolphins, game_time=timezone.now() + datetime.timedelta(hours=1))
        Pick.objects.create(user_name=other, team=bills, week=3)

        response = self.client.get('/allPicks/?week=3')
        self.assertContains(response, 'Not revealed')
        self.assertNotContains(response, 'Not submitted')
        self.assertNotContains(response, 'Bills')
        self.assertEqual(response.context['current_week_cards'][0]['team'], '-')

        game.game_time = timezone.now() - datetime.timedelta(minutes=1)
        game.save()
        response = self.client.get('/allPicks/?week=3')
        self.assertContains(response, 'Bills')

    def setUp(self):
        self.user = User.objects.create_user(username='viewer')
        self.client.force_login(self.user)

    def test_unloaded_schedule_does_not_announce_a_loss(self):
        response = self.client.get('/add_pick/?week=4')
        self.assertContains(response, 'No matchups found for Week 4')
        self.assertNotContains(response, 'No teams are available')
        self.assertNotContains(response, 'will be recorded as a No Pick loss')

    def test_week_board_shows_selected_week_and_marks_missed_pick(self):
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=self.user, team=team, week=2, is_win=True)
        Pick.objects.create(user_name=self.user, team=team, week=3, is_win=False, missed_deadline=True)
        response = self.client.get('/allPicks/?week=2')
        self.assertEqual(response.context['selected_week'], 2)
        self.assertEqual(response.context['current_week_cards'][0]['team'], 'Bills')
        response = self.client.get('/allPicks/?week=3')
        self.assertContains(response, 'No pick recorded')
        for invalid in ['oops', '0', '19']:
            response = self.client.get('/allPicks/', {'week': invalid})
            self.assertEqual(response.context['selected_week'], response.context['current_nfl_week'])

    def test_dashboard_summarizes_only_own_picks_newest_first(self):
        team = Team.objects.create(team_name='Bills')
        other = User.objects.create_user(username='other')
        Pick.objects.create(user_name=other, team=team, week=1, is_win=True)
        Pick.objects.create(user_name=self.user, team=team, week=1, is_win=False)
        Pick.objects.create(user_name=self.user, team=team, week=2, is_win=None)
        response = self.client.get('/')
        self.assertEqual(response.context['wins'], 0)
        self.assertEqual(response.context['losses'], 1)
        self.assertEqual(response.context['pending'], 1)
        self.assertEqual([p.week for p in response.context['object_list']], [2, 1])

    def test_protected_pages_redirect_to_the_real_login_page(self):
        self.client.logout()
        response = self.client.get('/allPicks/')
        self.assertRedirects(response, '/members/login/?next=/allPicks/')
