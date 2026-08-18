from django import forms
from apps.departments.models import Department, Branch

class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ['name', 'description']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'e.g. Aider Creative, IT Club, Marketing'
            }),
            'description': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Brief description of department scope and operations...'
            }),
        }


class BranchForm(forms.ModelForm):
    class Meta:
        model = Branch
        fields = ['department', 'name', 'location']
        widgets = {
            'department': forms.Select(attrs={'class': 'form-select form-select-lg', 'id': 'branch-dept-select'}),
            'name': forms.TextInput(attrs={'class': 'form-control form-control-lg', 'placeholder': 'e.g. Marketing, IT Club Balussery, Calicut'}),
            'location': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. 4th Floor, Tech Hub / Remote / Calicut Campus'}),
        }

    def __init__(self, *args, user=None, initial_dept=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and user.role == 'MANAGER' and user.department:
            # If manager has an assigned department, lock or default the department
            self.fields['department'].initial = user.department
        if initial_dept:
            self.fields['department'].initial = initial_dept
