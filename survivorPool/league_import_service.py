"""Server-owned reviews and atomic, backed-up replacement of pilot picks."""
import hashlib
import json
from collections import Counter
from decimal import Decimal
from datetime import timedelta

from django.conf import settings
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection, transaction
from django.utils import timezone

from .league_import_parser import ImportValidationError
from .models import (
    ChatMessage, Game, LeagueImport, Pick, PickLossAdjustment, SeasonSettings, Team, WeekLockRun,
)


def league_snapshot():
    """No passwords or auth credentials are included in the backup."""
    return {
        'season_year': settings.NFL_SEASON_YEAR,
        'picks': list(Pick.objects.order_by('id').values()),
        'week_locks': list(WeekLockRun.objects.filter(
            season_year=settings.NFL_SEASON_YEAR,
        ).order_by('id').values()),
        'weekly_summaries': list(ChatMessage.objects.filter(
            message_type=ChatMessage.MESSAGE_WEEKLY_LOCK,
        ).order_by('id').values()),
        'users': list(User.objects.order_by('id').values('id', 'username', 'is_active')),
        'teams': list(Team.objects.order_by('id').values('id', 'team_name')),
        'games': list(Game.objects.filter(
            season_year=settings.NFL_SEASON_YEAR,
        ).order_by('id').values()),
        'season_settings': list(SeasonSettings.objects.filter(
            season_year=settings.NFL_SEASON_YEAR,
        ).values()),
        'loss_adjustments': list(PickLossAdjustment.objects.order_by('id').values()),
    }


def snapshot_fingerprint(snapshot):
    serialized = json.dumps(snapshot, cls=DjangoJSONEncoder, sort_keys=True)
    return hashlib.sha256(serialized.encode()).hexdigest()


def build_review(batch, mapping, loss_choices):
    errors, warnings = [], list(batch.source['warnings'])
    if batch.season_year != settings.NFL_SEASON_YEAR:
        errors.append('Only the configured current season can be replaced.')
    users = {str(user.pk): user for user in User.objects.filter(is_active=True)}
    selected = []
    for index, player in enumerate(batch.source['players']):
        user = users.get(str(mapping.get(str(index), '')))
        if not user:
            errors.append(f'{player["name"]}: select an active app account.')
        selected.append(user)
    ids = [user.pk for user in selected if user]
    if len(ids) != len(set(ids)):
        errors.append('Each spreadsheet player must map to a different app account.')
    counts = [Counter() for _ in selected]
    for pick in batch.source['picks']:
        index = pick['player_index']
        stats = counts[index]
        stats['picks'] += 1
        if pick['is_win'] is True:
            stats['wins'] += 1
        elif pick['is_win'] is False:
            stats['losses'] += 1
            key = f'{index}_{pick["week"]}'
            choice = loss_choices.get(key, '')
            if choice not in {'standard', 'favorite'}:
                errors.append(f'{batch.source["players"][index]["name"]}, Week {pick["week"]}: classify this loss.')
            elif pick['missed_deadline'] and choice == 'favorite':
                errors.append(f'{batch.source["players"][index]["name"]}, Week {pick["week"]}: no-pick losses must be standard.')
            elif choice == 'favorite':
                stats['favorite_losses'] += 1
        else:
            stats['pending'] += 1
        if pick['missed_deadline']:
            stats['missed'] += 1

    season = SeasonSettings.objects.filter(season_year=batch.season_year).first()
    buy_in = season.buy_in if season else Decimal('50')
    standard = season.loss_amount if season else Decimal('10')
    favorite = season.favorite_loss_amount if season else Decimal('25')
    player_rows, total = [], Decimal('0')
    for index, player in enumerate(batch.source['players']):
        stats = counts[index]
        amount = buy_in + (stats['losses'] - stats['favorite_losses']) * standard + stats['favorite_losses'] * favorite
        expected = Decimal(player['expected_total']) if player['expected_total'] is not None else None
        difference = amount - expected if expected is not None else None
        if player['expected_losses'] is not None and player['expected_losses'] != stats['losses']:
            errors.append(f'{player["name"]}: loss count does not match the spreadsheet summary.')
        if difference is not None and difference != 0:
            errors.append(f'{player["name"]}: calculated amount ${amount:.2f} does not match sheet amount ${expected:.2f}.')
        total += amount
        player_rows.append({
            'name': player['name'],
            'username': selected[index].username if selected[index] else 'Unmapped',
            'wins': stats['wins'], 'losses': stats['losses'],
            'favorite_losses': stats['favorite_losses'], 'total': f'{amount:.2f}',
            'expected_total': f'{expected:.2f}' if expected is not None else '',
            'difference': f'{difference:.2f}' if difference is not None else '',
        })
    expected_pot = batch.source.get('expected_pot')
    if expected_pot is not None and total != Decimal(expected_pot):
        errors.append(f'Calculated pot ${total:.2f} does not match spreadsheet pot ${Decimal(expected_pot):.2f}.')
    mapped_ids = set(ids)
    totals = sum(counts, Counter())
    return {
        'errors': errors, 'warnings': warnings, 'players': player_rows,
        'total': f'{total:.2f}', 'pick_count': len(batch.source['picks']),
        'wins': totals['wins'], 'losses': totals['losses'], 'missed': totals['missed'],
        'existing_count': Pick.objects.count(),
        'omitted_users': [u.username for u in users.values() if u.pk not in mapped_ids],
        'ready': not errors, 'mapping': mapping, 'loss_choices': loss_choices,
    }


