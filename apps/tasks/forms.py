from django import forms
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.tasks.models import (
    Client,
    ClientAssignment,
    ClientAssignmentSubmission,
    ClientAssignmentSubmissionAttachment,
    Task,
    TaskExtensionRequest,
    TaskSubmission,
)
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
    """Form used by assigned member to submit deliverable media and remarks for manager review."""
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
                'placeholder': 'Detail your completed deliverables, output summary, design decisions, links, and handover remarks...',
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


class ManagerSubmissionReviewForm(forms.Form):
    """Form used by Creative Department Manager to evaluate submitted deliverables."""
    DECISION_CHOICES = [
        ('APPROVE', 'Approve & Mark Completed (Deliverables Verified)'),
        ('REVISION', 'Request Revision from Member (Needs Work / Do Again)'),
        ('REASSIGN', 'Reassign Task to Another Branch Member'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'required': True})
    )
    manager_feedback = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Provide feedback, specific revision instructions, or approval appreciation notes...'
        })
    )
    new_deadline = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )
    reassign_branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        empty_label="Select Branch",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_sub_review_branch'})
    )
    reassign_user = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Select Member",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_sub_review_user'})
    )

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department:
            self.fields['reassign_branch'].queryset = Branch.objects.filter(department=department)
            self.fields['reassign_user'].queryset = User.objects.filter(department=department).exclude(role=User.Role.SUPERADMIN)
        else:
            self.fields['reassign_branch'].queryset = Branch.objects.all()
            self.fields['reassign_user'].queryset = User.objects.all().exclude(role=User.Role.SUPERADMIN)


class ClientForm(forms.ModelForm):
    class Meta:
        model = Client
        fields = [
            'client_number',
            'name',
            'company',
            'needs',
            'email',
            'phone',
            'address',
            'notes',
        ]
        widgets = {
            'client_number': forms.TextInput(attrs={
                'class': 'form-control font-monospace fw-bold',
                'placeholder': 'e.g. CR-CL-001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Sarah Jenkins'
            }),
            'company': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Nexus Media Group'
            }),
            'needs': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Specify the client’s creative needs, branding guidelines, deliverables, video editing, social media campaigns, etc.'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. client@company.com'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. +91 98765 43210'
            }),
            'address': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Office location / billing address...'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Internal notes, special instructions, or client preferences...'
            }),
        }

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk and not self.initial.get('client_number'):
            dept_name = department.name if department else "Creative"
            self.initial['client_number'] = Client.generate_next_client_number(dept_name)

    def clean_client_number(self):
        cn = self.cleaned_data.get('client_number', '').strip().upper()
        if not cn:
            raise forms.ValidationError("Client number is required.")
        qs = Client.objects.filter(client_number__iexact=cn)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Client number '{cn}' is already assigned to another client.")
        return cn


class CustomerForm(forms.ModelForm):
    """
    Used in HR / Management Customer Management module to add or edit external customers/clients for any department.
    """
    class Meta:
        model = Client
        fields = [
            'department',
            'client_number',
            'name',
            'company',
            'phone',
            'address',
            'email',
            'needs',
            'notes',
        ]
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select', 'id': 'id_customer_department'}),
            'client_number': forms.TextInput(attrs={
                'class': 'form-control font-monospace fw-bold',
                'placeholder': 'e.g. CR-CL-001 / MK-CL-001 / CUST-001'
            }),
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Customer Name / Contact Person (e.g. Sarah Jenkins / Rajesh Kumar)'
            }),
            'company': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Company / Brand / Organization (e.g. Apex Media / Nexus Group)'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control font-monospace',
                'placeholder': 'e.g. +91 98765 43210'
            }),
            'address': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Place / City / Location / Office Address (e.g. Kochi, Kerala / Bangalore / Dubai)'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. contact@clientcompany.com'
            }),
            'needs': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 3,
                'placeholder': 'Customer creative/service requirements, deliverables, campaign scope, technology stack, etc.'
            }),
            'notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Internal notes, communication preferences, referral details...'
            }),
        }
        labels = {
            'department': 'Department Associated With',
            'client_number': 'Customer Code / ID',
            'name': 'Customer / Client Name',
            'company': 'Company / Brand Name',
            'address': 'Place / City / Location',
            'phone': 'Contact Phone / WhatsApp',
            'email': 'Email Address',
            'needs': 'Requirements / Scope of Work',
            'notes': 'Internal Notes & Guidelines',
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].empty_label = "Select Department"
        self.fields['department'].required = True
        self.fields['name'].required = True
        self.fields['company'].required = True
        self.fields['phone'].required = True
        if not self.instance.pk and not self.initial.get('client_number'):
            first_dept = Department.objects.first()
            dept_name = first_dept.name if first_dept else "Creative"
            self.initial['client_number'] = Client.generate_next_client_number(dept_name)

    def clean_client_number(self):
        cn = self.cleaned_data.get('client_number', '').strip().upper()
        if not cn:
            raise forms.ValidationError("Customer code / Client number is required.")
        qs = Client.objects.filter(client_number__iexact=cn)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError(f"Customer code '{cn}' is already assigned to another customer.")
        return cn


class CustomerFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by customer name, place, phone, company, or customer code...'
        })
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all(),
        required=False,
        empty_label="All Departments",
        widget=forms.Select(attrs={'class': 'form-select'})
    )


class ClientFilterForm(forms.Form):
    q = forms.CharField(
        required=False,
        widget=forms.TextInput(attrs={
            'class': 'form-control',
            'placeholder': 'Search by client #, name, company, or needs...'
        })
    )


class ClientAssignmentForm(forms.ModelForm):
    """
    Used by Creative Department Manager to assign a client to a branch and its Executive for a specific task.
    """
    class Meta:
        model = ClientAssignment
        fields = [
            'client',
            'branch',
            'executive',
            'task_title',
            'task_scope',
            'deadline',
        ]
        widgets = {
            'client': forms.Select(attrs={'class': 'form-select', 'id': 'id_assign_client'}),
            'branch': forms.Select(attrs={'class': 'form-select', 'id': 'id_assign_branch'}),
            'executive': forms.Select(attrs={'class': 'form-select', 'id': 'id_assign_executive'}),
            'task_title': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'e.g. Marketing Campaign, Brand Identity Designing, 4K Video Production'
            }),
            'task_scope': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Specify branch-specific deliverables, creative instructions, formats, and scope...'
            }),
            'deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
        }

    def __init__(self, *args, department=None, initial_client=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department:
            self.fields['client'].queryset = Client.objects.filter(department=department)
            self.fields['branch'].queryset = Branch.objects.filter(department=department)
            self.fields['executive'].queryset = User.objects.filter(
                department=department,
                role=User.Role.EXECUTIVE
            )
        else:
            self.fields['client'].queryset = Client.objects.all()
            self.fields['branch'].queryset = Branch.objects.all()
            self.fields['executive'].queryset = User.objects.filter(role=User.Role.EXECUTIVE)

        if initial_client:
            self.fields['client'].initial = initial_client


class ExecutiveDelegationForm(forms.ModelForm):
    """
    Used by Branch Executive to assign / delegate a received client task to staff members or interns in their branch.
    """
    class Meta:
        model = ClientAssignment
        fields = [
            'delegated_member',
            'executive_notes',
            'deadline',
        ]
        widgets = {
            'delegated_member': forms.Select(attrs={'class': 'form-select'}),
            'executive_notes': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Provide step-by-step guidance, creative specifications, review checkpoints, or asset guidelines to your team member...'
            }),
            'deadline': forms.DateTimeInput(attrs={
                'class': 'form-control',
                'type': 'datetime-local'
            }),
        }

    def __init__(self, *args, branch=None, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        member_qs = User.objects.filter(role__in=[User.Role.STAFF, User.Role.INTERN])
        if branch:
            member_qs = member_qs.filter(branch=branch)
        elif department:
            member_qs = member_qs.filter(department=department)
        self.fields['delegated_member'].queryset = member_qs
        self.fields['delegated_member'].required = True
        self.fields['delegated_member'].label = "Assign to Branch Member / Intern"


class ClientAssignmentSubmissionForm(forms.ModelForm):
    """
    Used by assigned Staff member or Intern to submit deliverable details & media files
    to their direct Branch Executive.
    """
    class Meta:
        model = ClientAssignmentSubmission
        fields = ['remarks']
        widgets = {
            'remarks': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 5,
                'placeholder': 'Detail your completed work, output specifications, design/campaign links, and deliverables overview...',
                'required': True,
            })
        }
        labels = {
            'remarks': 'Work Completion Summary & Deliverables Overview'
        }


