from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from apps.departments.models import Department, Branch
from apps.departments.forms import DepartmentForm, BranchForm
from apps.hierarchy.permissions import can_create_department, can_create_branch, get_user_level
from apps.hierarchy.decorators import department_creation_required, branch_creation_required

@login_required
def department_list_view(request):
    departments = Department.objects.prefetch_related('branches', 'users').all()
    user = request.user

    return render(request, 'departments/department_list.html', {
        'departments': departments,
        'can_create_dept': can_create_department(user),
        'can_create_branch': can_create_branch(user),
    })

@login_required
def department_detail_view(request, pk):
    dept = get_object_or_404(Department.objects.prefetch_related('branches', 'users'), pk=pk)
    user = request.user
    return render(request, 'departments/department_detail.html', {
        'department': dept,
        'branches': dept.branches.all(),
        'members': dept.users.all(),
        'can_create_dept': can_create_department(user),
        'can_create_branch': can_create_branch(user),
    })

@login_required
@department_creation_required
def department_create_view(request):
    if request.method == 'POST':
        form = DepartmentForm(request.POST)
        if form.is_valid():
            dept = form.save()
            messages.success(request, f"Department '{dept.name}' created successfully!")
            return redirect('department_detail', pk=dept.pk)
    else:
        form = DepartmentForm()
    
    return render(request, 'departments/department_form.html', {
        'form': form,
        'title': 'Create New Department',
        'is_edit': False
    })

@login_required
@department_creation_required
def department_update_view(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        form = DepartmentForm(request.POST, instance=dept)
        if form.is_valid():
            form.save()
            messages.success(request, f"Department '{dept.name}' updated successfully.")
            return redirect('department_detail', pk=dept.pk)
    else:
        form = DepartmentForm(instance=dept)
    
    return render(request, 'departments/department_form.html', {
        'form': form,
        'title': f'Edit Department: {dept.name}',
        'is_edit': True,
        'department': dept
    })

@login_required
@department_creation_required
def department_delete_view(request, pk):
    dept = get_object_or_404(Department, pk=pk)
    if request.method == 'POST':
        name = dept.name
        dept.delete()
        messages.success(request, f"Department '{name}' and associated records have been removed.")
        return redirect('department_list')
    return render(request, 'departments/department_confirm_delete.html', {'department': dept})

@login_required
@branch_creation_required
def branch_create_view(request):
    initial_dept = None
    dept_id = request.GET.get('dept_id')
    if dept_id:
        try:
            initial_dept = Department.objects.get(pk=dept_id)
        except Department.DoesNotExist:
            pass

    if request.method == 'POST':
        form = BranchForm(request.POST, user=request.user)
        if form.is_valid():
            branch = form.save()
            messages.success(request, f"Branch '{branch.name}' added to {branch.department.name} successfully!")
            return redirect('department_detail', pk=branch.department.pk)
    else:
        form = BranchForm(user=request.user, initial_dept=initial_dept)
    
    return render(request, 'departments/branch_form.html', {
        'form': form,
        'title': 'Add New Branch',
        'is_edit': False
    })

@login_required
@branch_creation_required
def branch_update_view(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if request.method == 'POST':
        form = BranchForm(request.POST, instance=branch, user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"Branch '{branch.name}' updated successfully.")
            return redirect('department_detail', pk=branch.department.pk)
    else:
        form = BranchForm(instance=branch, user=request.user)
    
    return render(request, 'departments/branch_form.html', {
        'form': form,
        'title': f'Edit Branch: {branch.name}',
        'is_edit': True,
        'branch': branch
    })

@login_required
def branch_detail_view(request, pk):
    branch = get_object_or_404(Branch.objects.select_related('department').prefetch_related('users'), pk=pk)
    return render(request, 'departments/branch_detail.html', {
        'branch': branch,
        'members': branch.users.all(),
        'can_create_branch': can_create_branch(request.user),
    })

@login_required
def branch_delete_view(request, pk):
    branch = get_object_or_404(Branch, pk=pk)
    if not can_create_branch(request.user):
        messages.error(request, "Access Denied: You do not have permission to delete branches.")
        return redirect('department_list')

    dept_id = branch.department.id
    if request.method == 'POST':
        name = branch.name
        branch.delete()
        messages.success(request, f"Branch '{name}' deleted.")
        return redirect('department_detail', pk=dept_id)
    return render(request, 'departments/branch_confirm_delete.html', {'branch': branch})
