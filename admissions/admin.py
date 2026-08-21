from django.contrib import admin
from django.conf import settings
from django.urls import path, reverse, NoReverseMatch
from django.shortcuts import redirect, get_object_or_404, render
from django.utils.html import format_html, mark_safe
from django.contrib import messages
from django.db import transaction

import os
import shutil
import tempfile

import openpyxl

from django.contrib.auth.models import User
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import (
    Student,
    Announcement,
    FailedEmail,
    Course,
    ClassSummary,
    LanguageOption,
    TuitionProgram,
    DataSource,
    AdminAccount,
)

# CRITICAL: sheet names the importer (import_courses.py) actually reads.
# The uploader below refuses to accept a file missing any of these, so a
# bad upload can never silently wipe out the working spreadsheet.
REQUIRED_COURSE_SHEETS = (
    'Course List', 'Class Summary', 'CBSE Languages', 'Tuition Programs', 'Sources',
)


@admin.register(Course)
class CourseAdmin(admin.ModelAdmin):
    change_list_template = 'admin/admissions/course/change_list.html'

    list_display = (
        'class_level',
        'subject',
        'official_name',
        'category',
    )
    list_filter = (
        'class_level',
        'category',
    )
    search_fields = (
        'subject',
        'official_name',
        'coverage',
    )

    def get_urls(self):
        custom_urls = [
            path(
                'upload-courses/',
                self.admin_site.admin_view(self.upload_courses_view),
                name='admissions_course_upload',
            ),
        ]
        return custom_urls + super().get_urls()

    def upload_courses_view(self, request):
        """
        CRITICAL: validates the uploaded workbook with openpyxl BEFORE it is
        allowed to overwrite the live courses.xlsx in PRIVATE_DATA_ROOT.
        A file that fails to open, or is missing any required sheet, is
        rejected outright - the existing file is never touched.
        """
        if request.method == 'POST' and request.FILES.get('spreadsheet'):
            uploaded = request.FILES['spreadsheet']

            if not uploaded.name.lower().endswith(('.xlsx', '.xlsm')):
                messages.error(request, "Please upload a .xlsx or .xlsm file.")
                return redirect('admin:admissions_course_upload')

            with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False) as tmp:
                for chunk in uploaded.chunks():
                    tmp.write(chunk)
                tmp_path = tmp.name

            try:
                workbook = openpyxl.load_workbook(tmp_path, read_only=True, data_only=True)
            except Exception as exc:
                os.remove(tmp_path)
                messages.error(
                    request,
                    f"That file isn't a valid Excel workbook openpyxl could open "
                    f"(it may be corrupted or a different format): {exc}"
                )
                return redirect('admin:admissions_course_upload')

            sheet_names = set(workbook.sheetnames)
            workbook.close()
            missing = [s for s in REQUIRED_COURSE_SHEETS if s not in sheet_names]

            if missing:
                os.remove(tmp_path)
                messages.error(
                    request,
                    "Rejected - this workbook is missing required sheet(s): "
                    f"{', '.join(missing)}. The existing courses.xlsx was NOT changed."
                )
                return redirect('admin:admissions_course_upload')

            os.makedirs(settings.PRIVATE_DATA_ROOT, exist_ok=True)
            target_path = os.path.join(settings.PRIVATE_DATA_ROOT, 'courses.xlsx')
            shutil.move(tmp_path, target_path)

            messages.success(
                request,
                "Spreadsheet validated and saved. Now run "
                "`python manage.py import_courses` to load the new data."
            )
            return redirect('admin:admissions_course_upload')

        return render(request, 'admin/admissions/course_upload.html', {
            'required_sheets': REQUIRED_COURSE_SHEETS,
            'opts': self.model._meta,
        })


