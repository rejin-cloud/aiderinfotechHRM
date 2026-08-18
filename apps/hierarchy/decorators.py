from functools import wraps
from django.shortcuts import redirect
from django.contrib import messages
from apps.hierarchy.permissions import (
    get_user_level,
    can_create_department,
    can_create_branch
)

def role_required(*allowed_roles):
    """
    Decorator for views that checks whether a user has one of the allowed roles.
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access this page.")
                return redirect('login')
            if request.user.role not in allowed_roles and not request.user.is_super_or_server_admin():
                messages.error(request, f"Access Denied: Your role ({request.user.get_role_display()}) does not have permission to perform this action.")
                return redirect('dashboard_router')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def level_required(max_level):
    """
    Decorator requiring the user's system level to be <= max_level (1=highest, 4=lowest).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                messages.warning(request, "Please log in to access this page.")
                return redirect('login')
            user_lvl = get_user_level(request.user)
            if user_lvl > max_level:
                messages.error(request, f"Access Denied: Level {max_level} authority required. Your account is Level {user_lvl}.")
                return redirect('dashboard_router')
            return view_func(request, *args, **kwargs)
        return _wrapped_view
    return decorator

def department_creation_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not can_create_department(request.user):
            messages.error(request, "Access Denied: Department creation is restricted to Superadmin / Server Admin (Level 1).")
            return redirect('department_list')
        return view_func(request, *args, **kwargs)
    return _wrapped_view

def branch_creation_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not can_create_branch(request.user):
            messages.error(request, "Access Denied: Branch creation is restricted to Superadmin, Server Admin, and Managers.")
            return redirect('department_list')
        return view_func(request, *args, **kwargs)
    return _wrapped_view
