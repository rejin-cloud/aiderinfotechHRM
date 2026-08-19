import datetime
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date, parse_datetime

from apps.departments.models import Branch, Department
from apps.hierarchy.permissions import get_user_level
from apps.tasks.forms import (
    ClientAssignmentForm,
    ClientFilterForm,
    ClientForm,
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


