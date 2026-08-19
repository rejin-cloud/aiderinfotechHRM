import calendar
import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.departments.models import Branch, Department
from apps.hierarchy.permissions import get_user_level
from apps.tasks.forms import (
    ClientAssignmentExecutiveReviewForm,
    ClientAssignmentForm,
    ClientAssignmentManagerReviewForm,
    ClientAssignmentSubmissionForm,
    ClientFilterForm,
    ClientForm,
    CustomerFilterForm,
    CustomerForm,
    ExecutiveDelegationForm,
    ManagerExtensionReviewForm,
    ManagerSubmissionReviewForm,
    TaskCompletionForm,
    TaskExtensionRequestForm,
    TaskFilterForm,
    TaskForm,
)
from apps.tasks.models import (
    Client,
    ClientAssignment,
    ClientAssignmentSubmission,
    ClientAssignmentSubmissionAttachment,
    Task,
    TaskAttachment,
    TaskExtensionRequest,
    TaskSubmission,
    TaskSubmissionAttachment,
)
from apps.tasks.permissions import (
    can_manage_creative_tasks,
    can_view_creative_tasks,
    is_creative_department,
)
from apps.users.models import User


def get_creative_department_instance():
    """Helper to locate the Creative Department."""
    dept = Department.objects.filter(name__icontains='creative').first()
    if not dept:
        dept = Department.objects.first()
    return dept


@login_required
def task_list_view(request):
    """
    Lists tasks scoped to the Creative Department.
    - Creative Department Manager & Corporate Leadership see all tasks with assignment statuses.
    - Branch members see all tasks for their branch.
    - Non-assigned members cannot see who the task is assigned to.
    """
    # Automatic update: expired active tasks are moved to ON_HOLD
    Task.update_overdue_tasks()

    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You do not have permission to view Creative Department tasks.")
        return redirect('dashboard_router')

    # Determine department
    creative_dept = get_creative_department_instance()
    if user.department and is_creative_department(user.department):
        department = user.department
    else:
        department = creative_dept

    is_creative_manager = can_manage_creative_tasks(user)
    is_leadership = get_user_level(user) <= 2 or is_creative_manager

    # Base Queryset
    tasks = Task.objects.filter(department=department).select_related('created_by', 'assigned_to', 'branch', 'department').prefetch_related('attachments', 'extension_requests', 'submissions')

    # Scoping rule:
    # - Leadership / Manager sees all tasks in the department.
    # - Regular members see tasks belonging to their branch (or general tasks if no branch specified).
    if not is_leadership:
        if user.branch:
            tasks = tasks.filter(models.Q(branch=user.branch) | models.Q(branch__isnull=True))
        else:
            tasks = tasks.filter(branch__isnull=True)

    # Apply filters
    filter_form = TaskFilterForm(request.GET, department=department)
    if filter_form.is_valid():
        q = filter_form.cleaned_data.get('q')
        priority = filter_form.cleaned_data.get('priority')
        status = filter_form.cleaned_data.get('status')

        if q:
            tasks = tasks.filter(
                models.Q(task_number__icontains=q) |
                models.Q(title__icontains=q) |
                models.Q(description__icontains=q) |
                models.Q(instructions__icontains=q)
            )
        if priority:
            tasks = tasks.filter(priority=priority)
        if status:
            tasks = tasks.filter(status=status)

    # Stats for dashboard header
    total_tasks = tasks.count()
    active_tasks = tasks.filter(status=Task.Status.ACTIVE).count()
    under_review_tasks = tasks.filter(status=Task.Status.UNDER_REVIEW).count()
    completed_tasks = tasks.filter(status=Task.Status.COMPLETED).count()
    on_hold_tasks = tasks.filter(status=Task.Status.ON_HOLD).count()
    urgent_tasks = tasks.filter(priority=Task.Priority.URGENT, status=Task.Status.ACTIVE).count()

    # Pending extension requests counter for manager
    pending_requests_count = 0
    if is_creative_manager:
        pending_requests_count = TaskExtensionRequest.objects.filter(
            task__department=department,
            status=TaskExtensionRequest.Status.PENDING
        ).count()

    context = {
        'tasks': tasks,
        'department': department,
        'is_creative_manager': is_creative_manager,
        'is_leadership': is_leadership,
        'filter_form': filter_form,
        'total_tasks': total_tasks,
        'active_tasks': active_tasks,
        'under_review_tasks': under_review_tasks,
        'completed_tasks': completed_tasks,
        'on_hold_tasks': on_hold_tasks,
        'urgent_tasks': urgent_tasks,
        'pending_requests_count': pending_requests_count,
        'page_title': f'Creative Tasks Hub &bull; {department.name if department else "Aider Creative"}',
    }
    return render(request, 'tasks/task_list.html', context)


@login_required
def task_create_view(request):
    """
    Creates a new creative department task.
    - STRICTLY restricted to the Creative Department Manager (and Superadmin).
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager is authorized to create tasks.")
        return redirect('task_list')

    department = get_creative_department_instance()

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, department=department)
        if form.is_valid():
            task = form.save(commit=False)
            task.department = department
            task.created_by = user
            task.save()

            # Handle multi-file document attachments (accepts any file format)
            files = request.FILES.getlist('documents')
            for f in files:
                TaskAttachment.objects.create(
                    task=task,
                    file=f
                )

            messages.success(
                request,
                f"Task [{task.task_number}] '{task.title}' was created successfully! You can now assign it to a branch member."
            )
            return redirect('task_assign_specific', task_id=task.id)
    else:
        form = TaskForm(department=department)

    context = {
        'form': form,
        'department': department,
        'page_title': 'Create Creative Department Task',
    }
    return render(request, 'tasks/task_create.html', context)


@login_required
def task_assign_view(request, task_id=None):
    """
    Dedicated Task Assignment Portal:
    - STRICTLY restricted to the Creative Department Manager (and Superadmin).
    - Cascading workflow: Step 1 (Task) -> Step 2 (Branch) -> Step 3 (Branch Member) -> Step 4 (Deadline).
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager is authorized to assign tasks.")
        return redirect('task_list')

    department = get_creative_department_instance()
    tasks = Task.objects.filter(department=department).select_related('created_by', 'assigned_to', 'branch').order_by('-created_at')
    branches = Branch.objects.filter(department=department).order_by('name')

    selected_task = None
    if task_id:
        selected_task = get_object_or_404(Task, pk=task_id, department=department)
    elif request.GET.get('task'):
        try:
            selected_task = Task.objects.get(pk=request.GET.get('task'), department=department)
        except (Task.DoesNotExist, ValueError):
            pass

    if request.method == 'POST':
        post_task_id = request.POST.get('task_id')
        post_branch_id = request.POST.get('branch_id')
        post_user_id = request.POST.get('user_id')

        if not post_task_id:
            messages.error(request, "Please select a task to assign.")
            return redirect('task_assign')

        task = get_object_or_404(Task, pk=post_task_id, department=department)

        if not post_branch_id:
            messages.error(request, "Please select a target branch in the department.")
            return redirect('task_assign_specific', task_id=task.id)

        branch = get_object_or_404(Branch, pk=post_branch_id, department=department)

        if not post_user_id:
            messages.error(request, f"Please select a member from the '{branch.name}' branch.")
            return redirect('task_assign_specific', task_id=task.id)

        assigned_user = get_object_or_404(
            User,
            pk=post_user_id,
            department=department,
            branch=branch
        )

        # Update assignment & deadline
        task.branch = branch
        task.assigned_to = assigned_user

        post_deadline = request.POST.get('deadline', '').strip()
        if post_deadline:
            try:
                parsed_dt = parse_datetime(post_deadline)
                if parsed_dt is None:
                    parsed_d = parse_date(post_deadline)
                    if parsed_d:
                        parsed_dt = datetime.datetime.combine(parsed_d, datetime.time(18, 0))
                if parsed_dt:
                    if timezone.is_naive(parsed_dt):
                        parsed_dt = timezone.make_aware(parsed_dt, timezone.get_current_timezone())
                    task.deadline = parsed_dt
            except Exception:
                pass
        elif 'deadline' in request.POST and not post_deadline:
            task.deadline = None

        # If task was on hold due to missing assignment or overdue reassignment, resume to ACTIVE
        if task.status in [Task.Status.ON_HOLD, Task.Status.UNDER_REVIEW]:
            task.status = Task.Status.ACTIVE

        task.save()

        deadline_msg = f" with deadline {timezone.localtime(task.deadline).strftime('%b %d, %Y %I:%M %p')}" if task.deadline else ""
        messages.success(
            request,
            f"Success! Task [{task.task_number}] '{task.title}' has been assigned to {assigned_user.get_full_name() or assigned_user.username} ({branch.name}){deadline_msg}."
        )
        return redirect('task_detail', task_id=task.id)

    # Prepare branch members data structure for seamless JS switching
    branch_members_data = {}
    for b in branches:
        members_qs = User.objects.filter(department=department, branch=b).exclude(role=User.Role.SUPERADMIN).order_by('first_name', 'username')
        branch_members_data[b.id] = [
            {
                'id': m.id,
                'name': m.get_full_name() or m.username,
                'username': m.username,
                'role': m.get_role_display(),
                'designation': m.designation or 'Staff',
                'avatar_color': getattr(m, 'avatar_color', '#4f46e5') or '#4f46e5'
            }
            for m in members_qs
        ]

    context = {
        'department': department,
        'tasks': tasks,
        'branches': branches,
        'selected_task': selected_task,
        'branch_members_data': branch_members_data,
        'page_title': 'Assign Creative Tasks & Delegations',
    }
    return render(request, 'tasks/task_assign.html', context)


