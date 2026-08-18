from django import forms
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.tasks.models import Task
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
            'deadline',
            'branch',
            'assigned_to',
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
            'deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'assigned_to': forms.Select(attrs={'class': 'form-select'}),
        }

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department:
            self.fields['branch'].queryset = Branch.objects.filter(department=department)
            self.fields['assigned_to'].queryset = User.objects.filter(department=department).exclude(role=User.Role.SUPERADMIN)
            self.fields['branch'].empty_label = "All Department Branches"
            self.fields['assigned_to'].empty_label = "All Department Members (Team Task)"
        else:
            self.fields['branch'].empty_label = "All Branches"
            self.fields['assigned_to'].empty_label = "All Department Members"

        # If creating new task and no initial task_number, pre-fill
        if not self.instance.pk and not self.initial.get('task_number'):
            dept_name = department.name if department else "Creative"
            self.initial['task_number'] = Task.generate_next_task_number(dept_name)

    def clean_task_number(self):
        tn = self.cleaned_data.get('task_number', '').strip().upper()
        if not tn:
            raise forms.ValidationError("Task number is required.")
        # Check uniqueness excluding self
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
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        empty_label="All Branches",
        widget=forms.Select(attrs={'class': 'form-select form-select-sm', 'onchange': 'this.form.submit()'})
    )

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department:
            self.fields['branch'].queryset = Branch.objects.filter(department=department)
