from typing import Any, Dict
from django.shortcuts import render, redirect
from django.http import HttpResponse
from django.views.generic import ListView, DetailView, CreateView, UpdateView, DeleteView
from django_tables2 import SingleTableView
from .models import Pick, User, Team
from django.urls import reverse_lazy
from .forms import PostForm
from .tables import PickTable
import pandas as pd
import datetime
from django.contrib.auth.models import User

def health_check(request):
    """Lightweight health check endpoint - redirects to home for users"""
    return redirect('/home/')

LEADERBOARD_COLUMNS = [
    'User Name',
    'Team',
    "IsWin",
    "Week"
]


# Create your views here.
#def index(request):
    #return HttpResponse("Hello, world. You're at the Survivor Pool index.")

class HomeView(ListView):
    model = Pick
    template_name = 'home.html'
    ordering = ['week']

class AddPickView(CreateView):
    model = Pick
    form_class = PostForm
    template_name = 'add_pick.html'
    
    def get_form_kwargs(self):
        kwargs = super(AddPickView, self).get_form_kwargs()
        kwargs['user'] = self.request.user
        return kwargs

class PickDetailView(DetailView):
    model = Pick
    template_name = 'pick_details.html'

class UpdatePickView(UpdateView):
    model = Pick
    template_name = 'update_pick.html'
    form_class = None
    
    def get_form_class(self):
        from .forms import UpdatePickForm
        return UpdatePickForm
    
    def get_form_kwargs(self):
        kwargs = super(UpdatePickView, self).get_form_kwargs()
        pick = self.get_object()
        kwargs['user'] = pick.user_name
        kwargs['current_pick'] = pick
        return kwargs
    
    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        pick = self.get_object()
        context['is_locked'] = self.is_week_locked(pick.week)
        return context
    
    def form_valid(self, form):
        pick = self.get_object()
        
        # Check if week is locked
        if self.is_week_locked(pick.week):
            form.add_error(None, f"Week {pick.week} is locked. Picks cannot be changed after Sunday morning EST.")
            return self.form_invalid(form)
        
        return super().form_valid(form)
    
    def is_week_locked(self, week_number):
        """Check if the given week is locked (past Sunday morning EST)"""
        import pytz
        est = pytz.timezone('US/Eastern')
        now = datetime.datetime.now(est)
        
        # Calculate the Sunday of the given week
        season_start = datetime.datetime(2025, 9, 5, tzinfo=est)
        days_to_week = (week_number - 1) * 7
        week_sunday = season_start + datetime.timedelta(days=days_to_week + 2)
        week_sunday = week_sunday.replace(hour=9, minute=0, second=0, microsecond=0)
        
        return now >= week_sunday

class DeletePickView(DeleteView):
    model = Pick
    template_name = 'delete_pick.html'
    fields = ['week']
    success_url = reverse_lazy('home')

class PickView(SingleTableView):
    model = Pick
    table_class = PickTable
    template_name = 'leaderboard.html'

def buildPickDataFrame(max_week=None):
    userMapping = {}
    teamMapping = {}
    pickList = []
    users = list(User.objects.all().values())
    # picks = list(Pick.objects.all().values())
    teams = list(Team.objects.all().values())

    # Fetch picks, optionally filter by max_week
    if max_week is not None:
        picks = list(Pick.objects.filter(week__lte=max_week).values())
    else:
        picks = list(Pick.objects.all().values())

    for user in users:
        id = user.get("id")
        userMapping[id] = user.get('username')
    
    for team in teams:
        id = team.get("id")
        teamMapping[id] = team.get('team_name')

    
    for pick in picks:
        pickUserName = userMapping.get(pick['user_name_id'])
        pickTeam = teamMapping.get(pick['team_id'])
        isWin = pick.get('is_win')
        week = pick.get('week')
        pickList.append((pickUserName, pickTeam, isWin, week) )
    
    df = pd.DataFrame(pickList, columns=LEADERBOARD_COLUMNS)
    return df

def modelToDataFrame(request):
    ''' Builds a dataframe to display the league leaderboard'''
    df = buildPickDataFrame()
    
    # Create leaderboard with correct win counts
    # Convert NULL to False for counting, then count only True wins per user
    df['IsWinBool'] = df['IsWin'].fillna(False)
    win_counts = df[df['IsWinBool'] == True].groupby('User Name')['IsWinBool'].count().reset_index()
    win_counts.columns = ['User Name', 'Win Count']
    
    # Get all unique users (including those with no wins)
    all_users = df[['User Name']].drop_duplicates()
    dfLeaderBoard = all_users.merge(win_counts, on='User Name', how='left')
    dfLeaderBoard['Win Count'] = dfLeaderBoard['Win Count'].fillna(0).astype(int)
    dfLeaderBoard = dfLeaderBoard.sort_values('Win Count', ascending=False)

    print(dfLeaderBoard)

    context = {
        'df': dfLeaderBoard.to_html(classes=["table-bordered", "table-striped", "table-hover"], index=False),
    }

    return render(request, 'league_leaderboard.html', context)

def allPicksView(request):
    '''Builds a dataframe to display all picks up to given week'''

    current_nfl_week = 5
    season_start_date = datetime.datetime(2025, 9, 5).date()
    if datetime.date.today() < season_start_date:
        current_nfl_week = 1
    else:
        current_nfl_week = get_current_nfl_week(season_start_date)

    df = buildPickDataFrame(max_week=current_nfl_week)

    #tweak dataframe to create a view of all picks up to current week sorted by week chronologically
    df = df.sort_values(by=['Week'])
    
    # Create pivot with weeks as rows and usernames as columns
    df['status'] = df['IsWin']  # Keep status for styling reference
    df_display = df.pivot(index='Week', columns='User Name', values='Team')
    df_status = df.pivot(index='Week', columns='User Name', values='status')
    
    df_display = df_display.rename_axis(columns=None).reset_index()
    df_status = df_status.rename_axis(columns=None).reset_index()
    
    df_display = df_display.fillna("")
    df_display = df_display.rename(columns={'Week': 'Week'})
    
    print(df_display)

    # Style function to add background colors based on pick result
    def style_cell(val):
        # Get the row index from the cell position
        row_idx = val.name
        results = []
        
        for col in df_display.columns:
            cell_val = df_display.loc[row_idx, col]
            
            if col == 'Week' or not cell_val or cell_val == "":
                results.append('')
            else:
                # Get the status for this cell
                status = df_status.loc[row_idx, col]
                
                if pd.isna(status):
                    results.append('background-color: #fff3cd; color: #856404;')  # Yellow for TBD
                elif status == True:
                    results.append('background-color: #d4edda; color: #155724;')  # Green for wins
                elif status == False:
                    results.append('background-color: #f8d7da; color: #721c24;')  # Red for losses
                else:
                    results.append('')
        
        return results

    # Apply styling
    styled_df = df_display.style.apply(style_cell, axis=1)

    context = {
        'df': styled_df.to_html(classes=["table-bordered", "table-striped", "table-hover"], index=False),
    }

    return render(request, 'allPicks.html', context)

def get_current_nfl_week(season_start_date):
    today = datetime.datetime.now().date()
    if today < season_start_date:
        return 0  # preseason or offseason
    delta = today - season_start_date
    week = delta.days // 7 + 1
    return min(week, 18)  # limit to 18 weeks
    
    

        