@login_required
def branch_members_api(request, branch_id):
    """API endpoint to dynamically fetch members of a specific branch in the Creative Department."""
    user = request.user
    if not can_manage_creative_tasks(user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    department = get_creative_department_instance()
    branch = get_object_or_404(Branch, pk=branch_id, department=department)

    members = User.objects.filter(department=department, branch=branch).exclude(role=User.Role.SUPERADMIN).order_by('first_name', 'username')
    data = [
        {
            'id': m.id,
            'name': m.get_full_name() or m.username,
            'username': m.username,
            'role': m.get_role_display(),
            'designation': m.designation or 'Staff',
            'avatar_color': getattr(m, 'avatar_color', '#4f46e5') or '#4f46e5'
        }
        for m in members
    ]
    return JsonResponse({'branch_id': branch.id, 'branch_name': branch.name, 'members': data})


@login_required
def task_detail_view(request, task_id):
    """
    Detailed Task View:
    - Creative Department Manager & Corporate Leadership can view all tasks, submissions, and assignment details.
    - Branch members can view tasks for their branch (with assignee identity hidden).
    - Assigned Member sees 'Assigned to You' and can submit deliverables or request extension.
    """
    Task.update_overdue_tasks()

    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You cannot view this task.")
        return redirect('dashboard_router')

    task = get_object_or_404(
        Task.objects.select_related('department', 'branch', 'created_by', 'assigned_to').prefetch_related(
            'attachments',
            'submissions__attachments',
            'submissions__submitted_by',
            'extension_requests__requested_by'
        ),
        pk=task_id
    )

    is_creative_manager = can_manage_creative_tasks(user)
    is_leadership = get_user_level(user) <= 2 or is_creative_manager
    is_assigned_to_me = (task.assigned_to == user)

    # Branch Scoping Rule:
    if not is_leadership:
        if task.branch and user.branch and task.branch != user.branch:
            messages.error(request, "Access restricted: This task belongs to another branch.")
            return redirect('task_list')

    # Pending extension request and submissions
    pending_extension = task.extension_requests.filter(status=TaskExtensionRequest.Status.PENDING).first()
    latest_submission = task.submissions.order_by('-submitted_at').first()
    pending_submission = task.submissions.filter(review_status=TaskSubmission.ReviewStatus.PENDING).first()

    context = {
        'task': task,
        'is_creative_manager': is_creative_manager,
        'is_leadership': is_leadership,
        'is_assigned_to_me': is_assigned_to_me,
        'pending_extension': pending_extension,
        'latest_submission': latest_submission,
        'pending_submission': pending_submission,
        'page_title': f'Task Brief &bull; [{task.task_number}] {task.title}',
    }
    return render(request, 'tasks/task_detail.html', context)


@login_required
def task_complete_view(request, task_id):
    """
    Deliverables Submission Portal:
    - STRICTLY restricted to the assigned member of the task.
    - Assigned member submits remarks and supporting media/deliverables (any file format).
    - Status transitions to UNDER_REVIEW (Only the Creative Department Manager can mark COMPLETED).
    """
    user = request.user
    task = get_object_or_404(Task, pk=task_id)

    # Verify authorization: only the assigned member can submit deliverables
    if task.assigned_to != user:
        messages.error(request, "Permission Denied: Only the member assigned to this task can submit completion deliverables.")
        return redirect('task_detail', task_id=task.id)

    if task.status == Task.Status.COMPLETED:
        messages.info(request, "This task has already been reviewed and marked as Completed by your Department Manager.")
        return redirect('task_detail', task_id=task.id)

    if request.method == 'POST':
        form = TaskCompletionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.task = task
            submission.submitted_by = user
            submission.review_status = TaskSubmission.ReviewStatus.PENDING
            submission.save()

            # Handle submitted media files & documents (accepts any file format)
            files = request.FILES.getlist('submission_files')
            for f in files:
                TaskSubmissionAttachment.objects.create(
                    submission=submission,
                    file=f
                )

            # Update task status to UNDER_REVIEW (NOT COMPLETED!)
            task.status = Task.Status.UNDER_REVIEW
            task.save()

            messages.success(
                request,
                f"Deliverables for task [{task.task_number}] '{task.title}' have been submitted successfully! Your submission is now Under Review by the Creative Department Manager."
            )
            return redirect('task_detail', task_id=task.id)
    else:
        form = TaskCompletionForm()

    context = {
        'task': task,
        'form': form,
        'page_title': f'Submit Deliverables &bull; {task.task_number}',
    }
    return render(request, 'tasks/task_complete.html', context)


@login_required
def manager_submission_review_view(request, task_id, submission_id=None):
    """
    Manager Review Portal for Task Deliverable Submissions:
    - STRICTLY restricted to Creative Department Manager.
    - Evaluation options:
      1. APPROVE: Verifies deliverables and marks task COMPLETED.
      2. REVISION: Requests revision from current member (task returns to ACTIVE, optional feedback & deadline).
      3. REASSIGN: Reassigns task to another member (task returns to ACTIVE with new member).
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can review submissions.")
        return redirect('task_list')

    department = get_creative_department_instance()
    task = get_object_or_404(Task, pk=task_id, department=department)

    if submission_id:
        submission = get_object_or_404(TaskSubmission, pk=submission_id, task=task)
    else:
        submission = task.submissions.order_by('-submitted_at').first()

    if not submission:
        messages.warning(request, "No deliverables have been submitted for this task yet.")
        return redirect('task_detail', task_id=task.id)

    if request.method == 'POST':
        form = ManagerSubmissionReviewForm(request.POST, department=department)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            feedback = form.cleaned_data.get('manager_feedback', '')

            submission.manager_feedback = feedback
            submission.reviewed_by = user
            submission.reviewed_at = timezone.now()

            if decision == 'APPROVE':
                task.status = Task.Status.COMPLETED
                task.completed_at = timezone.now()
                task.save()

                submission.review_status = TaskSubmission.ReviewStatus.APPROVED
                submission.save()

                messages.success(
                    request,
                    f"Excellent! Task [{task.task_number}] has been approved and marked as Completed."
                )

            elif decision == 'REVISION':
                task.status = Task.Status.ACTIVE
                new_deadline = form.cleaned_data.get('new_deadline')
                if new_deadline:
                    task.deadline = new_deadline
                task.save()

                submission.review_status = TaskSubmission.ReviewStatus.CHANGES_REQUESTED
                submission.save()

                messages.warning(
                    request,
                    f"Revision requested for task [{task.task_number}]. The task has been returned to {task.assigned_to.get_full_name() or task.assigned_to.username} with your feedback."
                )

            elif decision == 'REASSIGN':
                reassign_branch = form.cleaned_data.get('reassign_branch')
                reassign_user = form.cleaned_data.get('reassign_user')
                new_deadline = form.cleaned_data.get('new_deadline')

                if not reassign_user:
                    messages.error(request, "Please select a member to reassign this task to.")
                    return render(request, 'tasks/manager_submission_review.html', {'task': task, 'submission': submission, 'form': form, 'department': department})

                if reassign_branch:
                    task.branch = reassign_branch
                task.assigned_to = reassign_user
                if new_deadline:
                    task.deadline = new_deadline
                task.status = Task.Status.ACTIVE
                task.save()

                submission.review_status = TaskSubmission.ReviewStatus.REASSIGNED
                submission.save()

                messages.success(
                    request,
                    f"Task [{task.task_number}] has been reassigned to {reassign_user.get_full_name() or reassign_user.username} and resumed to Active."
                )

            return redirect('task_detail', task_id=task.id)
    else:
        initial_data = {}
        if task.branch:
            initial_data['reassign_branch'] = task.branch
        if task.deadline and task.deadline > timezone.now():
            initial_data['new_deadline'] = task.deadline
        form = ManagerSubmissionReviewForm(initial=initial_data, department=department)

    context = {
        'task': task,
        'submission': submission,
        'form': form,
        'department': department,
        'page_title': f'Review Deliverables &bull; {task.task_number}',
    }
    return render(request, 'tasks/manager_submission_review.html', context)


@login_required
def task_request_extension_view(request, task_id):
    """
    Extension / Reassignment request portal:
    - STRICTLY restricted to the assigned member of the task.
    - Member can request more days or request task reassignment.
    """
    user = request.user
    task = get_object_or_404(Task, pk=task_id)

    if task.assigned_to != user:
        messages.error(request, "Permission Denied: Only the assigned member can request an extension or reassignment.")
        return redirect('task_detail', task_id=task.id)

    if task.status == Task.Status.COMPLETED:
        messages.info(request, "This task is already completed.")
        return redirect('task_detail', task_id=task.id)

    # Check for existing pending request
    if task.extension_requests.filter(status=TaskExtensionRequest.Status.PENDING).exists():
        messages.warning(request, "You already have a pending extension/reassignment request awaiting manager review.")
        return redirect('task_detail', task_id=task.id)

    if request.method == 'POST':
        form = TaskExtensionRequestForm(request.POST)
        if form.is_valid():
            ext_req = form.save(commit=False)
            ext_req.task = task
            ext_req.requested_by = user
            ext_req.status = TaskExtensionRequest.Status.PENDING
            ext_req.save()

            # Ensure overdue task status is explicitly ON_HOLD
            if task.deadline and timezone.now() > task.deadline and task.status != Task.Status.ON_HOLD:
                task.status = Task.Status.ON_HOLD
                task.save()

            req_type_name = ext_req.get_request_type_display()
            messages.success(
                request,
                f"Your {req_type_name} request for task [{task.task_number}] has been submitted to the Creative Department Manager for review."
            )
            return redirect('task_detail', task_id=task.id)
    else:
        # Prepopulate default requested days
        form = TaskExtensionRequestForm(initial={'requested_days': 3})

    context = {
        'task': task,
        'form': form,
        'page_title': f'Request Extension / Reassignment &bull; {task.task_number}',
    }
    return render(request, 'tasks/task_request_extension.html', context)


@login_required
def manager_extension_requests_view(request):
    """
    Manager Review Portal for Extension & Reassignment Requests:
    - STRICTLY restricted to Creative Department Manager.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can review task requests.")
        return redirect('task_list')

    department = get_creative_department_instance()
    status_filter = request.GET.get('status', 'PENDING')

    requests_qs = TaskExtensionRequest.objects.filter(
        task__department=department
    ).select_related('task', 'requested_by', 'task__branch', 'reviewed_by').order_by('-created_at')

    if status_filter and status_filter != 'ALL':
        requests_qs = requests_qs.filter(status=status_filter)

    pending_count = TaskExtensionRequest.objects.filter(
        task__department=department,
        status=TaskExtensionRequest.Status.PENDING
    ).count()

    context = {
        'department': department,
        'requests': requests_qs,
        'current_status': status_filter,
        'pending_count': pending_count,
        'page_title': 'Review Extension & Reassignment Requests',
    }
    return render(request, 'tasks/manager_extension_requests.html', context)


@login_required
def manager_extension_review_view(request, request_id):
    """
    Handles manager decision on a specific extension or reassignment request:
    - Grant More Days / Extend Deadline (sets new deadline, resumes task to ACTIVE)
    - Reassign Task to Another Member (sets new branch & member, optional deadline, resumes task to ACTIVE)
    - Reject Request (keeps task status)
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can review requests.")
        return redirect('task_list')

    department = get_creative_department_instance()
    ext_request = get_object_or_404(
        TaskExtensionRequest.objects.select_related('task', 'requested_by', 'task__branch'),
        pk=request_id,
        task__department=department
    )
    task = ext_request.task

    if request.method == 'POST':
        form = ManagerExtensionReviewForm(request.POST, department=department)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            manager_remarks = form.cleaned_data.get('manager_remarks', '')

            if decision == 'EXTEND':
                new_deadline = form.cleaned_data.get('new_deadline')
                if not new_deadline:
                    # Fallback to calculating from requested days or +3 days
                    days = ext_request.requested_days or 3
                    base_time = task.deadline if (task.deadline and task.deadline > timezone.now()) else timezone.now()
                    new_deadline = base_time + datetime.timedelta(days=days)

                task.deadline = new_deadline
                task.status = Task.Status.ACTIVE
                task.save()

                ext_request.status = TaskExtensionRequest.Status.APPROVED
                ext_request.manager_action = TaskExtensionRequest.ManagerAction.EXTENDED
                ext_request.reviewed_by = user
                ext_request.reviewed_at = timezone.now()
                ext_request.manager_remarks = manager_remarks
                ext_request.save()

                messages.success(
                    request,
                    f"Approved! Task [{task.task_number}] deadline extended to {timezone.localtime(task.deadline).strftime('%b %d, %Y %I:%M %p')} and resumed to Active."
                )

            elif decision == 'REASSIGN':
                reassign_branch = form.cleaned_data.get('reassign_branch')
                reassign_user = form.cleaned_data.get('reassign_user')
                new_deadline = form.cleaned_data.get('new_deadline')

                if not reassign_user:
                    messages.error(request, "Please select a member to reassign this task to.")
                    return render(request, 'tasks/manager_extension_review.html', {'ext_request': ext_request, 'task': task, 'form': form, 'department': department})

                if reassign_branch:
                    task.branch = reassign_branch
                task.assigned_to = reassign_user
                if new_deadline:
                    task.deadline = new_deadline
                task.status = Task.Status.ACTIVE
                task.save()

                ext_request.status = TaskExtensionRequest.Status.APPROVED
                ext_request.manager_action = TaskExtensionRequest.ManagerAction.REASSIGNED
                ext_request.reviewed_by = user
                ext_request.reviewed_at = timezone.now()
                ext_request.manager_remarks = manager_remarks
                ext_request.save()

                messages.success(
                    request,
                    f"Reassigned! Task [{task.task_number}] has been successfully reassigned to {reassign_user.get_full_name() or reassign_user.username} and resumed to Active."
                )

            elif decision == 'REJECT':
                ext_request.status = TaskExtensionRequest.Status.REJECTED
                ext_request.manager_action = TaskExtensionRequest.ManagerAction.REJECTED
                ext_request.reviewed_by = user
                ext_request.reviewed_at = timezone.now()
                ext_request.manager_remarks = manager_remarks
                ext_request.save()

                messages.warning(
                    request,
                    f"Extension request for task [{task.task_number}] was rejected."
                )

            return redirect('manager_extension_requests')
    else:
        # Prepopulate suggested new deadline if days requested
        initial_data = {}
        if ext_request.requested_days:
            base_time = task.deadline if (task.deadline and task.deadline > timezone.now()) else timezone.now()
            sug_deadline = base_time + datetime.timedelta(days=ext_request.requested_days)
            initial_data['new_deadline'] = sug_deadline
        elif ext_request.requested_deadline:
            initial_data['new_deadline'] = ext_request.requested_deadline

        if task.branch:
            initial_data['reassign_branch'] = task.branch

        form = ManagerExtensionReviewForm(initial=initial_data, department=department)

    context = {
        'ext_request': ext_request,
        'task': task,
        'form': form,
        'department': department,
        'page_title': f'Review Request &bull; {task.task_number}',
    }
    return render(request, 'tasks/manager_extension_review.html', context)


@login_required
def task_edit_view(request, task_id):
    """
    Edits a task:
    - STRICTLY restricted to the Creative Department Manager.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can modify tasks.")
        return redirect('task_detail', task_id=task_id)

    task = get_object_or_404(Task, pk=task_id)
    department = task.department

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, instance=task, department=department)
        if form.is_valid():
            task = form.save()

            # Process any newly attached files
            files = request.FILES.getlist('documents')
            for f in files:
                TaskAttachment.objects.create(
                    task=task,
                    file=f
                )

            messages.success(request, f"Task [{task.task_number}] updated successfully.")
            return redirect('task_detail', task_id=task.id)
    else:
        form = TaskForm(instance=task, department=department)

    context = {
        'form': form,
        'task': task,
        'department': department,
        'page_title': f'Edit Task &bull; {task.task_number}',
    }
    return render(request, 'tasks/task_edit.html', context)