def _lock_league_tables():
    # These table locks block ordinary pick edits, result posting, odds updates,
    # and account changes only for the short replacement transaction.
    if connection.vendor == 'postgresql':
        models = (Team, User, Game, ChatMessage, WeekLockRun, SeasonSettings, PickLossAdjustment)
        names = sorted(connection.ops.quote_name(model._meta.db_table) for model in models)
        with connection.cursor() as cursor:
            # Pick writers acquire their lock before reading/validating. Taking
            # this first also lets in-flight weekly finalization finish, rather
            # than holding its chat table while waiting for its pick writes.
            pick_table = connection.ops.quote_name(Pick._meta.db_table)
            cursor.execute(f'LOCK TABLE {pick_table} IN EXCLUSIVE MODE')
            cursor.execute(f'LOCK TABLE {", ".join(names)} IN SHARE ROW EXCLUSIVE MODE')


@transaction.atomic
def apply_import(batch_id, actor, confirmation, ack_replace, ack_omitted=False, ack_warnings=False, review_token=None):
    if not actor.is_active or not actor.is_staff:
        raise ImportValidationError('Only active staff can replace league picks.')
    batch = LeagueImport.objects.select_for_update().get(pk=batch_id, created_by=actor)
    if batch.status == LeagueImport.STATUS_APPLIED:
        return batch
    if batch.status != LeagueImport.STATUS_REVIEWED or not batch.review.get('ready'):
        raise ImportValidationError('Save a valid review before replacing picks.')
    if review_token is None or review_token != batch.review.get('review_token'):
        raise ImportValidationError('The review changed. Reload and check the latest review.')
    if timezone.now() - batch.created_at > timedelta(hours=24):
        raise ImportValidationError('This draft has expired. Upload the workbook again.')
    if confirmation.strip() != f'REPLACE {batch.season_year}' or not ack_replace:
        raise ImportValidationError(f'Type REPLACE {batch.season_year} and acknowledge the replacement.')
    _lock_league_tables()
    # On SQLite this acquires the write lock before taking the snapshot.
    batch.save(update_fields=['status'])
    snapshot = league_snapshot()
    if snapshot_fingerprint(snapshot) != batch.fingerprint:
        raise ImportValidationError('League data changed since review. Save and review again before confirming.')
    review = build_review(batch, batch.review['mapping'], batch.review['loss_choices'])
    if not review['ready']:
        raise ImportValidationError('The saved review is no longer valid. Review the mappings and amounts again.')
    if review['omitted_users'] and not ack_omitted:
        raise ImportValidationError('Acknowledge the active accounts absent from the spreadsheet.')
    if review['warnings'] and not ack_warnings:
        raise ImportValidationError('Acknowledge the spreadsheet warnings before continuing.')

    batch.backup = snapshot
    # Persist the backup inside the same transaction as the replacement.
    batch.save(update_fields=['backup'])
    old_count = Pick.objects.count()
    Pick.objects.all().delete()
    WeekLockRun.objects.filter(season_year=batch.season_year).delete()
    ChatMessage.objects.filter(message_type=ChatMessage.MESSAGE_WEEKLY_LOCK).delete()
    no_pick_team = None
    new_picks = []
    for entry in batch.source['picks']:
        team_id = entry['team_id']
        if entry['missed_deadline']:
            if no_pick_team is None:
                no_pick_team, _ = Team.objects.get_or_create(team_name='No Pick')
            team_id = no_pick_team.pk
        choice = review['loss_choices'].get(f'{entry["player_index"]}_{entry["week"]}')
        new_picks.append(Pick(
            user_name_id=int(review['mapping'][str(entry['player_index'])]),
            week=entry['week'], team_id=team_id, is_win=entry['is_win'],
            missed_deadline=entry['missed_deadline'],
            imported_result=entry['week'] <= batch.completed_week,
            favorite_loss_override=(choice == 'favorite') if entry['is_win'] is False else None,
        ))
    Pick.objects.bulk_create(new_picks)
    WeekLockRun.objects.bulk_create([
        WeekLockRun(season_year=batch.season_year, week=week)
        for week in range(1, batch.completed_week + 1)
    ])
    batch.status = LeagueImport.STATUS_APPLIED
    batch.applied_at = timezone.now()
    batch.summary = {
        'replaced_count': old_count, 'imported_count': len(new_picks),
        'wins': review['wins'], 'losses': review['losses'], 'missed': review['missed'],
        'total': review['total'], 'players': review['players'],
        'completed_week': batch.completed_week, 'season_year': batch.season_year,
    }
    batch.save(update_fields=['status', 'applied_at', 'summary'])
    return batch
