import django.db.models.deletion
from django.db import migrations, models


def seed_legacy_courses_and_link_students(apps, schema_editor):
    """
    For every distinct string currently stored in Student.course (e.g. 'math',
    'science', 'english'), create a matching dummy Course row (class_level='LEGACY')
    and point that student's new course_new FK at it. This is what lets the
    following AlterField happen without an IntegrityError - every existing row
    already has a valid target by the time the FK is enforced.
    """
    Student = apps.get_model('admissions', 'Student')
    Course = apps.get_model('admissions', 'Course')

    distinct_values = Student.objects.values_list('course', flat=True).distinct()
    mapping = {}
    for value in distinct_values:
        if not value:
            continue
        course, _ = Course.objects.get_or_create(
            class_level='LEGACY',
            subject=value,
            defaults={
                'official_name': value.title(),
                'category': 'Legacy',
                'coverage': 'Imported automatically from a pre-upgrade application record.',
            },
        )
        mapping[value] = course.id

    for student in Student.objects.all():
        course_id = mapping.get(student.course)
        if course_id:
            student.course_new_id = course_id
            student.save(update_fields=['course_new'])


def noop_reverse(apps, schema_editor):
    # Not meaningfully reversible - the original string values aren't restored.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ('admissions', '0004_course_classsummary_languageoption_and_more'),
    ]

    operations = [
        # Step A: add a temporary FK column alongside the old CharField.
        migrations.AddField(
            model_name='student',
            name='course_new',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='legacy_students_tmp',
                to='admissions.course',
            ),
        ),
        # Step B: seed one dummy Course per legacy string value, then link every
        # existing student to it via the temporary FK column.
        migrations.RunPython(seed_legacy_courses_and_link_students, noop_reverse),
        # Step C: drop the old CharField now that every student has a valid FK target.
        migrations.RemoveField(
            model_name='student',
            name='course',
        ),
        # Step D: rename the temporary FK into the field's real name.
        migrations.RenameField(
            model_name='student',
            old_name='course_new',
            new_name='course',
        ),
        # Step E: fix the FK's related_name/options to match the final model state.
        migrations.AlterField(
            model_name='student',
            name='course',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name='students',
                to='admissions.course',
            ),
        ),
    ]
