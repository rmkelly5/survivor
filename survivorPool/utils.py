"""Shared helpers for week locking, NFL calendar, and pick grids."""
from __future__ import annotations

import datetime
from typing import Any

import pytz
from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count, Q

from .models import Pick

EST = pytz.timezone('US/Eastern')
WEEK_LOCK_HOUR = 13
WEEK_LOCK_MINUTE = 5


def get_current_nfl_week(season_start_date=None) -> int:
    season_start_date = season_start_date or settings.NFL_SEASON_START_DATE
    today = datetime.date.today()
    if today < season_start_date:
        return 1
    delta = today - season_start_date
    return min(delta.days // 7 + 1, 18)


def get_week_lock_datetime(week_number: int, season_start_date=None) -> datetime.datetime:
    """Sunday 1:05 PM US/Eastern for the given NFL week."""
    season_start_date = season_start_date or settings.NFL_SEASON_START_DATE
    season_start = datetime.datetime.combine(season_start_date, datetime.time.min)
    season_start = EST.localize(season_start)
    days_to_week = (week_number - 1) * 7
    week_sunday = season_start + datetime.timedelta(days=days_to_week + 2)
    return week_sunday.replace(
        hour=WEEK_LOCK_HOUR,
        minute=WEEK_LOCK_MINUTE,
        second=0,
        microsecond=0,
    )


def is_week_locked(week_number: int) -> bool:
    now = datetime.datetime.now(EST)
    return now >= get_week_lock_datetime(week_number)


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
    """Win/loss counts and simple pot contribution per player."""
    users = User.objects.filter(
        is_active=True,
        is_staff=False,
        is_superuser=False,
    ).annotate(
        win_count=Count('pick', filter=Q(pick__is_win=True)),
        loss_count=Count('pick', filter=Q(pick__is_win=False)),
    ).order_by('-win_count', 'username')

    rows = []
    for user in users:
        loss_count = user.loss_count or 0
        rows.append({
            'username': user.username,
            'win_count': user.win_count or 0,
            'loss_count': loss_count,
            'pot_contribution': 50 + loss_count * 10,
        })
    return rows


def get_league_member_usernames() -> list[str]:
    """Users who have submitted at least one real pick."""
    return list(
        Pick.objects.filter(
            missed_deadline=False,
            user_name__is_active=True,
            user_name__is_staff=False,
            user_name__is_superuser=False,
        )
        .order_by('user_name__username')
        .values_list('user_name__username', flat=True)
        .distinct()
    )
