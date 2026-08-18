from django import forms
from django.contrib.auth.forms import AuthenticationForm
from apps.users.models import User
from apps.departments.models import Department, Branch

class UserLoginForm(AuthenticationForm):
    username = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter your username',
            'id': 'login-username'
        })
    )
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Enter your password',
            'id': 'login-password'
        })
    )


class UserCreationRBACForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={'class': 'form-control', 'placeholder': 'Set default password'}),
        required=True,
        initial='admin123'
    )

    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'role', 'department', 'branch', 'employee_id',
            'designation', 'phone', 'joining_date'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. jdoe'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'First Name'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Last Name'}),
            'email': forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'john.doe@company.com'}),
            'role': forms.Select(attrs={'class': 'form-select', 'id': 'role-select'}),
            'department': forms.Select(attrs={'class': 'form-select', 'id': 'department-select'}),
            'branch': forms.Select(attrs={'class': 'form-select', 'id': 'branch-select'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'EMP-1001'}),
            'designation': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'e.g. Senior Graphic Designer'}),
            'phone': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+1 (555) 000-0000'}),
            'joining_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user

        # Filter assignable roles based on acting user authority
        if acting_user:
            allowed_roles = acting_user.get_assignable_roles()
            self.fields['role'].choices = allowed_roles
            
            # If acting user is Manager or Dept Manager, restrict department
            if acting_user.role == User.Role.DEPT_MANAGER and acting_user.department:
                self.fields['department'].queryset = Department.objects.filter(id=acting_user.department_id)
                self.fields['department'].initial = acting_user.department
                if acting_user.branch:
                    self.fields['branch'].queryset = Branch.objects.filter(id=acting_user.branch_id)
                    self.fields['branch'].initial = acting_user.branch

    def clean_role(self):
        role = self.cleaned_data.get('role')
        if self.acting_user and not self.acting_user.can_assign_role(role):
            raise forms.ValidationError(
                f"You do not have permission to assign the role of '{role}'."
            )
        return role

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get('password')
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user