@login_required
def task_delete_view(request, task_id):
    """
    Deletes a task:
    - STRICTLY restricted to the Creative Department Manager.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can delete tasks.")
        return redirect('task_detail', task_id=task_id)

    task = get_object_or_404(Task, pk=task_id)

    if request.method == 'POST':
        task_num = task.task_number
        task.delete()
        messages.success(request, f"Task [{task_num}] has been deleted.")
        return redirect('task_list')

    return render(request, 'tasks/task_confirm_delete.html', {'task': task})


@login_required
def attachment_delete_view(request, attachment_id):
    """Deletes a specific attachment file from a task."""
    user = request.user
    attachment = get_object_or_404(TaskAttachment, pk=attachment_id)
    task_id = attachment.task.id

    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can remove task documents.")
        return redirect('task_detail', task_id=task_id)

    if request.method == 'POST':
        fname = attachment.filename
        attachment.delete()
        messages.success(request, f"Attachment '{fname}' was removed.")

    return redirect('task_detail', task_id=task_id)


# =====================================================================
# Creative Department Client Management Views
# =====================================================================

@login_required
def client_list_view(request):
    """
    Dedicated Client Directory for Creative Department operations.
    Shows client number, name, company, needs snippet, and associated tasks count.
    """
    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You do not have permission to view Creative Department clients.")
        return redirect('dashboard_router')

    creative_dept = get_creative_department_instance()
    if user.department and is_creative_department(user.department):
        department = user.department
    else:
        department = creative_dept

    is_creative_manager = can_manage_creative_tasks(user)

    clients = Client.objects.filter(department=department).select_related('created_by').prefetch_related('tasks')

    form = ClientFilterForm(request.GET)
    if form.is_valid():
        q = form.cleaned_data.get('q')
        if q:
            clients = clients.filter(
                models.Q(client_number__icontains=q) |
                models.Q(name__icontains=q) |
                models.Q(company__icontains=q) |
                models.Q(needs__icontains=q) |
                models.Q(email__icontains=q)
            )

    total_clients = clients.count()

    context = {
        'clients': clients,
        'filter_form': form,
        'department': department,
        'is_creative_manager': is_creative_manager,
        'total_clients': total_clients,
        'page_title': 'Creative Department Clients',
    }
    return render(request, 'tasks/client_list.html', context)


@login_required
def client_create_view(request):
    """
    Dedicated Page in Creative Department Manager portal for adding new clients.
    Mandatory fields: client number, client name, company, needs.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager has authority to add new clients.")
        return redirect('client_list')

    creative_dept = get_creative_department_instance()
    if user.department and is_creative_department(user.department):
        department = user.department
    else:
        department = creative_dept

    if request.method == 'POST':
        form = ClientForm(request.POST, department=department)
        if form.is_valid():
            client = form.save(commit=False)
            client.department = department
            client.created_by = user
            client.save()

            messages.success(
                request,
                f"Client [{client.client_number}] '{client.name}' ({client.company}) has been added successfully!"
            )
            return redirect('client_list')
    else:
        form = ClientForm(department=department)

    return render(request, 'tasks/client_create.html', {
        'form': form,
        'department': department,
        'page_title': 'Add New Client | Creative Department',
    })


