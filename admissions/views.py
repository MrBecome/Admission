import base64
import logging
import os
import re
from functools import wraps

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate, login as auth_login, logout as auth_logout
from django.contrib.auth.models import User
from django.core import signing
from django.core.mail import send_mail
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
from django.http import Http404, JsonResponse
from django.views.decorators.csrf import csrf_protect, csrf_exempt
from django.middleware.csrf import get_token

from .forms import StudentForm, StudentSetPasswordForm, StudentAuthForm, AnnouncementForm
from .models import (
    Student, Announcement, FailedEmail, Course, ClassSummary, TuitionProgram,
)
from .security import generate_otp, verify_otp as check_otp, clear_otp

SET_PASSWORD_SALT = 'admissions-set-password'
SET_PASSWORD_MAX_AGE = 60 * 60 * 24  # 24 hours

logger = logging.getLogger(__name__)


# ---------------------------- DECORATORS ----------------------------
def otp_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated or not request.user.is_superuser or not request.session.get('otp_verified'):
            messages.info(request, "Please log in as admin to continue.")
            return redirect('admin_login')
        return view_func(request, *args, **kwargs)
    return wrapper


def student_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.session.get('student_id'):
            messages.info(request, "Please sign in to view your application status.")
            return redirect('student_login')
        return view_func(request, *args, **kwargs)
    return wrapper


# ---------------------------- QR CODE (STATIC) ----------------------------
def _get_qr_base64(student):
    """
    Returns a base64 PNG of the *fixed* payment QR image.
    The image is read from media/qr_codes/qr_1.png – same for every student.
    If the file is missing, returns None.
    """
    # Do not show QR if payment is already verified
    if student.payment_status and student.payment_verification == 'verified':
        return None

    qr_path = os.path.join(settings.MEDIA_ROOT, 'qr_codes', 'qr_1.png')
    if not os.path.exists(qr_path):
        logger.warning("Static QR image not found at %s", qr_path)
        return None

    with open(qr_path, 'rb') as f:
        return base64.b64encode(f.read()).decode()


# ---------------------------- PAYMENT RECEIPT (FIXED) ----------------------------
def payment_receipt(request, app_id):
    """
    ✅ FIXED: Supports both Application ID (e.g., IVA00000010) and
    numeric primary key (e.g., 10) seamlessly.
    """
    # Try to find student by application_id (string) OR numeric id
    try:
        student = Student.objects.get(application_id=app_id)
    except Student.DoesNotExist:
        try:
            # If app_id can be parsed as an integer, look up by numeric id
            student = Student.objects.get(id=int(app_id))
        except (Student.DoesNotExist, ValueError):
            raise Http404("No Student matches the given query.")

    # Check authorization: allow if student is logged in or session matches
    is_authorized = False
    if request.user.is_authenticated and request.user == student.user:
        is_authorized = True
    elif request.session.get('student_id') == student.id:
        is_authorized = True

    if not is_authorized:
        messages.error(request, "You are not authorized to view this receipt.")
        return redirect('student_login')

    # Only show receipt if payment is verified
    if not student.payment_status or student.payment_verification != 'verified':
        messages.info(request, "Payment is not yet verified. The receipt will be available after verification.")
        return redirect('success', student_id=student.id)

    return render(request, 'admissions/receipt.html', {'student': student})


# ---------------------------- AUTOCOMPLETE API ----------------------------
def autocomplete_search(request):
    term = request.GET.get('term', '').strip()
    results = []

    if len(term) >= 2:  # Only trigger after 2 characters are typed
        # 1. Search Announcements
        announcements = Announcement.objects.filter(
            Q(title__icontains=term) | Q(message__icontains=term)
        )[:3]
        for a in announcements:
            results.append({'label': f'📢 {a.title}', 'value': a.title})

        # 2. Search Courses
        courses = Course.objects.filter(
            Q(subject__icontains=term) | Q(official_name__icontains=term)
        )[:3]
        for c in courses:
            results.append({'label': f'📚 {c}', 'value': c.subject})

        # 3. Smart Links (Like Google's "Did you mean?")
        lower_term = term.lower()
        if any(w in lower_term for w in ('admission', 'apply', 'admit')):
            results.append({'label': '📝 Apply for Admission', 'value': 'admission'})
        if any(w in lower_term for w in ('track', 'status', 'application')):
            results.append({'label': '🔍 Track Your Application', 'value': 'track'})

    return JsonResponse(results, safe=False)


