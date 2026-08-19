import os
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.departments.models import Branch, Department


class Client(models.Model):
    """
    Client registry for Creative Department operations.
    Stores client identification, contact person, company name, and project needs/scope.
    """
    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='clients',
        db_index=True
    )
    client_number = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="Unique client identifier code (e.g., CR-CL-001)"
    )
    name = models.CharField(max_length=255, help_text="Client Name / Contact Person")
    company = models.CharField(max_length=255, help_text="Company / Brand / Organization Name")
    needs = models.TextField(help_text="Client creative needs, specifications, requirements, and deliverables")

    email = models.EmailField(blank=True, null=True, help_text="Contact email address")
    phone = models.CharField(max_length=50, blank=True, null=True, help_text="Contact phone / WhatsApp number")
    address = models.TextField(blank=True, null=True, help_text="Company address or office location")
    notes = models.TextField(blank=True, null=True, help_text="Internal notes or creative guidelines")

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='created_clients'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Creative Client'
        verbose_name_plural = 'Creative Clients'

    def __str__(self):
        return f"[{self.client_number}] {self.name} - {self.company}"

    @classmethod
    def generate_next_client_number(cls, department_name="Creative"):
        """Generates a sequential unique client number e.g. CR-CL-001."""
        prefix = "CR-CL"
        if department_name and "creative" not in department_name.lower():
            code = "".join(w[0] for w in department_name.split() if w)[:3].upper()
            prefix = f"{code}-CL"

        last_client = cls.objects.filter(client_number__startswith=prefix).order_by('-id').first()
        if last_client:
            try:
                num_part = int(last_client.client_number.split('-')[-1])
                next_num = num_part + 1
            except (ValueError, IndexError):
                next_num = cls.objects.filter(client_number__startswith=prefix).count() + 1
        else:
            next_num = 1
        return f"{prefix}-{next_num:03d}"