@login_required
def client_detail_view(request, client_id):
    """
    Client Profile Dossier:
    Shows Client Number, Client Name, Company, Needs / Scope, Contact info, and Associated Tasks.
    """
    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You do not have permission to view this client.")
        return redirect('dashboard_router')

    client = get_object_or_404(Client.objects.select_related('department', 'created_by').prefetch_related('tasks'), pk=client_id)
    is_creative_manager = can_manage_creative_tasks(user)

    tasks = client.tasks.select_related('assigned_to', 'branch').order_by('-created_at')

    return render(request, 'tasks/client_detail.html', {
        'client': client,
        'tasks': tasks,
        'is_creative_manager': is_creative_manager,
        'page_title': f'Client: {client.name} ({client.company})',
    })


@login_required
def client_edit_view(request, client_id):
    """
    Allows Creative Department Manager to update client details, company info, and needs.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can edit client information.")
        return redirect('client_detail', client_id=client_id)

    client = get_object_or_404(Client, pk=client_id)

    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client, department=client.department)
        if form.is_valid():
            form.save()
            messages.success(request, f"Client [{client.client_number}] details updated successfully.")
            return redirect('client_detail', client_id=client.id)
    else:
        form = ClientForm(instance=client, department=client.department)

    return render(request, 'tasks/client_edit.html', {
        'form': form,
        'client': client,
        'page_title': f'Edit Client: {client.name}',
    })


@login_required
def client_delete_view(request, client_id):
    """
    Allows Creative Department Manager to delete a client with confirmation.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can delete clients.")
        return redirect('client_list')

    client = get_object_or_404(Client, pk=client_id)

    if request.method == 'POST':
        c_num = client.client_number
        c_name = client.name
        client.delete()
        messages.success(request, f"Client [{c_num}] '{c_name}' was removed from the client registry.")
        return redirect('client_list')

    return render(request, 'tasks/client_confirm_delete.html', {'client': client})


# =====================================================================
# Multi-Branch Client Assignment & Executive Delegation Views
# =====================================================================

