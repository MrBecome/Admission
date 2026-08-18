from django.conf import settings
from django.core.management.base import BaseCommand

from admissions.models import Student
from admissions.views import generate_username, SET_PASSWORD_SALT
from django.contrib.auth.models import User
from django.core import signing
from django.core.mail import send_mail
from django.urls import reverse


class Command(BaseCommand):
    help = (
        "Backfills login accounts for students who applied before account-creation "
        "was added, and resends the setup email to any student whose account still "
        "has no usable password."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--base-url',
            default=getattr(settings, 'SITE_BASE_URL', 'http://127.0.0.1:8000'),
            help="Base URL to build the set-password link with (default: http://127.0.0.1:8000)",
        )

    def handle(self, *args, **options):
        base_url = options['base_url'].rstrip('/')
        fixed = 0

        for student in Student.objects.all():
            if student.user is None:
                username = generate_username(student.email)
                user = User.objects.create_user(username=username, email=student.email)
                user.set_unusable_password()
                user.save()
                student.user = user
                student.save(update_fields=['user'])
                self.stdout.write(f"Created account for student {student.id} ({student.email}) -> {username}")

            if not student.user.has_usable_password():
                token = signing.dumps({'student_id': student.id}, salt=SET_PASSWORD_SALT)
                set_password_url = f"{base_url}{reverse('set_password', args=[token])}"
                application_id = f'IVA{student.id:06d}'
                subject = 'Admission Confirmation - Infinity Academy'
                message = (
                    f"Dear {student.full_name},\n\n"
                    f"Application ID: {application_id}\n"
                    f"Course: {student.get_course_display()}\n\n"
                    f"Your student portal username is: {student.user.username}\n"
                    f"Set your password using the link below (valid for 24 hours):\n"
                    f"{set_password_url}\n\n"
                    f"Sign in afterwards at {base_url}{reverse('student_login')}\n\n"
                    f"- Infinity Academy Registrar's Office"
                )
                try:
                    send_mail(
                        subject, message, settings.DEFAULT_FROM_EMAIL,
                        [student.email, settings.ADMIN_EMAIL], fail_silently=False,
                    )
                except Exception as exc:
                    self.stdout.write(self.style.ERROR(f"Email failed for student {student.id}: {exc}"))
                    continue
                self.stdout.write(self.style.SUCCESS(f"Resent setup email to {student.email}"))
                fixed += 1

        self.stdout.write(self.style.SUCCESS(f"Done. {fixed} student(s) emailed."))
