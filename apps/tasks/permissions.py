from apps.hierarchy.permissions import get_user_level
from apps.users.models import User


def is_creative_department(department):
    """Helper to verify if a department is the Creative Department."""
    if not department:
        return False
    return 'creative' in department.name.lower()


def can_manage_creative_tasks(user):
    """
    Strict permission check: ONLY the Creative Department Manager
    (and superadmin oversight) can create, edit, update, or delete tasks.
    No other employees or department managers have task creation authority.
    """
    if not user or not user.is_authenticated:
        return False

    # Superadmin / Server Admin emergency oversight
    if user.role in [User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]:
        return True

    # Creative Department Manager
    if user.role == User.Role.DEPT_MANAGER and is_creative_department(user.department):
        return True

    return False


def can_view_creative_tasks(user):
    """
    Read-only permission check:
    - Creative Department members (Executives, Interns, Staff, Dept Manager)
    - Corporate Leadership (Superadmin, Server Admin, HR, General Manager)
    """
    if not user or not user.is_authenticated:
        return False

    # Executive Leadership & HR
    if get_user_level(user) <= 2:
        return True

    # Creative Department personnel
    if user.department and is_creative_department(user.department):
        return True

    return False
