from django.contrib import admin
from apps.departments.models import Department, Branch

class BranchInline(admin.TabularInline):
    model = Branch
    extra = 1

@admin.register(Department)
class DepartmentAdmin(admin.ModelAdmin):
    list_display = ('name', 'branch_count', 'member_count', 'created_at')
    search_fields = ('name', 'description')
    inlines = [BranchInline]

@admin.register(Branch)
class BranchAdmin(admin.ModelAdmin):
    list_display = ('name', 'department', 'location', 'member_count', 'created_at')
    list_filter = ('department',)
    search_fields = ('name', 'location', 'department__name')
