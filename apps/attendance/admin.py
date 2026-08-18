from django.contrib import admin
from apps.attendance.models import Attendance, LeaveRequest


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ('user', 'date', 'status', 'check_in', 'check_out', 'work_duration_minutes')
    list_filter = ('status', 'date', 'user__department')
    search_fields = ('user__username', 'user__employee_id', 'user__first_name', 'user__last_name')
    date_hierarchy = 'date'


@admin.register(LeaveRequest)
class LeaveRequestAdmin(admin.ModelAdmin):
    list_display = ('user', 'leave_type', 'start_date', 'end_date', 'status', 'created_at')
    list_filter = ('status', 'leave_type', 'user__department')
    search_fields = ('user__username', 'user__employee_id', 'reason')
    date_hierarchy = 'start_date'
