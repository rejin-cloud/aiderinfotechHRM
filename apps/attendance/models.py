from datetime import datetime, time, date
from django.conf import settings
from django.db import models
from django.utils import timezone


class Attendance(models.Model):
    class Status(models.TextChoices):
        PRESENT = 'PRESENT', 'Present'
        LATE = 'LATE', 'Present (Late)'
        HALF_DAY = 'HALF_DAY', 'Half Day'
        ABSENT = 'ABSENT', 'Absent'
        ON_LEAVE = 'ON_LEAVE', 'On Leave'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='attendances',
        db_index=True
    )
    date = models.DateField(default=timezone.now, db_index=True)
    check_in = models.DateTimeField(null=True, blank=True)
    check_out = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ABSENT,
        db_index=True
    )
    is_late = models.BooleanField(default=False, db_index=True)
    work_duration_minutes = models.PositiveIntegerField(default=0)
    check_in_notes = models.TextField(blank=True, null=True)
    check_out_notes = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-date', 'user']
        unique_together = ('user', 'date')
        verbose_name = 'Daily Attendance Record'
        verbose_name_plural = 'Daily Attendance Records'

    def __str__(self):
        return f"{self.user.username} - {self.date} ({self.get_status_display()})"

    @property
    def is_present(self):
        """Returns True if the employee attended work on this date."""
        return self.status in [self.Status.PRESENT, self.Status.LATE, self.Status.HALF_DAY] or bool(self.check_in and self.status not in [self.Status.ABSENT, self.Status.ON_LEAVE])

    @property
    def formatted_duration(self):
        if not self.work_duration_minutes:
            return "0 hrs 0 mins"
        hrs = self.work_duration_minutes // 60
        mins = self.work_duration_minutes % 60
        if hrs > 0 and mins > 0:
            return f"{hrs}h {mins}m"
        elif hrs > 0:
            return f"{hrs} hrs"
        return f"{mins} mins"

    @property
    def status_badge_class(self):
        mapping = {
            self.Status.PRESENT: 'bg-success text-white',
            self.Status.LATE: 'bg-warning text-dark',
            self.Status.HALF_DAY: 'bg-info text-dark',
            self.Status.ABSENT: 'bg-danger text-white',
            self.Status.ON_LEAVE: 'bg-primary text-white',
        }
        return mapping.get(self.status, 'bg-secondary text-white')

    WORK_START_TIME = time(9, 30)  # Official work start cutoff: 09:30 AM IST

    def calculate_duration_and_status(self):
        """
        Calculates work duration and auto-sets status based on check-in/out times.
        - Check-in <= 09:30 AM IST: PRESENT (On-Time)
        - Check-in > 09:30 AM IST: PRESENT & LATE (is_late=True, status=LATE)
        - Work duration < 4 hours: HALF_DAY
        """
        if self.status == self.Status.ON_LEAVE:
            return

        if self.check_in:
            # Check if check_in was after 9:30 AM local time (IST)
            check_in_local = timezone.localtime(self.check_in)
            if check_in_local.time() > self.WORK_START_TIME:
                self.is_late = True
                self.status = self.Status.LATE
            else:
                self.is_late = False
                self.status = self.Status.PRESENT

            if self.check_out:
                duration = self.check_out - self.check_in
                mins = max(0, int(duration.total_seconds() // 60))
                self.work_duration_minutes = mins
                # If worked less than 4 hours (240 mins), consider Half Day
                if mins < 240 and mins > 30:
                    self.status = self.Status.HALF_DAY
        else:
            self.is_late = False
            self.status = self.Status.ABSENT
            self.work_duration_minutes = 0


class LeaveRequest(models.Model):
    class LeaveType(models.TextChoices):
        CASUAL = 'CASUAL', 'Casual Leave'
        SICK = 'SICK', 'Sick / Medical Leave'
        ANNUAL = 'ANNUAL', 'Annual / Earned Leave'
        UNPAID = 'UNPAID', 'Unpaid Leave (LWP)'
        EMERGENCY = 'EMERGENCY', 'Emergency Leave'

    class Status(models.TextChoices):
        PENDING_DEPT_REVIEW = 'PENDING_DEPT_REVIEW', 'Pending Dept Manager Review'
        PENDING_MANAGER_APPROVAL = 'PENDING_MANAGER_APPROVAL', 'Pending Manager Final Approval'
        PENDING_SUPERADMIN_APPROVAL = 'PENDING_SUPERADMIN_APPROVAL', 'Pending Super Admin Approval'
        APPROVED = 'APPROVED', 'Approved'
        REJECTED = 'REJECTED', 'Rejected'
        CANCELLED = 'CANCELLED', 'Cancelled by Applicant'

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='leave_requests',
        db_index=True
    )
    leave_type = models.CharField(
        max_length=25,
        choices=LeaveType.choices,
        default=LeaveType.CASUAL
    )
    start_date = models.DateField()
    end_date = models.DateField()
    is_half_day = models.BooleanField(default=False)
    half_day_period = models.CharField(
        max_length=15,
        choices=[
            ('FIRST_HALF', 'First Half (Morning)'),
            ('SECOND_HALF', 'Second Half (Afternoon)')
        ],
        null=True,
        blank=True
    )
    reason = models.TextField()
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.PENDING_DEPT_REVIEW,
        db_index=True
    )

    # Multi-Stage Audit Trail
    # Stage 1: Department Manager Review & Forward (For Staff/Intern/Exec)
    reviewed_by_dept_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='dept_reviewed_leaves'
    )
    dept_manager_notes = models.TextField(blank=True, default='')
    dept_manager_reviewed_at = models.DateTimeField(null=True, blank=True)

    # Stage 2: Manager Final Decision (For Staff/Intern/Exec)
    approved_by_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='manager_approved_leaves'
    )
    manager_decision_notes = models.TextField(blank=True, default='')
    manager_decided_at = models.DateTimeField(null=True, blank=True)

    # Stage 3: Super Admin Executive Approval (For Server Admin, HR, Manager)
    approved_by_superadmin = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='superadmin_approved_leaves'
    )
    superadmin_decision_notes = models.TextField(blank=True, default='')
    superadmin_decided_at = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Leave Application'
        verbose_name_plural = 'Leave Applications'

    def __str__(self):
        return f"{self.user.username} - {self.get_leave_type_display()} ({self.start_date} to {self.end_date}) [{self.get_status_display()}]"

    @property
    def total_days(self):
        if self.is_half_day:
            return 0.5
        if self.start_date and self.end_date:
            delta = (self.end_date - self.start_date).days + 1
            return max(1, delta)
        return 1

    @property
    def status_badge_class(self):
        mapping = {
            self.Status.PENDING_DEPT_REVIEW: 'bg-warning text-dark',
            self.Status.PENDING_MANAGER_APPROVAL: 'bg-info text-dark',
            self.Status.PENDING_SUPERADMIN_APPROVAL: 'bg-primary text-white',
            self.Status.APPROVED: 'bg-success text-white',
            self.Status.REJECTED: 'bg-danger text-white',
            self.Status.CANCELLED: 'bg-secondary text-white',
        }
        return mapping.get(self.status, 'bg-secondary text-white')
