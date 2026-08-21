import base64
import logging
import os
import re
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import (
    authenticate,
    login as auth_login,
    logout as auth_logout,
)
from django.contrib.auth.models import User
from django.core import signing
from django.core.mail import send_mail
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import (
    get_object_or_404,
    redirect,
    render,
)
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.views.decorators.csrf import csrf_protect

from .forms import (
    AnnouncementForm,
    StudentAuthForm,
    StudentForm,
    StudentPasswordSetupRequestForm,
    StudentSetPasswordForm,
)

from .models import (
    Announcement,
    ClassSummary,
    Course,
    FailedEmail,
    Student,
    TuitionProgram,
)

from .security import (
    clear_otp,
    generate_otp,
    verify_otp as check_otp,
)


# ============================================================
# CONFIGURATION
# ============================================================

SET_PASSWORD_SALT = "admissions-set-password"

# Password setup link is valid for 24 hours.
SET_PASSWORD_MAX_AGE = 60 * 60 * 24

logger = logging.getLogger(__name__)


# ============================================================
# DECORATORS
# ============================================================

def otp_required(view_func):
    """
    Protect admin views with:
        1. authenticated Django user
        2. superuser status
        3. successful OTP verification
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if (
            not request.user.is_authenticated
            or not request.user.is_superuser
            or not request.session.get("otp_verified")
        ):
            messages.info(
                request,
                "Please log in as admin to continue.",
            )
            return redirect("admin_login")

        return view_func(request, *args, **kwargs)

    return wrapper


def student_required(view_func):
    """
    Protect student portal pages.
    """

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.session.get("student_id"):

            messages.info(
                request,
                "Please sign in to view your application status.",
            )

            return redirect("student_login")

        return view_func(request, *args, **kwargs)

    return wrapper


# ============================================================
# QR CODE
# ============================================================

def _get_qr_base64(student):
    """
    Return the fixed payment QR image as base64.

    QR is hidden after payment verification.
    """

    if (
        student.payment_status
        and student.payment_verification == "verified"
    ):
        return None

    qr_path = os.path.join(
        settings.MEDIA_ROOT,
        "qr_codes",
        "qr_1.png",
    )

    if not os.path.exists(qr_path):

        logger.warning(
            "Static QR image not found at %s",
            qr_path,
        )

        return None

    try:

        with open(qr_path, "rb") as qr_file:
            return base64.b64encode(
                qr_file.read()
            ).decode()

    except OSError as exc:

        logger.error(
            "Unable to read QR image: %s",
            exc,
        )

        return None


# ============================================================
# PAYMENT RECEIPT
# ============================================================

def payment_receipt(request, app_id):
    """
    Display a verified payment receipt.

    Supports:
        IVA00000010
        10
    """

    student = None

    # Try application ID first.
    try:

        student = Student.objects.get(
            application_id=app_id
        )

    except Student.DoesNotExist:

        # Fall back to numeric primary key.
        try:

            student = Student.objects.get(
                id=int(app_id)
            )

        except (
            Student.DoesNotExist,
            ValueError,
            TypeError,
        ):

            raise Http404(
                "No Student matches the given query."
            )

    # --------------------------------------------------------
    # Authorization
    # --------------------------------------------------------

    is_authorized = False

    if (
        request.user.is_authenticated
        and student.user_id == request.user.id
    ):
        is_authorized = True

    elif request.session.get("student_id") == student.id:
        is_authorized = True

    elif (
        request.user.is_authenticated
        and request.user.is_superuser
    ):
        is_authorized = True

    if not is_authorized:

        messages.error(
            request,
            "You are not authorized to view this receipt.",
        )

        return redirect("student_login")

    # --------------------------------------------------------
    # Payment verification
    # --------------------------------------------------------

    if (
        not student.payment_status
        or student.payment_verification != "verified"
    ):

        messages.info(
            request,
            "Payment is not yet verified. "
            "The receipt will be available after verification.",
        )

        return redirect(
            "success",
            student_id=student.id,
        )

    return render(
        request,
        "admissions/receipt.html",
        {
            "student": student,
        },
    )


# ============================================================
# AUTOCOMPLETE SEARCH
# ============================================================

def autocomplete_search(request):

    term = request.GET.get(
        "term",
        "",
    ).strip()

    results = []

    if len(term) >= 2:

        # ----------------------------------------------------
        # Announcements
        # ----------------------------------------------------

        announcements = (
            Announcement.objects
            .filter(
                Q(title__icontains=term)
                | Q(message__icontains=term)
            )
            .filter(is_active=True)[:3]
        )

        for announcement in announcements:

            results.append(
                {
                    "label": (
                        f"📢 {announcement.title}"
                    ),
                    "value": announcement.title,
                }
            )

        # ----------------------------------------------------
        # Courses
        # ----------------------------------------------------

        courses = (
            Course.objects
            .filter(
                Q(subject__icontains=term)
                | Q(official_name__icontains=term)
            )[:3]
        )

        for course in courses:

            results.append(
                {
                    "label": f"📚 {course}",
                    "value": course.subject,
                }
            )

        # ----------------------------------------------------
        # Smart links
        # ----------------------------------------------------

        lower_term = term.lower()

        if any(
            word in lower_term
            for word in (
                "admission",
                "apply",
                "admit",
            )
        ):

            results.append(
                {
                    "label": "📝 Apply for Admission",
                    "value": "admission",
                }
            )

        if any(
            word in lower_term
            for word in (
                "track",
                "status",
                "application",
            )
        ):

            results.append(
                {
                    "label": "🔍 Track Your Application",
                    "value": "track",
                }
            )

    return JsonResponse(
        results,
        safe=False,
    )


# ============================================================
# HELPERS
# ============================================================

def generate_username(email):
    """
    Generate a unique username from the student's email.

    Example:
        arif@gmail.com
        ->
        arif

    If arif already exists:
        arif1
        arif2
        etc.
    """

    base = re.sub(
        r"[^a-zA-Z0-9_]",
        "",
        email.split("@")[0],
    ).lower()

    if not base:
        base = "student"

    username = base
    counter = 1

    while User.objects.filter(
        username=username
    ).exists():

        username = f"{base}{counter}"
        counter += 1

    return username


_LOGO_CACHE = {}


def _get_logo_base64():
    """
    Load the academy logo for HTML email templates.
    """

    if "data" not in _LOGO_CACHE:

        logo_path = os.path.join(
            settings.BASE_DIR,
            "static",
            "images",
            "logo.png",
        )

        try:

            with open(logo_path, "rb") as logo_file:

                _LOGO_CACHE["data"] = (
                    base64.b64encode(
                        logo_file.read()
                    ).decode()
                )

        except FileNotFoundError:

            _LOGO_CACHE["data"] = None

    return _LOGO_CACHE["data"]


# ============================================================
# CREATE STUDENT ACCOUNT + EMAIL
# ============================================================

def _create_student_account_and_notify(
    request,
    student,
):
    """
    Create a Django User account for the student.

    The account initially has NO usable password.

    The student receives:
        - Application ID
        - Username
        - Password setup link

    Password is never emailed or stored in plain text.
    """

    # --------------------------------------------------------
    # Create username
    # --------------------------------------------------------

    username = generate_username(
        student.email
    )

    # --------------------------------------------------------
    # Create user
    # --------------------------------------------------------

    user = User.objects.create_user(
        username=username,
        email=student.email,
    )

    # No password yet.
    user.set_unusable_password()

    user.is_active = True

    user.save(
        update_fields=[
            "password",
            "is_active",
        ]
    )

    # --------------------------------------------------------
    # Link User to Student
    # --------------------------------------------------------

    student.user = user

    student.save(
        update_fields=[
            "user",
        ]
    )

    # --------------------------------------------------------
    # Signed password setup token
    # --------------------------------------------------------

    token = signing.dumps(
        {
            "student_id": student.id,
        },
        salt=SET_PASSWORD_SALT,
    )

    set_password_url = request.build_absolute_uri(
        reverse(
            "set_password",
            args=[token],
        )
    )

    # --------------------------------------------------------
    # Application information
    # --------------------------------------------------------

    application_id = (
        f"IVA{student.id:06d}"
    )

    course_display = (
        str(student.course)
        if student.course
        else "Not specified"
    )

    # --------------------------------------------------------
    # Email
    # --------------------------------------------------------

    subject = (
        "Admission Confirmation - Infinity Academy"
    )

    context = {
        "student": student,
        "application_id": application_id,
        "course_display": course_display,
        "username": username,
        "set_password_url": set_password_url,
        "logo_base64": _get_logo_base64(),
    }

    try:

        html_message = render_to_string(
            "admissions/emails/welcome_email.html",
            context,
        )

    except Exception as exc:

        logger.warning(
            "Welcome email template unavailable: %s",
            exc,
        )

        html_message = f"""
        <html>
        <body>
            <h2>Welcome to Infinity Academy</h2>

            <p>Dear {student.full_name},</p>

            <p>Your admission application has been received.</p>

            <p>
                <strong>Application ID:</strong>
                {application_id}
            </p>

            <p>
                <strong>Username:</strong>
                {username}
            </p>

            <p>
                <strong>Course:</strong>
                {course_display}
            </p>

            <p>
                Create your student portal password:
            </p>

            <p>
                <a href="{set_password_url}">
                    Create / Set Password
                </a>
            </p>

            <p>
                This password setup link expires in 24 hours.
            </p>

            <p>
                Infinity Academy
            </p>
        </body>
        </html>
        """

    plain_message = strip_tags(
        html_message
    )

    recipient_list = [
        student.email
    ]

    # --------------------------------------------------------
    # Send to student
    # --------------------------------------------------------

    try:

        send_mail(
            subject=subject,
            message=plain_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipient_list,
            html_message=html_message,
            fail_silently=False,
        )

        logger.info(
            "Admission email sent successfully to %s",
            student.email,
        )

        # ----------------------------------------------------
        # Admin copy
        # ----------------------------------------------------

        if getattr(
            settings,
            "ADMIN_EMAIL",
            "",
        ):

            send_mail(
                subject=f"[ADMIN COPY] {subject}",
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[
                    settings.ADMIN_EMAIL
                ],
                html_message=html_message,
                fail_silently=True,
            )

    except Exception as exc:

        logger.exception(
            "Admission email failed for student %s",
            student.id,
        )

        FailedEmail.objects.create(
            student=student,
            subject=subject,
            message=plain_message,
            recipient_list=", ".join(
                recipient_list
            ),
            error=str(exc),
        )

        raise


# ============================================================
# SEARCH
# ============================================================

def search_view(request):

    query = request.GET.get(
        "q",
        "",
    ).strip()

    announcements = None
    classes = None
    programs = None
    courses = None

    smart_links = []

    if query:

        announcements = Announcement.objects.filter(
            Q(title__icontains=query)
            | Q(message__icontains=query)
        )

        classes = ClassSummary.objects.filter(
            Q(class_level__icontains=query)
            | Q(core_subjects__icontains=query)
        )

        programs = TuitionProgram.objects.filter(
            Q(name__icontains=query)
            | Q(coverage__icontains=query)
        )

        courses = (
            Course.objects
            .exclude(class_level="LEGACY")
            .filter(
                Q(subject__icontains=query)
                | Q(official_name__icontains=query)
            )
        )

        lowered = query.lower()

        if any(
            word in lowered
            for word in (
                "admission",
                "apply",
                "admit",
            )
        ):

            smart_links.append(
                {
                    "label": "Apply for Admission",
                    "url": reverse(
                        "admission_form"
                    ),
                }
            )

        if any(
            word in lowered
            for word in (
                "track",
                "status",
                "application",
            )
        ):

            smart_links.append(
                {
                    "label": "Track Your Application",
                    "url": reverse(
                        "student_login"
                    ),
                }
            )

    has_results = bool(
        query
        and (
            (
                announcements
                and announcements.exists()
            )
            or (
                classes
                and classes.exists()
            )
            or (
                programs
                and programs.exists()
            )
            or (
                courses
                and courses.exists()
            )
            or smart_links
        )
    )

    return render(
        request,
        "admissions/search_results.html",
        {
            "query": query,
            "announcements": announcements,
            "classes": classes,
            "programs": programs,
            "courses": courses,
            "smart_links": smart_links,
            "has_results": has_results,
        },
    )


# ============================================================
# HOME
# ============================================================

def home_view(request):

    announcements = (
        Announcement.objects
        .filter(is_active=True)[:5]
    )

    return render(
        request,
        "admissions/home.html",
        {
            "announcements": announcements,
        },
    )


# ============================================================
# ADMISSION
# ============================================================

@csrf_protect
def admission_form(request):

    if request.method == "POST":

        form = StudentForm(
            request.POST
        )

        if form.is_valid():

            student = form.save()

            email_sent = False

            try:

                _create_student_account_and_notify(
                    request,
                    student,
                )

                email_sent = True

            except Exception as exc:

                logger.exception(
                    "Student account/email creation failed: %s",
                    exc,
                )

                messages.warning(
                    request,
                    "Your application was saved, "
                    "but we could not send the confirmation email. "
                    "Please contact the admissions office.",
                )

            if email_sent:

                messages.success(
                    request,
                    "Application received! "
                    "Check your email for your Application ID, "
                    "username and password setup link.",
                )

            return redirect(
                "success",
                student_id=student.id,
            )

        # Show form errors.
        for field, errors in form.errors.items():

            for error in errors:

                messages.error(
                    request,
                    f"{field}: {error}",
                )

    else:

        form = StudentForm()

    return render(
        request,
        "admissions/admission.html",
        {
            "form": form,
        },
    )


# ============================================================
# SUCCESS
# ============================================================

def success_view(
    request,
    student_id,
):

    student = get_object_or_404(
        Student,
        id=student_id,
    )

    return render(
        request,
        "admissions/success.html",
        {
            "student": student,
            "qr_base64": _get_qr_base64(
                student
            ),
        },
    )


# ============================================================
# MOCK PAYMENT
# ============================================================

@csrf_protect
def mock_payment(
    request,
    student_id,
):

    student = get_object_or_404(
        Student,
        id=student_id,
    )

    if (
        student.payment_verification
        == "verified"
    ):

        messages.info(
            request,
            "This student's payment is already verified.",
        )

    elif (
        student.payment_status
        and student.payment_verification
        == "pending"
    ):

        messages.info(
            request,
            "Payment already submitted and awaiting verification.",
        )

    else:

        student.payment_status = True
        student.amount_paid = 500.00

        student.transaction_id = (
            "TXN"
            + timezone.now().strftime(
                "%Y%m%d%H%M%S%f"
            )[:17]
        )

        student.payment_date = timezone.now()

        student.payment_verification = "pending"

        student.save()

        messages.success(
            request,
            f"Payment of ₹500 for "
            f"{student.full_name} submitted. "
            f"Awaiting admin verification.",
        )

    return redirect(
        "success",
        student_id=student.id,
    )


# ============================================================
# SET PASSWORD FROM EMAIL TOKEN
# ============================================================

@csrf_protect
def set_password(
    request,
    token,
):
    """
    Secure password creation/reset.

    The token:
        - is cryptographically signed
        - contains the Student ID
        - expires after 24 hours

    The password is saved through Django's SetPasswordForm,
    which securely hashes it.
    """

    # --------------------------------------------------------
    # Validate token
    # --------------------------------------------------------

    try:

        data = signing.loads(
            token,
            salt=SET_PASSWORD_SALT,
            max_age=SET_PASSWORD_MAX_AGE,
        )

    except signing.SignatureExpired:

        messages.error(
            request,
            "This password setup link has expired. "
            "Please verify your application again.",
        )

        return redirect(
            "student_password_setup_request"
        )

    except signing.BadSignature:

        messages.error(
            request,
            "This password setup link is invalid.",
        )

        return redirect(
            "student_password_setup_request"
        )

    # --------------------------------------------------------
    # Get student ID
    # --------------------------------------------------------

    student_id = data.get(
        "student_id"
    )

    if not student_id:

        messages.error(
            request,
            "This password setup link is invalid.",
        )

        return redirect(
            "student_password_setup_request"
        )

    # --------------------------------------------------------
    # Get student
    # --------------------------------------------------------

    student = (
        Student.objects
        .select_related("user")
        .filter(id=student_id)
        .first()
    )

    if not student:

        messages.error(
            request,
            "The associated student application "
            "could not be found.",
        )

        return redirect(
            "student_password_setup_request"
        )

    # --------------------------------------------------------
    # Student must have a User account
    # --------------------------------------------------------

    if not student.user:

        messages.error(
            request,
            "No student login account is linked "
            "to this application. "
            "Please contact the admissions office.",
        )

        return redirect(
            "student_password_setup_request"
        )

    user = student.user

    # --------------------------------------------------------
    # Password form
    # --------------------------------------------------------

    if request.method == "POST":

        form = StudentSetPasswordForm(
            user,
            request.POST,
        )

        if form.is_valid():

            # Django securely hashes the password.
            form.save()

            # Make sure account is active.
            if not user.is_active:

                user.is_active = True

                user.save(
                    update_fields=[
                        "is_active"
                    ]
                )

            # Clear old student session.
            request.session.pop(
                "student_id",
                None,
            )

            messages.success(
                request,
                "Your password has been created successfully. "
                "You can now sign in using your username and new password.",
            )

            return redirect(
                "student_login"
            )

    else:

        form = StudentSetPasswordForm(
            user
        )

    return render(
        request,
        "admissions/set_password.html",
        {
            "form": form,
            "student": student,
        },
    )


# ============================================================
# PASSWORD SETUP / RESET REQUEST
# ============================================================

@csrf_protect
def student_password_setup_request(
    request,
):
    """
    Verify the student using:

        Application Number
        +
        Email Address

    Accepted application numbers:

        IVA000123
        IVA123
        000123
        123

    Both values MUST match the Student database.
    """

    if request.method == "POST":

        form = StudentPasswordSetupRequestForm(
            request.POST
        )

        if not form.is_valid():

            return render(
                request,
                "admissions/student_password_request.html",
                {
                    "form": form,
                },
            )

        # ----------------------------------------------------
        # Cleaned values
        # ----------------------------------------------------

        raw_application = (
            form.cleaned_data[
                "application_number"
            ]
        )

        email = (
            form.cleaned_data[
                "email"
            ]
            .strip()
            .lower()
        )

        # ----------------------------------------------------
        # Normalize application number
        # ----------------------------------------------------

        application_value = (
            raw_application.upper()
        )

        if application_value.startswith(
            "IVA"
        ):

            application_value = (
                application_value[3:]
            )

        # Keep only digits.
        digits = "".join(
            character
            for character in application_value
            if character.isdigit()
        )

        if not digits:

            form.add_error(
                "application_number",
                "Please enter a valid application number, "
                "for example IVA000123.",
            )

            return render(
                request,
                "admissions/student_password_request.html",
                {
                    "form": form,
                },
            )

        try:

            student_id = int(
                digits
            )

        except ValueError:

            form.add_error(
                "application_number",
                "The application number is not valid.",
            )

            return render(
                request,
                "admissions/student_password_request.html",
                {
                    "form": form,
                },
            )

        # ----------------------------------------------------
        # VERIFY APPLICATION + EMAIL
        # ----------------------------------------------------

        student = (
            Student.objects
            .select_related("user")
            .filter(
                id=student_id,
                email__iexact=email,
            )
            .first()
        )

        if not student:

            # Do not reveal which field was incorrect.
            form.add_error(
                None,
                "We could not find an application matching "
                "that application number and email address.",
            )

            return render(
                request,
                "admissions/student_password_request.html",
                {
                    "form": form,
                },
            )

        # ----------------------------------------------------
        # Create account if old record has no User
        # ----------------------------------------------------

        if not student.user:

            username = generate_username(
                student.email
            )

            user = User.objects.create_user(
                username=username,
                email=student.email,
            )

            user.set_unusable_password()

            user.is_active = True

            user.save()

            student.user = user

            student.save(
                update_fields=[
                    "user"
                ]
            )

        # ----------------------------------------------------
        # Create signed password token
        # ----------------------------------------------------

        token = signing.dumps(
            {
                "student_id": student.id,
            },
            salt=SET_PASSWORD_SALT,
        )

        return redirect(
            "set_password",
            token=token,
        )

    # --------------------------------------------------------
    # GET
    # --------------------------------------------------------

    form = StudentPasswordSetupRequestForm()

    return render(
        request,
        "admissions/student_password_request.html",
        {
            "form": form,
        },
    )


# ============================================================
# STUDENT LOGIN
# ============================================================

@csrf_protect
def student_login(request):
    """
    Student login.

    Credentials:

        Username
        +
        Password

    The password is checked by Django authentication.
    """

    if request.user.is_authenticated:

        # If a logged-in student already has a profile,
        # go directly there.
        student = (
            Student.objects
            .filter(user=request.user)
            .first()
        )

        if student:

            request.session[
                "student_id"
            ] = student.id

            return redirect(
                "student_profile"
            )

        # Do not allow a normal authenticated user
        # to enter the student portal accidentally.
        auth_logout(request)

    # --------------------------------------------------------
    # POST
    # --------------------------------------------------------

    if request.method == "POST":

        form = StudentAuthForm(
            request.POST,
            request=request,
        )

        if form.is_valid():

            user = form.get_user()

            if user is None:

                messages.error(
                    request,
                    "Invalid username or password.",
                )

            else:

                # Find the student's profile.
                student = (
                    Student.objects
                    .filter(user=user)
                    .first()
                )

                if student is None:

                    messages.error(
                        request,
                        "This account is not linked "
                        "to a student application.",
                    )

                elif not user.is_active:

                    messages.error(
                        request,
                        "This student account is inactive.",
                    )

                else:

                    # Django login.
                    auth_login(
                        request,
                        user,
                    )

                    # Student session.
                    request.session[
                        "student_id"
                    ] = student.id

                    request.session.modified = True

                    return redirect(
                        "student_profile"
                    )

    else:

        form = StudentAuthForm(
            request=request,
        )

    return render(
        request,
        "admissions/student_login.html",
        {
            "form": form,
        },
    )


# ============================================================
# STUDENT PROFILE
# ============================================================

@student_required
def student_profile(request):

    student = get_object_or_404(
        Student,
        id=request.session[
            "student_id"
        ],
    )

    announcements = (
        Announcement.objects
        .filter(is_active=True)[:5]
    )

    return render(
        request,
        "admissions/student_profile.html",
        {
            "student": student,
            "qr_base64": _get_qr_base64(
                student
            ),
            "announcements": announcements,
        },
    )


# ============================================================
# STUDENT LOGOUT
# ============================================================

def student_logout(request):

    request.session.pop(
        "student_id",
        None,
    )

    auth_logout(request)

    messages.info(
        request,
        "You have been signed out.",
    )

    return redirect(
        "student_login"
    )


# ============================================================
# ADMIN LOGIN
# ============================================================

@csrf_protect
def admin_login(request):

    if request.method == "POST":

        username = (
            request.POST
            .get("username", "")
            .strip()
        )

        password = request.POST.get(
            "password",
            "",
        )

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if (
            user is not None
            and user.is_superuser
        ):

            if not user.email:

                messages.error(
                    request,
                    "This admin account has no email configured.",
                )

                return render(
                    request,
                    "admissions/admin_login.html",
                )

            # Generate OTP.
            otp = generate_otp(
                user.id
            )

            request.session[
                "pending_admin_id"
            ] = user.id

            # ------------------------------------------------
            # OTP email
            # ------------------------------------------------

            try:

                html_message = render_to_string(
                    "admissions/emails/admin_otp_email.html",
                    {
                        "otp": otp,
                        "user": user,
                    },
                )

            except Exception as exc:

                logger.warning(
                    "OTP email template unavailable: %s",
                    exc,
                )

                html_message = f"""
                <html>
                <body>
                    <h2>Infinity Academy Admin OTP</h2>
                    <p>
                        Your OTP code is:
                        <strong>{otp}</strong>
                    </p>
                    <p>
                        This OTP expires in 5 minutes.
                    </p>
                </body>
                </html>
                """

            plain_message = strip_tags(
                html_message
            )

            try:

                send_mail(
                    "Your Infinity Academy Admin OTP",
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=html_message,
                    fail_silently=False,
                )

                messages.info(
                    request,
                    "An OTP has been sent to your registered admin email.",
                )

            except Exception as exc:

                logger.exception(
                    "Admin OTP email failed: %s",
                    exc,
                )

                messages.error(
                    request,
                    "Could not send the OTP email. "
                    "Please check the email configuration.",
                )

                return render(
                    request,
                    "admissions/admin_login.html",
                )

            return redirect(
                "admin_otp"
            )

        messages.error(
            request,
            "Invalid credentials, or this account is not an admin.",
        )

    return render(
        request,
        "admissions/admin_login.html",
    )


# ============================================================
# ADMIN OTP
# ============================================================

@csrf_protect
def verify_otp(request):

    pending_id = request.session.get(
        "pending_admin_id"
    )

    if not pending_id:

        return redirect(
            "admin_login"
        )

    if request.method == "POST":

        entered = (
            request.POST
            .get("otp", "")
            .strip()
        )

        if check_otp(
            pending_id,
            entered,
        ):

            try:

                user = User.objects.get(
                    id=pending_id
                )

            except User.DoesNotExist:

                request.session.pop(
                    "pending_admin_id",
                    None,
                )

                messages.error(
                    request,
                    "Admin account could not be found.",
                )

                return redirect(
                    "admin_login"
                )

            auth_login(
                request,
                user,
            )

            request.session.pop(
                "pending_admin_id",
                None,
            )

            request.session[
                "otp_verified"
            ] = True

            request.session.modified = True

            messages.success(
                request,
                "Admin login successful.",
            )

            return redirect(
                "admin_panel"
            )

        messages.error(
            request,
            "Invalid or expired OTP. Please try again.",
        )

    pending_user = None

    try:

        pending_user = User.objects.get(
            id=pending_id
        )

    except User.DoesNotExist:

        pending_user = None

    return render(
        request,
        "admissions/admin_otp.html",
        {
            "user": pending_user,
        },
    )


# ============================================================
# ADMIN LOGOUT
# ============================================================

def admin_logout(request):

    if request.user.is_authenticated:

        clear_otp(
            request.user.id
        )

    auth_logout(request)

    request.session.flush()

    messages.info(
        request,
        "Logged out successfully.",
    )

    return redirect(
        "admin_login"
    )


# ============================================================
# ADMIN PANEL
# ============================================================

@otp_required
def admin_panel(request):

    pending = Student.objects.filter(
        payment_status=True,
        payment_verification="pending",
    )

    verified = Student.objects.filter(
        payment_verification="verified",
    )

    rejected = Student.objects.filter(
        payment_verification="rejected",
    )

    all_students = (
        Student.objects
        .all()
        .order_by("-admission_date")
    )

    return render(
        request,
        "admissions/admin_panel.html",
        {
            "pending": pending,
            "verified": verified,
            "rejected": rejected,
            "all_students": all_students,
        },
    )


# ============================================================
# ADMIN VERIFY PAYMENT
# ============================================================

@csrf_protect
@otp_required
def admin_verify(
    request,
    student_id,
):

    student = get_object_or_404(
        Student,
        id=student_id,
    )

    if (
        student.payment_verification
        == "pending"
    ):

        student.payment_verification = (
            "verified"
        )

        student.save(
            update_fields=[
                "payment_verification"
            ]
        )

        messages.success(
            request,
            f"Payment for "
            f"{student.full_name} verified.",
        )

    return redirect(
        "admin_panel"
    )


# ============================================================
# ADMIN REJECT PAYMENT
# ============================================================

@csrf_protect
@otp_required
def admin_reject(
    request,
    student_id,
):

    student = get_object_or_404(
        Student,
        id=student_id,
    )

    if (
        student.payment_verification
        == "pending"
    ):

        student.payment_verification = (
            "rejected"
        )

        student.payment_status = False
        student.amount_paid = 0
        student.transaction_id = None
        student.payment_date = None

        student.save()

        messages.warning(
            request,
            f"Payment for "
            f"{student.full_name} rejected.",
        )

    return redirect(
        "admin_panel"
    )


# ============================================================
# ANNOUNCEMENTS
# ============================================================

@csrf_protect
@otp_required
def announcement_list(request):

    if request.method == "POST":

        form = AnnouncementForm(
            request.POST
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Announcement posted.",
            )

            return redirect(
                "announcement_list"
            )

    else:

        form = AnnouncementForm()

    announcements = (
        Announcement.objects
        .all()
        .order_by("-id")
    )

    return render(
        request,
        "admissions/announcements.html",
        {
            "form": form,
            "announcements": announcements,
        },
    )


# ============================================================
# CREATE ANNOUNCEMENT
# ============================================================

@csrf_protect
@otp_required
def announcement_create(request):

    if request.method == "POST":

        form = AnnouncementForm(
            request.POST
        )

        if form.is_valid():

            form.save()

            messages.success(
                request,
                "Announcement created.",
            )

            return redirect(
                "announcement_list"
            )

    else:

        form = AnnouncementForm()

    announcements = (
        Announcement.objects
        .all()
        .order_by("-id")
    )

    return render(
        request,
        "admissions/announcements.html",
        {
            "form": form,
            "announcements": announcements,
        },
    )


# ============================================================
# TOGGLE ANNOUNCEMENT
# ============================================================

@csrf_protect
@otp_required
def announcement_toggle(
    request,
    announcement_id,
):

    announcement = get_object_or_404(
        Announcement,
        id=announcement_id,
    )

    announcement.is_active = (
        not announcement.is_active
    )

    announcement.save(
        update_fields=[
            "is_active"
        ]
    )

    return redirect(
        "announcement_list"
    )


# ============================================================
# DELETE ANNOUNCEMENT
# ============================================================

@csrf_protect
@otp_required
def announcement_delete(
    request,
    announcement_id,
):

    announcement = get_object_or_404(
        Announcement,
        id=announcement_id,
    )

    announcement.delete()

    messages.info(
        request,
        "Announcement deleted.",
    )

    return redirect(
        "announcement_list"
    )


# ============================================================
# CONTACT PAGE
# ============================================================

@csrf_protect
def contact(request):
    """
    Public contact/complaint form.

    Messages are sent to the configured academy
    contact email address.
    """

    if request.method != "POST":

        return render(
            request,
            "admissions/contact.html",
        )

    # --------------------------------------------------------
    # Read values
    # --------------------------------------------------------

    name = (
        request.POST
        .get("name", "")
        .strip()
    )

    email = (
        request.POST
        .get("email", "")
        .strip()
        .lower()
    )

    subject = (
        request.POST
        .get("subject", "")
        .strip()
    )

    complaint_type = (
        request.POST
        .get("complaint_type", "")
        .strip()
    )

    message = (
        request.POST
        .get("message", "")
        .strip()
    )

    # --------------------------------------------------------
    # Validate name
    # --------------------------------------------------------

    if not name:

        messages.error(
            request,
            "Please enter your name.",
        )

        return redirect(
            "contact"
        )

    if len(name) > 100:

        messages.error(
            request,
            "Name is too long.",
        )

        return redirect(
            "contact"
        )

    # --------------------------------------------------------
    # Validate email
    # --------------------------------------------------------

    email_pattern = (
        r"^[A-Za-z0-9._%+-]+@"
        r"[A-Za-z0-9.-]+\.[A-Za-z]{2,}$"
    )

    if not email or not re.match(
        email_pattern,
        email,
    ):

        messages.error(
            request,
            "Please enter a valid email address.",
        )

        return redirect(
            "contact"
        )

    if len(email) > 254:

        messages.error(
            request,
            "Email address is too long.",
        )

        return redirect(
            "contact"
        )

    # --------------------------------------------------------
    # Validate complaint type
    # --------------------------------------------------------

    allowed_types = {
        "admission",
        "payment",
        "technical",
        "complaint",
        "suggestion",
        "general",
        "other",
    }

    if complaint_type not in allowed_types:

        messages.error(
            request,
            "Please select a valid message type.",
        )

        return redirect(
            "contact"
        )

    # --------------------------------------------------------
    # Subject
    # --------------------------------------------------------

    if not subject:

        subject = "New Contact Message"

    if len(subject) > 200:

        messages.error(
            request,
            "Subject is too long.",
        )

        return redirect(
            "contact"
        )

    # --------------------------------------------------------
    # Message
    # --------------------------------------------------------

    if not message:

        messages.error(
            request,
            "Please enter your message.",
        )

        return redirect(
            "contact"
        )

    if len(message) > 5000:

        messages.error(
            request,
            "Message is too long. "
            "Maximum 5000 characters.",
        )

        return redirect(
            "contact"
        )

    # --------------------------------------------------------
    # Contact recipient
    # --------------------------------------------------------

    recipient_email = getattr(
        settings,
        "CONTACT_EMAIL",
        "",
    )

    if not recipient_email:

        recipient_email = getattr(
            settings,
            "ADMIN_EMAIL",
            settings.DEFAULT_FROM_EMAIL,
        )

    # --------------------------------------------------------
    # Email subject
    # --------------------------------------------------------

    email_subject = (
        f"[Infinity Academy Contact] {subject}"
    )

    # --------------------------------------------------------
    # Email body
    # --------------------------------------------------------

    email_body = f"""
Infinity Academy
Contact Form Submission

============================================================

Name:
{name}

Email:
{email}

Message Type:
{complaint_type}

Subject:
{subject}

============================================================

Message:

{message}

============================================================

This message was submitted through the
Infinity Academy Contact Us page.

Reply directly to this email to respond to the visitor.
"""

    # --------------------------------------------------------
    # Send email
    # --------------------------------------------------------

    try:

        send_mail(
            subject=email_subject,
            message=email_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[
                recipient_email
            ],
            fail_silently=False,
            reply_to=[
                email
            ],
        )

        logger.info(
            "Contact form email sent successfully. "
            "From=%s To=%s Type=%s",
            email,
            recipient_email,
            complaint_type,
        )

        messages.success(
            request,
            "Your message has been sent successfully. "
            "We will get back to you soon.",
        )

    except Exception as exc:

        logger.exception(
            "Contact form email failed: %s",
            exc,
        )

        messages.error(
            request,
            "We could not send your message right now. "
            "Please try again or contact us directly.",
        )

    return redirect(
        "contact"
    )