@admin.register(Student)
class StudentAdmin(admin.ModelAdmin):
    """
    NOTE: registered exactly once, via this single @admin.register(Student)
    decorator. There is no admin.site.register(Student, ...) call anywhere
    else in this file — a duplicate registration would itself raise
    django.contrib.admin.sites.AlreadyRegistered at startup (not a 500 on
    the changelist page), so if you were seeing that specific error, check
    for a second admin.py / apps.py in another app that also imports and
    registers Student.
    """

    list_display = (
        'full_name',
        'email',
        'phone',
        'get_class_level',
        'course',
        'application_id_display',
        'payment_status',
        'amount_paid',
        'verification_badge',
        'admission_date',
        'action_buttons'
    )

    list_display_links = ('full_name',)
    list_editable = ('payment_status', 'amount_paid')

    list_filter = (
        'course',
        'payment_status',
        'payment_verification',
        'admission_date',
    )

    search_fields = (
        'full_name',
        'email',
        'phone',
        'application_id',
        'transaction_id',
        'course__subject',
    )

    list_per_page = 50
    list_max_show_all = 500
    show_full_result_count = True
    save_on_top = True
    save_as = True
    save_as_continue = True
    empty_value_display = '-'

    autocomplete_fields = ('course',)
    date_hierarchy = 'admission_date'

    fieldsets = (
        ('Personal Information', {
            'fields': (
                'full_name',
                'email',
                'phone',
                'address',
            ),
            'classes': ('wide',)
        }),
        ('Application & Course', {
            'fields': (
                'course',
                'application_id',
                'admission_date',
                'user',
            ),
            'classes': ('collapse',)
        }),
        ('Payment & Verification', {
            'fields': (
                'payment_status',
                'payment_verification',
                'amount_paid',
                'transaction_id',
                'payment_date',
            ),
            'classes': ('collapse',)
        }),
    )

    readonly_fields = (
        'application_id',
        'admission_date',
        'user',
    )

    actions = [
        'mark_verified',
        'mark_rejected',
    ]

    def get_queryset(self, request):
        # select_related on both course AND user: 'course' is displayed
        # directly and 'user' is touched indirectly via __str__/model
        # access from list_display columns. Without this, admin falls
        # back to a query-per-row, which is slow but NOT the cause of a
        # 500 - included here for completeness/perf, not as a bug fix.
        return (
            super()
            .get_queryset(request)
            .select_related('course', 'user')
        )

    def get_class_level(self, obj):
        return obj.course.class_level if obj.course_id else '-'

    get_class_level.short_description = 'Class'
    get_class_level.admin_order_field = 'course__class_level'

    def application_id_display(self, obj):
        app_id = obj.application_id or '-'
        if not obj.application_id:
            # No JS copy-button needed / no id to copy - render plain text
            # so the onclick handler never runs with an empty string.
            return app_id
        return format_html(
            '<span style="font-family:monospace; background:#f8f9fa; color:#0A2540; padding:4px 10px; border:1px solid #e9ecef; border-radius:6px; display:inline-flex; align-items:center; gap:8px; font-weight:600;">'
            '{} <span style="cursor:pointer; color:#0A2540; font-size:0.9rem; background:#e2e8f0; padding:0 4px; border-radius:4px;" onclick="navigator.clipboard.writeText(\'{}\'); alert(\'Application ID copied!\');">Copy</span>'
            '</span>',
            app_id, app_id
        )
    application_id_display.short_description = 'Application ID'
    application_id_display.admin_order_field = 'application_id'

    def verification_badge(self, obj):
        if obj.payment_verification == 'verified':
            return mark_safe(
                '<span style="background:#198754; color:#ffffff; padding:4px 14px; border-radius:50px; font-weight:bold; display:inline-block; box-shadow:0 2px 4px rgba(25,135,84,0.3);">Verified</span>'
            )
        elif obj.payment_verification == 'rejected':
            return mark_safe(
                '<span style="background:#dc3545; color:#ffffff; padding:4px 14px; border-radius:50px; font-weight:bold; display:inline-block; box-shadow:0 2px 4px rgba(220,53,69,0.3);">Rejected</span>'
            )
        return mark_safe(
            '<span style="background:#ffc107; color:#000000; padding:4px 14px; border-radius:50px; font-weight:bold; display:inline-block; box-shadow:0 2px 4px rgba(255,193,7,0.3);">Pending</span>'
        )

    verification_badge.short_description = 'Status'

    def action_buttons(self, obj):
        """
        HARDENED: reverse() on a custom admin URL raises NoReverseMatch if
        the URL name/namespace doesn't resolve (e.g. right after a fresh
        deploy before urls are fully loaded, or if the object has no pk
        yet in some edge-case rendering path such as the "add" preview).
        We now catch that instead of letting it bubble into a 500.
        """
        if obj.pk is None:
            return '-'

        if obj.payment_verification == 'verified':
            return mark_safe(
                '<span style="color:#198754; font-weight:bold;">Already Verified</span>'
            )
        elif obj.payment_verification == 'rejected':
            return mark_safe(
                '<span style="color:#dc3545; font-weight:bold;">Already Rejected</span>'
            )

        try:
            verify_url = reverse('admin:verify_payment', args=[obj.id])
            reject_url = reverse('admin:reject_payment', args=[obj.id])
        except NoReverseMatch:
            return '-'

        safe_name = obj.full_name.replace("'", "\\'") if obj.full_name else 'this student'

        return format_html(
            '<div style="display:inline-flex; gap:8px; align-items:center;">'
            '<a href="{}" onclick="return confirm(\'Are you sure you want to verify {}?\');" style="background:#198754; color:white; padding:4px 12px; border-radius:30px; text-decoration:none; font-size:12px; font-weight:bold; box-shadow:0 1px 3px rgba(0,0,0,0.1); transition:0.2s;">Verify</a>'
            '<a href="{}" onclick="return confirm(\'Are you sure you want to reject {}?\');" style="background:#dc3545; color:white; padding:4px 12px; border-radius:30px; text-decoration:none; font-size:12px; font-weight:bold; box-shadow:0 1px 3px rgba(0,0,0,0.1); transition:0.2s;">Reject</a>'
            '</div>',
            verify_url, safe_name, reject_url, safe_name
        )

    action_buttons.short_description = 'Quick Actions'

    def get_urls(self):
        urls = super().get_urls()
        custom_urls = [
            path(
                'verify/<int:student_id>/',
                self.admin_site.admin_view(self.verify_payment),
                name='verify_payment',
            ),
            path(
                'reject/<int:student_id>/',
                self.admin_site.admin_view(self.reject_payment),
                name='reject_payment',
            ),
        ]
        return custom_urls + urls

    @transaction.atomic
    def verify_payment(self, request, student_id):
        try:
            student = get_object_or_404(Student, id=student_id)
            student.payment_verification = 'verified'
            student.payment_status = True
            student.save()
            self.message_user(
                request,
                f"Successfully marked {student.full_name} as Verified.",
                messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(
                request,
                f"Error verifying student: {str(e)}",
                messages.ERROR,
            )
        return redirect('admin:admissions_student_changelist')

    @transaction.atomic
    def reject_payment(self, request, student_id):
        try:
            student = get_object_or_404(Student, id=student_id)
            student.payment_verification = 'rejected'
            student.payment_status = False
            student.save()
            self.message_user(
                request,
                f"Successfully marked {student.full_name} as Rejected.",
                messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(
                request,
                f"Error rejecting student: {str(e)}",
                messages.ERROR,
            )
        return redirect('admin:admissions_student_changelist')

    def mark_verified(self, request, queryset):
        try:
            updated = queryset.update(
                payment_verification='verified',
                payment_status=True,
            )
            self.message_user(
                request,
                f"Successfully Verified {updated} student(s).",
                messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(
                request,
                f"Bulk Verify failed: {str(e)}",
                messages.ERROR,
            )
    mark_verified.short_description = "Mark selected students as Verified"

    def mark_rejected(self, request, queryset):
        try:
            updated = queryset.update(
                payment_verification='rejected',
                payment_status=False,
            )
            self.message_user(
                request,
                f"Successfully Rejected {updated} student(s).",
                messages.SUCCESS,
            )
        except Exception as e:
            self.message_user(
                request,
                f"Bulk Reject failed: {str(e)}",
                messages.ERROR,
            )
    mark_rejected.short_description = "Mark selected students as Rejected"

    class Media:
        css = {
            'all': ('admin/css/custom_admin.css',)
        }


# ==============================================================================
# ALL OTHER ADMINS ARE PRESERVED EXACTLY AS THEY WERE
# ==============================================================================

@admin.register(Announcement)
class AnnouncementAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'is_active',
        'created_at',
    )
    list_filter = ('is_active',)
    search_fields = ('title', 'message')


@admin.register(FailedEmail)
class FailedEmailAdmin(admin.ModelAdmin):
    list_display = (
        'student',
        'subject',
        'retry_count',
        'resolved',
        'created_at',
    )
    list_filter = ('resolved',)
    readonly_fields = (
        'student',
        'subject',
        'message',
        'recipient_list',
        'error',
        'retry_count',
        'created_at',
    )


@admin.register(ClassSummary)
class ClassSummaryAdmin(admin.ModelAdmin):
    list_display = (
        'class_level',
        'core_subjects',
    )
    search_fields = (
        'class_level',
        'core_subjects',
    )


@admin.register(LanguageOption)
class LanguageOptionAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'level_use',
    )
    search_fields = ('name',)


@admin.register(TuitionProgram)
class TuitionProgramAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'target_classes',
        'program_type',
    )
    list_filter = ('program_type',)
    search_fields = (
        'name',
        'coverage',
    )


