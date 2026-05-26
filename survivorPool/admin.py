from django.contrib import admin

from .models import ChatMessage, Game, Pick, SeasonSettings, Team, WeekLockRun

admin.site.register(Team)
admin.site.register(Pick)
admin.site.register(Game)
admin.site.register(ChatMessage)
admin.site.register(WeekLockRun)
admin.site.register(SeasonSettings)
