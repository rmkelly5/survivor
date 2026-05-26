import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.core.management.base import BaseCommand
from django.utils import timezone

from survivorPool.models import ChatMessage, Game, Pick, SeasonSettings, Team, WeekLockRun


class Command(BaseCommand):
    help = "Seed deterministic local data for Playwright browser smoke tests."

    def handle(self, *args, **options):
        demo_usernames = [
            'browser_user',
            'rival_player',
            'admin_user',
            'alex_b',
            'casey_q',
            'drew_m',
            'jamie_r',
            'jordan_p',
            'morgan_l',
            'quinn_s',
            'sam_t',
            'taylor_w',
            'avery_k',
            'riley_c',
        ]

        WeekLockRun.objects.all().delete()
        ChatMessage.objects.all().delete()
        Pick.objects.all().delete()
        Game.objects.all().delete()
        Team.objects.all().delete()
        User.objects.filter(username__in=demo_usernames).delete()

        browser_user = User.objects.create_user(
            username='browser_user',
            password='Test4321!',
            email='browser@example.com',
        )
        rival = User.objects.create_user(
            username='rival_player',
            password='Test4321!',
            email='rival@example.com',
        )
        User.objects.create_superuser(
            username='admin_user',
            password='Test4321!',
            email='admin@example.com',
        )
        demo_users = [
            browser_user,
            rival,
            User.objects.create_user(username='alex_b', password='Test4321!', email='alex@example.com'),
            User.objects.create_user(username='casey_q', password='Test4321!', email='casey@example.com'),
            User.objects.create_user(username='drew_m', password='Test4321!', email='drew@example.com'),
            User.objects.create_user(username='jamie_r', password='Test4321!', email='jamie@example.com'),
            User.objects.create_user(username='jordan_p', password='Test4321!', email='jordan@example.com'),
            User.objects.create_user(username='morgan_l', password='Test4321!', email='morgan@example.com'),
            User.objects.create_user(username='quinn_s', password='Test4321!', email='quinn@example.com'),
            User.objects.create_user(username='sam_t', password='Test4321!', email='sam@example.com'),
            User.objects.create_user(username='taylor_w', password='Test4321!', email='taylor@example.com'),
            User.objects.create_user(username='avery_k', password='Test4321!', email='avery@example.com'),
            User.objects.create_user(username='riley_c', password='Test4321!', email='riley@example.com'),
        ]

        teams = {
            name: Team.objects.create(team_name=name)
            for name in [
                'Bills',
                'Dolphins',
                'Packers',
                'Bears',
                'Chiefs',
                'Raiders',
                'Patriots',
                'Jets',
                'Ravens',
                'Bengals',
                'Cowboys',
                'Eagles',
                'Lions',
                'Vikings',
                '49ers',
                'Seahawks',
                'Texans',
                'Colts',
                'No Pick',
            ]
        }

        SeasonSettings.objects.update_or_create(
            season_year=settings.NFL_SEASON_YEAR,
            defaults={
                'buy_in': Decimal('50.00'),
                'loss_amount': Decimal('10.00'),
                'favorite_loss_amount': Decimal('25.00'),
                'underdog_half_threshold': Decimal('5.00'),
            },
        )

        base = timezone.make_aware(
            datetime.datetime(settings.NFL_SEASON_YEAR, 9, 13, 13, 0),
            timezone.get_current_timezone(),
        )
        games = [
            (1, 'Bills', 'Dolphins', 0, True),
            (1, 'Packers', 'Bears', 0, False),
            (1, 'Ravens', 'Bengals', 1, True),
            (2, 'Chiefs', 'Raiders', 7, True),
            (2, 'Jets', 'Patriots', 7, False),
            (2, 'Cowboys', 'Eagles', 8, False),
            (3, 'Lions', 'Vikings', 14, True),
            (3, '49ers', 'Seahawks', 14, True),
            (4, 'Texans', 'Colts', 21, False),
            (4, 'Bills', 'Patriots', 21, True),
            (5, 'Eagles', 'Cowboys', 28, True),
            (5, 'Bengals', 'Ravens', 28, False),
            (6, 'Vikings', 'Lions', 35, False),
            (6, 'Seahawks', '49ers', 35, False),
            (7, 'Patriots', 'Bills', 42, True),
            (7, 'Bears', 'Packers', 42, False),
            (7, 'Chiefs', 'Jets', 43, True),
        ]
        for week, home, away, days_offset, home_favorite in games:
            Game.objects.create(
                season_year=settings.NFL_SEASON_YEAR,
                week=week,
                home_team=teams[home],
                away_team=teams[away],
                game_time=base + datetime.timedelta(days=days_offset),
                home_spread=Decimal('3.5') if home_favorite else None,
                away_spread=None if home_favorite else Decimal('2.5'),
                home_moneyline=-150 if home_favorite else 120,
                away_moneyline=130 if home_favorite else -135,
                home_is_favorite=home_favorite,
                away_is_favorite=not home_favorite,
            )

        pick_plan = {
            'browser_user': [('Dolphins', False), ('Chiefs', True), ('Lions', True), ('Texans', False), ('Eagles', True), ('Vikings', True), ('Bills', None)],
            'rival_player': [('Bills', True), ('Packers', True), ('49ers', False), ('Patriots', True), ('Ravens', False), ('Seahawks', True), ('Bears', None)],
            'alex_b': [('Ravens', True), ('Cowboys', False), ('Vikings', True), ('Bills', True), ('Bengals', True), ('49ers', None)],
            'casey_q': [('Packers', True), ('Jets', False), ('Lions', True), ('Colts', False), ('Cowboys', True), ('No Pick', False), ('Patriots', None)],
            'drew_m': [('Bengals', False), ('Raiders', True), ('Seahawks', True), ('Texans', True), ('Eagles', False), ('Lions', None)],
            'jamie_r': [('Bears', False), ('Chiefs', True), ('49ers', True), ('Patriots', False), ('Ravens', True), ('Vikings', None)],
            'jordan_p': [('Bills', True), ('Eagles', True), ('Lions', False), ('Colts', True), ('Bengals', None)],
            'morgan_l': [('Dolphins', False), ('Patriots', True), ('Vikings', True), ('Texans', True), ('Cowboys', False), ('49ers', None)],
            'quinn_s': [('Ravens', True), ('Jets', False), ('Seahawks', False), ('Bills', True), ('Eagles', True), ('No Pick', False)],
            'sam_t': [('Packers', True), ('Chiefs', True), ('Lions', True), ('Patriots', True), ('Bengals', False), ('Vikings', None)],
            'taylor_w': [('Bears', False), ('Cowboys', False), ('49ers', True), ('Texans', True), ('Ravens', True)],
            'avery_k': [('Bills', True), ('Raiders', False), ('Vikings', True), ('Colts', False), ('Eagles', None)],
            'riley_c': [('Dolphins', False), ('Packers', True), ('Seahawks', True), ('Patriots', True), ('Cowboys', False), ('Lions', None)],
        }
        users_by_name = {user.username: user for user in demo_users}
        for username, picks in pick_plan.items():
            for week, (team_name, result) in enumerate(picks, start=1):
                Pick.objects.create(
                    user_name=users_by_name[username],
                    team=teams[team_name],
                    week=week,
                    is_win=result,
                    missed_deadline=team_name == 'No Pick',
                )

        chat_lines = [
            ('alex_b', 'Bills looked way too obvious but I took them anyway.'),
            ('casey_q', 'Putting this in writing so I cannot deny it later: Week 2 scares me.'),
            ('browser_user', 'If the Packers lose I am blaming the group chat.'),
            ('rival_player', 'Respectfully, this is already chaos.'),
            ('jamie_r', 'Sunday reminder: do not wait until kickoff to remember this exists.'),
            ('sam_t', 'My spreadsheet says Chiefs. My gut says pain.'),
            ('morgan_l', 'Pot is getting spicy for September.'),
            ('quinn_s', 'Can we get a shame corner trophy?'),
            ('taylor_w', 'I have changed my pick four times and learned nothing.'),
            ('avery_k', 'Week 7 board is nasty.'),
            ('riley_c', 'No pick should absolutely count as a public roast.'),
            ('drew_m', 'The bot posting everyone at lock is elite.'),
        ]
        for i in range(188):
            author_name, body = chat_lines[i % len(chat_lines)]
            ChatMessage.objects.create(
                author=users_by_name[author_name],
                body=body,
            )

        ChatMessage.objects.create(
            author=None,
            body='Week 5 locked. Shame corner: casey_q and quinn_s missed the deadline.',
            message_type=ChatMessage.MESSAGE_WEEKLY_LOCK,
            week=5,
        )
        ChatMessage.objects.create(
            author=None,
            body='Week 7 preview posted. Three players are still TBD and the pot is already moving.',
            message_type=ChatMessage.MESSAGE_WEEKLY_LOCK,
            week=7,
        )

        self.stdout.write(self.style.SUCCESS('Seeded browser smoke data.'))