@login_required
def client_assign_view(request, client_id=None):
    """
    Dedicated Page for Creative Department Manager to assign a Client to a specific Branch
    and that Branch's Executive for a particular task (e.g. Marketing, Designing, Editing).
    A single client can have multiple branch assignments.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager has authority to assign clients.")
        return redirect('client_list')

    creative_dept = get_creative_department_instance()
    if user.department and is_creative_department(user.department):
        department = user.department
    else:
        department = creative_dept

    selected_client = None
    if client_id:
        selected_client = get_object_or_404(Client, pk=client_id, department=department)

    existing_assignments = []
    if selected_client:
        existing_assignments = selected_client.assignments.select_related(
            'branch', 'executive', 'delegated_member'
        ).order_by('-created_at')

    if request.method == 'POST':
        form = ClientAssignmentForm(
            request.POST,
            department=department,
            initial_client=selected_client
        )
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.assigned_by = user
            assignment.status = ClientAssignment.Status.ASSIGNED_TO_EXECUTIVE
            assignment.save()

            messages.success(
                request,
                f"Client [{assignment.client.client_number}] '{assignment.client.name}' was assigned to "
                f"the {assignment.branch.name} Branch (Executive: {assignment.executive.get_full_name() or assignment.executive.username}) "
                f"for '{assignment.task_title}'."
            )
            return redirect('client_detail', client_id=assignment.client.id)
    else:
        form = ClientAssignmentForm(
            department=department,
            initial_client=selected_client
        )

    # All branches in creative department
    branches = Branch.objects.filter(department=department)
    clients = Client.objects.filter(department=department)

    return render(request, 'tasks/client_assign.html', {
        'form': form,
        'selected_client': selected_client,
        'existing_assignments': existing_assignments,
        'department': department,
        'branches': branches,
        'clients': clients,
        'page_title': f'Assign Client to Branch | {department.name}',
    })


@login_required
def executive_client_assignments_view(request):
    """
    Dedicated Portal for Branch Executives & Team Members:
    - Branch Executive views client assignments assigned to them for their branch.
    - Staff / Interns view client tasks delegated to them.
    - Department Manager & Leadership view all client branch allocations.
    """
    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You do not have permission to view client assignments.")
        return redirect('dashboard_router')

    creative_dept = get_creative_department_instance()
    is_creative_manager = can_manage_creative_tasks(user)

    if is_creative_manager or get_user_level(user) <= 2:
        assignments = ClientAssignment.objects.all().select_related(
            'client', 'branch', 'assigned_by', 'executive', 'delegated_member'
        )
    elif user.role == User.Role.EXECUTIVE:
        assignments = ClientAssignment.objects.filter(
            models.Q(executive=user) | models.Q(branch=user.branch)
        ).select_related('client', 'branch', 'assigned_by', 'executive', 'delegated_member')
    else:
        # Staff / Intern: view tasks delegated to them or for their branch
        assignments = ClientAssignment.objects.filter(
            models.Q(delegated_member=user) | models.Q(branch=user.branch)
        ).select_related('client', 'branch', 'assigned_by', 'executive', 'delegated_member')

    pending_delegations_count = 0
    if user.role == User.Role.EXECUTIVE:
        pending_delegations_count = assignments.filter(
            executive=user,
            status=ClientAssignment.Status.ASSIGNED_TO_EXECUTIVE
        ).count()

    return render(request, 'tasks/executive_client_assignments.html', {
        'assignments': assignments,
        'pending_delegations_count': pending_delegations_count,
        'is_creative_manager': is_creative_manager,
        'page_title': 'Client Branch Allocations & Assignments',
    })


@login_required
def executive_client_delegate_view(request, assignment_id):
    """
    Dedicated Page for Branch Executive to delegate an assigned client task
    to staff members or interns in their specific branch.
    """
    user = request.user
    assignment = get_object_or_404(
        ClientAssignment.objects.select_related('client', 'branch', 'executive', 'assigned_by'),
        pk=assignment_id
    )

    # Permission: only the assigned Executive or Creative Manager
    is_creative_manager = can_manage_creative_tasks(user)
    if not is_creative_manager and assignment.executive != user and get_user_level(user) > 2:
        messages.error(request, "Permission Denied: Only the assigned Branch Executive can delegate this client task.")
        return redirect('executive_client_assignments')

    branch = assignment.branch

    if request.method == 'POST':
        form = ExecutiveDelegationForm(request.POST, branch=branch, instance=assignment)
        if form.is_valid():
            assignment = form.save(commit=False)
            assignment.delegated_at = timezone.now()
            assignment.status = ClientAssignment.Status.DELEGATED
            assignment.save()

            messages.success(
                request,
                f"Client deliverable '{assignment.task_title}' for [{assignment.client.company}] "
                f"was successfully delegated to {assignment.delegated_member.get_full_name() or assignment.delegated_member.username}."
            )
            return redirect('executive_client_assignments')
    else:
        form = ExecutiveDelegationForm(branch=branch, instance=assignment)

    return render(request, 'tasks/executive_client_delegate.html', {
        'assignment': assignment,
        'form': form,
        'branch': branch,
        'page_title': f'Delegate Client Task: {assignment.task_title}',
    })


@login_required
def branch_executives_api(request, branch_id):
    """
    JSON API returning Executives belonging to a specific branch.
    Used for dynamic executive dropdown filtering in client assignment forms.
    """
    if not request.user.is_authenticated:
        return JsonResponse({'error': 'Unauthorized'}, status=401)

    branch = get_object_or_404(Branch, pk=branch_id)
    executives = User.objects.filter(
        branch=branch,
        role=User.Role.EXECUTIVE
    ).values('id', 'username', 'first_name', 'last_name', 'designation')

    data = [
        {
            'id': e['id'],
            'name': f"{e['first_name']} {e['last_name']}".strip() or e['username'],
            'designation': e['designation'] or 'Executive'
        }
        for e in executives
    ]
    return JsonResponse({'executives': data})


@login_required
def client_assignment_detail_view(request, assignment_id):
    """
    Comprehensive Dossier View for a Multi-Branch Client Assignment:
    - View client briefs, branch deliverables scope, timeline, delegation details.
    - View complete deliverables submission history, attached files, executive feedback, and manager reviews.
    - Contextual action buttons:
      - Assigned Delegate: Submit Completed Work / Resubmit Revisions.
      - Branch Executive: Review Delegate Submissions / Reassign Delegate.
      - Department Manager: Final Review & Approval.
    """
    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You cannot view this client assignment.")
        return redirect('dashboard_router')

    assignment = get_object_or_404(
        ClientAssignment.objects.select_related(
            'client', 'branch', 'assigned_by', 'executive', 'delegated_member'
        ).prefetch_related(
            'submissions__attachments',
            'submissions__submitted_by',
            'submissions__executive_reviewed_by',
            'submissions__manager_reviewed_by'
        ),
        pk=assignment_id
    )

    is_creative_manager = can_manage_creative_tasks(user)
    is_leadership = get_user_level(user) <= 2 or is_creative_manager
    is_executive_lead = (assignment.executive == user)
    is_assigned_delegate = (assignment.delegated_member == user)

    # Permission check for regular members: must belong to branch or be assigned
    if not is_leadership and not is_executive_lead and not is_assigned_delegate:
        if assignment.branch != user.branch:
            messages.error(request, "Access restricted: This client assignment belongs to another branch.")
            return redirect('executive_client_assignments')

    latest_submission = assignment.submissions.order_by('-submitted_at').first()

    # Can this user submit work? (Assigned delegate when status allows submission)
    can_submit_work = is_assigned_delegate and assignment.status in [
        ClientAssignment.Status.DELEGATED,
        ClientAssignment.Status.IN_PROGRESS,
        ClientAssignment.Status.EXECUTIVE_REVISION,
        ClientAssignment.Status.DEPT_MANAGER_REVISION,
    ]

    # Can executive review?
    can_executive_review = (is_executive_lead or is_leadership) and assignment.status in [
        ClientAssignment.Status.UNDER_EXECUTIVE_REVIEW,
        ClientAssignment.Status.DELEGATED,
        ClientAssignment.Status.IN_PROGRESS,
    ]

    # Can department manager review?
    can_manager_review = is_leadership and assignment.status in [
        ClientAssignment.Status.UNDER_DEPT_MANAGER_REVIEW,
        ClientAssignment.Status.UNDER_EXECUTIVE_REVIEW,
        ClientAssignment.Status.DELEGATED,
        ClientAssignment.Status.IN_PROGRESS,
    ]

    context = {
        'assignment': assignment,
        'latest_submission': latest_submission,
        'is_creative_manager': is_creative_manager,
        'is_leadership': is_leadership,
        'is_executive_lead': is_executive_lead,
        'is_assigned_delegate': is_assigned_delegate,
        'can_submit_work': can_submit_work,
        'can_executive_review': can_executive_review,
        'can_manager_review': can_manager_review,
        'page_title': f'Client Directive &bull; [{assignment.client.client_number}] {assignment.task_title}',
    }
    return render(request, 'tasks/client_assignment_detail.html', context)


@login_required
def client_assignment_submit_view(request, assignment_id):
    """
    Deliverables Submission Portal for Staff / Intern:
    - Restricted to the assigned delegated_member.
    - Uploads work details, completion remarks, and supporting media files (any format).
    - Status transitions to UNDER_EXECUTIVE_REVIEW (Sent directly to Branch Executive).
    """
    user = request.user
    assignment = get_object_or_404(
        ClientAssignment.objects.select_related('client', 'branch', 'executive', 'delegated_member'),
        pk=assignment_id
    )

    is_creative_manager = can_manage_creative_tasks(user)
    if assignment.delegated_member != user and not is_creative_manager:
        messages.error(request, "Permission Denied: Only the member delegated to this task can submit deliverables.")
        return redirect('client_assignment_detail', assignment_id=assignment.id)

    if assignment.status == ClientAssignment.Status.COMPLETED:
        messages.info(request, "This assignment has already been completed and approved by the Department Manager.")
        return redirect('client_assignment_detail', assignment_id=assignment.id)

    if request.method == 'POST':
        form = ClientAssignmentSubmissionForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save(commit=False)
            submission.assignment = assignment
            submission.submitted_by = user
            submission.review_stage = ClientAssignmentSubmission.ReviewStage.PENDING_EXECUTIVE
            submission.save()

            # Process attached media & documents
            files = request.FILES.getlist('submission_files')
            for f in files:
                ClientAssignmentSubmissionAttachment.objects.create(
                    submission=submission,
                    file=f
                )

            # Move status to UNDER_EXECUTIVE_REVIEW
            assignment.status = ClientAssignment.Status.UNDER_EXECUTIVE_REVIEW
            assignment.save()

            messages.success(
                request,
                f"Work deliverables for '{assignment.task_title}' have been submitted to Executive "
                f"{assignment.executive.get_full_name() or assignment.executive.username} for review."
            )
            return redirect('client_assignment_detail', assignment_id=assignment.id)
    else:
        form = ClientAssignmentSubmissionForm()

    return render(request, 'tasks/client_assignment_submit.html', {
        'assignment': assignment,
        'form': form,
        'page_title': f'Submit Deliverables &bull; {assignment.task_title}',
    })


@login_required
def client_assignment_executive_review_view(request, assignment_id, submission_id=None):
    """
    Executive Review Portal:
    - Restricted to the Branch Executive assigned to supervise this branch task.
    - Evaluation options:
      1. FORWARD_TO_MANAGER: Satisfied -> Forwards to Creative Department Manager for final approval.
      2. REQUEST_REVISION: Not Satisfied -> Requests delegate to redo/revise with specific feedback.
      3. REASSIGN: Reassigns the task to another staff member or intern in the branch.
    """
    user = request.user
    assignment = get_object_or_404(
        ClientAssignment.objects.select_related('client', 'branch', 'executive', 'delegated_member', 'assigned_by'),
        pk=assignment_id
    )

    is_creative_manager = can_manage_creative_tasks(user)
    if assignment.executive != user and not is_creative_manager and get_user_level(user) > 2:
        messages.error(request, "Permission Denied: Only the Branch Executive can review these submissions.")
        return redirect('client_assignment_detail', assignment_id=assignment.id)

    if submission_id:
        submission = get_object_or_404(ClientAssignmentSubmission, pk=submission_id, assignment=assignment)
    else:
        submission = assignment.submissions.order_by('-submitted_at').first()

    if not submission:
        messages.warning(request, "No deliverables have been submitted by the delegate yet.")
        return redirect('client_assignment_detail', assignment_id=assignment.id)

    branch = assignment.branch

    if request.method == 'POST':
        form = ClientAssignmentExecutiveReviewForm(request.POST, branch=branch)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            feedback = form.cleaned_data.get('feedback', '').strip()
            new_deadline = form.cleaned_data.get('new_deadline')

            submission.executive_feedback = feedback
            submission.executive_reviewed_by = user
            submission.executive_reviewed_at = timezone.now()

            if decision == 'FORWARD_TO_MANAGER':
                submission.review_stage = ClientAssignmentSubmission.ReviewStage.FORWARDED_TO_MANAGER
                submission.save()

                assignment.status = ClientAssignment.Status.UNDER_DEPT_MANAGER_REVIEW
                assignment.save()

                messages.success(
                    request,
                    f"Satisfied! Deliverables for '{assignment.task_title}' have been forwarded to Department Manager for final sign-off."
                )

            elif decision == 'REQUEST_REVISION':
                submission.review_stage = ClientAssignmentSubmission.ReviewStage.EXECUTIVE_REVISION_REQUESTED
                submission.save()

                assignment.status = ClientAssignment.Status.EXECUTIVE_REVISION
                if new_deadline:
                    assignment.deadline = new_deadline
                assignment.save()

                delegate_name = assignment.delegated_member.get_full_name() or assignment.delegated_member.username if assignment.delegated_member else "the delegate"
                messages.warning(
                    request,
                    f"Revision requested for '{assignment.task_title}'. {delegate_name} has been asked to redo / revise based on your feedback."
                )

            elif decision == 'REASSIGN':
                new_delegate = form.cleaned_data.get('reassign_to')
                if not new_delegate:
                    messages.error(request, "Please select a branch member to reassign this task to.")
                    return render(request, 'tasks/client_assignment_executive_review.html', {
                        'assignment': assignment,
                        'submission': submission,
                        'form': form,
                        'branch': branch,
                        'page_title': f'Executive Review &bull; {assignment.task_title}',
                    })

                submission.review_stage = ClientAssignmentSubmission.ReviewStage.EXECUTIVE_REVISION_REQUESTED
                submission.save()

                assignment.delegated_member = new_delegate
                assignment.delegated_at = timezone.now()
                assignment.executive_notes = feedback or assignment.executive_notes
                assignment.status = ClientAssignment.Status.DELEGATED
                if new_deadline:
                    assignment.deadline = new_deadline
                assignment.save()

                messages.success(
                    request,
                    f"Task '{assignment.task_title}' was reassigned to {new_delegate.get_full_name() or new_delegate.username}."
                )

            return redirect('client_assignment_detail', assignment_id=assignment.id)
    else:
        form = ClientAssignmentExecutiveReviewForm(branch=branch)

    return render(request, 'tasks/client_assignment_executive_review.html', {
        'assignment': assignment,
        'submission': submission,
        'form': form,
        'branch': branch,
        'page_title': f'Executive Review &bull; {assignment.task_title}',
    })


@login_required
def client_assignment_manager_review_view(request, assignment_id, submission_id=None):
    """
    Department Manager Final Approval Portal:
    - Restricted to Creative Department Manager & Corporate Leadership (Level <= 2).
    - Evaluation options:
      1. APPROVE: Verifies deliverables and marks assignment as COMPLETED.
      2. REQUEST_REVISION: Requests revisions or adjustments from branch team.
      3. REASSIGN_BRANCH: Reassigns client task to another branch / executive.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager can perform final approval.")
        return redirect('executive_client_assignments')

    creative_dept = get_creative_department_instance()
    assignment = get_object_or_404(
        ClientAssignment.objects.select_related('client', 'branch', 'executive', 'delegated_member', 'assigned_by'),
        pk=assignment_id
    )

    if submission_id:
        submission = get_object_or_404(ClientAssignmentSubmission, pk=submission_id, assignment=assignment)
    else:
        submission = assignment.submissions.order_by('-submitted_at').first()

    if not submission:
        messages.warning(request, "No deliverables have been submitted for this client task yet.")
        return redirect('client_assignment_detail', assignment_id=assignment.id)

    if request.method == 'POST':
        form = ClientAssignmentManagerReviewForm(request.POST, department=creative_dept)
        if form.is_valid():
            decision = form.cleaned_data['decision']
            feedback = form.cleaned_data.get('manager_feedback', '').strip()
            new_deadline = form.cleaned_data.get('new_deadline')

            submission.manager_feedback = feedback
            submission.manager_reviewed_by = user
            submission.manager_reviewed_at = timezone.now()

            if decision == 'APPROVE':
                submission.review_stage = ClientAssignmentSubmission.ReviewStage.MANAGER_APPROVED
                submission.save()

                assignment.status = ClientAssignment.Status.COMPLETED
                assignment.save()

                messages.success(
                    request,
                    f"Excellent! Client deliverable '{assignment.task_title}' for [{assignment.client.company}] "
                    f"has been approved and marked as Completed."
                )

            elif decision == 'REQUEST_REVISION':
                submission.review_stage = ClientAssignmentSubmission.ReviewStage.MANAGER_REVISION_REQUESTED
                submission.save()

                assignment.status = ClientAssignment.Status.DEPT_MANAGER_REVISION
                if new_deadline:
                    assignment.deadline = new_deadline
                assignment.save()

                messages.warning(
                    request,
                    f"Revision requested for '{assignment.task_title}'. The branch team has been notified with your directions."
                )

            elif decision == 'REASSIGN_BRANCH':
                new_branch = form.cleaned_data.get('reassign_branch')
                new_exec = form.cleaned_data.get('reassign_executive')

                if not new_branch or not new_exec:
                    messages.error(request, "Please select both a target branch and an executive to reassign.")
                    return render(request, 'tasks/client_assignment_manager_review.html', {
                        'assignment': assignment,
                        'submission': submission,
                        'form': form,
                        'page_title': f'Department Manager Review &bull; {assignment.task_title}',
                    })

                assignment.branch = new_branch
                assignment.executive = new_exec
                assignment.delegated_member = None
                assignment.delegated_at = None
                assignment.status = ClientAssignment.Status.ASSIGNED_TO_EXECUTIVE
                if new_deadline:
                    assignment.deadline = new_deadline
                assignment.save()

                messages.success(
                    request,
                    f"Client task '{assignment.task_title}' was reassigned to the {new_branch.name} Branch (Executive: {new_exec.get_full_name() or new_exec.username})."
                )

            return redirect('client_assignment_detail', assignment_id=assignment.id)
    else:
        form = ClientAssignmentManagerReviewForm(department=creative_dept)

    return render(request, 'tasks/client_assignment_manager_review.html', {
        'assignment': assignment,
        'submission': submission,
        'form': form,
        'page_title': f'Department Manager Review &bull; {assignment.task_title}',
    })


