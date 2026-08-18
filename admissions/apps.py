from django.apps import AppConfig


class AdmissionsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'admissions'

    def ready(self):
        from . import checks  # noqa: F401  (registers the email-config system check)
