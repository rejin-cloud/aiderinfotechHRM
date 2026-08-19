from django.contrib import admin
from .models import Candidate


@admin.register(Candidate)
class CandidateAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'place', 'department', 'branch', 'role_applied', 'status', 'created_at')
    list_filter = ('status', 'role_applied', 'department', 'interview_mode')
    search_fields = ('name', 'phone', 'email', 'place', 'designation_applied')
