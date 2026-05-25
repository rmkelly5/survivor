from typing import Any, Dict
from django.conf import settings
from django.shortcuts import render
from django.http import HttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django_tables2 import SingleTableView
from .models import Game, Pick, User, Team
from django.urls import reverse_lazy
from .forms import PostForm
from .tables import PickTable
import pandas as pd
import datetime
from django.contrib.auth.models import User
from django.contrib.auth.mixins import LoginRequiredMixin

LEADERBOARD_COLUMNS = ['User Name', 'Team', "IsWin", "Week"]

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

# Create your views here.
#def index(request):
#return HttpResponse("Hello, world. You're at the Survivor Pool index.")


class HomeView(ListView):
    model = Pick
    template_name = 'home.html'
    ordering = ['week']


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

        if self.request.user.is_authenticated:
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
        kwargs = super(AddPickView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

    def form_valid(self, form):
        form.instance.user_name = self.request.user
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        display_week = self._get_display_week()

        used_team_ids = set()
        if self.request.user.is_authenticated:
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
                matchups.append({
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
                })
        else:
            week_teams = list(Team.objects.filter(current_week=display_week))
            paired_ids = set()
            for team in week_teams:
                if team.id in paired_ids:
                    continue
                if not team.is_home:
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
                    'away_logo': logo_url(away) if away else "",
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
                        'away_logo': "",
                        'away_picked': False,
                        'away_is_favorite': False,
                        'away_spread': None,
                        'away_moneyline': None,
                        'game_time': team.game_time,
                    })

        selected_team_id = None
        if self.request.method == 'POST':
            try:
                selected_team_id = int(self.request.POST.get('team', ''))
            except (ValueError, TypeError):
                pass

        context['matchups'] = matchups
        context['used_team_ids'] = used_team_ids
        context['display_week'] = display_week
        context['selected_team_id'] = selected_team_id
        return context


class PickDetailView(DetailView):
    model = Pick
    template_name = 'pick_details.html'


class UpdatePickView(UpdateView):
    model = Pick
    template_name = 'update_pick.html'
    form_class = None

    def get_form_class(self):
        from .forms import UpdatePickForm
        return UpdatePickForm

    def get_form_kwargs(self):
        kwargs = super(UpdatePickView, self).get_form_kwargs()
        pick = self.get_object()
        kwargs['user'] = pick.user_name
        kwargs['current_pick'] = pick
        return kwargs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pick = self.get_object()
        context['is_locked'] = self.is_week_locked(pick.week)
        return context

    def form_valid(self, form):
        pick = self.get_object()

        # Check if week is locked
        if self.is_week_locked(pick.week):
            form.add_error(
                None,
                f"Week {pick.week} is locked. Picks cannot be changed after Sunday morning EST."
            )
            return self.form_invalid(form)

        return super().form_valid(form)

    def is_week_locked(self, week_number):
        """Check if the given week is locked (past Sunday morning EST)"""
        import pytz
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)

        # Calculate the Sunday of the given week
        season_start = datetime.datetime.combine(
            settings.NFL_SEASON_START_DATE,
            datetime.datetime.min.time(),
        )
        season_start = est.localize(season_start)
        days_to_week = (week_number - 1) * 7
        week_sunday = season_start + datetime.timedelta(days=days_to_week + 2)
        week_sunday = week_sunday.replace(hour=9,
                                          minute=0,
                                          second=0,
                                          microsecond=0)

        return now >= week_sunday


class DeletePickView(DeleteView):
    model = Pick
    template_name = 'delete_pick.html'
    fields = ['week']
    success_url = reverse_lazy('home')


class PickView(SingleTableView):
    model = Pick
    table_class = PickTable
    template_name = 'leaderboard.html'


