from datetime import date
from django import forms
from django.utils import timezone
from apps.attendance.models import Attendance, LeaveRequest
from apps.departments.models import Department
from apps.users.models import User


class CheckInForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional check-in notes (e.g. Working from Lab / Client meeting)...'
        })
    )


class CheckOutForm(forms.Form):
    notes = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Optional daily summary or handoff notes...'
        })
    )


class LeaveApplicationForm(forms.ModelForm):
    """Standard Leave Application Form for employees below manager level (Executive, Staff, Intern)."""
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'is_half_day', 'half_day_period', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_half_day': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_is_half_day'}),
            'half_day_period': forms.Select(attrs={'class': 'form-select', 'id': 'id_half_day_period'}),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Please state the detailed reason for your leave application...'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        is_half_day = cleaned_data.get('is_half_day')
        half_day_period = cleaned_data.get('half_day_period')

        if start_date and end_date:
            if end_date < start_date:
                raise forms.ValidationError("End date cannot be earlier than start date.")

        if is_half_day:
            if not half_day_period:
                raise forms.ValidationError("Please select whether the half-day leave is for the First Half or Second Half.")
            if start_date and end_date and start_date != end_date:
                cleaned_data['end_date'] = start_date

        return cleaned_data


class ExecutiveLeaveApplicationForm(forms.ModelForm):
    """Separate Dedicated Leave Application Form for Server Admin, HR, and Manager level personals."""
    class Meta:
        model = LeaveRequest
        fields = ['leave_type', 'start_date', 'end_date', 'is_half_day', 'half_day_period', 'reason']
        widgets = {
            'leave_type': forms.Select(attrs={'class': 'form-select font-monospace'}),
            'start_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'end_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'is_half_day': forms.CheckboxInput(attrs={'class': 'form-check-input', 'id': 'id_exec_is_half_day'}),
            'half_day_period': forms.Select(attrs={'class': 'form-select', 'id': 'id_exec_half_day_period'}),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Detail your executive leave request, coverage plan, operational delegation, or emergency notes for Super Admin review...'
            }),
        }

    def clean(self):
        cleaned_data = super().clean()
        start_date = cleaned_data.get('start_date')
        end_date = cleaned_data.get('end_date')
        is_half_day = cleaned_data.get('is_half_day')
        half_day_period = cleaned_data.get('half_day_period')

        if start_date and end_date:
            if end_date < start_date:
                raise forms.ValidationError("End date cannot be earlier than start date.")

        if is_half_day:
            if not half_day_period:
                raise forms.ValidationError("Please select whether the half-day leave is for the First Half or Second Half.")
            if start_date and end_date and start_date != end_date:
                cleaned_data['end_date'] = start_date

        return cleaned_data


class DeptManagerReviewForm(forms.Form):
    ACTION_CHOICES = [
        ('RECOMMEND', 'Forward & Recommend to General Manager for Final Approval'),
        ('REJECT', 'Reject Application at Department Level'),
    ]
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add department review remarks or recommendations for the Manager...'
        })
    )


class ManagerFinalDecisionForm(forms.Form):
    ACTION_CHOICES = [
        ('APPROVE', 'Grant Official Final Approval'),
        ('REJECT', 'Decline / Reject Leave Request'),
    ]
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add official manager remarks or instructions...'
        })
    )


class SuperadminLeaveDecisionForm(forms.Form):
    """Evaluation form used by Super Admin to approve or reject executive leave requests."""
    ACTION_CHOICES = [
        ('APPROVE', 'Grant Official Super Admin Approval (Mark Leave Approved)'),
        ('REJECT', 'Decline / Reject Executive Leave Request'),
    ]
    action = forms.ChoiceField(
        choices=ACTION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'required': True})
    )
    notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Add Super Admin decision notes, delegation instructions, or remarks...'
        })
    )


class MonthlyReportFilterForm(forms.Form):
    MONTH_CHOICES = [
        (1, 'January'), (2, 'February'), (3, 'March'), (4, 'April'),
        (5, 'May'), (6, 'June'), (7, 'July'), (8, 'August'),
        (9, 'September'), (10, 'October'), (11, 'November'), (12, 'December')
    ]
    
    current_year = date.today().year
    YEAR_CHOICES = [(y, str(y)) for y in range(current_year - 2, current_year + 3)]

    month = forms.ChoiceField(
        choices=MONTH_CHOICES,
        initial=date.today().month,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    year = forms.ChoiceField(
        choices=YEAR_CHOICES,
        initial=current_year,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        empty_label="All Departments",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
    user = forms.ModelChoiceField(
        queryset=User.objects.exclude(role=User.Role.SUPERADMIN),
        required=False,
        empty_label="All Employees",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm'})
    )