class ClientAssignmentExecutiveReviewForm(forms.Form):
    """
    Used by Branch Executive to review delegate's submission:
    1. FORWARD_TO_MANAGER: Satisfied -> Forward to Department Manager for final approval.
    2. REQUEST_REVISION: Not Satisfied -> Request delegate to redo / revise with feedback.
    3. REASSIGN: Reassign task to another member/intern in the branch.
    """
    DECISION_CHOICES = [
        ('FORWARD_TO_MANAGER', 'Satisfied — Forward to Department Manager for Final Approval'),
        ('REQUEST_REVISION', 'Not Satisfied — Request Delegate to Redo / Revise'),
        ('REASSIGN', 'Reassign Task to Another Branch Member / Intern'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'required': True})
    )
    feedback = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Provide feedback, specific revision requirements, or recommendation notes for your Department Manager...'
        })
    )
    reassign_to = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Select New Delegate",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_reassign_to'})
    )
    new_deadline = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )

    def __init__(self, *args, branch=None, **kwargs):
        super().__init__(*args, **kwargs)
        if branch:
            self.fields['reassign_to'].queryset = User.objects.filter(
                branch=branch,
                role__in=[User.Role.STAFF, User.Role.INTERN]
            )
        else:
            self.fields['reassign_to'].queryset = User.objects.filter(
                role__in=[User.Role.STAFF, User.Role.INTERN]
            )


class ClientAssignmentManagerReviewForm(forms.Form):
    """
    Used by Creative Department Manager for final approval and completion.
    1. APPROVE: Verifies deliverables and marks assignment COMPLETED.
    2. REQUEST_REVISION: Requests revision or adjustments from branch team.
    3. REASSIGN_BRANCH: Reassigns client task to another branch / executive.
    """
    DECISION_CHOICES = [
        ('APPROVE', 'Final Approval — Mark Completed (Deliverables Verified)'),
        ('REQUEST_REVISION', 'Request Modifications / Revisions from Branch Team'),
        ('REASSIGN_BRANCH', 'Reassign to Another Branch & Executive'),
    ]

    decision = forms.ChoiceField(
        choices=DECISION_CHOICES,
        widget=forms.RadioSelect(attrs={'class': 'form-check-input', 'required': True})
    )
    manager_feedback = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'form-control',
            'rows': 4,
            'placeholder': 'Add executive feedback, appreciation notes, or revision directions...'
        })
    )
    reassign_branch = forms.ModelChoiceField(
        queryset=Branch.objects.none(),
        required=False,
        empty_label="Select Target Branch",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_mgr_reassign_branch'})
    )
    reassign_executive = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        empty_label="Select Branch Executive",
        widget=forms.Select(attrs={'class': 'form-select', 'id': 'id_mgr_reassign_executive'})
    )
    new_deadline = forms.DateTimeField(
        required=False,
        widget=forms.DateTimeInput(attrs={'class': 'form-control', 'type': 'datetime-local'})
    )

    def __init__(self, *args, department=None, **kwargs):
        super().__init__(*args, **kwargs)
        if department:
            self.fields['reassign_branch'].queryset = Branch.objects.filter(department=department)
            self.fields['reassign_executive'].queryset = User.objects.filter(
                department=department,
                role=User.Role.EXECUTIVE
            )
        else:
            self.fields['reassign_branch'].queryset = Branch.objects.all()
            self.fields['reassign_executive'].queryset = User.objects.filter(role=User.Role.EXECUTIVE)


