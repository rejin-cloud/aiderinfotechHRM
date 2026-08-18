from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from apps.departments.models import Department
from apps.tasks.forms import TaskFilterForm, TaskForm
from apps.tasks.models import Task, TaskAttachment
from apps.tasks.permissions import can_manage_creative_tasks, can_view_creative_tasks, is_creative_department


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
    - Creative Department Manager sees full management controls and 'Create Task' action.
    - Creative Department members (Staff, Interns, Executives) see read-only task cards.
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

    # Base Queryset
    tasks = Task.objects.filter(department=department).select_related('created_by', 'assigned_to', 'branch', 'department').prefetch_related('attachments')

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
                f"Task [{task.task_number}] '{task.title}' was created successfully with {len(files)} attachment(s)!"
            )
            return redirect('task_detail', task_id=task.id)
    else:
        form = TaskForm(department=department)

    context = {
        'form': form,
        'department': department,
    }
    return render(request, 'tasks/task_create.html', context)


@login_required
def task_detail_view(request, task_id):
    """
    Detailed Task View:
    - Accessible to all Creative Department members.
    - Displays full creative brief, instructions, deadline, priority, and downloadable assets.
    - Completely READ-ONLY for regular members (Executives, Interns, Staff).
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

    context = {
        'task': task,
        'is_creative_manager': is_creative_manager,
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
