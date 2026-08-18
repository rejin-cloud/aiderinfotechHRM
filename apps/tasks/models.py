import os
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.departments.models import Branch, Department


class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active / In Progress'
        COMPLETED = 'COMPLETED', 'Completed'
        ON_HOLD = 'ON_HOLD', 'On Hold'
        ARCHIVED = 'ARCHIVED', 'Archived'

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='tasks',
        db_index=True
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        help_text="Target specific branch (e.g., Designing, Editing, Marketing) or leave blank for All Branches."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_tasks'
    )
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='assigned_tasks',
        help_text="Assign to an individual member, or leave blank for full department team visibility."
    )
    task_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique task number code (e.g., CR-TASK-001)"
    )
    title = models.CharField(max_length=255, help_text="Task Title / Headline")
    description = models.TextField(help_text="Detailed task description and deliverables")
    instructions = models.TextField(
        blank=True,
        null=True,
        help_text="Step-by-step instructions, creative briefs, specifications, or guidelines"
    )
    priority = models.CharField(
        max_length=20,
        choices=Priority.choices,
        default=Priority.MEDIUM,
        db_index=True
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True
    )
    deadline = models.DateTimeField(null=True, blank=True, help_text="Target completion deadline (IST)")
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when task was marked completed")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Creative Task'
        verbose_name_plural = 'Creative Tasks'

    def __str__(self):
        return f"[{self.task_number}] {self.title}"

    @classmethod
    def update_overdue_tasks(cls):
        """
        Automatically updates any active task whose deadline has expired
        to 'ON_HOLD' status.
        """
        now = timezone.now()
        cls.objects.filter(
            status=cls.Status.ACTIVE,
            deadline__isnull=False,
            deadline__lt=now
        ).update(status=cls.Status.ON_HOLD)

    @property
    def priority_badge_class(self):
        mapping = {
            self.Priority.LOW: 'bg-secondary-subtle text-secondary border',
            self.Priority.MEDIUM: 'bg-info-subtle text-info border',
            self.Priority.HIGH: 'bg-warning-subtle text-warning border',
            self.Priority.URGENT: 'bg-danger text-white',
        }
        return mapping.get(self.priority, 'bg-light text-dark')

    @property
    def status_badge_class(self):
        mapping = {
            self.Status.ACTIVE: 'bg-primary text-white',
            self.Status.COMPLETED: 'bg-success text-white',
            self.Status.ON_HOLD: 'bg-danger text-white',
            self.Status.ARCHIVED: 'bg-secondary text-white',
        }
        return mapping.get(self.status, 'bg-secondary text-white')

    @property
    def is_overdue(self):
        if self.deadline and self.status != self.Status.COMPLETED:
            return timezone.now() > self.deadline
        return False

    @property
    def latest_submission(self):
        return self.submissions.order_by('-submitted_at').first()

    @property
    def latest_extension_request(self):
        return self.extension_requests.order_by('-created_at').first()

    @property
    def has_pending_extension_request(self):
        return self.extension_requests.filter(status=TaskExtensionRequest.Status.PENDING).exists()

    @classmethod
    def generate_next_task_number(cls, department_name="Creative"):
        """Generates a sequential unique task number e.g. CR-TASK-001."""
        prefix = "CR-TASK"
        if department_name and "creative" not in department_name.lower():
            code = "".join(w[0] for w in department_name.split() if w)[:3].upper()
            prefix = f"{code}-TASK"

        last_task = cls.objects.filter(task_number__startswith=prefix).order_by('-id').first()
        if last_task:
            try:
                num_part = int(last_task.task_number.split('-')[-1])
                next_num = num_part + 1
            except (ValueError, IndexError):
                next_num = cls.objects.filter(task_number__startswith=prefix).count() + 1
        else:
            next_num = 1
        return f"{prefix}-{next_num:03d}"


class TaskAttachment(models.Model):
    """Stores files & documents of ANY format created as initial task briefing materials."""
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='tasks/documents/%Y/%m/')
    filename = models.CharField(max_length=255, blank=True)
    file_size_bytes = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"{self.filename or os.path.basename(self.file.name)} ({self.task.task_number})"

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
            try:
                self.file_size_bytes = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    @property
    def formatted_file_size(self):
        bytes_val = self.file_size_bytes or 0
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        return f"{bytes_val / (1024 * 1024):.1f} MB"

    @property
    def file_extension(self):
        if self.filename:
            ext = os.path.splitext(self.filename)[1].lower()
            return ext.lstrip('.')
        return 'file'

    @property
    def icon_class(self):
        ext = self.file_extension
        if ext in ['pdf']:
            return 'bi-file-earmark-pdf text-danger'
        elif ext in ['doc', 'docx', 'txt', 'rtf']:
            return 'bi-file-earmark-word text-primary'
        elif ext in ['xls', 'xlsx', 'csv']:
            return 'bi-file-earmark-excel text-success'
        elif ext in ['zip', 'rar', '7z', 'tar', 'gz']:
            return 'bi-file-earmark-zip text-warning'
        elif ext in ['psd', 'ai', 'eps', 'svg', 'png', 'jpg', 'jpeg', 'webp', 'gif']:
            return 'bi-file-earmark-image text-info'
        elif ext in ['mp4', 'mov', 'avi', 'mkv']:
            return 'bi-file-earmark-play text-primary'
        return 'bi-file-earmark-text text-secondary'