# ---------------------------- HELPERS ----------------------------
def generate_username(email):
    """Turns the part of an email before '@' into a unique Django username."""
    base = re.sub(r'[^a-zA-Z0-9_]', '', email.split('@')[0]).lower() or 'student'
    username = base
    counter = 1
    while User.objects.filter(username=username).exists():
        username = f'{base}{counter}'
        counter += 1
    return username


_LOGO_CACHE = {}


def _get_logo_base64():
    """Reads and caches the site logo as base64, for inline embedding in HTML emails."""
    if 'data' not in _LOGO_CACHE:
        logo_path = os.path.join(settings.BASE_DIR, 'static', 'images', 'logo.png')
        try:
            with open(logo_path, 'rb') as f:
                _LOGO_CACHE['data'] = base64.b64encode(f.read()).decode()
        except FileNotFoundError:
            _LOGO_CACHE['data'] = None
    return _LOGO_CACHE['data']


def _create_student_account_and_notify(request, student):
    """
    Creates the student's login account (no usable password yet) and
    emails the application ID plus a link to set a password. A copy of the
    email also goes to the admin address.
    """
    username = generate_username(student.email)
    user = User.objects.create_user(username=username, email=student.email)
    user.set_unusable_password()
    user.save()
    student.user = user
    student.save(update_fields=['user'])

    token = signing.dumps({'student_id': student.id}, salt=SET_PASSWORD_SALT)
    set_password_url = request.build_absolute_uri(reverse('set_password', args=[token]))
    application_id = f'IVA{student.id:06d}'
    course_display = str(student.course) if student.course else 'Not specified'

    subject = 'Admission Confirmation - Infinity Academy'
    
    # ✅ FIXED: Use correct template path with fallback
    try:
        html_message = render_to_string('admissions/emails/welcome_email.html', {
            'student': student,
            'application_id': application_id,
            'course_display': course_display,
            'username': username,
            'set_password_url': set_password_url,
            'logo_base64': _get_logo_base64(),
        })
    except Exception as e:
        logger.warning("Email template not found, using plain text: %s", e)
        html_message = f"""
        <html>
        <body>
            <h2>Welcome to Infinity Academy!</h2>
            <p>Dear {student.full_name},</p>
            <p>Your application has been received.</p>
            <p><strong>Application ID:</strong> {application_id}</p>
            <p><strong>Username:</strong> {username}</p>
            <p><strong>Course:</strong> {course_display}</p>
            <p>Click the link below to set your password:</p>
            <p><a href="{set_password_url}">{set_password_url}</a></p>
            <p>Thank you for applying to Infinity Academy!</p>
        </body>
        </html>
        """
    
    plain_message = strip_tags(html_message)

    recipient_list = [student.email]
    
    # ✅ FIXED: Try sending email with better error handling
    try:
        send_mail(
            subject,
            plain_message,
            settings.DEFAULT_FROM_EMAIL,
            recipient_list,
            html_message=html_message,
            fail_silently=False,
        )
        logger.info("Email sent successfully to %s", student.email)
        
        # ✅ Also send a copy to admin
        if settings.ADMIN_EMAIL:
            send_mail(
                f'[ADMIN COPY] {subject}',
                plain_message,
                settings.DEFAULT_FROM_EMAIL,
                [settings.ADMIN_EMAIL],
                html_message=html_message,
                fail_silently=True,
            )
            
    except Exception as exc:
        logger.error("Admission email failed for student %s: %s", student.id, exc)
        FailedEmail.objects.create(
            student=student,
            subject=subject,
            message=plain_message,
            recipient_list=', '.join(recipient_list),
            error=str(exc),
        )
        # ✅ Re-raise to let the calling view handle it
        raise


