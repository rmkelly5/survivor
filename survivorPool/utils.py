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
    return pick.imported_result or pick.missed_deadline or is_team_game_started(pick.team, pick.week)


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
        pick_is_visible = (
            pick.missed_deadline
            or pick.is_win is not None
            or is_team_game_started(pick.team, pick.week)
        )
        pick_lookup[(pick.week, player)] = {
            'team': (
                pick.team.team_name
                if pick_is_visible and not pick.missed_deadline
                else ''
            ),
            'status': pick_status(pick.is_win) if pick_is_visible else '',
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


def select_biggest_spread_favorites(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Select all tied favorites by points given, never by moneyline.

    Stored spreads are positive magnitudes for favorites, with a separate
    favorite flag. abs() also handles signed negative favorite spreads.
    Missing spreads, underdogs, and pick'em games are not candidates.
    """
    favorites = [
        candidate for candidate in candidates
        if candidate.get('is_favorite')
        and candidate.get('spread') is not None
        and abs(candidate['spread']) > 0
    ]
    if not favorites:
        return []
    largest_spread = max(abs(candidate['spread']) for candidate in favorites)
    return [
        candidate for candidate in favorites
        if abs(candidate['spread']) == largest_spread
    ]


def get_underdog_credit_counts(games=None, user_id=None) -> dict[int, int]:
    """Count qualifying wins; odds store the favorite's spread as a magnitude.

    The opposite team is the underdog. Never infer a point spread from moneyline
    odds, and never award a credit for a pending, losing, or missed pick.
    """
    if games is None:
        games = Game.objects.filter(
            season_year=settings.NFL_SEASON_YEAR,
        ).values(
            'week', 'home_team_id', 'away_team_id',
            'home_spread', 'away_spread', 'home_is_favorite', 'away_is_favorite',
        )
    qualifying_picks = set()
    for game in games:
        for side, opponent in (('home', 'away'), ('away', 'home')):
            spread = game[f'{opponent}_spread']
            if (
                not game[f'{side}_is_favorite']
                and game[f'{opponent}_is_favorite']
                and spread is not None
                and abs(spread) >= Decimal('5')
            ):
                qualifying_picks.add((game['week'], game[f'{side}_team_id']))

    winners = Pick.objects.filter(is_win=True, missed_deadline=False)
    if user_id is not None:
        winners = winners.filter(user_name_id=user_id)
    credits = defaultdict(int)
    for pick in winners.values('user_name_id', 'team_id', 'week'):
        if (pick['week'], pick['team_id']) in qualifying_picks:
            credits[pick['user_name_id']] += 1
    return credits


def loss_credit_summary(actual_losses: int, credit_count: int) -> dict[str, Any]:
    """Apply record-only credits, banking excess without refunding loss fees."""
    credits = Decimal(credit_count) / Decimal('2')
    return {
        'actual_loss_count': actual_losses,
        'loss_count': max(Decimal('0'), Decimal(actual_losses) - credits),
        'loss_credit_count': credit_count,
        'loss_credit_total': credits,
        'banked_loss_credits': max(Decimal('0'), credits - Decimal(actual_losses)),
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

    weekly_spreads = defaultdict(list)
    games = list(Game.objects.filter(
        season_year=settings.NFL_SEASON_YEAR,
    ).values(
        'week',
        'home_team_id',
        'home_spread',
        'home_is_favorite',
        'away_team_id',
        'away_spread',
        'away_is_favorite',
    ))
    for game in games:
        for side in ('home', 'away'):
            weekly_spreads[game['week']].append({
                'team_id': game[f'{side}_team_id'],
                'spread': game[f'{side}_spread'],
                'is_favorite': game[f'{side}_is_favorite'],
            })

    biggest_favorite_ids = {
        week: {
            candidate['team_id']
            for candidate in select_biggest_spread_favorites(teams)
        }
        for week, teams in weekly_spreads.items()
    }
    credit_counts = get_underdog_credit_counts(games=games)

    favorite_losses_by_user = defaultdict(int)
    for pick in Pick.objects.filter(
        is_win=False,
        user_name__is_active=True,
    ).values('user_name_id', 'team_id', 'week', 'favorite_loss_override', 'missed_deadline'):
        is_favorite = pick['favorite_loss_override']
        if is_favorite is None:
            is_favorite = (
                not pick['missed_deadline']
                and pick['team_id'] in biggest_favorite_ids.get(pick['week'], set())
            )
        if is_favorite:
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
            **loss_credit_summary(loss_count, credit_counts.get(user.id, 0)),
            'standard_loss_count': standard_loss_count,
            'favorite_loss_count': favorite_loss_count,
            'pot_contribution': (
                buy_in
                + standard_loss_count * loss_amount
                + favorite_loss_count * favorite_loss_amount
            ),
        })
    return sorted(rows, key=lambda row: (
        -row['win_count'],
        row['loss_count'],
        row['pot_contribution'],
        row['username'],
    ))


def get_league_member_usernames() -> list[str]:
    """All active users who participate in the league."""
    return list(
        User.objects.filter(is_active=True)
        .order_by('username')
        .values_list('username', flat=True)
    )
