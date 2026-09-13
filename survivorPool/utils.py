"""Shared helpers for NFL timing and pick grids."""
from __future__ import annotations

import datetime
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Q
from django.utils import timezone

from .models import Game, Pick, SeasonSettings, Team

def get_current_nfl_week(season_start_date=None) -> int:
    season_start_date = season_start_date or settings.NFL_SEASON_START_DATE
    today = datetime.date.today()
    if today < season_start_date:
        return 1
    delta = today - season_start_date
    return min(delta.days // 7 + 1, 18)


def all_week_games_started(week_number: int) -> bool:
    """Return true only when every scheduled game for the week has kicked off."""
    game_times = list(Game.objects.filter(
        season_year=settings.NFL_SEASON_YEAR,
        week=week_number,
    ).values_list('game_time', flat=True))
    now = timezone.now()
    # An unknown kickoff must not finalize the week and erase a valid late-pick window.
    return bool(game_times) and all(game_time and now >= game_time for game_time in game_times)


def get_team_game_time(team: Team, week_number: int):
    """Return the scheduled kickoff for a team in a given week."""
    game = (
        Game.objects.filter(
            Q(home_team=team) | Q(away_team=team),
            season_year=settings.NFL_SEASON_YEAR,
            week=week_number,
        )
        .exclude(game_time__isnull=True)
        .first()
    )
    if game:
        return game.game_time
    if team.current_week == week_number:
        return team.game_time
    return None


def is_team_game_started(team: Team, week_number: int) -> bool:
    """Use the selected team's kickoff as its only pick deadline."""
    game_time = get_team_game_time(team, week_number)
    return game_time is not None and timezone.now() >= game_time


def is_pick_locked(pick: Pick) -> bool:
    return pick.missed_deadline or is_team_game_started(pick.team, pick.week)


def pick_status(is_win) -> str:
    if is_win is None:
        return 'TBD'
    if is_win:
        return 'WIN'
    return 'LOSS'


def build_picks_grid(max_week: int | None = None) -> dict[str, Any]:
    """Build league picks grid without pandas."""
    picks_qs = Pick.objects.select_related('user_name', 'team').order_by('week', 'user_name__username')
    if max_week is not None:
        picks_qs = picks_qs.filter(week__lte=max_week)

    pick_lookup: dict[tuple[int, str], dict[str, str]] = {}
    weeks_set: set[int] = set()
    players_set: set[str] = set()

    for pick in picks_qs:
        player = pick.user_name.username
        weeks_set.add(pick.week)
        players_set.add(player)
        pick_lookup[(pick.week, player)] = {
            'team': '' if pick.missed_deadline else pick.team.team_name,
            'status': pick_status(pick.is_win),
            'missed_deadline': pick.missed_deadline,
        }

    weeks = sorted(weeks_set)
    players = sorted(players_set)
    rows = []
    for week in weeks:
        cells = []
        for player in players:
            cells.append(pick_lookup.get((week, player), {'team': '', 'status': '', 'missed_deadline': False}))
        rows.append({'week': week, 'cells': cells})

    return {
        'players': players,
        'rows': rows,
        'weeks': weeks,
        'pick_lookup': pick_lookup,
    }


def build_leaderboard_rows() -> list[dict[str, Any]]:
    """Build standings and pot contributions using the configured loss rules."""
    season_settings = SeasonSettings.objects.filter(
        season_year=settings.NFL_SEASON_YEAR,
    ).first()
    buy_in = season_settings.buy_in if season_settings else Decimal('50')
    loss_amount = season_settings.loss_amount if season_settings else Decimal('10')
    favorite_loss_amount = (
        season_settings.favorite_loss_amount
        if season_settings
        else Decimal('25')
    )

    weekly_moneylines = defaultdict(list)
    for game in Game.objects.filter(
        season_year=settings.NFL_SEASON_YEAR,
    ).values(
        'week',
        'home_team_id',
        'home_moneyline',
        'away_team_id',
        'away_moneyline',
    ):
        if game['home_moneyline'] is not None:
            weekly_moneylines[game['week']].append(
                (game['home_moneyline'], game['home_team_id'])
            )
        if game['away_moneyline'] is not None:
            weekly_moneylines[game['week']].append(
                (game['away_moneyline'], game['away_team_id'])
            )

    biggest_favorite_ids = {}
    for week, teams in weekly_moneylines.items():
        best_moneyline = min(moneyline for moneyline, _ in teams)
        biggest_favorite_ids[week] = {
            team_id
            for moneyline, team_id in teams
            if moneyline == best_moneyline
        }

    favorite_losses_by_user = defaultdict(int)
    for pick in Pick.objects.filter(
        is_win=False,
        user_name__is_active=True,
    ).values('user_name_id', 'team_id', 'week'):
        if pick['team_id'] in biggest_favorite_ids.get(pick['week'], set()):
            favorite_losses_by_user[pick['user_name_id']] += 1

    users = User.objects.filter(
        is_active=True,
    ).annotate(
        win_count=Count('pick', filter=Q(pick__is_win=True)),
        loss_count=Count('pick', filter=Q(pick__is_win=False)),
    ).order_by('-win_count', 'username')

    rows = []
    for user in users:
        loss_count = user.loss_count or 0
        favorite_loss_count = favorite_losses_by_user[user.id]
        standard_loss_count = loss_count - favorite_loss_count
        rows.append({
            'username': user.username,
            'win_count': user.win_count or 0,
            'loss_count': loss_count,
            'standard_loss_count': standard_loss_count,
            'favorite_loss_count': favorite_loss_count,
            'pot_contribution': (
                buy_in
                + standard_loss_count * loss_amount
                + favorite_loss_count * favorite_loss_amount
            ),
        })
    return rows


def get_league_member_usernames() -> list[str]:
    """Users who have submitted at least one real pick."""
    return list(
        Pick.objects.filter(
            missed_deadline=False,
            user_name__is_active=True,
        )
        .order_by('user_name__username')
        .values_list('user_name__username', flat=True)
        .distinct()
    )
