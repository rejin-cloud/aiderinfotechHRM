from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout, authenticate
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.db.models import Q
from apps.users.models import User
from apps.users.forms import (
    UserLoginForm,
    UserCreationRBACForm,
    UserUpdateRBACForm,
    UserSelfProfileForm,
    UserRegistrationForm,
    UserAssignmentForm
)
from apps.departments.models import Department, Branch
from apps.hierarchy.permissions import can_manage_user, get_user_level

def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_router')
    
    if request.method == 'POST':
        form = UserLoginForm(request, data=request.POST)
        if form.is_valid():
            user = form.get_user()
            login(request, user)
            messages.success(request, f"Welcome back, {user.get_full_name() or user.username}! Logged in as {user.get_role_display()}.")
            return redirect('dashboard_router')
        else:
            messages.error(request, "Invalid username or password. Please try again.")
    else:
        form = UserLoginForm()
    
    return render(request, 'auth/login.html', {
        'form': form
    })

def register_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard_router')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)
        if form.is_valid():
            user = form.save()
            messages.success(request, f"Account registered successfully for {user.username}! Please sign in.")
            return redirect('login')
        else:
            messages.error(request, "Please correct the errors below to complete registration.")
    else:
        form = UserRegistrationForm()

    return render(request, 'auth/register.html', {
        'form': form
    })

def logout_view(request):
    logout(request)
    messages.info(request, "You have been successfully logged out.")
    return redirect('login')


def quick_switch_user_view(request, user_id):
    """
    Convenience development utility allowing 1-click switching to any role
    to test the distinct role dashboards and permissions instantly.
    """
    target_user = get_object_or_404(User, pk=user_id)
    login(request, target_user)
    messages.success(request, f"Switched view to {target_user.get_full_name() or target_user.username} ({target_user.get_role_display()}) - Level {target_user.level}")
    return redirect('dashboard_router')

@login_required
def profile_view(request):
    if request.method == 'POST':
        form = UserSelfProfileForm(request.POST, instance=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, "Your profile details have been updated successfully.")
            return redirect('profile')
    else:
        form = UserSelfProfileForm(instance=request.user)
    
    return render(request, 'auth/profile.html', {'form': form})

@login_required
def user_list_view(request):
    # Retrieve manageable users or full directory based on role
    current_user = request.user
    role_filter = request.GET.get('role', '')
    dept_filter = request.GET.get('department', '')
    branch_filter = request.GET.get('branch', '')
    search_query = request.GET.get('q', '')

    queryset = User.objects.select_related('department', 'branch').order_by('id')

    # If level 3, restrict to own department/branch
    if current_user.role == User.Role.DEPT_MANAGER:
        if current_user.department:
            queryset = queryset.filter(department=current_user.department)
        if current_user.branch:
            queryset = queryset.filter(branch=current_user.branch)

    if role_filter:
        queryset = queryset.filter(role=role_filter)
    if dept_filter:
        queryset = queryset.filter(department_id=dept_filter)
    if branch_filter:
        queryset = queryset.filter(branch_id=branch_filter)
    if search_query:
        queryset = queryset.filter(
            Q(username__icontains=search_query) |
            Q(first_name__icontains=search_query) |
            Q(last_name__icontains=search_query) |
            Q(email__icontains=search_query) |
            Q(employee_id__icontains=search_query) |
            Q(designation__icontains=search_query)
        )

    departments = Department.objects.all()
    branches = Branch.objects.all()
    roles = User.Role.choices

    can_add_user = len(current_user.get_assignable_roles()) > 0

    return render(request, 'users/user_list.html', {
        'users_list': queryset,
        'departments': departments,
        'branches': branches,
        'roles': roles,
        'role_filter': role_filter,
        'dept_filter': dept_filter,
        'branch_filter': branch_filter,
        'search_query': search_query,
        'can_add_user': can_add_user,
    })

@login_required
def user_create_view(request):
    assignable_roles = request.user.get_assignable_roles()
    if not assignable_roles:
        messages.error(request, "You do not have authorization to create or assign users.")
        return redirect('user_list')

    if request.method == 'POST':
        form = UserCreationRBACForm(request.POST, acting_user=request.user)
        if form.is_valid():
            new_user = form.save()
            messages.success(request, f"User '{new_user.username}' created successfully as {new_user.get_role_display()}!")
            return redirect('user_list')
    else:
        form = UserCreationRBACForm(acting_user=request.user)

    return render(request, 'users/user_form.html', {
        'form': form,
        'title': 'Add New Employee / Member',
        'is_edit': False
    })

