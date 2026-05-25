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

class Pick(models.Model):
    team = models.ForeignKey(Team, on_delete=models.CASCADE)
    user_name = models.ForeignKey(User, on_delete=models.CASCADE)
    publication_date = models.DateTimeField("date published", default=timezone.now)
    week = models.IntegerField()
    is_win = models.BooleanField(null=True, blank=True, default=None)

    class Meta:
        unique_together = ('user_name', 'week')

    def __str__(self):
        return str(self.team) + ' | ' + str(self.user_name)
    
    def get_absolute_url(self):
        return reverse('home') 
    
    
