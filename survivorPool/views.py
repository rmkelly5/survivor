import datetime
import io

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.contrib.auth.models import User
from django.core.management import call_command
from django.db.models import Q
from django.shortcuts import redirect, render
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView
from django_tables2 import SingleTableView

from .forms import PostForm
from .models import Game, Pick, Team, WeekLockRun
from .tables import PickTable
from .utils import (
    build_leaderboard_rows,
    build_picks_grid,
    get_current_nfl_week,
    is_pick_locked,
    is_week_locked,
)

NFL_TEAM_LOGOS = {
    'Cardinals': 'ari',
    'Falcons': 'atl',
    'Ravens': 'bal',
    'Bills': 'buf',
    'Panthers': 'car',
    'Bears': 'chi',
    'Bengals': 'cin',
    'Browns': 'cle',
    'Cowboys': 'dal',
    'Broncos': 'den',
    'Lions': 'det',
    'Packers': 'gb',
    'Texans': 'hou',
    'Colts': 'ind',
    'Jaguars': 'jax',
    'Chiefs': 'kc',
    'Raiders': 'lv',
    'Chargers': 'lac',
    'Rams': 'lar',
    'Dolphins': 'mia',
    'Vikings': 'min',
    'Patriots': 'ne',
    'Saints': 'no',
    'Giants': 'nyg',
    'Jets': 'nyj',
    'Eagles': 'phi',
    'Steelers': 'pit',
    '49ers': 'sf',
    'Seahawks': 'sea',
    'Buccaneers': 'tb',
    'Titans': 'ten',
    'Commanders': 'wsh',
}


class HomeView(ListView):
    model = Pick
    template_name = 'home.html'
    ordering = ['week']

    def get_queryset(self):
        if not self.request.user.is_authenticated:
            return Pick.objects.none()
        return Pick.objects.filter(
            user_name=self.request.user,
        ).select_related('team', 'user_name')