class ClientAssignment(models.Model):
    """
    Multi-Branch, Hierarchical Client Task Assignment:
    - Stage 1: Creative Department Manager assigns a Client to a Branch and its Executive for a specific task.
    - Stage 2: The Branch Executive delegates the task to a staff member or intern in their branch.
    """
    class Status(models.TextChoices):
        ASSIGNED_TO_EXECUTIVE = 'ASSIGNED_TO_EXECUTIVE', 'Assigned to Branch Executive'
        DELEGATED = 'DELEGATED', 'Delegated to Member / Intern'
        IN_PROGRESS = 'IN_PROGRESS', 'In Progress'
        UNDER_EXECUTIVE_REVIEW = 'UNDER_EXECUTIVE_REVIEW', 'Submitted / Under Executive Review'
        EXECUTIVE_REVISION = 'EXECUTIVE_REVISION', 'Revision Requested by Executive'
        UNDER_DEPT_MANAGER_REVIEW = 'UNDER_DEPT_MANAGER_REVIEW', 'Forwarded to Dept Manager / Final Review'
        DEPT_MANAGER_REVISION = 'DEPT_MANAGER_REVISION', 'Revision Requested by Dept Manager'
        COMPLETED = 'COMPLETED', 'Approved & Completed'
        ON_HOLD = 'ON_HOLD', 'On Hold'
        UNDER_REVIEW = 'UNDER_REVIEW', 'Completed / Under Review'

    client = models.ForeignKey(
        Client,
        on_delete=models.CASCADE,
        related_name='assignments',
        db_index=True
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.CASCADE,
        related_name='client_assignments',
        db_index=True
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='manager_client_assignments',
        help_text="Creative Department Manager who initiated the branch assignment"
    )
    executive = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='executive_received_client_assignments',
        help_text="Branch Executive responsible for supervising and delegating"
    )

    task_title = models.CharField(
        max_length=255,
        help_text="Specific task title for this branch (e.g. Marketing Campaign, UI/UX Design, 4K Video Editing)"
    )
    task_scope = models.TextField(
        help_text="Specific instructions, deliverables, and scope delegated to this branch"
    )
    deadline = models.DateTimeField(null=True, blank=True, help_text="Target completion deadline")

    status = models.CharField(
        max_length=35,
        choices=Status.choices,
        default=Status.ASSIGNED_TO_EXECUTIVE,
        db_index=True
    )

    # Stage 2: Delegation to Branch Member or Intern by Executive
    delegated_member = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='member_assigned_client_tasks',
        help_text="Staff member or intern assigned by the Branch Executive"
    )
    delegated_at = models.DateTimeField(null=True, blank=True)
    executive_notes = models.TextField(
        blank=True,
        null=True,
        help_text="Guidance, instructions, or allocation remarks from the Branch Executive"
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Client Branch Assignment'
        verbose_name_plural = 'Client Branch Assignments'

    def __str__(self):
        return f"[{self.client.client_number}] -> {self.branch.name}: {self.task_title}"

    @property
    def status_badge_class(self):
        mapping = {
            self.Status.ASSIGNED_TO_EXECUTIVE: 'bg-warning text-dark',
            self.Status.DELEGATED: 'bg-info text-dark',
            self.Status.IN_PROGRESS: 'bg-primary text-white',
            self.Status.UNDER_EXECUTIVE_REVIEW: 'bg-purple-subtle text-primary border',
            self.Status.EXECUTIVE_REVISION: 'bg-warning-subtle text-warning border',
            self.Status.UNDER_DEPT_MANAGER_REVIEW: 'bg-teal-subtle text-teal border',
            self.Status.DEPT_MANAGER_REVISION: 'bg-danger-subtle text-danger border',
            self.Status.UNDER_REVIEW: 'bg-purple-subtle text-primary border',
            self.Status.COMPLETED: 'bg-success text-white',
            self.Status.ON_HOLD: 'bg-danger text-white',
        }
        return mapping.get(self.status, 'bg-secondary text-white')

    @property
    def is_overdue(self):
        if self.deadline and self.status not in [self.Status.COMPLETED, self.Status.UNDER_EXECUTIVE_REVIEW, self.Status.UNDER_DEPT_MANAGER_REVIEW]:
            return timezone.now() > self.deadline
        return False


class ClientAssignmentSubmission(models.Model):
    """
    Stores deliverable submissions by assigned Staff member or Intern for a Client Assignment.
    Review Hierarchy:
    1. Assigned delegate submits completion remarks & media files -> Status: UNDER_EXECUTIVE_REVIEW
    2. Branch Executive reviews:
       - Satisfied: Forwards to Creative Department Manager -> Status: UNDER_DEPT_MANAGER_REVIEW
       - Revisions needed: Requests revision with feedback -> Status: EXECUTIVE_REVISION
       - Reassign: Assigns to another member in the branch -> Status: DELEGATED
    3. Creative Department Manager performs final evaluation:
       - Approved: Marks client assignment -> Status: COMPLETED
       - Revision: Requests further changes -> Status: DEPT_MANAGER_REVISION
    """
    class ReviewStage(models.TextChoices):
        PENDING_EXECUTIVE = 'PENDING_EXECUTIVE', 'Pending Executive Review'
        EXECUTIVE_REVISION_REQUESTED = 'EXECUTIVE_REVISION_REQUESTED', 'Revision Requested by Executive'
        FORWARDED_TO_MANAGER = 'FORWARDED_TO_MANAGER', 'Forwarded to Dept Manager'
        MANAGER_REVISION_REQUESTED = 'MANAGER_REVISION_REQUESTED', 'Revision Requested by Dept Manager'
        MANAGER_APPROVED = 'MANAGER_APPROVED', 'Approved by Dept Manager'

    assignment = models.ForeignKey(
        ClientAssignment,
        on_delete=models.CASCADE,
        related_name='submissions',
        db_index=True
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='client_assignment_submissions'
    )
    remarks = models.TextField(help_text="Deliverables summary, output specs, links, and remarks")
    submitted_at = models.DateTimeField(auto_now_add=True)
    
    review_stage = models.CharField(
        max_length=35,
        choices=ReviewStage.choices,
        default=ReviewStage.PENDING_EXECUTIVE,
        db_index=True
    )

    # Executive Review Stage
    executive_feedback = models.TextField(blank=True, null=True, help_text="Executive review feedback or revision instructions")
    executive_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='exec_reviewed_client_submissions'
    )
    executive_reviewed_at = models.DateTimeField(null=True, blank=True)

    # Department Manager Review Stage
    manager_feedback = models.TextField(blank=True, null=True, help_text="Department Manager final evaluation remarks")
    manager_reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='mgr_reviewed_client_submissions'
    )
    manager_reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Client Assignment Submission'
        verbose_name_plural = 'Client Assignment Submissions'

    def __str__(self):
        return f"Submission for [{self.assignment.client.client_number}] {self.assignment.task_title} by {self.submitted_by.username}"


