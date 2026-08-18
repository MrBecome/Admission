import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0002_announcement_student_user'),
    ]

    operations = [
        migrations.CreateModel(
            name='FailedEmail',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('subject', models.CharField(max_length=255)),
                ('message', models.TextField()),
                ('recipient_list', models.TextField(help_text='Comma-separated recipient addresses')),
                ('error', models.TextField()),
                ('retry_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('resolved', models.BooleanField(default=False)),
                ('student', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='failed_emails', to='admissions.student')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
    ]
