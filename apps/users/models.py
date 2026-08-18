from django.contrib.auth.models import AbstractUser
from django.db import models

class User(AbstractUser):
    class Role(models.TextChoices):
        SUPERADMIN = 'SUPERADMIN', 'Superadmin / Owner'
        SERVER_ADMIN = 'SERVER_ADMIN', 'Server Admin'
        HR = 'HR', 'HR'
        MANAGER = 'MANAGER', 'Manager'
        DEPT_MANAGER = 'DEPT_MANAGER', 'Department Manager'
        EXECUTIVE = 'EXECUTIVE', 'Executive'
        INTERN = 'INTERN', 'Intern'
        STAFF = 'STAFF', 'Staff'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.STAFF,
        db_index=True
    )
    department = models.ForeignKey(
        'departments.Department',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        db_index=True
    )
    branch = models.ForeignKey(
        'departments.Branch',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='users',
        db_index=True
    )
    
    # Extended profile attributes
    phone = models.CharField(max_length=25, blank=True, null=True)
    employee_id = models.CharField(max_length=30, blank=True, null=True, unique=True)
    designation = models.CharField(max_length=100, blank=True, null=True)
    joining_date = models.DateField(blank=True, null=True)
    bio = models.TextField(blank=True, null=True)
    avatar_color = models.CharField(max_length=20, default='#4f46e5')

    def is_super_or_server_admin(self):
        return self.role in [self.Role.SUPERADMIN, self.Role.SERVER_ADMIN]

    @property
    def level(self):
        if self.role in [self.Role.SUPERADMIN, self.Role.SERVER_ADMIN]:
            return 1
        elif self.role in [self.Role.HR, self.Role.MANAGER]:
            return 2
        elif self.role == self.Role.DEPT_MANAGER:
            return 3
        else:
            return 4

    @property
    def role_badge_class(self):
        classes = {
            self.Role.SUPERADMIN: 'bg-danger text-white',
            self.Role.SERVER_ADMIN: 'bg-dark text-white',
            self.Role.HR: 'bg-primary text-white',
            self.Role.MANAGER: 'bg-info text-dark',
            self.Role.DEPT_MANAGER: 'bg-success text-white',
            self.Role.EXECUTIVE: 'bg-warning text-dark',
            self.Role.INTERN: 'bg-secondary text-white',
            self.Role.STAFF: 'bg-light text-dark border',
        }
        return classes.get(self.role, 'bg-secondary text-white')

    def can_create_department(self):
        """Only Level 1 (Superadmin / Server Admin) can create departments."""
        return self.is_super_or_server_admin()

    def can_create_branch(self):
        """Level 1 and Managers can create branches."""
        return self.is_super_or_server_admin() or self.role == self.Role.MANAGER

    def can_assign_role(self, target_role_value):
        """
        Validates whether current user can assign a user to target_role_value:
        - Level 1: Can assign anyone (HR, Manager, Dept Mgr, Executive, Intern, Staff)
        - Level 2 (HR & Manager): Can assign Dept Managers, Executives, Interns, Staff
        - Level 3 (Dept Manager): Can assign Executives, Interns, Staff
        - Level 4: No assignment capabilities
        """
        if self.is_super_or_server_admin():
            return True
        elif self.role in [self.Role.HR, self.Role.MANAGER]:
            return target_role_value in [
                self.Role.DEPT_MANAGER,
                self.Role.EXECUTIVE,
                self.Role.INTERN,
                self.Role.STAFF
            ]
        elif self.role == self.Role.DEPT_MANAGER:
            return target_role_value in [
                self.Role.EXECUTIVE,
                self.Role.INTERN,
                self.Role.STAFF
            ]
        return False

    def get_assignable_roles(self):
        """Returns list of (value, label) tuples of roles current user is allowed to assign."""
        if self.is_super_or_server_admin():
            return self.Role.choices
        elif self.role in [self.Role.HR, self.Role.MANAGER]:
            return [
                (self.Role.DEPT_MANAGER, 'Department Manager'),
                (self.Role.EXECUTIVE, 'Executive'),
                (self.Role.INTERN, 'Intern'),
                (self.Role.STAFF, 'Staff'),
            ]
        elif self.role == self.Role.DEPT_MANAGER:
            return [
                (self.Role.EXECUTIVE, 'Executive'),
                (self.Role.INTERN, 'Intern'),
                (self.Role.STAFF, 'Staff'),
            ]
        return []

    def get_manageable_users(self):
        """Returns queryset of users that the current user has authority to manage."""
        from apps.users.models import User
        if self.is_super_or_server_admin():
            return User.objects.all().select_related('department', 'branch')
        elif self.role == self.Role.HR:
            # HR manages all non-level-1 users
            return User.objects.exclude(role__in=[self.Role.SUPERADMIN, self.Role.SERVER_ADMIN]).select_related('department', 'branch')
        elif self.role == self.Role.MANAGER:
            # Manager manages users in their department or all non-level-1 users
            if self.department:
                return User.objects.filter(department=self.department).exclude(role__in=[self.Role.SUPERADMIN, self.Role.SERVER_ADMIN]).select_related('department', 'branch')
            return User.objects.exclude(role__in=[self.Role.SUPERADMIN, self.Role.SERVER_ADMIN]).select_related('department', 'branch')
        elif self.role == self.Role.DEPT_MANAGER:
            # Dept Manager manages Executives, Interns, Staff in their department/branch
            qs = User.objects.filter(role__in=[self.Role.EXECUTIVE, self.Role.INTERN, self.Role.STAFF])
            if self.department:
                qs = qs.filter(department=self.department)
            if self.branch:
                qs = qs.filter(branch=self.branch)
            return qs.select_related('department', 'branch')
        else:
            return User.objects.none()

    def __str__(self):
        display = self.get_full_name() or self.username
        return f"{display} ({self.get_role_display()})"