@admin.register(DataSource)
class DataSourceAdmin(admin.ModelAdmin):
    list_display = ('source',)
    search_fields = ('source',)


# ==============================================================================
# USERS vs ADMIN ACCOUNTS
# ==============================================================================
#
# Django's default admin lumps every auth.User row into one "Users"
# screen - student accounts (created automatically when a student
# applies / sets up their portal password) end up mixed in with real
# superuser accounts (created only via `createsuperuser` in the
# terminal). That mixing is what caused the mismatch you were seeing.
#
# Fix: split the SAME table into two admin views by queryset -
# no schema change, no data migration, no risk to existing logins.
#
#   "Users"          -> is_superuser=False  (students only)
#   "Admin Accounts"  -> is_superuser=True   (terminal-created admins only,
#                                              fully read-only here)

class RestrictedUserAdmin(DjangoUserAdmin):
    """Shows student accounts only. Superusers are filtered out here and
    surfaced separately under Admin Details (see AdminAccountAdmin)."""

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_superuser=False)

    def get_fieldsets(self, request, obj=None):
        """
        HARDENED: without this override, any staff user with access to
        this screen could open a student's User record and manually tick
        the 'Superuser status' checkbox in the default Permissions
        fieldset - silently promoting a student account to a real admin.

        Non-superusers editing here never see the is_superuser / is_staff
        / groups / user_permissions controls at all, so that path is
        closed. Superusers still see the full default fieldsets.
        """
        fieldsets = super().get_fieldsets(request, obj)

        if request.user.is_superuser:
            return fieldsets

        safe_fieldsets = []
        for name, opts in fieldsets:
            opts = dict(opts)
            fields = opts.get('fields', ())
            opts['fields'] = tuple(
                f for f in fields
                if f not in (
                    'is_superuser',
                    'is_staff',
                    'groups',
                    'user_permissions',
                )
            )
            safe_fieldsets.append((name, opts))
        return safe_fieldsets


@admin.register(AdminAccount)
class AdminAccountAdmin(DjangoUserAdmin):
    """
    Read-only view of superuser accounts. Appears under its own
    "Admin Details" section in the sidebar (see admin_details app).

    Accounts here are created ONLY via:
        python manage.py createsuperuser

    Add / change / delete are all disabled - there is no way to create,
    edit, or reset an admin password from this screen. This is
    intentional: terminal access is the only path to a superuser
    account, so it can never collide with student account creation.
    """

    def get_queryset(self, request):
        return super().get_queryset(request).filter(is_superuser=True)

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return True


admin.site.unregister(User)
admin.site.register(User, RestrictedUserAdmin)