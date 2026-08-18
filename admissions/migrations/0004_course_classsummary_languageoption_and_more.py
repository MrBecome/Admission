from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0003_failedemail'),
    ]

    operations = [
        migrations.CreateModel(
            name='ClassSummary',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('class_level', models.CharField(max_length=10, unique=True)),
                ('core_subjects', models.TextField(blank=True)),
                ('languages', models.TextField(blank=True)),
                ('enrichment_options', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['class_level'],
                'verbose_name_plural': 'Class summaries',
            },
        ),
        migrations.CreateModel(
            name='Course',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('class_level', models.CharField(max_length=10)),
                ('subject', models.CharField(max_length=100)),
                ('official_name', models.CharField(blank=True, max_length=200)),
                ('category', models.CharField(blank=True, max_length=50)),
                ('coverage', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['class_level', 'subject'],
                'unique_together': {('class_level', 'subject')},
            },
        ),
        migrations.CreateModel(
            name='DataSource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('source', models.CharField(max_length=200, unique=True)),
                ('description', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['source'],
            },
        ),
        migrations.CreateModel(
            name='LanguageOption',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=100, unique=True)),
                ('level_use', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
        migrations.CreateModel(
            name='TuitionProgram',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=150, unique=True)),
                ('target_classes', models.CharField(blank=True, max_length=50)),
                ('program_type', models.CharField(blank=True, max_length=50)),
                ('coverage', models.TextField(blank=True)),
            ],
            options={
                'ordering': ['name'],
            },
        ),
    ]
