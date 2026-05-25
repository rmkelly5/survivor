from django import forms
from .models import Pick, Team
from datetime import datetime, timedelta
import pytz

CHOICES = ((1, 1), (2, 2), (3, 3), (4, 4), (5, 5), (6, 6), (7, 7), (8, 8),
           (9, 9), (10, 10), (11, 11), (12, 12), (13, 13), (14, 14), (15, 15),
           (16, 16), (17, 17), (18, 18))


class PostForm(forms.ModelForm):
    week = forms.ChoiceField(choices=CHOICES)

    class Meta:
        model = Pick
        fields = (
            "team",
            "week",
            "user_name",
        )

        widgets = {
            "team":
            forms.Select(attrs={"class": "form-control"}),
            "user_name":
            forms.TextInput(
                attrs={
                    "class": "form-control",
                    "value": "",
                    "id": "user",
                    "type": "hidden"
                }),
            "week":
            forms.Select(choices=CHOICES, attrs={"class": "form-control"})
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.week_number = kwargs.pop('week_number', None)
        super(PostForm, self).__init__(*args, **kwargs)

        if self.user and self.user.is_authenticated:
            self.fields['user_name'].required = False
            self.fields['user_name'].initial = self.user.id

        selected_week = self.week_number
        if selected_week is None:
            if self.is_bound:
                selected_week = self.data.get(self.add_prefix('week'))
            else:
                selected_week = self.initial.get('week')

        try:
            selected_week = int(selected_week)
        except (TypeError, ValueError):
            selected_week = None

        available_teams = Team.objects.all()
        if selected_week is not None:
            available_teams = available_teams.filter(current_week=selected_week)

        # Filter out teams that this user has already picked this season
        if self.user and self.user.is_authenticated:
            used_team_ids = Pick.objects.filter(
                user_name=self.user).values_list('team_id', flat=True)
            available_teams = available_teams.exclude(id__in=used_team_ids)
            self.fields['team'].queryset = available_teams
        else:
            self.fields['team'].queryset = available_teams
        
        # Customize team display to show matchup and odds (always show even if not logged in)
        self.fields['team'].label_from_instance = self.team_label

    def team_label(self, team):
        """Custom label showing team with matchup and betting odds"""
        if not team.opponent:
            return str(team.team_name)
        
        # Build the label with matchup info
        label_parts = []
        
        # Team name with favorite indicator
        team_name = str(team.team_name)
        if team.is_favorite:
            team_name = f"⭐ {team_name}"
        
        # Add opponent
        location = "vs" if team.is_home else "@"
        label_parts.append(f"{team_name} ({location} {team.opponent}")
        
        # Add spread if available
        if team.spread and team.is_favorite:
            label_parts.append(f"-{team.spread}")
        
        # Add moneyline if available
        if team.moneyline:
            if team.moneyline > 0:
                label_parts.append(f"+{team.moneyline}")
            else:
                label_parts.append(f"{team.moneyline}")
        
        label_parts.append(")")
        
        # Add game time if available (stored in EST)
        if team.game_time:
            game_time_str = team.game_time.strftime("%a %I:%M %p EST")
            label_parts.append(f"- {game_time_str}")
        
        return " ".join(label_parts)

    def clean(self):
        cleaned_data = super().clean()
        team = cleaned_data.get('team')
        week = cleaned_data.get('week')
        user_name = self.user if self.user and self.user.is_authenticated else cleaned_data.get('user_name')

        # Check if user already picked this team in a previous week
        if team and user_name:
            previous_pick = Pick.objects.filter(user_name=user_name,
                                                team=team).first()
            if previous_pick:
                raise forms.ValidationError(
                    f"You already picked {team.team_name} in Week {previous_pick.week}. You cannot pick the same team twice in a season."
                )

        # Check if week is locked (Sunday morning or later)
        if week:
            week_num = int(week)
            if self.is_week_locked(week_num):
                raise forms.ValidationError(
                    f"Week {week_num} is locked. Picks cannot be made or changed after Sunday morning EST."
                )

            if team and team.current_week != week_num:
                raise forms.ValidationError(
                    f"{team.team_name} is not available for Week {week_num}. Please choose a team from the displayed matchups."
                )

        return cleaned_data

    def is_week_locked(self, week_number):
        """Check if the given week is locked (past Sunday morning EST)"""
        est = pytz.timezone('US/Eastern')
        now = datetime.now(est)

        # Calculate the Sunday of the given week
        # Assuming NFL season starts Week 1 on Sept 5, 2025
        season_start = datetime(2025, 9, 5, tzinfo=est)  # Friday before Week 1
        days_to_week = (week_number - 1) * 7
        # Sunday of the given week (Week 1 Sunday is Sept 7)
        week_sunday = season_start + timedelta(days=days_to_week + 2)
        week_sunday = week_sunday.replace(hour=9,
                                          minute=0,
                                          second=0,
                                          microsecond=0)  # 9 AM EST Sunday

        return now >= week_sunday


class UpdatePickForm(forms.ModelForm):

    class Meta:
        model = Pick
        fields = ("team", )
        widgets = {
            "team": forms.Select(attrs={"class": "form-control"}),
        }

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.current_pick = kwargs.pop('current_pick', None)
        super(UpdatePickForm, self).__init__(*args, **kwargs)

        # Filter out teams that this user has already picked (except the current one)
        if self.user and self.current_pick:
            used_team_ids = Pick.objects.filter(user_name=self.user).exclude(
                id=self.current_pick.id).values_list('team_id', flat=True)
            available_teams = Team.objects.exclude(id__in=used_team_ids)
            self.fields['team'].queryset = available_teams
