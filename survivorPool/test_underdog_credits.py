from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.urls import reverse

from .models import Game, Pick, Team
from .utils import build_leaderboard_rows, loss_credit_summary


class CreditBankTests(SimpleTestCase):
    def test_unused_credits_are_banked_without_negative_losses(self):
        record = loss_credit_summary(0, 3)
        self.assertEqual(record['loss_count'], 0)
        self.assertEqual(record['loss_credit_total'], Decimal('1.5'))
        self.assertEqual(record['banked_loss_credits'], Decimal('1.5'))

    def test_future_losses_consume_the_bank(self):
        self.assertEqual(loss_credit_summary(1, 3)['banked_loss_credits'], Decimal('0.5'))
        self.assertEqual(loss_credit_summary(1, 3)['loss_count'], 0)
        self.assertEqual(loss_credit_summary(2, 3)['banked_loss_credits'], 0)
        self.assertEqual(loss_credit_summary(2, 3)['loss_count'], Decimal('0.5'))


class UnderdogCreditTests(TestCase):
    def setUp(self):
        self.player = User.objects.create_user(username='player')
        self.favorite = Team.objects.create(team_name='Bills')
        self.underdog = Team.objects.create(team_name='Dolphins')

    def game(self, week, spread=5, home_underdog=False, year=None):
        return Game.objects.create(
            season_year=year or settings.NFL_SEASON_YEAR,
            week=week,
            home_team=self.underdog if home_underdog else self.favorite,
            away_team=self.favorite if home_underdog else self.underdog,
            home_spread=None if home_underdog else spread,
            away_spread=spread if home_underdog else None,
            home_is_favorite=not home_underdog,
            away_is_favorite=home_underdog,
        )

    def pick(self, week, is_win=True, team=None, user=None, **kwargs):
        return Pick.objects.create(
            user_name=user or self.player, team=team or self.underdog,
            week=week, is_win=is_win, **kwargs,
        )

    def row(self, user=None):
        return next(
            row for row in build_leaderboard_rows()
            if row['username'] == (user or self.player).username
        )

    def test_exactly_five_point_underdog_win_earns_credit_and_normal_win(self):
        self.game(1, 5)
        self.pick(1)
        self.pick(2, is_win=False)
        row = self.row()
        self.assertEqual(row['win_count'], 1)
        self.assertEqual(row['actual_loss_count'], 1)
        self.assertEqual(row['loss_count'], Decimal('0.5'))
        self.assertEqual(row['loss_credit_count'], 1)
        self.assertEqual(row['pot_contribution'], 60)

    def test_home_underdog_qualifies_with_signed_opponent_spread(self):
        self.game(1, Decimal('-5.5'), home_underdog=True)
        self.pick(1)
        self.assertEqual(self.row()['loss_credit_total'], Decimal('0.5'))

    def test_smaller_spread_favorite_pending_and_losing_picks_do_not_earn_credits(self):
        self.game(1, Decimal('4.5'))
        self.pick(1)
        self.game(2, 7)
        self.pick(2, team=self.favorite)
        self.game(3, 8)
        self.pick(3, is_win=None)
        self.game(4, 10)
        self.pick(4, is_win=False)
        row = self.row()
        self.assertEqual(row['win_count'], 2)
        self.assertEqual(row['loss_credit_count'], 0)
        self.assertEqual(row['loss_count'], 1)
        self.assertEqual(row['pot_contribution'], 60)

    def test_missing_spread_or_other_season_does_not_infer_credit_from_moneyline(self):
        game = self.game(1, None)
        game.away_moneyline = 500
        game.save()
        self.pick(1)
        self.game(2, 9, year=settings.NFL_SEASON_YEAR - 1)
        self.pick(2)
        self.pick(3)  # No stored matchup or spread.
        self.assertEqual(self.row()['loss_credit_count'], 0)

    def test_banked_credits_offset_later_losses_but_never_refund_fees(self):
        for week in (1, 2):
            self.game(week, 6)
            self.pick(week)
        row = self.row()
        self.assertEqual(row['loss_count'], 0)
        self.assertEqual(row['banked_loss_credits'], 1)
        self.assertEqual(row['pot_contribution'], 50)

        self.pick(3, is_win=False, missed_deadline=True)
        row = self.row()
        self.assertEqual(row['loss_count'], 0)
        self.assertEqual(row['banked_loss_credits'], 0)
        self.assertEqual(row['pot_contribution'], 60)

        self.pick(4, is_win=False)
        row = self.row()
        self.assertEqual(row['loss_count'], 1)
        self.assertEqual(row['pot_contribution'], 70)

    def test_credits_are_unlimited_and_repeated_reads_do_not_duplicate_them(self):
        for week in range(1, 6):
            self.game(week, 5)
            self.pick(week)
        for week in range(6, 9):
            self.pick(week, is_win=False)
        first = self.row()
        self.assertEqual(first['loss_credit_count'], 5)
        self.assertEqual(first['loss_count'], Decimal('0.5'))
        self.assertEqual(first['pot_contribution'], 80)
        self.assertEqual(self.row(), first)
        self.assertEqual(Pick.objects.filter(is_win=False).count(), 3)

    def test_favorite_loss_fee_and_imported_outcomes_are_preserved(self):
        self.game(1, 5)
        self.pick(1, imported_result=True)
        self.pick(2, is_win=False, favorite_loss_override=True, imported_result=True)
        row = self.row()
        self.assertEqual(row['loss_count'], Decimal('0.5'))
        self.assertEqual(row['favorite_loss_count'], 1)
        self.assertEqual(row['pot_contribution'], 75)
        self.assertTrue(Pick.objects.get(week=1).is_win)

    def test_adjusted_record_is_used_before_contribution_tiebreak(self):
        other = User.objects.create_user(username='alpha')
        self.game(1, 5)
        self.pick(1)
        self.pick(1, user=other, team=self.favorite)
        self.pick(2, is_win=False)
        self.pick(2, is_win=False, user=other)
        rows = build_leaderboard_rows()
        self.assertEqual([row['username'] for row in rows], ['player', 'alpha'])
        self.assertEqual(rows[0]['loss_count'], Decimal('0.5'))
        self.assertEqual(rows[1]['loss_count'], 1)
        self.assertEqual(rows[0]['pot_contribution'], rows[1]['pot_contribution'])

    def test_corrected_result_removes_credit_without_changing_raw_loss_fees(self):
        self.game(1, 5)
        pick = self.pick(1)
        self.assertEqual(self.row()['loss_credit_count'], 1)
        pick.is_win = False
        pick.save(update_fields=['is_win'])
        row = self.row()
        self.assertEqual(row['loss_credit_count'], 0)
        self.assertEqual(row['win_count'], 0)
        self.assertEqual(row['loss_count'], 1)
        self.assertEqual(row['pot_contribution'], 60)

    def test_home_leaderboard_and_league_picks_show_adjusted_losses(self):
        self.game(1, 5)
        self.pick(1)
        self.pick(2, is_win=False)
        self.client.force_login(self.player)
        home = self.client.get('/')
        self.assertEqual(home.status_code, 200)
        self.assertEqual(home.context['wins'], 1)
        self.assertEqual(home.context['losses'], Decimal('0.5'))
        self.assertContains(home, 'Loss credits earned: 0.5')
        leaderboard = self.client.get('/league_leaderboard/')
        self.assertEqual(leaderboard.status_code, 200)
        self.assertContains(leaderboard, '1-0.5')
        self.assertEqual(leaderboard.context['total_pot'], 60)
        board = self.client.get(reverse('allPicks'))
        self.assertEqual(board.status_code, 200)
        self.assertContains(board, 'Adjusted losses')
        self.assertEqual(board.context['grid_summary'][0]['losses'], Decimal('0.5'))

    def test_home_and_leaderboard_show_the_credit_bank(self):
        self.game(1, 5)
        self.pick(1)
        self.client.force_login(self.player)
        home = self.client.get('/')
        self.assertEqual(home.context['banked_loss_credits'], Decimal('0.5'))
        self.assertContains(home, 'Banked credits: 0.5')
        leaderboard = self.client.get('/league_leaderboard/')
        self.assertContains(leaderboard, 'Banked: 0.5')