def buildPickDataFrame(max_week=None):
    userMapping = {}
    teamMapping = {}
    pickList = []
    users = list(User.objects.all().values())
    # picks = list(Pick.objects.all().values())
    teams = list(Team.objects.all().values())

    # Fetch picks, optionally filter by max_week
    if max_week is not None:
        picks = list(Pick.objects.filter(week__lte=max_week).values())
    else:
        picks = list(Pick.objects.all().values())

    for user in users:
        id = user.get("id")
        userMapping[id] = user.get('username')

    for team in teams:
        id = team.get("id")
        teamMapping[id] = team.get('team_name')

    for pick in picks:
        pickUserName = userMapping.get(pick['user_name_id'])
        pickTeam = teamMapping.get(pick['team_id'])
        isWin = pick.get('is_win')
        week = pick.get('week')
        pickList.append((pickUserName, pickTeam, isWin, week))

    df = pd.DataFrame(pickList, columns=LEADERBOARD_COLUMNS)
    return df


def modelToDataFrame(request):
    ''' Builds a dataframe to display the league leaderboard'''
    df = buildPickDataFrame()

    # Create leaderboard with correct win counts
    # Convert NULL to False for counting, then count only True wins per user
    df['IsWinBool'] = df['IsWin'].fillna(False)
    win_counts = df[df['IsWinBool'] == True].groupby(
        'User Name')['IsWinBool'].count().reset_index()
    win_counts.columns = ['User Name', 'Win Count']

    # LOSS COUNTS
    loss_counts = df[df['IsWinBool'] == False].groupby(
        'User Name')['IsWinBool'].count().reset_index()
    loss_counts.columns = ['User Name', 'Loss Count']

    # Get all unique users (including those with no wins)
    all_users = df[['User Name']].drop_duplicates()
    #dfLeaderBoard = all_users.merge(win_counts, on='User Name', how='left')

    dfLeaderBoard = all_users \
    .merge(win_counts, on='User Name', how='left') \
    .merge(loss_counts, on='User Name', how='left')

    dfLeaderBoard['Win Count'] = dfLeaderBoard['Win Count'].fillna(0).astype(
        int)
    dfLeaderBoard[
        'Points'] = dfLeaderBoard['Loss Count'].fillna(0).astype(int) * 10 + 50
    dfLeaderBoard = dfLeaderBoard.drop('Loss Count', axis=1)
    dfLeaderBoard = dfLeaderBoard.sort_values('Win Count', ascending=False)

    print(dfLeaderBoard)

    context = {
        'df':
        dfLeaderBoard.to_html(
            classes=["table-bordered", "table-striped", "table-hover"],
            index=False),
    }

    return render(request, 'league_leaderboard.html', context)


def allPicksView(request):
    '''Builds a structured picks grid for display'''

    season_start_date = settings.NFL_SEASON_START_DATE
    if datetime.date.today() < season_start_date:
        current_nfl_week = 1
    else:
        current_nfl_week = get_current_nfl_week(season_start_date)

    df = buildPickDataFrame(max_week=current_nfl_week)
    if df.empty:
        return render(request, 'allPicks.html', {'players': [], 'rows': [], 'eliminated': []})

    df = df.sort_values(by=['Week'])

    weeks = sorted(df['Week'].unique().tolist())
    players = sorted(df['User Name'].unique().tolist())

    # Build lookup: (week, player) -> {team, status}
    pick_lookup = {}
    for _, row in df.iterrows():
        week = row['Week']
        player = row['User Name']
        team = row['Team']
        is_win = row['IsWin']
        if pd.isna(is_win):
            status = 'TBD'
        elif is_win:
            status = 'WIN'
        else:
            status = 'LOSS'
        pick_lookup[(week, player)] = {'team': team, 'status': status}

    eliminated = {
        player for player in players
        if any(
            pick_lookup.get((w, player), {}).get('status') == 'LOSS'
            for w in weeks
        )
    }

    rows = []
    for week in weeks:
        cells = []
        for player in players:
            cell = pick_lookup.get((week, player), {'team': '', 'status': ''})
            cells.append(cell)
        rows.append({'week': week, 'cells': cells})

    context = {
        'players': players,
        'eliminated': list(eliminated),
        'rows': rows,
    }

    return render(request, 'allPicks.html', context)


def get_current_nfl_week(season_start_date):
    today = datetime.datetime.now().date()
    if today < season_start_date:
        return 0  # preseason or offseason
    delta = today - season_start_date
    week = delta.days // 7 + 1
    return min(week, 18)  # limit to 18 weeks
