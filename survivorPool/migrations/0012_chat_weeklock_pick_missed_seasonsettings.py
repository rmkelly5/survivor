# Generated manually for chat, week lock, and season settings

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('survivorPool', '0011_game'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name='pick',
            name='missed_deadline',
            field=models.BooleanField(
                default=False,
                help_text='Auto-assigned loss when no pick by Sunday 1:05 PM ET.',
            ),
        ),
        migrations.CreateModel(
            name='SeasonSettings',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season_year', models.IntegerField(unique=True)),
                ('buy_in', models.DecimalField(decimal_places=2, default=50, max_digits=8)),
                ('loss_amount', models.DecimalField(decimal_places=2, default=10, max_digits=8)),
                ('favorite_loss_amount', models.DecimalField(decimal_places=2, default=25, max_digits=8)),
                ('underdog_half_threshold', models.DecimalField(decimal_places=2, default=5, max_digits=4)),
            ],
        ),
        migrations.CreateModel(
            name='WeekLockRun',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('season_year', models.IntegerField()),
                ('week', models.IntegerField()),
                ('ran_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'unique_together': {('season_year', 'week')},
            },
        ),
        migrations.CreateModel(
            name='ChatMessage',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('body', models.TextField()),
                ('message_type', models.CharField(
                    choices=[('user', 'User'), ('weekly_lock_summary', 'Weekly lock summary')],
                    default='user',
                    max_length=32,
                )),
                ('week', models.IntegerField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('author', models.ForeignKey(
                    blank=True,
                    null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='chat_messages',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={
                'ordering': ['created_at'],
            },
        ),
    ]