class ClientAssignmentSubmissionAttachment(models.Model):
    """Stores media files & documents of ANY format uploaded for client deliverables."""
    submission = models.ForeignKey(
        ClientAssignmentSubmission,
        on_delete=models.CASCADE,
        related_name='attachments'
    )
    file = models.FileField(upload_to='tasks/client_submissions/%Y/%m/')
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



class Task(models.Model):
    class Priority(models.TextChoices):
        LOW = 'LOW', 'Low'
        MEDIUM = 'MEDIUM', 'Medium'
        HIGH = 'HIGH', 'High'
        URGENT = 'URGENT', 'Urgent'

    class Status(models.TextChoices):
        ACTIVE = 'ACTIVE', 'Active / In Progress'
        UNDER_REVIEW = 'UNDER_REVIEW', 'Submitted / Under Review'
        COMPLETED = 'COMPLETED', 'Completed'
        ON_HOLD = 'ON_HOLD', 'On Hold'
        ARCHIVED = 'ARCHIVED', 'Archived'

    department = models.ForeignKey(
        Department,
        on_delete=models.CASCADE,
        related_name='tasks',
        db_index=True
    )
    client = models.ForeignKey(
        Client,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='tasks',
        help_text="Associated client for this task (optional)"
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
    completed_at = models.DateTimeField(null=True, blank=True, help_text="Timestamp when manager verified and marked task completed")
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
        to 'ON_HOLD' status (does not affect tasks submitted for review or completed).
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
            self.Status.UNDER_REVIEW: 'bg-info text-dark',
            self.Status.COMPLETED: 'bg-success text-white',
            self.Status.ON_HOLD: 'bg-danger text-white',
            self.Status.ARCHIVED: 'bg-secondary text-white',
        }
        return mapping.get(self.status, 'bg-secondary text-white')

    @property
    def is_overdue(self):
        if self.deadline and self.status not in [self.Status.COMPLETED, self.Status.UNDER_REVIEW]:
            return timezone.now() > self.deadline
        return False

    @property
    def latest_submission(self):
        return self.submissions.order_by('-submitted_at').first()

    @property
    def pending_submission(self):
        return self.submissions.filter(review_status=TaskSubmission.ReviewStatus.PENDING).first()

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
    """
    Stores deliverable submissions by assigned member.
    The task moves to UNDER_REVIEW until the Creative Department Manager reviews it.
    """
    class ReviewStatus(models.TextChoices):
        PENDING = 'PENDING', 'Pending Manager Review'
        APPROVED = 'APPROVED', 'Approved & Marked Completed'
        CHANGES_REQUESTED = 'CHANGES_REQUESTED', 'Revision Requested'
        REASSIGNED = 'REASSIGNED', 'Reassigned to Another Member'

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
    remarks = models.TextField(help_text="Deliverables summary, output specs, links, and remarks")
    submitted_at = models.DateTimeField(auto_now_add=True)
    review_status = models.CharField(
        max_length=25,
        choices=ReviewStatus.choices,
        default=ReviewStatus.PENDING,
        db_index=True
    )
    manager_feedback = models.TextField(
        blank=True,
        null=True,
        help_text="Manager feedback, revision instructions, or approval notes"
    )
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_task_submissions'
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-submitted_at']
        verbose_name = 'Task Submission'
        verbose_name_plural = 'Task Submissions'

    def __str__(self):
        return f"Submission for [{self.task.task_number}] by {self.submitted_by.username} ({self.get_review_status_display()})"


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