@login_required
def creative_calendar_view(request):
    """
    Monthly Operational Calendar for Creative Department:
    - Auto-populated with:
      * Tasks: Assigned Date & Deadline Date
      * Client Branch Allocations: Assigned Date & Deadline Date
    - Detail drawers/modals for each event marker.
    - Fully accessible to all Creative Department members, executives, and managers.
    """
    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You do not have permission to view the Creative Department calendar.")
        return redirect('dashboard_router')

    dept = get_creative_department_instance()
    is_creative_manager = can_manage_creative_tasks(user)
    is_leadership = get_user_level(user) <= 2 or is_creative_manager

    # Resolve requested Year & Month in IST
    now = timezone.localtime(timezone.now())
    try:
        year = int(request.GET.get('year', now.year))
        month = int(request.GET.get('month', now.month))
        if not (1 <= month <= 12):
            month = now.month
        if not (2020 <= year <= 2040):
            year = now.year
    except (ValueError, TypeError):
        year = now.year
        month = now.month

    # Navigation months
    if month == 1:
        prev_month = 12
        prev_year = year - 1
    else:
        prev_month = month - 1
        prev_year = year

    if month == 12:
        next_month = 1
        next_year = year + 1
    else:
        next_month = month + 1
        next_year = year

    # Filter parameters
    selected_branch_id = request.GET.get('branch', '')
    selected_event_type = request.GET.get('event_type', 'ALL')

    # Date range for target month
    num_days = calendar.monthrange(year, month)[1]

    # 1. Fetch Tasks
    tasks_qs = Task.objects.filter(department=dept).select_related(
        'branch', 'assigned_to', 'created_by', 'client'
    )
    if selected_branch_id:
        tasks_qs = tasks_qs.filter(branch_id=selected_branch_id)
    if not is_leadership and user.branch:
        tasks_qs = tasks_qs.filter(Q(branch=user.branch) | Q(branch__isnull=True))

    # 2. Fetch Client Branch Assignments
    client_assign_qs = ClientAssignment.objects.filter(client__department=dept).select_related(
        'client', 'branch', 'executive', 'delegated_member', 'assigned_by'
    )
    if selected_branch_id:
        client_assign_qs = client_assign_qs.filter(branch_id=selected_branch_id)
    if not is_leadership and user.branch:
        client_assign_qs = client_assign_qs.filter(branch=user.branch)

    # Organize events by day of the month {day_int: [event_dicts]}
    days_events = {d: [] for d in range(1, num_days + 1)}

    # Process Tasks
    for t in tasks_qs:
        # A. Task Assigned Date
        t_assigned_dt = timezone.localtime(t.created_at)
        if t_assigned_dt.year == year and t_assigned_dt.month == month:
            d_num = t_assigned_dt.day
            if selected_event_type in ['ALL', 'TASK_ASSIGNED']:
                assignee_display = t.assigned_to.get_full_name() or t.assigned_to.username if (is_leadership or t.assigned_to == user) else "Assigned Member"
                days_events[d_num].append({
                    'id': f"task-assign-{t.id}",
                    'category': 'TASK_ASSIGNED',
                    'category_label': 'Task Assigned',
                    'badge_class': 'bg-primary text-white',
                    'pill_bg': '#4f46e5',
                    'icon': 'bi-plus-circle-fill',
                    'code': t.task_number,
                    'title': t.title,
                    'client_company': t.client.company if t.client else 'Internal Studio Directive',
                    'branch_name': t.branch.name if t.branch else 'All Branches',
                    'assignee': assignee_display,
                    'status': t.get_status_display(),
                    'status_badge': t.status_badge_class,
                    'priority': t.get_priority_display(),
                    'priority_badge': t.priority_badge_class,
                    'date_label': 'Assigned Date',
                    'date_val': t_assigned_dt.strftime('%b %d, %Y %I:%M %p'),
                    'deadline_val': timezone.localtime(t.deadline).strftime('%b %d, %Y %I:%M %p') if t.deadline else 'None',
                    'description': t.description,
                    'url': reverse('task_detail', kwargs={'task_id': t.id}),
                    'is_overdue': False,
                })

        # B. Task Deadline Date
        if t.deadline:
            t_deadline_dt = timezone.localtime(t.deadline)
            if t_deadline_dt.year == year and t_deadline_dt.month == month:
                d_num = t_deadline_dt.day
                if selected_event_type in ['ALL', 'TASK_DEADLINE']:
                    assignee_display = t.assigned_to.get_full_name() or t.assigned_to.username if (is_leadership or t.assigned_to == user) else "Assigned Member"
                    days_events[d_num].append({
                        'id': f"task-dead-{t.id}",
                        'category': 'TASK_DEADLINE',
                        'category_label': 'Task Deadline',
                        'badge_class': 'bg-danger text-white' if t.is_overdue else 'bg-rose text-white',
                        'pill_bg': '#ef4444' if t.is_overdue else '#e11d48',
                        'icon': 'bi-alarm-fill',
                        'code': t.task_number,
                        'title': t.title,
                        'client_company': t.client.company if t.client else 'Internal Studio Directive',
                        'branch_name': t.branch.name if t.branch else 'All Branches',
                        'assignee': assignee_display,
                        'status': t.get_status_display(),
                        'status_badge': t.status_badge_class,
                        'priority': t.get_priority_display(),
                        'priority_badge': t.priority_badge_class,
                        'date_label': 'Task Deadline',
                        'date_val': t_deadline_dt.strftime('%b %d, %Y %I:%M %p'),
                        'deadline_val': t_deadline_dt.strftime('%b %d, %Y %I:%M %p'),
                        'description': t.description,
                        'url': reverse('task_detail', kwargs={'task_id': t.id}),
                        'is_overdue': t.is_overdue,
                    })

    # Process Client Assignments
    for a in client_assign_qs:
        # A. Client Assignment Assigned Date
        a_assigned_dt = timezone.localtime(a.created_at)
        if a_assigned_dt.year == year and a_assigned_dt.month == month:
            d_num = a_assigned_dt.day
            if selected_event_type in ['ALL', 'CLIENT_ASSIGNED']:
                days_events[d_num].append({
                    'id': f"client-assign-{a.id}",
                    'category': 'CLIENT_ASSIGNED',
                    'category_label': 'Client Directive Assigned',
                    'badge_class': 'bg-teal text-white',
                    'pill_bg': '#0d9488',
                    'icon': 'bi-diagram-3-fill',
                    'code': a.client.client_number,
                    'title': f"{a.client.company} - {a.task_title}",
                    'client_company': a.client.company,
                    'branch_name': a.branch.name,
                    'executive': a.executive.get_full_name() or a.executive.username,
                    'assignee': a.delegated_member.get_full_name() or a.delegated_member.username if a.delegated_member else 'Awaiting Exec Delegation',
                    'status': a.get_status_display(),
                    'status_badge': a.status_badge_class,
                    'priority': 'Client Deliverable',
                    'priority_badge': 'bg-teal text-white',
                    'date_label': 'Allocated On',
                    'date_val': a_assigned_dt.strftime('%b %d, %Y %I:%M %p'),
                    'deadline_val': timezone.localtime(a.deadline).strftime('%b %d, %Y %I:%M %p') if a.deadline else 'None',
                    'description': a.task_scope,
                    'url': reverse('client_assignment_detail', kwargs={'assignment_id': a.id}),
                    'is_overdue': False,
                })

        # B. Client Assignment Deadline Date
        if a.deadline:
            a_deadline_dt = timezone.localtime(a.deadline)
            if a_deadline_dt.year == year and a_deadline_dt.month == month:
                d_num = a_deadline_dt.day
                if selected_event_type in ['ALL', 'CLIENT_DEADLINE']:
                    days_events[d_num].append({
                        'id': f"client-dead-{a.id}",
                        'category': 'CLIENT_DEADLINE',
                        'category_label': 'Client Deliverable Deadline',
                        'badge_class': 'bg-warning text-dark',
                        'pill_bg': '#f59e0b',
                        'icon': 'bi-flag-fill',
                        'code': a.client.client_number,
                        'title': f"{a.client.company} - {a.task_title}",
                        'client_company': a.client.company,
                        'branch_name': a.branch.name,
                        'executive': a.executive.get_full_name() or a.executive.username,
                        'assignee': a.delegated_member.get_full_name() or a.delegated_member.username if a.delegated_member else 'Awaiting Exec Delegation',
                        'status': a.get_status_display(),
                        'status_badge': a.status_badge_class,
                        'priority': 'Client Deliverable',
                        'priority_badge': 'bg-warning text-dark',
                        'date_label': 'Target Deadline',
                        'date_val': a_deadline_dt.strftime('%b %d, %Y %I:%M %p'),
                        'deadline_val': a_deadline_dt.strftime('%b %d, %Y %I:%M %p'),
                        'description': a.task_scope,
                        'url': reverse('client_assignment_detail', kwargs={'assignment_id': a.id}),
                        'is_overdue': a.is_overdue,
                    })

    # Build matrix of weeks: monthcalendar returns list of [Mon, Tue, Wed, Thu, Fri, Sat, Sun]
    cal = calendar.Calendar(firstweekday=0) # Monday first
    month_weeks = []
    
    today_date = now.date()

    for week in cal.monthdayscalendar(year, month):
        week_days = []
        for d in week:
            if d == 0:
                week_days.append({
                    'day_num': 0,
                    'is_current_month': False,
                    'is_today': False,
                    'events': [],
                    'events_count': 0,
                })
            else:
                d_date = datetime.date(year, month, d)
                ev_list = days_events.get(d, [])
                week_days.append({
                    'day_num': d,
                    'date': d_date,
                    'is_current_month': True,
                    'is_today': (d_date == today_date),
                    'events': ev_list,
                    'events_count': len(ev_list),
                })
        month_weeks.append(week_days)

    # Monthly Summary Stats
    total_events_month = sum(len(ev) for ev in days_events.values())
    task_deadlines_count = sum(1 for ev_list in days_events.values() for ev in ev_list if ev['category'] == 'TASK_DEADLINE')
    client_deadlines_count = sum(1 for ev_list in days_events.values() for ev in ev_list if ev['category'] == 'CLIENT_DEADLINE')
    task_assigned_count = sum(1 for ev_list in days_events.values() for ev in ev_list if ev['category'] == 'TASK_ASSIGNED')
    client_assigned_count = sum(1 for ev_list in days_events.values() for ev in ev_list if ev['category'] == 'CLIENT_ASSIGNED')

    branches = Branch.objects.filter(department=dept).order_by('name')

    month_name = calendar.month_name[month]
    month_choices = [(i, calendar.month_name[i]) for i in range(1, 13)]
    year_choices = list(range(now.year - 2, now.year + 4))

    return render(request, 'tasks/creative_calendar.html', {
        'year': year,
        'month': month,
        'month_name': month_name,
        'prev_month': prev_month,
        'prev_year': prev_year,
        'next_month': next_month,
        'next_year': next_year,
        'month_weeks': month_weeks,
        'month_choices': month_choices,
        'year_choices': year_choices,
        'branches': branches,
        'selected_branch_id': int(selected_branch_id) if selected_branch_id.isdigit() else '',
        'selected_event_type': selected_event_type,
        'total_events_month': total_events_month,
        'task_deadlines_count': task_deadlines_count,
        'client_deadlines_count': client_deadlines_count,
        'task_assigned_count': task_assigned_count,
        'client_assigned_count': client_assigned_count,
        'is_creative_manager': is_creative_manager,
        'page_title': f'Creative Operations Calendar &bull; {month_name} {year}',
    })


