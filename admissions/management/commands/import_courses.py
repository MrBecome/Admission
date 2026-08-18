import os
import pandas as pd
from django.conf import settings
from django.core.management.base import BaseCommand
from admissions.models import Course, ClassSummary, LanguageOption, TuitionProgram, DataSource

class Command(BaseCommand):
    help = 'Import ALL data from the multiple sheets of courses.xlsx'

    def handle(self, *args, **kwargs):
        # CRITICAL: source spreadsheet lives in PRIVATE_DATA_ROOT, never under
        # STATICFILES_DIRS/MEDIA_ROOT - those are served over HTTP, and this
        # file may contain unpublished curriculum/pricing data.
        file_path = os.path.join(settings.PRIVATE_DATA_ROOT, 'courses.xlsx')
        try:
            all_sheets = pd.read_excel(file_path, sheet_name=None)
            counts = {}

            if 'Course List' in all_sheets:
                df = all_sheets['Course List']
                count = 0
                for _, row in df.iterrows():
                    class_level = str(row.get('Class', '')).strip()
                    subject = str(row.get('Subject/Course', '')).strip()
                    if class_level and subject:
                        _, created = Course.objects.update_or_create(
                            class_level=class_level, subject=subject,
                            defaults={
                                'official_name': str(row.get('Official/Reference Name', '')).strip(),
                                'category': str(row.get('Category', '')).strip(),
                                'coverage': str(row.get('Coverage', '')).strip()
                            }
                        )
                        if created: count += 1
                counts['Courses'] = count

            if 'Class Summary' in all_sheets:
                df = all_sheets['Class Summary']
                count = 0
                for _, row in df.iterrows():
                    class_level = str(row.get('Class', '')).strip()
                    if class_level:
                        _, created = ClassSummary.objects.update_or_create(
                            class_level=class_level,
                            defaults={
                                'core_subjects': str(row.get('Core Subjects', '')).strip(),
                                'languages': str(row.get('Languages', '')).strip(),
                                'enrichment_options': str(row.get('Enrichment / Skill Options', '')).strip()
                            }
                        )
                        if created: count += 1
                counts['Class Summaries'] = count

            if 'CBSE Languages' in all_sheets:
                df = all_sheets['CBSE Languages']
                count = 0
                for _, row in df.iterrows():
                    name = str(row.get('Language options identified in CBSE curriculum', '')).strip()
                    if name:
                        _, created = LanguageOption.objects.update_or_create(
                            name=name, defaults={'level_use': str(row.get('Level/Use', '')).strip()}
                        )
                        if created: count += 1
                counts['Languages'] = count

            if 'Tuition Programs' in all_sheets:
                df = all_sheets['Tuition Programs']
                count = 0
                for _, row in df.iterrows():
                    name = str(row.get('Program', '')).strip()
                    if name:
                        _, created = TuitionProgram.objects.update_or_create(
                            name=name,
                            defaults={
                                'target_classes': str(row.get('Target Classes', '')).strip(),
                                'program_type': str(row.get('Type', '')).strip(),
                                'coverage': str(row.get('Suggested Coverage', '')).strip()
                            }
                        )
                        if created: count += 1
                counts['Tuition Programs'] = count

            if 'Sources' in all_sheets:
                df = all_sheets['Sources']
                count = 0
                for _, row in df.iterrows():
                    source = str(row.get('Source', '')).strip()
                    if source:
                        # FIXED: DataSource's field is 'description' (see models.py),
                        # not 'used_for' - this update_or_create would have raised
                        # a TypeError on every row of this sheet.
                        _, created = DataSource.objects.update_or_create(
                            source=source, defaults={'description': str(row.get('What was used', '')).strip()}
                        )
                        if created: count += 1
                counts['Sources'] = count

            self.stdout.write(self.style.SUCCESS("✅ Import Complete!"))
            self.stdout.write(str(counts))
        except Exception as e:
            self.stdout.write(self.style.ERROR(f'❌ Error: {e}'))