class TaskSubmission(models.Model):
    """Stores completion details, final remarks, and deliverable submissions by assigned member."""
    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='submissions'
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_submissions'
    )
    remarks = models.TextField(help_text="Completion remarks, delivery summary, and notes")
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Task Submission'
        verbose_name_plural = 'Task Submissions'

    def __str__(self):
        return f"Submission for [{self.task.task_number}] by {self.submitted_by.username}"


class TaskSubmissionAttachment(models.Model):
    """Stores submitted output deliverables & media of ANY file format (ZIP, PSD, AI, MP4, PDF, etc.)."""
    submission = models.ForeignKey(
        TaskSubmission,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='tasks/submissions/%Y/%m/')
    filename = models.CharField(max_length=255, blank=True)
    file_size_bytes = models.PositiveIntegerField(default=0)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['uploaded_at']

    def __str__(self):
        return f"{self.filename or os.path.basename(self.file.name)}"

    def save(self, *args, **kwargs):
        if self.file and not self.filename:
            self.filename = os.path.basename(self.file.name)
            try:
                self.file_size_bytes = self.file.size
            except Exception:
                pass
        super().save(*args, **kwargs)

    @property
    def formatted_file_size(self):
        bytes_val = self.file_size_bytes or 0
        if bytes_val < 1024:
            return f"{bytes_val} B"
        elif bytes_val < 1024 * 1024:
            return f"{bytes_val / 1024:.1f} KB"
        return f"{bytes_val / (1024 * 1024):.1f} MB"

    @property
    def file_extension(self):
        if self.filename:
            ext = os.path.splitext(self.filename)[1].lower()
            return ext.lstrip('.')
        return 'file'

    @property
    def icon_class(self):
        ext = self.file_extension
        if ext in ['pdf']:
            return 'bi-file-earmark-pdf text-danger'
        elif ext in ['doc', 'docx', 'txt', 'rtf']:
            return 'bi-file-earmark-word text-primary'
        elif ext in ['xls', 'xlsx', 'csv']:
            return 'bi-file-earmark-excel text-success'
        elif ext in ['zip', 'rar', '7z', 'tar', 'gz']:
            return 'bi-file-earmark-zip text-warning'
        elif ext in ['psd', 'ai', 'eps', 'svg', 'png', 'jpg', 'jpeg', 'webp', 'gif']:
            return 'bi-file-earmark-image text-info'
        elif ext in ['mp4', 'mov', 'avi', 'mkv']:
            return 'bi-file-earmark-play text-primary'
        return 'bi-file-earmark-text text-secondary'


class TaskExtensionRequest(models.Model):
    """Request submitted by assigned member when unable to finish task within deadline."""
    class RequestType(models.TextChoices):
        MORE_DAYS = 'MORE_DAYS', 'Request More Days / Extension'
        REASSIGN = 'REASSIGN', 'Request Task Reassignment'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending Manager Review'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'

    class ManagerAction(models.TextChoices):
        EXTENDED = 'EXTENDED', 'Deadline Extended'
        REASSIGNED = 'REASSIGNED', 'Task Reassigned'
        REJECTED = 'REJECTED', 'Request Rejected'

    task = models.ForeignKey(
        Task,
        on_delete=models.CASCADE,
        related_name='extension_requests'
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='task_extension_requests'
    )
    request_type = models.CharField(
        max_length=20,
        choices=RequestType.choices,
        default=RequestType.MORE_DAYS
    )
    requested_days = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Number of additional days requested"
    )
    requested_deadline = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Specific requested completion deadline"
    )
    reason = models.TextField(help_text="Reason for inability to complete within deadline / notes")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        db_index=True
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_task_extensions'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    manager_action = models.CharField(
        max_length=20,
        choices=ManagerAction.choices,
        null=True,
        blank=True
    )
    manager_remarks = models.TextField(
        blank=True,
        null=True,
        help_text="Decision notes and feedback from Department Manager"
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Task Extension Request'
        verbose_name_plural = 'Task Extension Requests'

    def __str__(self):
        return f"[{self.get_request_type_display()}] for {self.task.task_number} by {self.requested_by.username} ({self.get_status_display()})"
