from django.contrib.auth.models import User
from django.db import models
from django.urls import reverse
from django.core.exceptions import ValidationError

class Course(models.Model):
    """One row per Class + Subject combination, imported from courses.xlsx."""
    class_level = models.CharField(max_length=10, db_index=True)
    subject = models.CharField(max_length=100, db_index=True)
    official_name = models.CharField(max_length=200, blank=True)
    category = models.CharField(max_length=50, blank=True)
    coverage = models.TextField(blank=True)

    class Meta:
        ordering = ['class_level', 'subject']
        unique_together = ('class_level', 'subject')
        indexes = [
            models.Index(fields=['class_level', 'subject']),
        ]

    def __str__(self):
        return f"{self.class_level} - {self.subject}"


class ClassSummary(models.Model):
    """One row per class, summarising its core/language/enrichment subjects."""
    class_level = models.CharField(max_length=10, unique=True, db_index=True)
    core_subjects = models.TextField(blank=True)
    languages = models.TextField(blank=True)
    enrichment_options = models.TextField(blank=True)

    class Meta:
        ordering = ['class_level']
        verbose_name_plural = 'Class summaries'

    def __str__(self):
        return f"Class {self.class_level} summary"


class LanguageOption(models.Model):
    """A language available under the CBSE curriculum."""
    name = models.CharField(max_length=100, unique=True, db_index=True)
    level_use = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class TuitionProgram(models.Model):
    """A named tuition programme (Foundation, Olympiad, Board Prep, etc.)."""
    name = models.CharField(max_length=150, unique=True, db_index=True)
    target_classes = models.CharField(max_length=50, blank=True)
    program_type = models.CharField(max_length=50, blank=True)
    coverage = models.TextField(blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class DataSource(models.Model):
    """Reference/citation for where the imported curriculum data came from."""
    source = models.CharField(max_length=200, unique=True, db_index=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ['source']

    def __str__(self):
        return self.source


class Student(models.Model):
    VERIFICATION_CHOICES = [
        ('pending', 'Pending'),
        ('verified', 'Verified'),
        ('rejected', 'Rejected'),
    ]

    # --- Personal Information ---
    full_name = models.CharField(max_length=100, db_index=True)
    email = models.EmailField(unique=True, db_index=True)
    phone = models.CharField(max_length=15, db_index=True)
    address = models.TextField()

    # --- Application & Course ---
    course = models.ForeignKey(
        Course, on_delete=models.PROTECT, related_name='students', null=True, db_index=True
    )
    admission_date = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.OneToOneField(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name='student_profile'
    )

    # --- Application ID (Auto-Generated) ---
    application_id = models.CharField(
        max_length=20, 
        unique=True, 
        blank=True, 
        null=True, 
        db_index=True,
        help_text="Auto-generated on first save. Format: IVA[ID]"
    )

    # --- Payment Information ---
    payment_status = models.BooleanField(default=False, db_index=True)
    amount_paid = models.DecimalField(max_digits=8, decimal_places=2, default=0.00)
    payment_verification = models.CharField(
        max_length=10, 
        choices=VERIFICATION_CHOICES, 
        default='pending', 
        db_index=True
    )
    transaction_id = models.CharField(max_length=50, blank=True, null=True)
    payment_date = models.DateTimeField(blank=True, null=True)

    # --- Audit Trail ---
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        """Advanced model validation."""
        if self.payment_verification == 'verified' and self.amount_paid <= 0:
            raise ValidationError("A verified payment cannot have an amount of 0 or less.")

    def save(self, *args, **kwargs):
        # Auto-generate the application_id for NEW students only
        if not self.pk:
            super().save(*args, **kwargs) # Save first to get the auto-increment ID
            self.application_id = f"IVA{self.id:06d}"
            super().save(update_fields=['application_id']) # Save only the new field
        else:
            super().save(*args, **kwargs)

    def get_absolute_url(self):
        """Returns the URL to access a particular student instance.
        FIXED: was reverse('student_detail', ...) - no such URL name exists
        anywhere in urls.py, which would raise NoReverseMatch the moment
        anything called this (e.g. Django admin's 'View on site' link)."""
        return reverse('success', kwargs={'student_id': self.pk})

    def __str__(self):
        return f"{self.full_name} - {self.course}"


class Announcement(models.Model):
    title = models.CharField(max_length=200, db_index=True)
    message = models.TextField()
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.title


class FailedEmail(models.Model):
    """Logs an admission-confirmation email that failed to send, so it can be retried."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='failed_emails')
    subject = models.CharField(max_length=255)
    message = models.TextField()
    recipient_list = models.TextField(help_text="Comma-separated recipient addresses")
    error = models.TextField()
    retry_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    resolved = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['student', 'resolved']),
        ]

    def __str__(self):
        return f"Failed email for {self.student.full_name} ({'resolved' if self.resolved else 'pending'})"


# ================================================================
# ADMIN ACCOUNT (PROXY MODEL)
# ================================================================
#
# NOT a new database table - this is a proxy over Django's built-in
# auth.User model. It exists only so the admin site can show a
# separate "Admin Details" section for superuser accounts, kept apart
# from the "Users" section (which now shows students only - see
# RestrictedUserAdmin in admin.py).
#
# Accounts here are created ONLY via:
#     python manage.py createsuperuser
#
# AdminAccountAdmin (in admin.py) blocks add/change/delete on this
# model entirely, so a superuser account can never be created, edited,
# or have its password changed through this admin screen - terminal
# access is the only way in, by design.
class AdminAccount(User):
    class Meta:
        proxy = True
        app_label = "admin_details"
        verbose_name = "Admin Account"
        verbose_name_plural = "Admin Accounts"