@login_required
def user_update_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if not can_manage_user(request.user, target_user):
        messages.error(request, "Access Denied: You do not have permission to edit this user.")
        return redirect('user_list')

    if request.method == 'POST':
        form = UserUpdateRBACForm(request.POST, instance=target_user, acting_user=request.user)
        if form.is_valid():
            form.save()
            messages.success(request, f"User '{target_user.username}' updated successfully.")
            return redirect('user_list')
    else:
        form = UserUpdateRBACForm(instance=target_user, acting_user=request.user)

    return render(request, 'users/user_form.html', {
        'form': form,
        'title': f'Edit Employee: {target_user.get_full_name() or target_user.username}',
        'is_edit': True,
        'target_user': target_user
    })

@login_required
def user_detail_view(request, pk):
    target_user = get_object_or_404(User.objects.select_related('department', 'branch'), pk=pk)
    can_edit = can_manage_user(request.user, target_user)
    return render(request, 'users/user_detail.html', {
        'target_user': target_user,
        'can_edit': can_edit
    })

@login_required
def user_delete_view(request, pk):
    target_user = get_object_or_404(User, pk=pk)
    if not request.user.is_super_or_server_admin():
        messages.error(request, "Only Superadmin or Server Admin can delete user accounts.")
        return redirect('user_list')

    if target_user.id == request.user.id:
        messages.error(request, "You cannot delete your own active account.")
        return redirect('user_list')

    if request.method == 'POST':
        username = target_user.username
        target_user.delete()
        messages.success(request, f"User '{username}' has been deleted.")
        return redirect('user_list')

    return render(request, 'users/user_confirm_delete.html', {'target_user': target_user})

def get_branches_by_department_json(request):
    dept_id = request.GET.get('department_id')
    branches_data = []
    if dept_id:
        branches = Branch.objects.filter(department_id=dept_id).values('id', 'name', 'location')
        branches_data = list(branches)
    return JsonResponse({'branches': branches_data})


@login_required
def user_assign_view(request, user_id=None):
    if not request.user.is_super_or_server_admin():
        messages.error(request, "Access Denied: Only Superadmin or Server Admin can perform global employee assignments.")
        return redirect('dashboard_router')

    target_user = None
    if user_id:
        target_user = get_object_or_404(User, pk=user_id)
    else:
        req_user_id = request.POST.get('selected_user_id') or request.GET.get('user_id')
        if req_user_id:
            try:
                target_user = User.objects.get(pk=req_user_id)
            except User.DoesNotExist:
                target_user = None

    if request.method == 'POST':
        if not target_user:
            req_user_id = request.POST.get('user_id') or request.POST.get('selected_user_id')
            if req_user_id:
                target_user = get_object_or_404(User, pk=req_user_id)
            else:
                messages.error(request, "Please select an employee to assign.")
                return redirect('assign_employee')

        form = UserAssignmentForm(request.POST, instance=target_user)
        if form.is_valid():
            updated_user = form.save()
            dept_name = updated_user.department.name if updated_user.department else "Headquarters"
            messages.success(
                request,
                f"Successfully updated role for {updated_user.get_full_name() or updated_user.username} to '{updated_user.get_role_display()}' in department '{dept_name}'. Upon next sign in, they will be routed directly to the {updated_user.get_role_display()} Dashboard."
            )
            return redirect('superadmin_dashboard')
        else:
            messages.error(request, "Please correct the errors in the assignment form.")
    else:
        form = UserAssignmentForm(instance=target_user) if target_user else UserAssignmentForm()

    all_users = User.objects.all().select_related('department', 'branch').order_by('-id')
    departments = Department.objects.prefetch_related('branches').all().order_by('name')

    return render(request, 'users/assign_employee.html', {
        'form': form,
        'target_user': target_user,
        'all_users': all_users,
        'departments': departments,
        'page_title': 'Assign Employee Role & Department',
    })

