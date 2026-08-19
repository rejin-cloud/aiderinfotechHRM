from django.db import models
from django.conf import settings
from django.utils import timezone
from apps.departments.models import Department, Branch


class Candidate(models.Model):
    class Status(models.TextChoices):
        TO_BE_CALLED = 'TO_BE_CALLED', 'To Be Called'
        CALLED = 'CALLED', 'Called'
        APPROVED = 'APPROVED', 'Approved After Calling'
        REJECTED = 'REJECTED', 'Rejected'
        INTERVIEW_SCHEDULED = 'INTERVIEW_SCHEDULED', 'Interview Arranged'
        INTERVIEWED = 'INTERVIEWED', 'Interview Completed'
        SELECTED = 'SELECTED', 'Selected'
        ONBOARDED = 'ONBOARDED', 'Onboarded as Employee'

    class RoleApplied(models.TextChoices):
        STAFF = 'STAFF', 'Staff Member'
        EXECUTIVE = 'EXECUTIVE', 'Branch Executive'
        INTERN = 'INTERN', 'Department Intern'
        MANAGER = 'MANAGER', 'Manager'
        DEPT_MANAGER = 'DEPT_MANAGER', 'Department Manager'
        OTHER = 'OTHER', 'Other Specialist'

    class InterviewMode(models.TextChoices):
        IN_PERSON = 'IN_PERSON', 'In-Person (Office)'
        ONLINE = 'ONLINE', 'Online (Google Meet / Zoom)'
        PHONE = 'PHONE', 'Telephonic Interview'

    # 1. Candidate Personal & Contact Information
    name = models.CharField(max_length=150, verbose_name="Candidate Name")
    phone = models.CharField(max_length=25, verbose_name="Contact Number")
    email = models.EmailField(max_length=254, blank=True, null=True, verbose_name="Email Address")
    place = models.CharField(max_length=150, verbose_name="Place / City / Location")

    # 2. Applying Department & Branch Scope
    department = models.ForeignKey(
        Department,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='candidates',
        verbose_name="Applied Department"
    )
    branch = models.ForeignKey(
        Branch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='candidates',
        verbose_name="Applied Branch Wing"
    )
    role_applied = models.CharField(
        max_length=30,
        choices=RoleApplied.choices,
        default=RoleApplied.STAFF,
        verbose_name="Role / Level Applied"
    )
    designation_applied = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name="Designation / Position Title",
        help_text="e.g. Senior Graphic Designer, Video Editor, Marketing Associate"
    )
    qualification = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name="Highest Educational Qualification"
    )
    experience_years = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name="Relevant Experience",
        help_text="e.g. Fresher, 2 Years, 5+ Years"
    )
    resume = models.FileField(
        upload_to='candidate_resumes/',
        blank=True,
        null=True,
        verbose_name="Resume / CV / Portfolio Attachment"
    )
    notes = models.TextField(
        blank=True,
        default='',
        verbose_name="Initial Candidate Notes / Summary"
    )

    # 3. Lifecycle Status Pipeline
    status = models.CharField(
        max_length=30,
        choices=Status.choices,
        default=Status.TO_BE_CALLED,
        db_index=True,
        verbose_name="Candidate Pipeline Status"
    )

    # 4. Telephonic Calling & Screening Details
    called_at = models.DateTimeField(null=True, blank=True, verbose_name="Call Completed At")
    called_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='called_candidates',
        verbose_name="HR Executive who Called"
    )
    call_notes = models.TextField(
        blank=True,
        default='',
        verbose_name="Calling Summary & Discussion Notes"
    )
    call_rating = models.PositiveIntegerField(
        null=True,
        blank=True,
        choices=[
            (1, '1 - Needs Improvement'),
            (2, '2 - Fair'),
            (3, '3 - Good / Promising'),
            (4, '4 - Very Good'),
            (5, '5 - Exceptional Candidate'),
        ],
        verbose_name="Phone Screening Rating"
    )

    # 5. Screening Decision / Shortlisting (Approved / Rejected)
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="Decision Date")
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='reviewed_candidates',
        verbose_name="Reviewed & Decided By"
    )
    approval_notes = models.TextField(
        blank=True,
        default='',
        verbose_name="Approval / Shortlist Remarks"
    )

    # 6. Interview Arrangements
    interview_date = models.DateField(null=True, blank=True, verbose_name="Interview Date")
    interview_time = models.TimeField(null=True, blank=True, verbose_name="Interview Time")
    interview_mode = models.CharField(
        max_length=20,
        choices=InterviewMode.choices,
        default=InterviewMode.IN_PERSON,
        verbose_name="Interview Format"
    )
    interview_location = models.CharField(
        max_length=255,
        blank=True,
        default='',
        verbose_name="Interview Location / Meeting Link",
        help_text="e.g. HQ Office Room 302, or Google Meet URL"
    )
    interviewer_name = models.CharField(
        max_length=150,
        blank=True,
        default='',
        verbose_name="Interviewer(s) / Panel"
    )
    interview_instructions = models.TextField(
        blank=True,
        default='',
        verbose_name="Instructions for Candidate"
    )
    interview_feedback = models.TextField(
        blank=True,
        default='',
        verbose_name="Post-Interview Evaluation Notes"
    )

    # 7. Audit Metadata
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='created_candidates',
        verbose_name="Registered By"
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Candidate Application'
        verbose_name_plural = 'Candidate Applications'

    def __str__(self):
        return f"{self.name} - {self.get_role_applied_display()} ({self.get_status_display()})"

    @property
    def status_badge_class(self):
        mapping = {
            self.Status.TO_BE_CALLED: 'bg-warning text-dark',
            self.Status.CALLED: 'bg-info text-dark',
            self.Status.APPROVED: 'bg-success text-white',
            self.Status.REJECTED: 'bg-danger text-white',
            self.Status.INTERVIEW_SCHEDULED: 'bg-primary text-white',
            self.Status.INTERVIEWED: 'bg-purple text-white',
            self.Status.SELECTED: 'bg-teal text-white',
            self.Status.ONBOARDED: 'bg-dark text-white',
        }
        return mapping.get(self.status, 'bg-secondary text-white')

    @property
    def stage_number(self):
        mapping = {
            self.Status.TO_BE_CALLED: 1,
            self.Status.CALLED: 2,
            self.Status.APPROVED: 3,
            self.Status.INTERVIEW_SCHEDULED: 4,
            self.Status.INTERVIEWED: 5,
            self.Status.SELECTED: 6,
            self.Status.ONBOARDED: 7,
            self.Status.REJECTED: 0,
        }
        return mapping.get(self.status, 1)
