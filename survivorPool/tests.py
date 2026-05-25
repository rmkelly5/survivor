from django.contrib.auth.models import AnonymousUser, User
from django.core.management import call_command
from django.test import RequestFactory, TestCase
from unittest.mock import patch

from .forms import PostForm
from .models import ChatMessage, Game, Pick, Team, WeekLockRun
from .utils import build_picks_grid
from .views import AddPickView


class AddPickViewTests(TestCase):
    def test_display_week_defaults_to_next_loaded_unpicked_week(self):
        user = User.objects.create_user(username='miscia')
        cardinals = Team.objects.create(team_name='Cardinals', current_week=1)
        Team.objects.create(team_name='Bills', current_week=7)
        Pick.objects.create(user_name=user, team=cardinals, week=1, is_win=True)

        request = RequestFactory().get('/add_pick/')
        request.user = user
        view = AddPickView()
        view.request = request

        self.assertEqual(view._get_display_week(), 7)

    def test_query_param_week_takes_precedence(self):
        Team.objects.create(team_name='Bills', current_week=7)

        request = RequestFactory().get('/add_pick/?week=3')
        request.user = AnonymousUser()
        view = AddPickView()
        view.request = request

        self.assertEqual(view._get_display_week(), 3)

    def test_display_week_uses_loaded_game_schedule(self):
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

        self.assertEqual(view._get_display_week(), 2)


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

        with patch('survivorPool.forms.is_week_locked', return_value=False):
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


class AddPickSecurityTests(TestCase):
    def test_post_uses_logged_in_user_not_hidden_user_field(self):
        user = User.objects.create_user(username='miscia', password='password')
        other_user = User.objects.create_user(username='other')
        team = Team.objects.create(team_name='Bills', current_week=7)

        self.client.login(username='miscia', password='password')

        with patch('survivorPool.forms.is_week_locked', return_value=False):
            response = self.client.post(
                '/add_pick/',
                {'team': team.id, 'week': 7, 'user_name': other_user.id},
            )

        self.assertRedirects(response, '/', fetch_redirect_response=False)
        pick = Pick.objects.get()
        self.assertEqual(pick.user_name, user)

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


class UtilsTests(TestCase):
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

    def test_leaderboard_excludes_admin_users(self):
        User.objects.create_superuser(username='admin', password='password')
        player = User.objects.create_user(username='player')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=player, team=team, week=1, is_win=True)

        from .utils import build_leaderboard_rows
        rows = build_leaderboard_rows()

        self.assertEqual([row['username'] for row in rows], ['player'])


class LockWeekCommandTests(TestCase):
    def test_lock_week_posts_chat_and_auto_loss(self):
        user = User.objects.create_user(username='late')
        stranger = User.objects.create_user(username='stranger')
        User.objects.create_superuser(username='admin', password='password')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=user, team=team, week=1, is_win=True)

        with patch('survivorPool.management.commands.lock_week_and_post_chat.is_week_locked', return_value=True):
            call_command('lock_week_and_post_chat', '--week=3', '--force')

        pick = Pick.objects.get(user_name=user, week=3)
        self.assertFalse(pick.is_win)
        self.assertTrue(pick.missed_deadline)
        self.assertFalse(Pick.objects.filter(user_name__username='admin', week=3).exists())
        self.assertFalse(Pick.objects.filter(user_name=stranger, week=3).exists())
        self.assertTrue(WeekLockRun.objects.filter(week=3).exists())
        msg = ChatMessage.objects.get(message_type=ChatMessage.MESSAGE_WEEKLY_LOCK)
        self.assertIn('Week 3', msg.body)
        self.assertIn('late', msg.body)
        self.assertIn('Shame corner', msg.body)

    def test_force_lock_is_idempotent_for_chat_and_missed_picks(self):
        user = User.objects.create_user(username='late')
        team = Team.objects.create(team_name='Bills')
        Pick.objects.create(user_name=user, team=team, week=1, is_win=True)

        with patch('survivorPool.management.commands.lock_week_and_post_chat.is_week_locked', return_value=True):
            call_command('lock_week_and_post_chat', '--week=3', '--force')
            call_command('lock_week_and_post_chat', '--week=3', '--force')

        self.assertEqual(Pick.objects.filter(user_name=user, week=3, missed_deadline=True).count(), 1)
        self.assertEqual(ChatMessage.objects.filter(message_type=ChatMessage.MESSAGE_WEEKLY_LOCK, week=3).count(), 1)


class ChatViewTests(TestCase):
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
