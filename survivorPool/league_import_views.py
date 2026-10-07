import json
import uuid
import logging
from datetime import timedelta

from django import forms
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth.models import User
from django.core.serializers.json import DjangoJSONEncoder
from django.db import DatabaseError, transaction
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from .league_import_parser import ImportValidationError, normalized, parse_workbook
from .league_import_service import (
    _lock_league_tables, apply_import, build_review, league_snapshot, snapshot_fingerprint,
)
from .models import LeagueImport, Pick, PickLossAdjustment
from .league_write import pick_write_transaction


class LeagueUploadForm(forms.Form):
    file = forms.FileField(
        label='Google Sheets Excel export (.xlsx)',
        widget=forms.ClearableFileInput(attrs={'accept': '.xlsx'}),
    )
    season_year = forms.IntegerField(label='Season year')
    completed_week = forms.IntegerField(
        label='Last completed week', min_value=1, max_value=18,
        help_text='Blanks through this week become missed-pick losses. Later blanks stay unpicked.',
    )

    def clean_season_year(self):
        value = self.cleaned_data['season_year']
        if value != settings.NFL_SEASON_YEAR:
            raise forms.ValidationError(f'Only the configured {settings.NFL_SEASON_YEAR} season can be imported.')
        return value


@staff_member_required
@never_cache
def league_import_upload(request):
    form = LeagueUploadForm(request.POST or None, request.FILES or None, initial={
        'season_year': settings.NFL_SEASON_YEAR, 'completed_week': 4,
    })
    if request.method == 'POST' and form.is_valid():
        try:
            source = parse_workbook(form.cleaned_data['file'], form.cleaned_data['completed_week'])
            batch = LeagueImport.objects.create(
                created_by=request.user,
                filename=form.cleaned_data['file'].name[:255],
                season_year=form.cleaned_data['season_year'],
                completed_week=form.cleaned_data['completed_week'],
                source=source,
            )
            return redirect('league_import_review', batch_id=batch.pk)
        except ImportValidationError as exc:
            form.add_error('file', str(exc))
    return render(request, 'league_import_upload.html', {
        'form': form,
        'imports': LeagueImport.objects.filter(created_by=request.user)[:20],
    })


def _choices_from_post(batch, post):
    mapping = {
        str(index): post.get(f'mapping_{index}', '')
        for index in range(len(batch.source['players']))
    }
    losses = {
        f'{entry["player_index"]}_{entry["week"]}': post.get(
            f'loss_{entry["player_index"]}_{entry["week"]}', '',
        )
        for entry in batch.source['picks'] if entry['is_win'] is False
    }
    return mapping, losses


def _review_context(batch):
    users = list(User.objects.filter(is_active=True).order_by('username'))
    by_name = {}
    for user in users:
        by_name.setdefault(normalized(user.username), []).append(user)
    initial_mapping = {}
    for index, player in enumerate(batch.source['players']):
        matches = by_name.get(normalized(player['name']), [])
        initial_mapping[str(index)] = str(matches[0].pk) if len(matches) == 1 else ''
    mapping = batch.review.get('mapping', initial_mapping)
    losses = batch.review.get('loss_choices', {})
    review = build_review(batch, mapping, losses)
    if batch.status == LeagueImport.STATUS_APPLIED:
        # Reconciliation at import time is authoritative; subsequent picks are
        # not folded into the historic success receipt.
        review.update(batch.summary)
    mapping_rows = [
        dict(player, index=index, selected_user_id=str(mapping.get(str(index), '')))
        for index, player in enumerate(batch.source['players'])
    ]
    pick_rows, loss_rows = [], []
    for entry in batch.source['picks']:
        row = dict(
            entry, player=batch.source['players'][entry['player_index']]['name'],
            status='WIN' if entry['is_win'] is True else 'LOSS' if entry['is_win'] is False else 'TBD',
        )
        pick_rows.append(row)
        if entry['is_win'] is False:
            key = f'{entry["player_index"]}_{entry["week"]}'
            loss_rows.append(dict(row, key=key, selection=losses.get(key, '')))
    return {
        'batch': batch, 'users': users, 'review': review,
        'mapping_rows': mapping_rows, 'loss_rows': loss_rows, 'pick_rows': pick_rows,
        'review_saved': batch.status == LeagueImport.STATUS_REVIEWED,
    }