# ---------------------------- VIEWS ----------------------------
def search_view(request):
    query = request.GET.get('q', '').strip()
    announcements = classes = programs = courses = None
    smart_links = []

    if query:
        announcements = Announcement.objects.filter(
            Q(title__icontains=query) | Q(message__icontains=query)
        )
        classes = ClassSummary.objects.filter(
            Q(class_level__icontains=query) | Q(core_subjects__icontains=query)
        )
        programs = TuitionProgram.objects.filter(
            Q(name__icontains=query) | Q(coverage__icontains=query)
        )
        courses = Course.objects.exclude(class_level='LEGACY').filter(
            Q(subject__icontains=query) | Q(official_name__icontains=query)
        )

        lowered = query.lower()
        if any(word in lowered for word in ('admission', 'apply', 'admit')):
            smart_links.append({'label': 'Apply for Admission', 'url': reverse('admission_form')})
        if any(word in lowered for word in ('track', 'status', 'application')):
            smart_links.append({'label': 'Track Your Application', 'url': reverse('student_login')})

    has_results = bool(
        query and (
            (announcements and announcements.exists())
            or (classes and classes.exists())
            or (programs and programs.exists())
            or (courses and courses.exists())
            or smart_links
        )
    )

    return render(request, 'admissions/search_results.html', {
        'query': query,
        'announcements': announcements,
        'classes': classes,
        'programs': programs,
        'courses': courses,
        'smart_links': smart_links,
        'has_results': has_results,
    })


def home_view(request):
    announcements = Announcement.objects.filter(is_active=True)[:5]
    return render(request, 'admissions/home.html', {'announcements': announcements})


@csrf_protect
def admission_form(request):
    if request.method == 'POST':
        form = StudentForm(request.POST)
        if form.is_valid():
            student = form.save()
            email_sent = False
            try:
                _create_student_account_and_notify(request, student)
                email_sent = True
            except Exception as e:
                logger.error("Error in _create_student_account_and_notify for student %s: %s", student.id, e)
                # ✅ FIXED: Better error message
                messages.warning(
                    request,
                    "Your application was saved, but we could not send a confirmation email. "
                    "Please contact the registrar's office at admin@infinityacademy.com"
                )
            
            if email_sent:
                messages.success(
                    request,
                    "✅ Application received! Check your email for your Application ID "
                    "and a link to set your student-portal password."
                )
            
            return redirect('success', student_id=student.id)
        else:
            # ✅ FIXED: Show form errors
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f"{field}: {error}")
    else:
        form = StudentForm()
    
    return render(request, 'admissions/admission.html', {'form': form})


