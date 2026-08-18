from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Student',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('full_name', models.CharField(max_length=100)),
                ('email', models.EmailField(max_length=254, unique=True)),
                ('phone', models.CharField(max_length=15)),
                ('course', models.CharField(choices=[('math', 'Mathematics'), ('science', 'Science'), ('english', 'English')], max_length=20)),
                ('address', models.TextField()),
                ('admission_date', models.DateTimeField(auto_now_add=True)),
                ('payment_status', models.BooleanField(default=False)),
                ('amount_paid', models.DecimalField(decimal_places=2, default=0.0, max_digits=8)),
                ('payment_verification', models.CharField(choices=[('pending', 'Pending'), ('verified', 'Verified'), ('rejected', 'Rejected')], default='pending', max_length=10)),
                ('transaction_id', models.CharField(blank=True, max_length=50, null=True)),
                ('payment_date', models.DateTimeField(blank=True, null=True)),
                ('qr_code_path', models.CharField(blank=True, max_length=255, null=True)),
            ],
        ),
    ]
