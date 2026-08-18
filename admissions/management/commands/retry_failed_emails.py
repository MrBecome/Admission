from django.conf import settings
from django.core.mail import send_mail
from django.core.management.base import BaseCommand

from admissions.models import FailedEmail


class Command(BaseCommand):
    help = "Retries sending any admission-confirmation emails that previously failed."

    def handle(self, *args, **options):
        pending = FailedEmail.objects.filter(resolved=False)
        if not pending.exists():
            self.stdout.write(self.style.SUCCESS("No failed emails to retry."))
            return

        for failed in pending:
            recipients = [addr.strip() for addr in failed.recipient_list.split(',') if addr.strip()]
            try:
                send_mail(
                    failed.subject,
                    failed.message,
                    settings.DEFAULT_FROM_EMAIL,
                    recipients,
                    fail_silently=False,
                )
            except Exception as exc:
                failed.retry_count += 1
                failed.error = str(exc)
                failed.save(update_fields=['retry_count', 'error'])
                self.stdout.write(self.style.ERROR(
                    f"Retry failed for student {failed.student_id} (attempt {failed.retry_count}): {exc}"
                ))
            else:
                failed.resolved = True
                failed.save(update_fields=['resolved'])
                self.stdout.write(self.style.SUCCESS(f"Resent email for student {failed.student_id}."))
