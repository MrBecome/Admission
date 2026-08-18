from django import forms
from django.contrib.auth.forms import SetPasswordForm
from .models import Student, Announcement, Course

# Natural academic order for class-level optgroups. Plain alphabetical sorting of
# Roman numerals would put 'IX' before 'VI', which reads wrong to an applicant -
# so classes are ordered academically, while subjects within each class are
# still sorted alphabetically as requested.
CLASS_LEVEL_ORDER = ['VI', 'VII', 'VIII', 'IX', 'X']


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ['full_name', 'email', 'phone', 'course', 'address']
        widgets = {
            'address': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''
        self._build_grouped_course_choices()

    def _build_grouped_course_choices(self):
        """Groups Course objects by class_level so the <select> renders as
        <optgroup> blocks - pick a Class first, then a Subject within it."""
        courses = Course.objects.exclude(class_level='LEGACY').order_by('class_level', 'subject')
        grouped = {}
        for course in courses:
            label = course.subject
            if course.official_name and course.official_name != course.subject:
                label = f"{course.subject} \u2014 {course.official_name}"
            grouped.setdefault(course.class_level, []).append((course.pk, label))

        ordered_levels = [lvl for lvl in CLASS_LEVEL_ORDER if lvl in grouped]
        ordered_levels += sorted(lvl for lvl in grouped if lvl not in CLASS_LEVEL_ORDER)

        grouped_choices = [('', 'Select your class & subject')]
        for level in ordered_levels:
            group_label = f"Class {level}"
            grouped_choices.append((group_label, grouped[level]))

        self.fields['course'].choices = grouped_choices


class StudentSetPasswordForm(SetPasswordForm):
    """Lets a newly admitted student set their own login password."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''


class StudentAuthForm(forms.Form):
    username = forms.CharField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''


class AnnouncementForm(forms.ModelForm):
    class Meta:
        model = Announcement
        fields = ['title', 'message', 'is_active']
        widgets = {
            'message': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.label_suffix = ''
