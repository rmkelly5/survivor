from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from django.urls import reverse

class Team(models.Model):
    team_name = models.CharField(max_length=50)
    is_favorite = models.BooleanField(default=False)
    
    opponent = models.CharField(max_length=50, null=True, blank=True)
    game_time = models.DateTimeField(null=True, blank=True)
    spread = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    moneyline = models.IntegerField(null=True, blank=True)
    is_home = models.BooleanField(null=True, blank=True)
    current_week = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return str(self.team_name)


class Game(models.Model):
    season_year = models.IntegerField()
    week = models.IntegerField()
    home_team = models.ForeignKey(
        Team,
        related_name='home_games',
        on_delete=models.CASCADE,
    )
    away_team = models.ForeignKey(
        Team,
        related_name='away_games',
        on_delete=models.CASCADE,
    )
    game_time = models.DateTimeField(null=True, blank=True)
    home_spread = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    away_spread = models.DecimalField(max_digits=5, decimal_places=1, null=True, blank=True)
    home_moneyline = models.IntegerField(null=True, blank=True)
    away_moneyline = models.IntegerField(null=True, blank=True)
    home_is_favorite = models.BooleanField(default=False)
    away_is_favorite = models.BooleanField(default=False)

    class Meta:
        unique_together = ('season_year', 'week', 'home_team', 'away_team')
        ordering = ['season_year', 'week', 'game_time']

    def __str__(self):
        return f"{self.away_team} @ {self.home_team} | {self.season_year} Week {self.week}"


class Pick(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    user_name = models.ForeignKey(User, on_delete=models.CASCADE)
    publication_date = models.DateTimeField("date published", default=timezone.now)
    week = models.IntegerField()
    is_win = models.BooleanField(null=True, blank=True, default=None)
    missed_deadline = models.BooleanField(
        default=False,
        help_text="Auto-assigned loss when no pick by Sunday 1:05 PM ET.",
    )

    class Meta:
        unique_together = ('user_name', 'week')

    def __str__(self):
        return str(self.team) + ' | ' + str(self.user_name)

    def get_absolute_url(self):
        return reverse('home')


class ChatMessage(models.Model):
    MESSAGE_USER = 'user'
    MESSAGE_WEEKLY_LOCK = 'weekly_lock_summary'
    MESSAGE_TYPES = [
        (MESSAGE_USER, 'User'),
        (MESSAGE_WEEKLY_LOCK, 'Weekly lock summary'),
    ]

    author = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='chat_messages',
    )
    body = models.TextField()
    message_type = models.CharField(
        max_length=32,
        choices=MESSAGE_TYPES,
        default=MESSAGE_USER,
    )
    week = models.IntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at', 'id']

    def __str__(self):
        if self.message_type == self.MESSAGE_WEEKLY_LOCK:
            return f"Week {self.week} lock summary"
        return f"{self.author}: {self.body[:40]}"


class WeekLockRun(models.Model):
    season_year = models.IntegerField()
    week = models.IntegerField()
    ran_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('season_year', 'week')

    def __str__(self):
        return f"{self.season_year} Week {self.week} locked at {self.ran_at}"


class SeasonSettings(models.Model):
    season_year = models.IntegerField(unique=True)
    buy_in = models.DecimalField(max_digits=8, decimal_places=2, default=50)
    loss_amount = models.DecimalField(max_digits=8, decimal_places=2, default=10)
    favorite_loss_amount = models.DecimalField(max_digits=8, decimal_places=2, default=25)
    underdog_half_threshold = models.DecimalField(max_digits=4, decimal_places=2, default=5)

    def __str__(self):
        return f"Season {self.season_year} settings"