# =====================================================================
# HR Customer & External Client Management Across All Departments
# =====================================================================

def can_manage_customers(user):
    """
    Determines if user has authority to view and manage external customers across all departments:
    HR, Manager, Dept Manager, Server Admin, Superadmin.
    """
    if not user.is_authenticated:
        return False
    return user.role in [
        User.Role.HR,
        User.Role.MANAGER,
        User.Role.DEPT_MANAGER,
        User.Role.SERVER_ADMIN,
        User.Role.SUPERADMIN,
    ] or user.is_superuser


@login_required
def customer_management_view(request):
    """
    Dedicated Customer Management page in HR Dashboard.
    Populates external customers/clients across all departments with their basic details:
    Name, Place / City, Phone, Email, Company, Department, and Active Engagements.
    """
    user = request.user
    if not can_manage_customers(user):
        messages.error(request, "Access restricted: You do not have permission to view Customer Management.")
        return redirect('dashboard_router')

    dept_filter = request.GET.get('department', '').strip()
    search_q = request.GET.get('q', '').strip()

    customers = Client.objects.select_related('department', 'created_by').prefetch_related('assignments', 'tasks').order_by('-created_at')

    if dept_filter:
        customers = customers.filter(department_id=dept_filter)

    if search_q:
        customers = customers.filter(
            Q(name__icontains=search_q) |
            Q(company__icontains=search_q) |
            Q(phone__icontains=search_q) |
            Q(address__icontains=search_q) |
            Q(email__icontains=search_q) |
            Q(client_number__icontains=search_q) |
            Q(department__name__icontains=search_q)
        )

    total_customers = Client.objects.count()
    filtered_count = customers.count()

    # Department-wise customer breakdown
    department_stats = Department.objects.annotate(
        client_count=models.Count('clients')
    ).filter(client_count__gt=0).order_by('-client_count')

    all_departments = Department.objects.all()
    active_assignments_count = ClientAssignment.objects.exclude(status=ClientAssignment.Status.COMPLETED).count()

    context = {
        'customers': customers,
        'total_customers': total_customers,
        'filtered_count': filtered_count,
        'department_stats': department_stats,
        'all_departments': all_departments,
        'selected_dept': dept_filter,
        'search_q': search_q,
        'active_assignments_count': active_assignments_count,
        'page_title': 'External Customer & Client Management | HR Portal',
    }
    return render(request, 'dashboards/customer_management.html', context)


