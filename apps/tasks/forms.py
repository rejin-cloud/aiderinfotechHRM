from django import forms
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.tasks.models import Task, TaskExtensionRequest, TaskSubmission
from apps.users.models import User


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={'class': 'form-control'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_file_clean = super().clean
        if isinstance(data, (list, tuple)):
            result = [single_file_clean(d, initial) for d in data]
        else:
            result = single_file_clean(data, initial)
        return result


class TaskForm(forms.ModelForm):
    documents = MultipleFileField(
        required=False,
        help_text="Attach one or more documents or project assets (accepts any file format: PSD, AI, PDF, ZIP, MP4, DOCX, PNG, etc.)."
    )

    class Meta:
        model = Task
        fields = [
            'task_number',
            'title',
            'description',
            'instructions',
            'priority',
            'status',
        ]
        widgets = {
            'task_number': forms.TextInput(attrs={
                'class': 'form-control font-monospace fw-bold',
                'placeholder': 'e.g. CR-TASK-001'
            }),
            'title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Brand Identity Overhaul for Q3 Campaign'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Describe the core task objectives, deliverables, and requirements...'
            }),
            'instructions': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Provide step-by-step instructions, creative direction, color palettes, export specs, or guidelines...'
            }),
            'priority': forms.Select(attrs={'class': 'form-select'}),
            'status': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('task_number'):
            dept_name = department.name if department else "Creative"
            self.initial['task_number'] = Task.generate_next_task_number(dept_name)

    def clean_task_number(self):
        tn = self.cleaned_data.get('task_number', '').strip().upper()
        if not tn:
            raise forms.ValidationError("Task number is required.")
        qs = Task.objects.filter(task_number__iexact=tn)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Task number '{tn}' is already assigned to another task.")
        return tn


class TaskFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-sm',
            'placeholder': 'Search task number, title, keywords...'
        })
    )
    priority = forms.ChoiceField(
        choices=[('', 'All Priorities')] + list(Task.Priority.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'onchange': 'this.form.submit()'})
    )
    status = forms.ChoiceField(
        choices=[('', 'All Statuses')] + list(Task.Status.choices),
        required=False,
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'onchange': 'this.form.submit()'})
    )

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)


class TaskCompletionForm(forms.ModelForm):
    """Form used by assigned member to mark task complete with remarks and media attachments."""
    submission_files = MultipleFileField(
        required=False,
        help_text="Attach completed media, deliverables, or final assets (accepts ANY file format: ZIP, PSD, AI, MP4, PDF, PNG, JPG, DOCX, etc.)."
    )

    class Meta:
        model = TaskSubmission
        fields = ['remarks']
        widgets = {
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Detail your completed deliverables, output summary, design decisions, links, and final remarks...',
                'required': True,
            })
        }


class TaskExtensionRequestForm(forms.ModelForm):
    """Form used by assigned member to request more days or task reassignment."""
    class Meta:
        model = TaskExtensionRequest
        fields = [
            'request_type',
            'requested_days',
            'requested_deadline',
            'reason',
        ]
        widgets = {
            'request_type': forms.RadioSelect(attrs={'class': 'form-check-input'}),
            'requested_days': forms.NumberInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. 3',
                'min': '1',
                'max': '60'
            }),
            'requested_deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Explain why you are requesting more days or why the task should be reassigned...',
                'required': True,
            })
        }

    def clean(self):
        cleaned_data = super().clean()
        req_type = cleaned_data.get('request_type')
        days = cleaned_data.get('requested_days')
        deadline = cleaned_data.get('requested_deadline')

        if req_type == TaskExtensionRequest.RequestType.MORE_DAYS:
            if not days and not deadline:
                raise forms.ValidationError("Please specify either the number of additional days or a new target deadline date.")
        return cleaned_data


class ManagerExtensionReviewForm(forms.Form):
    """Form used by Creative Department Manager to evaluate extension/reassignment request."""
    DECISION_CHOICES = [
        ('EXTEND', 'Grant More Days (Extend Deadline & Resume Task)'),
        ('REASSIGN', 'Reassign Task to Another Branch Member'),
        ('REJECT', 'Reject Request (Keep Task As Is)'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'required': True})
    )
    new_deadline = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    reassign_branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        empty_label="Select Branch",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_review_branch'})
    )
    reassign_user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Select Member",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_review_user'})
    )
    manager_remarks = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 3,
            'placeholder': 'Add feedback, guidance, or managerial explanation...'
        })
    )

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department:
            self.fields['reassign_branch'].queryset = Branch.objects.filter(department=department)
            self.fields['reassign_user'].queryset = User.objects.filter(department=department).exclude(role=User.Role.SUPERADMIN)
        else:
            self.fields['reassign_branch'].queryset = Branch.objects.all()
            self.fields['reassign_user'].queryset = User.objects.all().exclude(role=User.Role.SUPERADMIN)
