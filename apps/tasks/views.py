from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.departments.models import Branch, Department
from apps.hierarchy.permissions import get_user_level
from apps.tasks.forms import TaskFilterForm, TaskForm
from apps.tasks.models import Task, TaskAttachment
from apps.tasks.permissions import can_manage_creative_tasks, can_view_creative_tasks, is_creative_department
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
    - Creative Department members (Staff, Interns, Executives) ONLY see tasks assigned directly to them.
    - Non-assigned members cannot see other members' assignments.
    """
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
    tasks = Task.objects.filter(department=department).select_related('created_by', 'assigned_to', 'branch', 'department').prefetch_related('attachments')

    # Scoping rule: regular members only see tasks assigned directly to them
    if not is_leadership:
        tasks = tasks.filter(assigned_to=user)

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
    completed_tasks = tasks.filter(status=Task.Status.COMPLETED).count()
    urgent_tasks = tasks.filter(priority=Task.Priority.URGENT, status=Task.Status.ACTIVE).count()

    context = {
        'tasks': tasks,
        'department': department,
        'is_creative_manager': is_creative_manager,
        'is_leadership': is_leadership,
        'filter_form': filter_form,
        'stats': {
            'total': total_tasks,
            'active': active_tasks,
            'completed': completed_tasks,
            'urgent': urgent_tasks,
        }
    }
    return render(request, 'tasks/task_list.html', context)


@login_required
def task_create_view(request):
    """
    Dedicated Task Creation Page:
    - STRICTLY restricted to the Creative Department Manager.
    - No one else can create tasks in the Creative Department.
    - Handles Task Number, Title, Description, Attachments (any file type), Instructions, etc.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager is authorized to create tasks in this department.")
        return redirect('task_list')

    # Determine department
    if user.department and is_creative_department(user.department):
        department = user.department
    else:
        department = get_creative_department_instance()

    if request.method == 'POST':
        form = TaskForm(request.POST, request.FILES, department=department)
        if form.is_valid():
            task = form.save(commit=False)
            task.department = department
            task.created_by = user
            task.save()

            # Process attached files (supports ANY file format)
            files = request.FILES.getlist('documents')
            for f in files:
                TaskAttachment.objects.create(
                    task=task,
                    file=f
                )

            messages.success(
                request,
                f"Task [{task.task_number}] '{task.title}' was created successfully with {len(files)} attachment(s)! You can now assign this task to a branch member."
            )
            return redirect('task_assign_specific', task_id=task.id)
    else:
        form = TaskForm(department=department)

    context = {
        'form': form,
        'department': department,
    }
    return render(request, 'tasks/task_create.html', context)


@login_required
def task_assign_view(request, task_id=None):
    """
    Dedicated Task Assignment Page:
    - STRICTLY restricted to the Creative Department Manager.
    - Step 1: Select a Task from Creative Department.
    - Step 2: Select a Branch in Creative Department.
    - Step 3: Select an Employee belonging to that selected branch only.
    - Step 4: Assign member to the task.
    """
    user = request.user
    if not can_manage_creative_tasks(user):
        messages.error(request, "Permission Denied: Only the Creative Department Manager is authorized to assign tasks.")
        return redirect('task_list')

    # Determine department
    if user.department and is_creative_department(user.department):
        department = user.department
    else:
        department = get_creative_department_instance()

    tasks = Task.objects.filter(department=department).select_related('assigned_to', 'branch').order_by('-created_at')
    branches = Branch.objects.filter(department=department).prefetch_related('users').order_by('name')

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

        # Update assignment
        task.branch = branch
        task.assigned_to = assigned_user
        task.save()

        messages.success(
            request,
            f"Success! Task [{task.task_number}] '{task.title}' has been assigned to {assigned_user.get_full_name() or assigned_user.username} ({branch.name})."
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
    }
    return render(request, 'tasks/task_assign.html', context)


@login_required
def branch_members_api(request, branch_id):
    """API endpoint returning member list for a given branch in Creative Department."""
    user = request.user
    if not can_manage_creative_tasks(user):
        return JsonResponse({'error': 'Unauthorized'}, status=403)

    branch = get_object_or_404(Branch, pk=branch_id)
    members = User.objects.filter(branch=branch, department=branch.department).exclude(role=User.Role.SUPERADMIN).order_by('first_name', 'username')

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
    - Creative Department Manager & Corporate Leadership can view all tasks and assignments.
    - Assigned Member can view full task brief, instructions, and download assets.
    - Non-assigned members cannot access tasks assigned to other people.
    """
    user = request.user
    if not can_view_creative_tasks(user):
        messages.error(request, "Access restricted: You cannot view this task.")
        return redirect('dashboard_router')

    task = get_object_or_404(
        Task.objects.select_related('department', 'branch', 'created_by', 'assigned_to').prefetch_related('attachments'),
        pk=task_id
    )

    is_creative_manager = can_manage_creative_tasks(user)
    is_leadership = get_user_level(user) <= 2 or is_creative_manager

    # Strict Privacy / Scoping Rule:
    # If regular member, they can only view if the task is assigned specifically to them
    if not is_leadership:
        if task.assigned_to != user:
            messages.error(request, "Access restricted: This task is assigned to another team member.")
            return redirect('task_list')

    context = {
        'task': task,
        'is_creative_manager': is_creative_manager,
        'is_leadership': is_leadership,
        'is_assigned_to_me': (task.assigned_to == user),
    }
    return render(request, 'tasks/task_detail.html', context)


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
