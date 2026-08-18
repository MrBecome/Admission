from django.conf import settings
from django.core.checks import Warning, register

PLACEHOLDER_MARKERS = ('your-email', 'your-app-password', 'infinityacademy.example')


@register()
def email_configuration_check(app_configs, **kwargs):
    """
    Flags the exact misconfiguration that silently prevents admission-confirmation
    emails from reaching real inboxes: leftover placeholder credentials, or the
    console backend still being active. Runs automatically on every
    `manage.py check` / `manage.py runserver`.
    """
    found = []
    host_user = getattr(settings, 'EMAIL_HOST_USER', '') or ''
    host_password = getattr(settings, 'EMAIL_HOST_PASSWORD', '') or ''
    admin_email = getattr(settings, 'ADMIN_EMAIL', '') or ''
    default_from = getattr(settings, 'DEFAULT_FROM_EMAIL', '') or ''
    backend = getattr(settings, 'EMAIL_BACKEND', '')

    if any(marker in host_user for marker in PLACEHOLDER_MARKERS) or \
       any(marker in host_password for marker in PLACEHOLDER_MARKERS):
        found.append(Warning(
            "EMAIL_HOST_USER / EMAIL_HOST_PASSWORD in settings.py are still placeholder "
            "values ('your-email@gmail.com' / 'your-app-password'). Admission emails will "
            "NOT be delivered until you replace these with a real Gmail address and app "
            "password.",
            id='admissions.W001',
        ))

    if backend == 'django.core.mail.backends.console.EmailBackend':
        found.append(Warning(
            "EMAIL_BACKEND is the console backend - emails print to this terminal only, "
            "no real email is sent. Set EMAIL_BACKEND = "
            "'django.core.mail.backends.smtp.EmailBackend' for real delivery.",
            id='admissions.W002',
        ))

    if any(marker in default_from for marker in PLACEHOLDER_MARKERS) or \
       any(marker in admin_email for marker in PLACEHOLDER_MARKERS):
        found.append(Warning(
            "DEFAULT_FROM_EMAIL / ADMIN_EMAIL in settings.py are still placeholder values.",
            id='admissions.W003',
        ))

    return found
