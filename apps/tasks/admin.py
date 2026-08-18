from django.contrib import admin
from apps.tasks.models import Task, TaskAttachment


class TaskAttachmentInline(admin.TabularInline):
    model = TaskAttachment
    extra = 1
    readonly_fields = ('file_size_bytes', 'uploaded_at')


@admin.register(Task)
class TaskAdmin(admin.ModelAdmin):
    list_display = ('task_number', 'title', 'department', 'branch', 'priority', 'status', 'created_by', 'deadline')
    list_filter = ('department', 'priority', 'status', 'branch')
    search_fields = ('task_number', 'title', 'description', 'instructions')
    inlines = [TaskAttachmentInline]


@admin.register(TaskAttachment)
class TaskAttachmentAdmin(admin.ModelAdmin):
    list_display = ('filename', 'task', 'file_size_bytes', 'uploaded_at')
    search_fields = ('filename', 'task__task_number')