def success_view(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    return render(request, 'admissions/success.html', {
        'student': student,
        'qr_base64': _get_qr_base64(student)
    })


@csrf_protect
def mock_payment(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if student.payment_verification == 'verified':
        messages.info(request, "This student's payment is already verified.")
    elif student.payment_status and student.payment_verification == 'pending':
        messages.info(request, "Payment already submitted and awaiting verification.")
    else:
        student.payment_status = True
        student.amount_paid = 500.00
        student.transaction_id = 'TXN' + timezone.now().strftime('%Y%m%d%H%M%S%f')[:17]
        student.payment_date = timezone.now()
        student.payment_verification = 'pending'
        student.save()
        messages.success(request, f"Payment of ₹500 for {student.full_name} submitted. Awaiting admin verification.")
    return redirect('success', student_id=student.id)


# ---- Set password (from admission-confirmation email) ----
@csrf_protect
def set_password(request, token):
    try:
        data = signing.loads(token, salt=SET_PASSWORD_SALT, max_age=SET_PASSWORD_MAX_AGE)
    except signing.SignatureExpired:
        messages.error(request, "This link has expired. Please contact the registrar's office for a new one.")
        return redirect('student_login')
    except signing.BadSignature:
        messages.error(request, "This link is invalid.")
        return redirect('student_login')

    student = get_object_or_404(Student, id=data['student_id'])
    if not student.user:
        messages.error(request, "No login account is linked to this application.")
        return redirect('student_login')

    if request.method == 'POST':
        form = StudentSetPasswordForm(student.user, request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Password set. You can now sign in below.")
            return redirect('student_login')
    else:
        form = StudentSetPasswordForm(student.user)
    return render(request, 'admissions/set_password.html', {'form': form, 'student': student})


# ---- Student portal (username + password) ----
@csrf_protect
def student_password_setup_request(request):
    if request.method == 'POST':
        raw_app_no = request.POST.get('application_no', '')
        email = request.POST.get('email', '').strip()
        digits = ''.join(ch for ch in raw_app_no if ch.isdigit()).lstrip('0')
        student = None
        if digits and email:
            try:
                student = Student.objects.get(id=int(digits), email__iexact=email)
            except Student.DoesNotExist:
                student = None
        if student and student.user:
            token = signing.dumps({'student_id': student.id}, salt=SET_PASSWORD_SALT)
            return redirect('set_password', token=token)
        messages.error(request, "We couldn't find an application matching that number and email.")
    return render(request, 'admissions/student_password_request.html')


@csrf_protect
def student_login(request):
    if request.method == 'POST':
        form = StudentAuthForm(request.POST)
        if form.is_valid():
            user = authenticate(
                request,
                username=form.cleaned_data['username'],
                password=form.cleaned_data['password'],
            )
            if user is not None and hasattr(user, 'student_profile'):
                auth_login(request, user)
                request.session['student_id'] = user.student_profile.id
                return redirect('student_profile')
            messages.error(request, "Invalid username or password.")
    else:
        form = StudentAuthForm()
    return render(request, 'admissions/student_login.html', {'form': form})


@student_required
def student_profile(request):
    student = get_object_or_404(Student, id=request.session['student_id'])
    announcements = Announcement.objects.filter(is_active=True)[:5]
    return render(request, 'admissions/student_profile.html', {
        'student': student,
        'qr_base64': _get_qr_base64(student),
        'announcements': announcements,
    })


def student_logout(request):
    request.session.pop('student_id', None)
    auth_logout(request)
    messages.info(request, "You have been signed out.")
    return redirect('student_login')


# ---- Admin OTP login ----
@csrf_protect
def admin_login(request):
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None and user.is_superuser:
            if not user.email:
                messages.error(request, "This admin account has no email set - add one in /admin/ first.")
                return render(request, 'admissions/admin_login.html')
            
            otp = generate_otp(user.id)
            request.session['pending_admin_id'] = user.id
            
            # ✅ FIXED: Email template with fallback
            try:
                html_message = render_to_string('admissions/emails/admin_otp_email.html', {
                    'otp': otp,
                    'user': user
                })
            except Exception as e:
                logger.warning("OTP email template not found: %s", e)
                html_message = f"""
                <html>
                <body>
                    <h2>Admin OTP Verification</h2>
                    <p>Your OTP code is: <strong>{otp}</strong></p>
                    <p>This OTP expires in 5 minutes.</p>
                </body>
                </html>
                """
            
            plain_message = strip_tags(html_message)

            try:
                send_mail(
                    'Your Infinity Academy Admin OTP',
                    plain_message,
                    settings.DEFAULT_FROM_EMAIL,
                    [user.email],
                    html_message=html_message,
                    fail_silently=False,
                )
                messages.info(request, f"OTP sent to {user.email}. It expires in 5 minutes.")
            except Exception as e:
                logger.error("OTP email failed: %s", e)
                messages.error(request, "Could not send OTP email. Please check email configuration.")
                return render(request, 'admissions/admin_login.html')
            
            return redirect('admin_otp')
        messages.error(request, "Invalid credentials, or this account is not an admin.")
    return render(request, 'admissions/admin_login.html')


# ✅ FIXED: Added @csrf_protect to enforce CSRF token validation
@csrf_protect
def verify_otp(request):
    pending_id = request.session.get('pending_admin_id')
    if not pending_id:
        return redirect('admin_login')
    if request.method == 'POST':
        entered = request.POST.get('otp', '').strip()
        if check_otp(pending_id, entered):
            user = User.objects.get(id=pending_id)
            auth_login(request, user)

            # ✅ FIXED: Replaced `del` with `.pop()` to prevent KeyError
            request.session.pop('pending_admin_id', None)
            
            request.session['otp_verified'] = True
            messages.success(request, "Login successful.")
            return redirect('admin_panel')
        messages.error(request, "Invalid or expired OTP. Please try again.")

    # Display the OTP entry page — include the pending user's email in context so
    # the template can show where the OTP was sent.
    pending_user = None
    try:
        pending_user = User.objects.get(id=pending_id)
    except User.DoesNotExist:
        pending_user = None

    return render(request, 'admissions/admin_otp.html', {'user': pending_user})


def admin_logout(request):
    if request.user.is_authenticated:
        clear_otp(request.user.id)
    auth_logout(request)
    request.session.flush()
    messages.info(request, "Logged out.")
    return redirect('admin_login')


# ---- Admin panel (OTP-protected) ----
@otp_required
def admin_panel(request):
    pending = Student.objects.filter(payment_status=True, payment_verification='pending')
    verified = Student.objects.filter(payment_verification='verified')
    rejected = Student.objects.filter(payment_verification='rejected')
    all_students = Student.objects.all().order_by('-admission_date')
    return render(request, 'admissions/admin_panel.html', {
        'pending': pending,
        'verified': verified,
        'rejected': rejected,
        'all_students': all_students,
    })


@otp_required
def admin_verify(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if student.payment_verification == 'pending':
        student.payment_verification = 'verified'
        student.save()
        messages.success(request, f"Payment for {student.full_name} verified.")
    return redirect('admin_panel')


@otp_required
def admin_reject(request, student_id):
    student = get_object_or_404(Student, id=student_id)
    if student.payment_verification == 'pending':
        student.payment_verification = 'rejected'
        student.payment_status = False
        student.amount_paid = 0
        student.transaction_id = None
        student.payment_date = None
        student.save()
        messages.warning(request, f"Payment for {student.full_name} rejected.")
    return redirect('admin_panel')


# ---- Admin announcements ----
@otp_required
def announcement_list(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Announcement posted.")
            return redirect('announcement_list')
    else:
        form = AnnouncementForm()
    announcements = Announcement.objects.all()
    return render(request, 'admissions/announcements.html', {'form': form, 'announcements': announcements})


# ✅ FIXED: was pointing at a template that doesn't exist
# (admissions/announcement_create.html) - reuse the same combined
# list+create template announcement_list already renders successfully with.
@csrf_protect
@otp_required
def announcement_create(request):
    if request.method == 'POST':
        form = AnnouncementForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Announcement created.")
            return redirect('announcement_list')
    else:
        form = AnnouncementForm()
    announcements = Announcement.objects.all()
    return render(request, 'admissions/announcements.html', {'form': form, 'announcements': announcements})


@otp_required
def announcement_toggle(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.is_active = not announcement.is_active
    announcement.save()
    return redirect('announcement_list')


@otp_required
def announcement_delete(request, announcement_id):
    announcement = get_object_or_404(Announcement, id=announcement_id)
    announcement.delete()
    messages.info(request, "Announcement deleted.")
    return redirect('announcement_list')