@login_required
def customer_create_view(request):
    """
    Allows HR and Managers to register a new external customer / client for any department.
    """
    user = request.user
    if not can_manage_customers(user):
        messages.error(request, "Permission Denied: You do not have authority to add new customers.")
        return redirect('customer_management')

    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save(commit=False)
            customer.created_by = user
            customer.save()
            messages.success(
                request,
                f"Customer [{customer.client_number}] '{customer.name}' ({customer.company}) has been successfully added to the {customer.department.name} department!"
            )
            return redirect('customer_detail', customer_id=customer.id)
    else:
        dept_id = request.GET.get('department')
        initial = {}
        if dept_id:
            try:
                dept = Department.objects.get(id=dept_id)
                initial['department'] = dept
                initial['client_number'] = Client.generate_next_client_number(dept.name)
            except Department.DoesNotExist:
                pass
        form = CustomerForm(initial=initial)

    return render(request, 'dashboards/customer_create.html', {
        'form': form,
        'page_title': 'Register New Customer | HR Management',
    })


@login_required
def customer_detail_view(request, customer_id):
    """
    Full Customer Profile Dossier:
    Shows customer identification, contact info (phone, place, email), company, department,
    requirements, branch engagements, tasks, and project history.
    """
    user = request.user
    if not can_manage_customers(user):
        messages.error(request, "Access restricted: You do not have permission to view customer details.")
        return redirect('dashboard_router')

    customer = get_object_or_404(
        Client.objects.select_related('department', 'created_by').prefetch_related(
            'assignments__branch',
            'assignments__executive',
            'assignments__delegated_member',
            'tasks__assigned_to',
            'tasks__branch'
        ),
        pk=customer_id
    )

    assignments = customer.assignments.select_related('branch', 'executive', 'delegated_member').order_by('-created_at')
    tasks = customer.tasks.select_related('assigned_to', 'branch').order_by('-created_at')

    return render(request, 'dashboards/customer_detail.html', {
        'customer': customer,
        'assignments': assignments,
        'tasks': tasks,
        'page_title': f"Customer Dossier: {customer.name} ({customer.company})",
    })


@login_required
def customer_edit_view(request, customer_id):
    """
    Allows HR and Managers to edit an existing customer profile.
    """
    user = request.user
    if not can_manage_customers(user):
        messages.error(request, "Permission Denied: You do not have authority to edit customers.")
        return redirect('customer_management')

    customer = get_object_or_404(Client, pk=customer_id)

    if request.method == 'POST':
        form = CustomerForm(request.POST, instance=customer)
        if form.is_valid():
            customer = form.save()
            messages.success(request, f"Customer [{customer.client_number}] details updated successfully.")
            return redirect('customer_detail', customer_id=customer.id)
    else:
        form = CustomerForm(instance=customer)

    return render(request, 'dashboards/customer_edit.html', {
        'form': form,
        'customer': customer,
        'page_title': f"Edit Customer: {customer.name}",
    })


@login_required
def customer_delete_view(request, customer_id):
    """
    Allows HR / Management to delete a customer record with confirmation.
    """
    user = request.user
    if not can_manage_customers(user):
        messages.error(request, "Permission Denied: You do not have authority to delete customers.")
        return redirect('customer_management')

    customer = get_object_or_404(Client, pk=customer_id)

    if request.method == 'POST':
        c_num = customer.client_number
        c_name = customer.name
        customer.delete()
        messages.success(request, f"Customer [{c_num}] '{c_name}' was removed permanently.")
        return redirect('customer_management')

    return render(request, 'dashboards/customer_confirm_delete.html', {
        'customer': customer,
        'page_title': f"Delete Customer: {customer.name}",
    })




