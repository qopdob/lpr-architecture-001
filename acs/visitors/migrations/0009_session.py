# Generated by Django 4.2.3 on 2024-08-09 03:28

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('visitors', '0008_event_visitor'),
    ]

    operations = [
        migrations.CreateModel(
            name='Session',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('in_event_type', models.CharField(blank=True, max_length=20, null=True, verbose_name='in event type')),
                ('out_event_type', models.CharField(blank=True, max_length=20, null=True, verbose_name='out event type')),
                ('in_event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='session_in', to='visitors.event', verbose_name='in event')),
                ('out_event', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='session_out', to='visitors.event', verbose_name='out event')),
            ],
        ),
    ]