class AddPickView(LoginRequiredMixin, CreateView):
    model = Pick
    form_class = PostForm
    template_name = 'add_pick.html'

    def _get_current_nfl_week(self):
        season_start_date = settings.NFL_SEASON_START_DATE
        today = datetime.date.today()
        if today < season_start_date:
            return 1
        delta = today - season_start_date
        return min(delta.days // 7 + 1, 18)

    def _get_loaded_weeks(self):
        game_weeks = set(
            Game.objects.filter(season_year=settings.NFL_SEASON_YEAR)
            .values_list('week', flat=True)
        )
        team_weeks = set(
            Team.objects.filter(current_week__isnull=False)
            .values_list('current_week', flat=True)
        )
        return sorted(game_weeks | team_weeks)

    def _get_default_week(self):
        current_week = self._get_current_nfl_week()
        loaded_weeks = self._get_loaded_weeks()
        if not loaded_weeks:
            return current_week

        picked_weeks = set(
            Pick.objects.filter(user_name=self.request.user)
            .values_list('week', flat=True)
        )
        for week in loaded_weeks:
            if week not in picked_weeks:
                return week

        if current_week in loaded_weeks:
            return current_week

        return loaded_weeks[-1]

    def _get_display_week(self):
        week_param = self.request.GET.get('week')
        if week_param and week_param.isdigit():
            week = int(week_param)
            if 1 <= week <= 18:
                return week

        return self._get_default_week()

    def get_initial(self):
        initial = super().get_initial()
        initial['week'] = self._get_display_week()
        return initial

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        kwargs['user'] = self.request.user
        if self.request.method == 'POST':
            week = self.request.POST.get('week')
            if week and week.isdigit():
                current_pick = Pick.objects.filter(
                    user_name=self.request.user,
                    week=int(week),
                ).first()
                if current_pick:
                    kwargs['instance'] = current_pick
                    kwargs['current_pick'] = current_pick
        return kwargs

    def form_valid(self, form):
        form.instance.user_name = self.request.user
        self.object = form.save()
        return redirect(self.get_success_url())

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        display_week = self._get_display_week()
        used_team_ids = set(
            Pick.objects.filter(user_name=self.request.user).values_list('team_id', flat=True)
        )

        games = list(
            Game.objects.filter(
                season_year=settings.NFL_SEASON_YEAR,
                week=display_week,
            )
            .select_related('home_team', 'away_team')
            .order_by('game_time')
        )

        def logo_url(team):
            abbrev = NFL_TEAM_LOGOS.get(team.team_name)
            return f"https://a.espncdn.com/i/teamlogos/nfl/500/{abbrev}.png" if abbrev else ""

        matchups = []
        if games:
            for game in games:
                matchups.append(self._matchup_from_game(game, used_team_ids, logo_url))
        else:
            matchups = self._matchups_from_teams(display_week, used_team_ids, logo_url)

        biggest_favorites = self._get_biggest_favorites(matchups)

        selected_team_id = None
        if self.request.method == 'POST':
            try:
                selected_team_id = int(self.request.POST.get('team', ''))
            except (ValueError, TypeError):
                pass

        context['matchups'] = matchups
        context['biggest_favorites'] = biggest_favorites
        context['used_team_ids'] = used_team_ids
        context['display_week'] = display_week
        context['selected_team_id'] = selected_team_id
        context['week_locked'] = is_week_locked(display_week)
        return context

    def _get_biggest_favorites(self, matchups):
        teams_with_odds = []
        for matchup in matchups:
            for side in ('away', 'home'):
                team = matchup.get(side)
                moneyline = matchup.get(f'{side}_moneyline')
                if team is not None and moneyline is not None:
                    teams_with_odds.append({
                        'team': team,
                        'logo': matchup.get(f'{side}_logo', ''),
                        'moneyline': moneyline,
                    })

        if not teams_with_odds:
            return []

        best_moneyline = min(team['moneyline'] for team in teams_with_odds)
        return [
            team for team in teams_with_odds
            if team['moneyline'] == best_moneyline
        ]

    def _matchup_from_game(self, game, used_team_ids, logo_url):
        return {
            'home': game.home_team,
            'home_logo': logo_url(game.home_team),
            'home_picked': game.home_team_id in used_team_ids,
            'home_is_favorite': game.home_is_favorite,
            'home_spread': game.home_spread,
            'home_moneyline': game.home_moneyline,
            'away': game.away_team,
            'away_logo': logo_url(game.away_team),
            'away_picked': game.away_team_id in used_team_ids,
            'away_is_favorite': game.away_is_favorite,
            'away_spread': game.away_spread,
            'away_moneyline': game.away_moneyline,
            'game_time': game.game_time,
        }

    def _matchups_from_teams(self, display_week, used_team_ids, logo_url):
        week_teams = list(Team.objects.filter(current_week=display_week))
        matchups = []
        paired_ids = set()
        for team in week_teams:
            if team.id in paired_ids or not team.is_home:
                continue
            away = next(
                (t for t in week_teams if t.team_name == team.opponent and not t.is_home),
                None,
            )
            matchups.append({
                'home': team,
                'home_logo': logo_url(team),
                'home_picked': team.id in used_team_ids,
                'home_is_favorite': team.is_favorite,
                'home_spread': team.spread,
                'home_moneyline': team.moneyline,
                'away': away,
                'away_logo': logo_url(away) if away else '',
                'away_picked': away.id in used_team_ids if away else False,
                'away_is_favorite': away.is_favorite if away else False,
                'away_spread': away.spread if away else None,
                'away_moneyline': away.moneyline if away else None,
                'game_time': team.game_time,
            })
            paired_ids.add(team.id)
            if away:
                paired_ids.add(away.id)

        for team in week_teams:
            if team.id not in paired_ids:
                matchups.append({
                    'home': team,
                    'home_logo': logo_url(team),
                    'home_picked': team.id in used_team_ids,
                    'home_is_favorite': team.is_favorite,
                    'home_spread': team.spread,
                    'home_moneyline': team.moneyline,
                    'away': None,
                    'away_logo': '',
                    'away_picked': False,
                    'away_is_favorite': False,
                    'away_spread': None,
                    'away_moneyline': None,
                    'game_time': team.game_time,
                })
        return matchups


class OwnerPickQuerysetMixin(LoginRequiredMixin):
    model = Pick

    def get_queryset(self):
        return Pick.objects.filter(
            user_name=self.request.user,
        ).select_related('team', 'user_name')


class PickDetailView(OwnerPickQuerysetMixin, DetailView):
    model = Pick
    template_name = 'pick_details.html'


class UpdatePickView(OwnerPickQuerysetMixin, UpdateView):
    model = Pick
    template_name = 'update_pick.html'

    def get_form_class(self):
        from .forms import UpdatePickForm
        return UpdatePickForm

    def get_form_kwargs(self):
        kwargs = super().get_form_kwargs()
        pick = self.get_object()
        kwargs['user'] = pick.user_name
        kwargs['current_pick'] = pick
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pick = self.get_object()
        context['is_locked'] = is_pick_locked(pick)
        return context

    def form_valid(self, form):
        pick = self.get_object()
        if is_pick_locked(pick):
            form.add_error(
                None,
                f"{pick.team.team_name}'s game has started, so this pick can no longer be changed.",
            )
            return self.form_invalid(form)
        return super().form_valid(form)


class DeletePickView(OwnerPickQuerysetMixin, DeleteView):
    model = Pick
    template_name = 'delete_pick.html'
    fields = ['week']
    success_url = reverse_lazy('home')


class PickView(SingleTableView):
    model = Pick
    table_class = PickTable
    template_name = 'leaderboard.html'


@login_required
def league_leaderboard_view(request):
    rows = build_leaderboard_rows()
    total_pot = sum(row['pot_contribution'] for row in rows)
    return render(request, 'league_leaderboard.html', {
        'leaderboard_rows': rows,
        'total_pot': total_pot,
        'season_year': settings.NFL_SEASON_YEAR,
    })


@login_required
def all_picks_view(request):
    season_start_date = settings.NFL_SEASON_START_DATE
    if datetime.date.today() < season_start_date:
        current_nfl_week = 1
    else:
        current_nfl_week = get_current_nfl_week(season_start_date)

    grid = build_picks_grid()
    leaderboard_rows = build_leaderboard_rows()
    leaderboard_lookup = {row['username']: row for row in leaderboard_rows}
    grid_summary = []
    for player in grid['players']:
        row = leaderboard_lookup.get(player, {})
        losses = row.get('loss_count', 0)
        pot = row.get('pot_contribution', 50)
        grid_summary.append({
            'player': player,
            'losses': losses,
            'owed': max(pot - 50, 0),
            'pot': pot,
        })

    current_week_cards = []
    if grid['players'] and current_nfl_week:
        for player in grid['players']:
            cell = grid['pick_lookup'].get((current_nfl_week, player), {})
            current_week_cards.append({
                'player': player,
                'team': cell.get('team') or '-',
                'status': cell.get('status') or '',
                'missed_deadline': cell.get('missed_deadline', False),
            })

    return render(request, 'allPicks.html', {
        'players': grid['players'],
        'rows': grid['rows'],
        'grid_summary': grid_summary,
        'current_nfl_week': current_nfl_week,
        'current_week_cards': current_week_cards,
        'season_year': settings.NFL_SEASON_YEAR,
    })


def rules_view(request):
    return render(request, 'rules.html')


@staff_member_required
def league_operations_view(request):
    try:
        selected_week = int(request.POST.get('week') or request.GET.get('week') or get_current_nfl_week())
    except (TypeError, ValueError):
        selected_week = get_current_nfl_week()
    selected_week = max(1, min(selected_week, 18))

    command_output = ''
    command_title = ''
    command_status = ''
    if request.method == 'POST':
        action = request.POST.get('action')
        commands = {
            'schedule': ('fetch_nfl_schedule', 'Schedule sync', {'year': settings.NFL_SEASON_YEAR}),
            'odds': ('fetch_nfl_odds', 'Odds refresh', {'year': settings.NFL_SEASON_YEAR}),
            'deadline': ('lock_week_and_post_chat', 'Sunday deadline', {}),
            'results': ('fetch_nfl_winners', 'Week results', {}),
        }
        command_config = commands.get(action)
        if command_config:
            command_name, command_title, command_options = command_config
            output = io.StringIO()
            try:
                call_command(
                    command_name,
                    week=selected_week,
                    stdout=output,
                    stderr=output,
                    **command_options,
                )
                command_status = 'success'
            except Exception as exc:
                command_status = 'error'
                output.write(f'\nOperation failed: {exc}')
            command_output = output.getvalue().strip() or 'Command completed without additional output.'
        else:
            command_title = 'Unknown operation'
            command_status = 'error'
            command_output = 'The requested operation is not available.'

    games = Game.objects.filter(
        season_year=settings.NFL_SEASON_YEAR,
        week=selected_week,
    )
    schedule_count = games.count()
    team_ids = set(games.values_list('home_team_id', flat=True))
    team_ids.update(games.values_list('away_team_id', flat=True))
    odds_count = games.filter(
        Q(home_moneyline__isnull=False) | Q(away_moneyline__isnull=False)
    ).count()
    lock_run = WeekLockRun.objects.filter(
        season_year=settings.NFL_SEASON_YEAR,
        week=selected_week,
    ).first()
    pick_counts = {
        'total': Pick.objects.filter(week=selected_week).count(),
        'pending': Pick.objects.filter(week=selected_week, is_win__isnull=True).count(),
        'wins': Pick.objects.filter(week=selected_week, is_win=True).count(),
        'losses': Pick.objects.filter(week=selected_week, is_win=False).count(),
    }

    if lock_run:
        operational_status = 'Deadline processed'
        status_detail = f'Processed {lock_run.ran_at:%b %d at %I:%M %p}.'
    elif schedule_count and odds_count == schedule_count:
        operational_status = 'Ready'
        status_detail = 'Schedule and odds are loaded.'
    elif schedule_count:
        operational_status = 'Needs odds'
        status_detail = 'Schedule loaded; betting lines are incomplete.'
    else:
        operational_status = 'Needs schedule'
        status_detail = 'No games are loaded for this week.'

    return render(request, 'league_operations.html', {
        'current_season': settings.NFL_SEASON_YEAR,
        'selected_week': selected_week,
        'week_options': range(1, 19),
        'schedule_count': schedule_count,
        'team_count': len(team_ids),
        'odds_count': odds_count,
        'operational_status': operational_status,
        'status_detail': status_detail,
        'pick_counts': pick_counts,
        'command_output': command_output,
        'command_title': command_title,
        'command_status': command_status,
    })


@login_required
def pot_view(request):
    return redirect('league_leaderboard')
