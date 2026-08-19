from django import forms
from django.utils import timezone
from .models import Candidate
from apps.departments.models import Department, Branch


class CandidateForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = [
            'name',
            'phone',
            'email',
            'place',
            'department',
            'branch',
            'role_applied',
            'designation_applied',
            'qualification',
            'experience_years',
            'resume',
            'notes',
        ]
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. John Doe / Sarah Jenkins'}),
            'phone': forms.TextInput(attrs={'class': 'form-control font-monospace', 'placeholder': 'e.g. +91 9876543210'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'e.g. candidate@example.com'}),
            'place': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Kochi, Kerala / Bangalore / Calicut'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'role_applied': forms.Select(attrs={'class': 'form-select'}),
            'designation_applied': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Graphic Designer / Video Editor / Marketing Executive'}),
            'qualification': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. B.Des / BCA / B.Tech / MBA / Diploma'}),
            'experience_years': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Fresher / 2+ Years / 4 Years'}),
            'resume': forms.FileInput(attrs={'class': 'form-control'}),
            'notes': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Key skills, portfolio links, interview notes, or source of application...'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].empty_label = "Select Department (Optional)"
        self.fields['branch'].empty_label = "Select Branch Wing (Optional)"


class CandidateCallLogForm(forms.Form):
    CALL_STATUS_CHOICES = [
        ('CALLED', 'Mark as Called (Pending Screening Decision)'),
        ('APPROVED', 'Mark as Called & Shortlist / Approve Immediately'),
        ('REJECTED', 'Mark as Called & Reject (Not Suitable / Declined)'),
    ]

    call_outcome = forms.ChoiceField(
        choices=CALL_STATUS_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='CALLED',
        label="Call Outcome / Status Update"
    )
    call_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Summarize phone conversation: candidate availability, communication skills, expected salary, notice period, interest level, etc...'
        }),
        required=True,
        label="Discussion & Screening Notes"
    )
    call_rating = forms.ChoiceField(
        choices=[
            ('', '-- Select Evaluation Rating --'),
            (1, '1 - Poor Fit / Not Interested'),
            (2, '2 - Fair'),
            (3, '3 - Good / Promising'),
            (4, '4 - Very Good Candidate'),
            (5, '5 - Exceptional / Top Priority'),
        ],
        widget=forms.Select(attrs={'class': 'form-select'}),
        required=False,
        label="Screening Rating"
    )


class CandidateDecisionForm(forms.Form):
    DECISION_CHOICES = [
        ('APPROVED', 'Approve Candidate (Shortlist for Interview)'),
        ('REJECTED', 'Reject Candidate'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input'}),
        initial='APPROVED',
        label="Screening Decision"
    )
    approval_notes = forms.CharField(
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add justification or feedback for this shortlisting / rejection decision...'
        }),
        required=False,
        label="Decision Feedback Remarks"
    )


class InterviewScheduleForm(forms.ModelForm):
    class Meta:
        model = Candidate
        fields = [
            'interview_date',
            'interview_time',
            'interview_mode',
            'interview_location',
            'interviewer_name',
            'interview_instructions',
        ]
        widgets = {
            'interview_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'interview_time': forms.TimeInput(attrs={'class': 'form-control', 'type': 'time'}),
            'interview_mode': forms.Select(attrs={'class': 'form-select'}),
            'interview_location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. HQ Office Conference Room 2, or Google Meet Link / Zoom URL'}),
            'interviewer_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. John Doe (Design Lead) & HR Team'}),
            'interview_instructions': forms.Textarea(attrs={'class': 'form-control', 'rows': 3, 'placeholder': 'Instructions for candidate: Bring hard copy portfolio, prepare presentation, test camera/mic, etc.'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['interview_date'].required = True
        self.fields['interview_time'].required = True