@staff_member_required
@never_cache
def league_import_review(request, batch_id):
    batch = get_object_or_404(LeagueImport, pk=batch_id, created_by=request.user)
    if request.method == 'POST':
        try:
            if batch.status == LeagueImport.STATUS_APPLIED:
                messages.info(request, 'This import was already applied; it will not run again.')
                return redirect('league_import_review', batch_id=batch.pk)
            if timezone.now() - batch.created_at > timedelta(hours=24):
                raise ImportValidationError('This draft has expired. Upload the workbook again.')
            action = request.POST.get('action')
            if action == 'review':
                mapping, losses = _choices_from_post(batch, request.POST)
                with transaction.atomic():
                    batch = LeagueImport.objects.select_for_update().get(pk=batch.pk)
                    if batch.status == LeagueImport.STATUS_APPLIED:
                        raise ImportValidationError('This import was already applied.')
                    _lock_league_tables()
                    batch.save(update_fields=['status'])
                    batch.review = build_review(batch, mapping, losses)
                    batch.review['review_token'] = str(uuid.uuid4())
                    batch.fingerprint = snapshot_fingerprint(league_snapshot())
                    batch.status = LeagueImport.STATUS_REVIEWED if batch.review['ready'] else LeagueImport.STATUS_DRAFT
                    batch.save(update_fields=['review', 'fingerprint', 'status'])
                if batch.review['ready']:
                    messages.success(request, 'Review saved. Totals match; check the replacement scope before confirming.')
                else:
                    messages.error(request, 'Review saved, but resolve the listed issues before replacement.')
            elif action == 'confirm':
                if request.POST.get('review_token') != batch.review.get('review_token'):
                    raise ImportValidationError('The review changed. Reload this page and check the latest review.')
                apply_import(
                    batch.pk, request.user, request.POST.get('confirmation', ''),
                    request.POST.get('ack_replace') in {'on', 'yes'},
                    request.POST.get('ack_omitted') in {'on', 'yes'},
                    request.POST.get('ack_warnings') in {'on', 'yes'},
                    review_token=request.POST.get('review_token'),
                )
                messages.success(request, 'Spreadsheet picks replaced the pilot history. A pre-import backup is available.')
            else:
                raise ImportValidationError('Unknown import action.')
            return redirect('league_import_review', batch_id=batch.pk)
        except ImportValidationError as exc:
            messages.error(request, str(exc))
            batch.refresh_from_db()
        except DatabaseError:
            logging.getLogger(__name__).exception('League import transaction failed for batch %s', batch.pk)
            messages.error(request, 'The import transaction failed. No picks were replaced. Reload and review again before retrying.')
            batch.refresh_from_db()
    return render(request, 'league_import_review.html', _review_context(batch))


@staff_member_required
@never_cache
def league_import_backup(request, batch_id):
    batch = get_object_or_404(LeagueImport, pk=batch_id, status=LeagueImport.STATUS_APPLIED)
    content = json.dumps({
        'format': 'survivor-pool-pre-import-backup-v1',
        'import_id': str(batch.pk), 'created_at': batch.applied_at,
        'applied_by_user_id': batch.created_by_id,
        'backup': batch.backup, 'import_summary': batch.summary,
    }, cls=DjangoJSONEncoder, indent=2)
    response = HttpResponse(content, content_type='application/json')
    response['Content-Disposition'] = f'attachment; filename="league-backup-{batch.pk}.json"'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@staff_member_required
@never_cache
def league_loss_overrides(request):
    if request.method == 'POST':
        try:
            choice = request.POST.get('override')
            reason = request.POST.get('reason', '').strip()
            if choice not in {'auto', 'standard', 'favorite'} or not reason or len(reason) > 500:
                raise ImportValidationError('Select a valid loss classification and enter a reason of 1–500 characters.')
            with pick_write_transaction():
                try:
                    pick_id = int(request.POST.get('pick_id', ''))
                except (ValueError, TypeError):
                    raise ImportValidationError('Select a valid losing pick.')
                pick = get_object_or_404(
                    Pick.objects.select_for_update().select_related('user_name', 'team'),
                    pk=pick_id, is_win=False,
                )
                if pick.imported_result and choice == 'auto':
                    raise ImportValidationError('Imported losses need an explicit standard or biggest-favorite classification.')
                if pick.missed_deadline and choice == 'favorite':
                    raise ImportValidationError('No-pick losses must be standard.')
                new_value = None if choice == 'auto' else choice == 'favorite'
                if new_value != pick.favorite_loss_override:
                    PickLossAdjustment.objects.create(
                        pick=pick, actor=request.user, old_value=pick.favorite_loss_override,
                        new_value=new_value, reason=reason,
                        pick_snapshot={'user_id': pick.user_name_id, 'username': pick.user_name.username,
                                       'team': pick.team.team_name, 'week': pick.week},
                    )
                    pick.favorite_loss_override = new_value
                    pick.save(update_fields=['favorite_loss_override'])
            messages.success(request, 'Loss classification saved. Standings and amounts owed have updated.')
            return redirect('league_loss_overrides')
        except ImportValidationError as exc:
            messages.error(request, str(exc))
    picks = Pick.objects.filter(is_win=False).select_related('user_name', 'team').order_by('week', 'user_name__username')
    entries = [{
        'pick': pick, 'user': pick.user_name, 'team': pick.team.team_name, 'week': pick.week,
        'override_value': 'auto' if pick.favorite_loss_override is None else 'favorite' if pick.favorite_loss_override else 'standard',
    } for pick in picks]
    return render(request, 'league_loss_overrides.html', {
        'entries': entries,
        'audit_rows': PickLossAdjustment.objects.select_related('actor', 'pick')[:100],
    })
