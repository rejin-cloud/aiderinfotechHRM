from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from apps.users.models import User

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('username', 'email', 'first_name', 'last_name', 'role', 'department', 'branch', 'is_staff')
    list_filter = ('role', 'department', 'branch', 'is_staff', 'is_active')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('HRMS Organization & RBAC', {
            'fields': ('role', 'department', 'branch', 'employee_id', 'designation', 'phone', 'joining_date', 'bio', 'avatar_color')
        }),
    )
    add_fieldsets = BaseUserAdmin.add_fieldsets + (
        ('HRMS Organization & RBAC', {
            'fields': ('role', 'department', 'branch', 'employee_id', 'designation', 'phone', 'joining_date')
        }),
    )
