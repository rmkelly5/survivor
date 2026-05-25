from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.db import transaction

from survivorPool.models import ChatMessage, Pick, Team, WeekLockRun
from survivorPool.utils import (
    build_picks_grid,
    get_current_nfl_week,
    get_league_member_usernames,
    is_week_locked,
)


class Command(BaseCommand):
    help = (
        'Lock a week at Sunday 1:05 PM ET: auto-loss for missing picks, '
        'then post the weekly summary to league chat.'
    )

    def add_arguments(self, parser):
        parser.add_argument('--week', type=int, help='NFL week number (default: current week)')
        parser.add_argument(
            '--force',
            action='store_true',
            help='Run even if week is not locked yet or already ran',
        )

    def handle(self, *args, **options):
        week = options['week'] or get_current_nfl_week()
        season_year = settings.NFL_SEASON_YEAR
        force = options['force']

        if not force and not is_week_locked(week):
            self.stderr.write(
                self.style.WARNING(
                    f'Week {week} is not locked yet (Sunday 1:05 PM ET). Use --force to override.'
                )
            )
            return

        if WeekLockRun.objects.filter(season_year=season_year, week=week).exists() and not force:
            self.stderr.write(
                self.style.WARNING(f'Week {week} already locked for {season_year}. Use --force to re-run.')
            )
            return

        no_pick_team, _ = Team.objects.get_or_create(team_name='No Pick')

        with transaction.atomic():
            league_usernames = get_league_member_usernames()

            if force:
                WeekLockRun.objects.filter(season_year=season_year, week=week).delete()
                ChatMessage.objects.filter(
                    message_type=ChatMessage.MESSAGE_WEEKLY_LOCK,
                    week=week,
                ).delete()
                Pick.objects.filter(week=week, missed_deadline=True).delete()

            missed_users = []
            league_users = User.objects.filter(
                username__in=league_usernames,
                is_active=True,
                is_staff=False,
                is_superuser=False,
            )
            for user in league_users:
                if Pick.objects.filter(user_name=user, week=week).exists():
                    continue
                Pick.objects.create(
                    user_name=user,
                    team=no_pick_team,
                    week=week,
                    is_win=False,
                    missed_deadline=True,
                )
                missed_users.append(user.username)

            WeekLockRun.objects.create(season_year=season_year, week=week)
            ChatMessage.objects.filter(
                message_type=ChatMessage.MESSAGE_WEEKLY_LOCK,
                week=week,
            ).delete()
            body = self._build_summary_message(week, missed_users)
            ChatMessage.objects.create(
                author=None,
                body=body,
                message_type=ChatMessage.MESSAGE_WEEKLY_LOCK,
                week=week,
            )

        self.stdout.write(self.style.SUCCESS(
            f'Week {week} locked. {len(missed_users)} missed pick(s). Chat summary posted.'
        ))

    def _build_summary_message(self, week: int, missed_usernames: list[str]) -> str:
        grid = build_picks_grid(max_week=week)
        lines = [f'Week {week} picks - LOCKED 1:05 PM ET', '']

        for player in grid['players']:
            cell = grid['pick_lookup'].get((week, player), {})
            team = cell.get('team') or ''
            if team:
                suffix = ' (NO PICK - auto LOSS)' if cell.get('missed_deadline') else ''
                lines.append(f'{player} - {team}{suffix}')
            elif player in missed_usernames:
                lines.append(f'{player} - NO PICK (auto LOSS)')

        if missed_usernames:
            lines.extend(['', 'NO PICK (auto LOSS):'])
            for name in missed_usernames:
                lines.append(f'  - {name}')
            lines.extend([
                '',
                f"Shame corner: {', '.join(missed_usernames)} didn't get it in on time.",
            ])
        else:
            lines.extend(['', 'Everyone got their picks in on time.'])

        return '\n'.join(lines)
