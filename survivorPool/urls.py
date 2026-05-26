from django.urls import path

from . import chat_views
from .views import (
    AddPickView,
    DeletePickView,
    HomeView,
    PickDetailView,
    PickView,
    UpdatePickView,
    all_picks_view,
    league_leaderboard_view,
    pot_view,
    rules_view,
)

urlpatterns = [
    path('', HomeView.as_view(), name="home"),
    path('add_pick/', AddPickView.as_view(), name="add_pick"),
    path('pick_details/<int:pk>', PickDetailView.as_view(), name="pick_details"),
    path('pick/edit/<int:pk>', UpdatePickView.as_view(), name="edit_pick"),
    path('pick/delete/<int:pk>', DeletePickView.as_view(), name="delete_pick"),
    path('leaderboard/', PickView.as_view(), name="leaderboard"),
    path('league_leaderboard/', league_leaderboard_view, name="league_leaderboard"),
    path('allPicks/', all_picks_view, name="allPicks"),
    path('chat/', chat_views.chat_view, name="chat"),
    path('chat/poll/', chat_views.chat_poll_api, name="chat_poll"),
    path('chat/send/', chat_views.chat_send_api, name="chat_send"),
    path('rules/', rules_view, name="rules"),
    path('pot/', pot_view, name="pot"),
]