class UserUpdateRBACForm(forms.ModelForm):
    class Meta:
        model = User
        fields = [
            'username', 'first_name', 'last_name', 'email',
            'role', 'department', 'branch', 'employee_id',
            'designation', 'phone', 'joining_date', 'bio', 'is_active'
        ]
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control'}),
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'role': forms.Select(attrs={'class': 'form-select'}),
            'department': forms.Select(attrs={'class': 'form-select'}),
            'branch': forms.Select(attrs={'class': 'form-select'}),
            'employee_id': forms.TextInput(attrs={'class': 'form-control'}),
            'designation': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'joining_date': forms.DateInput(attrs={'class': 'form-control', 'type': 'date'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }

    def __init__(self, *args, acting_user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.acting_user = acting_user
        if acting_user:
            allowed_roles = acting_user.get_assignable_roles()
            # Include instance's current role if not already in allowed roles
            current_role_choice = (self.instance.role, self.instance.get_role_display())
            if current_role_choice not in allowed_roles:
                allowed_roles = [current_role_choice] + list(allowed_roles)
            self.fields['role'].choices = allowed_roles
            
            # If acting user cannot assign roles, disable role change
            if not acting_user.can_assign_role(self.instance.role) and not acting_user.is_super_or_server_admin():
                self.fields['role'].disabled = True


class UserSelfProfileForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'bio']
        widgets = {
            'first_name': forms.TextInput(attrs={'class': 'form-control'}),
            'last_name': forms.TextInput(attrs={'class': 'form-control'}),
            'email': forms.EmailInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'bio': forms.Textarea(attrs={'class': 'form-control', 'rows': 3}),
        }


class UserRegistrationForm(forms.ModelForm):
    password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Create password (min 6 chars)',
            'id': 'register-password'
        }),
        required=True,
        min_length=6
    )
    confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'Confirm your password',
            'id': 'register-confirm-password'
        }),
        required=True
    )

    class Meta:
        model = User
        fields = ['username', 'email', 'phone', 'department']
        widgets = {
            'username': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'Choose username',
                'id': 'register-username'
            }),
            'email': forms.EmailInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': 'name@company.com',
                'id': 'register-email'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control form-control-lg',
                'placeholder': '+1 (555) 000-0000',
                'id': 'register-phone'
            }),
            'department': forms.Select(attrs={
                'class': 'form-select form-select-lg',
                'id': 'register-department'
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['department'].queryset = Department.objects.all().order_by('name')
        self.fields['department'].empty_label = "Select Department (Optional)"
        self.fields['email'].required = True

    def clean_username(self):
        username = self.cleaned_data.get('username')
        if User.objects.filter(username__iexact=username).exists():
            raise forms.ValidationError("A user with this username already exists.")
        return username

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get('password')
        confirm_password = cleaned_data.get('confirm_password')
        if password and confirm_password and password != confirm_password:
            self.add_error('confirm_password', "Passwords do not match.")
        return cleaned_data

    def save(self, commit=True):
        import datetime
        user = super().save(commit=False)
        user.set_password(self.cleaned_data.get('password'))
        user.role = User.Role.STAFF
        user.designation = 'Staff / Employee'
        user.is_staff = False
        user.is_superuser = False
        if not user.employee_id:
            count = User.objects.count() + 1
            user.employee_id = f"EMP-{1000 + count}"
        if not user.joining_date:
            user.joining_date = datetime.date.today()
        if commit:
            user.save()
        return user


class UserAssignmentForm(forms.ModelForm):
    role = forms.ChoiceField(
        choices=User.Role.choices,
        widget=forms.Select(attrs={'class': 'form-select form-select-lg', 'id': 'assign-role-select'}),
        required=True
    )
    department = forms.ModelChoiceField(
        queryset=Department.objects.all().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select form-select-lg', 'id': 'assign-dept-select'}),
        required=False,
        empty_label="Select Department (or None / HQ)"
    )
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all().order_by('name'),
        widget=forms.Select(attrs={'class': 'form-select form-select-lg', 'id': 'assign-branch-select'}),
        required=False,
        empty_label="Select Branch / Division (Optional)"
    )
    designation = forms.CharField(
        widget=forms.TextInput(attrs={
            'class': 'form-control form-control-lg',
            'placeholder': 'e.g. Senior Backend Engineer / HR Specialist / Branch Manager',
            'id': 'assign-designation'
        }),
        required=False
    )

    class Meta:
        model = User
        fields = ['role', 'department', 'branch', 'designation']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            if self.instance.department:
                self.fields['branch'].queryset = Branch.objects.filter(department=self.instance.department)
            else:
                self.fields['branch'].queryset = Branch.objects.all()

    def save(self, commit=True):
        user = super().save(commit=False)
        # Ensure staff/superuser permissions align with level 1 assignment
        if user.role in [User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]:
            user.is_staff = True
            if user.role == User.Role.SUPERADMIN:
                user.is_superuser = True
        else:
            if not user.is_superuser:
                user.is_staff = False

        # Set default designation if empty based on role
        if not user.designation or user.designation == 'Staff / Employee':
            role_designations = {
                User.Role.SUPERADMIN: 'Chief Executive Officer / System Owner',
                User.Role.SERVER_ADMIN: 'Principal Server Architect',
                User.Role.HR: 'Human Resources Specialist',
                User.Role.MANAGER: 'Department / Branch Manager',
                User.Role.DEPT_MANAGER: 'Department Lead Manager',
                User.Role.EXECUTIVE: 'Executive Specialist',
                User.Role.INTERN: 'Graduate Intern',
                User.Role.STAFF: 'Operational Staff',
            }
            user.designation = role_designations.get(user.role, 'Staff / Employee')
        
        if commit:
            user.save()
        return user



