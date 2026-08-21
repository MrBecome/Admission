from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.forms import SetPasswordForm

from .models import Student, Announcement, Course


# ============================================================
# ACADEMIC CLASS ORDER
# ============================================================

CLASS_LEVEL_ORDER = [
    "VI",
    "VII",
    "VIII",
    "IX",
    "X",
]


# ============================================================
# STUDENT ADMISSION FORM
# ============================================================

class StudentForm(forms.ModelForm):
    """
    Admission form used by students applying to Infinity Academy.
    """

    class Meta:
        model = Student

        fields = [
            "full_name",
            "email",
            "phone",
            "course",
            "address",
        ]

        widgets = {
            "full_name": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter your full name",
                    "autocomplete": "name",
                    "required": True,
                }
            ),

            "email": forms.EmailInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter your email address",
                    "autocomplete": "email",
                    "required": True,
                }
            ),

            "phone": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Enter your phone number",
                    "autocomplete": "tel",
                    "inputmode": "tel",
                    "required": True,
                }
            ),

            "address": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 4,
                    "placeholder": "Enter your complete address",
                    "autocomplete": "street-address",
                    "required": True,
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.label_suffix = ""

        self._build_grouped_course_choices()

    # --------------------------------------------------------
    # Course dropdown
    # --------------------------------------------------------

    def _build_grouped_course_choices(self):
        """
        Creates an academic class → subject grouped dropdown.

        Example:

            Class VI
                Mathematics
                Science

            Class VII
                Mathematics
                Science

            Class VIII
                Mathematics
                Science
        """

        courses = (
            Course.objects
            .exclude(class_level="LEGACY")
            .order_by("class_level", "subject")
        )

        grouped = {}

        for course in courses:

            label = course.subject

            if (
                course.official_name
                and course.official_name != course.subject
            ):
                label = (
                    f"{course.subject} — "
                    f"{course.official_name}"
                )

            grouped.setdefault(
                course.class_level,
                []
            ).append(
                (
                    course.pk,
                    label,
                )
            )

        # ----------------------------------------------------
        # Academic ordering
        # ----------------------------------------------------

        ordered_levels = [
            level
            for level in CLASS_LEVEL_ORDER
            if level in grouped
        ]

        # Put any additional class levels after VI-X.
        ordered_levels += sorted(
            level
            for level in grouped
            if level not in CLASS_LEVEL_ORDER
        )

        # ----------------------------------------------------
        # Build Django optgroups
        # ----------------------------------------------------

        grouped_choices = [
            (
                "",
                "Select your class & subject",
            )
        ]

        for level in ordered_levels:

            grouped_choices.append(
                (
                    f"Class {level}",
                    grouped[level],
                )
            )

        self.fields["course"].choices = grouped_choices


# ============================================================
# STUDENT PASSWORD CREATION / RESET
# ============================================================

