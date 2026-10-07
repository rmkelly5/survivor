import datetime
import io
import uuid
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from openpyxl import Workbook
from openpyxl.styles import PatternFill

from .league_import_parser import ImportValidationError, parse_workbook
from .league_import_service import apply_import, build_review, league_snapshot, snapshot_fingerprint
from .models import ChatMessage, Game, LeagueImport, Pick, PickLossAdjustment, Team, WeekLockRun
from .utils import build_leaderboard_rows, is_pick_locked


def workbook_upload(rows=None, summaries=True):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Survivor Pool'
    sheet.append(['Week', 'Alice', 'Bob'])
    data = rows if rows is not None else [
        [(1, None), ('Bills', 'B6D7A8'), ('Dolphins', 'E06666')],
        [(2, None), ('Dolphins', 'E06666'), ('Bills', 'B6D7A8')],
        [(3, None), (None, None), (None, None)],
    ]
    for entries in data:
        sheet.append([entry[0] for entry in entries])
        for column, (_, color) in enumerate(entries, 1):
            if color:
                sheet.cell(sheet.max_row, column).fill = PatternFill('solid', fgColor=color)
    if summaries:
        sheet.append(['Losses:', 1, 1])
        sheet.append(['$ Owed:', 60, 75])
        sheet.append(['Total Pot:', 135])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return SimpleUploadedFile('league.xlsx', output.getvalue())


class LeagueImportTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user(username='operator', is_staff=True)
        self.alice = User.objects.create_user(username='alice')
        self.bob = User.objects.create_user(username='bob')
        self.bills = Team.objects.create(team_name='Bills')
        self.dolphins = Team.objects.create(team_name='Dolphins')
        self.mapping = {'0': str(self.alice.pk), '1': str(self.bob.pk)}
        self.choices = {'0_2': 'standard', '1_1': 'favorite'}
        self.client.force_login(self.staff)

    def batch(self, upload=None):
        return LeagueImport.objects.create(
            created_by=self.staff, filename='league.xlsx', season_year=2026,
            completed_week=2, source=parse_workbook(upload or workbook_upload(), 2),
        )

    def reviewed(self):
        batch = self.batch()
        batch.review = build_review(batch, self.mapping, self.choices)
        self.assertTrue(batch.review['ready'], batch.review['errors'])
        batch.review['review_token'] = str(uuid.uuid4())
        batch.fingerprint = snapshot_fingerprint(league_snapshot())
        batch.status = LeagueImport.STATUS_REVIEWED
        batch.save()
        return batch

    def apply(self, batch, **kwargs):
        args = {
            'confirmation': 'REPLACE 2026', 'ack_replace': True,
            'ack_omitted': True, 'ack_warnings': True,
            'review_token': batch.review['review_token'],
        }
        args.update(kwargs)
        return apply_import(batch.pk, self.staff, **args)

    def test_upload_and_review_do_not_change_picks(self):
        old = Pick.objects.create(user_name=self.alice, team=self.bills, week=8)
        response = self.client.post(reverse('league_import_upload'), {
            'file': workbook_upload(), 'season_year': 2026, 'completed_week': 2,
        })
        self.assertEqual(response.status_code, 302)
        batch = LeagueImport.objects.get()
        self.assertEqual(len(batch.source['picks']), 4)
        review_url = reverse('league_import_review', kwargs={'batch_id': batch.pk})
        response = self.client.get(review_url)
        self.assertContains(response, 'All imported picks')
        self.assertContains(response, 'mapping_0')
        self.assertNotContains(response, 'Confirm and replace history')
        response = self.client.post(review_url, {
            'action': 'review', 'mapping_0': self.alice.pk, 'mapping_1': self.bob.pk,
            'loss_0_2': 'standard', 'loss_1_1': 'favorite',
        }, follow=True)
        self.assertContains(response, 'Confirm and replace history')
        self.assertContains(response, 'review_token')
        self.assertTrue(Pick.objects.filter(pk=old.pk).exists())
        self.assertEqual(Pick.objects.count(), 1)

    def test_apply_replaces_all_picks_preserves_other_data_and_saves_backup(self):
        old = Pick.objects.create(user_name=self.alice, team=self.bills, week=8)
        game = Game.objects.create(
            season_year=2026, week=8, home_team=self.bills, away_team=self.dolphins,
        )
        chat = ChatMessage.objects.create(author=self.alice, body='Preserve this conversation')
        generated = ChatMessage.objects.create(
            body='Old summary', message_type=ChatMessage.MESSAGE_WEEKLY_LOCK, week=8,
        )
        WeekLockRun.objects.create(season_year=2026, week=8)
        batch = self.reviewed()
        applied = self.apply(batch)
        self.assertEqual(Pick.objects.count(), 4)
        self.assertFalse(Pick.objects.filter(pk=old.pk).exists())
        self.assertTrue(Game.objects.filter(pk=game.pk).exists())
        self.assertTrue(ChatMessage.objects.filter(pk=chat.pk).exists())
        self.assertFalse(ChatMessage.objects.filter(pk=generated.pk).exists())
        self.assertEqual(WeekLockRun.objects.count(), 2)
        self.assertTrue(all(pick.imported_result for pick in Pick.objects.all()))
        self.assertEqual(applied.summary['total'], '135.00')
        self.assertEqual(applied.backup['picks'][0]['id'], old.pk)
        self.assertNotIn('password', str(applied.backup))
        response = self.client.get(reverse('league_import_backup', kwargs={'batch_id': batch.pk}))
        self.assertEqual(response.status_code, 200)
        self.assertIn('attachment', response['Content-Disposition'])
        self.assertEqual(response.json()['backup']['picks'][0]['id'], old.pk)
        ids = list(Pick.objects.values_list('pk', flat=True))
        self.apply(applied)
        self.assertEqual(ids, list(Pick.objects.values_list('pk', flat=True)))

    def test_confirm_post_uses_saved_review_and_requires_acknowledgments(self):
        batch = self.reviewed()
        url = reverse('league_import_review', kwargs={'batch_id': batch.pk})
        response = self.client.post(url, {
            'action': 'confirm', 'review_token': batch.review['review_token'],
            'confirmation': 'REPLACE 2026', 'ack_replace': 'yes', 'ack_omitted': 'yes',
        }, follow=True)
        self.assertContains(response, 'This batch has been applied')
        self.assertEqual(Pick.objects.count(), 4)

    def test_stale_review_does_not_delete_or_overwrite_new_picks(self):
        batch = self.reviewed()
        pick = Pick.objects.create(user_name=self.bob, team=self.bills, week=6)
        with self.assertRaisesMessage(ImportValidationError, 'League data changed'):
            self.apply(batch)
        self.assertTrue(Pick.objects.filter(pk=pick.pk).exists())
        batch.refresh_from_db()
        self.assertFalse(batch.backup)
        self.assertEqual(batch.status, LeagueImport.STATUS_REVIEWED)

    def test_confirmation_phrase_omission_and_token_are_enforced(self):
        batch = self.reviewed()
        for kwargs in (
            {'confirmation': 'replace'}, {'ack_replace': False},
            {'ack_omitted': False}, {'review_token': 'wrong'},
        ):
            with self.assertRaises(ImportValidationError):
                self.apply(batch, **kwargs)
        self.assertEqual(Pick.objects.count(), 0)

    def test_transaction_failure_restores_original_history(self):
        original = Pick.objects.create(user_name=self.bob, team=self.bills, week=7)
        batch = self.reviewed()
        with patch('survivorPool.league_import_service.Pick.objects.bulk_create', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.apply(batch)
        self.assertTrue(Pick.objects.filter(pk=original.pk).exists())
        batch.refresh_from_db()
        self.assertFalse(batch.backup)
        self.assertEqual(batch.status, LeagueImport.STATUS_REVIEWED)

    def test_duplicate_mapping_missing_classifications_and_money_mismatch_block_review(self):
        batch = self.batch()
        for mapping, choices in (
            ({'0': str(self.alice.pk), '1': str(self.alice.pk)}, self.choices),
            ({'0': '', '1': str(self.bob.pk)}, self.choices),
            (self.mapping, {}),
            (self.mapping, {'0_2': 'standard', '1_1': 'standard'}),
        ):
            self.assertFalse(build_review(batch, mapping, choices)['ready'])

    def test_blank_completed_cells_are_losses_future_blanks_are_not(self):
        source = parse_workbook(workbook_upload([
            [(1, None), (None, None), ('Bills', 'B6D7A8')],
            [(2, None), ('Bills', 'B6D7A8'), ('Dolphins', 'E06666')],
            [(3, None), (None, None), (None, None)],
        ], summaries=False), 2)
        self.assertEqual(len(source['picks']), 4)
        self.assertTrue(source['picks'][0]['missed_deadline'])
        self.assertIs(source['picks'][0]['is_win'], False)
        self.assertFalse(any(pick['week'] == 3 for pick in source['picks']))

    def test_pending_future_pick_is_imported_without_protecting_its_outcome(self):
        source = parse_workbook(workbook_upload([
            [(1, None), ('Bills', 'B6D7A8'), ('Dolphins', 'E06666')],
            [(2, None), ('Dolphins', 'E06666'), ('Bills', 'B6D7A8')],
            [(3, None), ('Bills', None), (None, None)],
        ]), 2)
        batch = self.batch()
        batch.source = source
        batch.save(update_fields=['source'])
        review = build_review(batch, self.mapping, self.choices)
        batch.review = dict(review, review_token='future-token')
        batch.status = LeagueImport.STATUS_REVIEWED
        batch.fingerprint = snapshot_fingerprint(league_snapshot())
        batch.save()
        self.apply(batch)
        pending = Pick.objects.get(user_name=self.alice, week=3)
        self.assertIsNone(pending.is_win)
        self.assertFalse(pending.imported_result)

    def test_bad_colors_unknown_teams_duplicate_weeks_and_future_results_are_rejected(self):
        cases = [
            [[(1, None), ('Bills', None), ('Dolphins', 'E06666')]],
            [[(1, None), ('Unknown FC', 'B6D7A8'), ('Dolphins', 'E06666')]],
            [[(1, None), ('Bills', 'B6D7A8'), ('Dolphins', 'E06666')]] * 2,
            [[(1, None), ('Bills', 'B6D7A8'), ('Dolphins', 'E06666')],
             [(2, None), ('Bills', 'B6D7A8'), ('Dolphins', 'E06666')]],
        ]
        for rows in cases:
            with self.assertRaises(ImportValidationError):
                parse_workbook(workbook_upload(rows, summaries=False), 1)
        with self.assertRaises(ImportValidationError):
            parse_workbook(SimpleUploadedFile('league.csv', b'Week,Alice'), 1)
        with self.assertRaises(ImportValidationError):
            parse_workbook(SimpleUploadedFile('league.xlsx', b'not excel'), 1)

    def test_only_staff_can_upload_review_apply_download_or_adjust(self):
        batch = self.reviewed()
        self.client.force_login(self.alice)
        for name, kwargs in (
            ('league_import_upload', {}),
            ('league_import_review', {'batch_id': batch.pk}),
            ('league_import_backup', {'batch_id': batch.pk}),
            ('league_loss_overrides', {}),
        ):
            response = self.client.get(reverse(name, kwargs=kwargs))
            self.assertEqual(response.status_code, 302)
        response = self.client.post(reverse('league_import_review', kwargs={'batch_id': batch.pk}), {
            'action': 'confirm', 'confirmation': 'REPLACE 2026', 'ack_replace': 'yes',
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Pick.objects.count(), 0)

    def test_wrong_season_is_rejected_without_creating_import(self):
        response = self.client.post(reverse('league_import_upload'), {
            'file': workbook_upload(), 'season_year': 2025, 'completed_week': 2,
        })
        self.assertContains(response, 'Only the configured')
        self.assertFalse(LeagueImport.objects.exists())

    def test_manual_loss_overrides_take_precedence_over_weekly_odds_and_are_audited(self):
        Game.objects.create(
            season_year=2026, week=1, home_team=self.bills, away_team=self.dolphins,
            home_moneyline=-500, away_moneyline=250,
        )
        pick = Pick.objects.create(
            user_name=self.alice, team=self.bills, week=1, is_win=False,
            imported_result=True, favorite_loss_override=False,
        )
        alice_row = next(row for row in build_leaderboard_rows() if row['username'] == 'alice')
        self.assertEqual(alice_row['pot_contribution'], Decimal('60'))
        response = self.client.post(reverse('league_loss_overrides'), {
            'pick_id': pick.pk, 'override': 'favorite', 'reason': 'Historical biggest favorite',
        }, follow=True)
        self.assertContains(response, 'Imported loss')
        pick.refresh_from_db()
        self.assertTrue(pick.favorite_loss_override)
        self.assertEqual(PickLossAdjustment.objects.count(), 1)
        alice_row = next(row for row in build_leaderboard_rows() if row['username'] == 'alice')
        self.assertEqual(alice_row['pot_contribution'], Decimal('75'))
        self.client.post(reverse('league_loss_overrides'), {
            'pick_id': pick.pk, 'override': 'auto', 'reason': 'Disallowed imported auto',
        })
        pick.refresh_from_db()
        self.assertTrue(pick.favorite_loss_override)

    @patch('survivorPool.management.commands.fetch_nfl_winners.get_nfl_weekly_winners')
    def test_results_updates_do_not_overwrite_imported_outcomes(self, winners):
        protected = Pick.objects.create(
            user_name=self.alice, team=self.bills, week=1, is_win=False,
            imported_result=True, favorite_loss_override=False,
        )
        normal = Pick.objects.create(user_name=self.bob, team=self.bills, week=1)
        Game.objects.create(
            season_year=2026, week=1, home_team=self.bills, away_team=self.dolphins,
            game_time=timezone.now() - datetime.timedelta(days=1),
        )
        WeekLockRun.objects.create(season_year=2026, week=1)
        winners.return_value = [{'winner': 'Buffalo Bills', 'loser': 'Miami Dolphins'}]
        call_command('fetch_nfl_winners', week=1)
        protected.refresh_from_db()
        normal.refresh_from_db()
        self.assertFalse(protected.is_win)
        self.assertTrue(normal.is_win)

    def test_force_finalization_preserves_imported_missed_pick_and_override(self):
        no_pick = Team.objects.create(team_name='No Pick')
        protected = Pick.objects.create(
            user_name=self.alice, team=no_pick, week=1, is_win=False,
            missed_deadline=True, imported_result=True, favorite_loss_override=False,
        )
        call_command('lock_week_and_post_chat', week=1, force=True)
        self.assertTrue(Pick.objects.filter(pk=protected.pk, imported_result=True).exists())

    def test_expired_draft_refuses_application(self):
        batch = self.reviewed()
        LeagueImport.objects.filter(pk=batch.pk).update(created_at=timezone.now() - datetime.timedelta(days=2))
        with self.assertRaisesMessage(ImportValidationError, 'expired'):
            self.apply(batch)

    def test_owner_cannot_delete_or_unlock_imported_history(self):
        protected = Pick.objects.create(
            user_name=self.alice, team=self.bills, week=1,
            is_win=True, imported_result=True,
        )
        self.assertTrue(is_pick_locked(protected))
        self.client.force_login(self.alice)
        response = self.client.post(reverse('delete_pick', kwargs={'pk': protected.pk}), follow=True)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(Pick.objects.filter(pk=protected.pk).exists())
