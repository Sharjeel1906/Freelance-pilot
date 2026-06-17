# Generated migration for scheduled_call_at field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('ai_agents', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='jobmatchresult',
            name='scheduled_call_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