class StudentSetPasswordForm(SetPasswordForm):
    """
    Secure Django password creation/reset form.

    Django's SetPasswordForm handles:

        - Password confirmation
        - Password validation
        - AUTH_PASSWORD_VALIDATORS
        - Secure password hashing
        - Saving the password
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.label_suffix = ""

        # ----------------------------------------------------
        # Password 1
        # ----------------------------------------------------

        self.fields["new_password1"].label = (
            "New Password"
        )

        self.fields["new_password1"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Create a strong password",
            "autocomplete": "new-password",
            "required": True,
        })

        # ----------------------------------------------------
        # Password confirmation
        # ----------------------------------------------------

        self.fields["new_password2"].label = (
            "Confirm New Password"
        )

        self.fields["new_password2"].widget.attrs.update({
            "class": "form-control",
            "placeholder": "Enter the password again",
            "autocomplete": "new-password",
            "required": True,
        })


# ============================================================
# STUDENT PASSWORD SETUP / RESET VERIFICATION
# ============================================================

class StudentPasswordSetupRequestForm(forms.Form):
    """
    Verifies a student's identity before allowing them
    to create or reset their student portal password.

    Required information:

        1. Application Number
        2. Email Address

    Both values are verified against the Student database
    by the corresponding view.
    """

    # --------------------------------------------------------
    # Application Number
    # --------------------------------------------------------

    application_number = forms.CharField(
        label="Application Number",
        max_length=100,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your application number",
                "autocomplete": "off",
                "autocapitalize": "characters",
                "spellcheck": "false",
                "required": True,
            }
        ),
    )

    # --------------------------------------------------------
    # Email Address
    # --------------------------------------------------------
    #
    # IMPORTANT:
    # Do NOT add strip=True here.
    #
    # Django's EmailField already passes strip=True internally.
    # Adding strip=True again causes:
    #
    # TypeError:
    # CharField.__init__() got multiple values
    # for keyword argument 'strip'
    #
    # --------------------------------------------------------

    email = forms.EmailField(
        label="Email Address",
        widget=forms.EmailInput(
            attrs={
                "class": "form-control",
                "placeholder": (
                    "Enter the email used during admission"
                ),
                "autocomplete": "email",
                "inputmode": "email",
                "spellcheck": "false",
                "required": True,
            }
        ),
    )

    # --------------------------------------------------------
    # Clean application number
    # --------------------------------------------------------

    def clean_application_number(self):
        value = self.cleaned_data.get(
            "application_number"
        )

        if not value:
            return value

        return value.strip().upper()

    # --------------------------------------------------------
    # Clean email
    # --------------------------------------------------------

    def clean_email(self):
        value = self.cleaned_data.get(
            "email"
        )

        if not value:
            return value

        return value.strip().lower()


# ============================================================
# STUDENT LOGIN FORM
# ============================================================

class StudentAuthForm(forms.Form):
    """
    Student portal authentication form.

    Students log in using:

        Username
        Password

    Authentication is performed through Django's authentication
    framework. Passwords are never manually compared.
    """

    # --------------------------------------------------------
    # Username
    # --------------------------------------------------------

    username = forms.CharField(
        label="Username",
        max_length=150,
        strip=True,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your username",
                "autocomplete": "username",
                "spellcheck": "false",
                "required": True,
            }
        ),
    )

    # --------------------------------------------------------
    # Password
    # --------------------------------------------------------

    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control",
                "placeholder": "Enter your password",
                "autocomplete": "current-password",
                "required": True,
            }
        ),
    )

    def __init__(
        self,
        *args,
        request=None,
        **kwargs
    ):
        self.request = request
        self.user_cache = None

        super().__init__(
            *args,
            **kwargs
        )

        self.label_suffix = ""

    # --------------------------------------------------------
    # Authenticate student
    # --------------------------------------------------------

    def clean(self):
        cleaned_data = super().clean()

        username = cleaned_data.get(
            "username"
        )

        password = cleaned_data.get(
            "password"
        )

        if username and password:

            self.user_cache = authenticate(
                self.request,
                username=username,
                password=password,
            )

            # ------------------------------------------------
            # Invalid credentials
            # ------------------------------------------------

            if self.user_cache is None:

                raise forms.ValidationError(
                    "Invalid username or password."
                )

            # ------------------------------------------------
            # Inactive account
            # ------------------------------------------------

            if not self.user_cache.is_active:

                raise forms.ValidationError(
                    "This student account is currently inactive."
                )

        return cleaned_data

    # --------------------------------------------------------
    # Get authenticated user
    # --------------------------------------------------------

    def get_user(self):
        return self.user_cache


# ============================================================
# ANNOUNCEMENT FORM
# ============================================================

class AnnouncementForm(forms.ModelForm):
    """
    Admin form for creating and updating website announcements.
    """

    class Meta:
        model = Announcement

        fields = [
            "title",
            "message",
            "is_active",
        ]

        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "form-control",
                    "placeholder": "Announcement title",
                    "autocomplete": "off",
                    "required": True,
                }
            ),

            "message": forms.Textarea(
                attrs={
                    "class": "form-control",
                    "rows": 5,
                    "placeholder": (
                        "Write the announcement..."
                    ),
                }
            ),

            "is_active": forms.CheckboxInput(
                attrs={
                    "class": "form-check-input",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(
            *args,
            **kwargs
        )

        self.label_suffix = ""