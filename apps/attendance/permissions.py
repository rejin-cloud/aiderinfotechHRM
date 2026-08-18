from apps.users.models import User
from apps.hierarchy.permissions import get_user_level


def can_log_attendance(user):
    """
    Super Admin is exempted from daily check-in / check-out.
    All other employees (Server Admin, HR, Manager, Dept Manager, Executive, Intern, Staff) log attendance.
    """
    if not user or not user.is_authenticated:
        return False
    return user.role != User.Role.SUPERADMIN


def can_view_user_attendance(acting_user, target_user):
    """
    Implements attendance visibility rules:
    - Each person can see their own record.
    - Level 1 (Superadmin / Server Admin) and HR can view all records.
    - Managers (Level 2) can see records of personnel below their level.
    - Department Managers (Level 3) can see records of THEIR department only.
    - Staff / Interns / Executives can only see their own records.
    """
    if not acting_user or not acting_user.is_authenticated:
        return False

    if acting_user.id == target_user.id:
        return True

    acting_level = get_user_level(acting_user)
    target_level = get_user_level(target_user)

    if acting_level == 1:
        return True

    if acting_user.role == User.Role.HR:
        return True

    if acting_user.role == User.Role.MANAGER:
        # Managers see records below their level (Level 3 and 4)
        if acting_user.department and target_user.department:
            return acting_user.department_id == target_user.department_id and target_level > 2
        return target_level > 2

    if acting_user.role == User.Role.DEPT_MANAGER:
        # Department managers can see records of their department ONLY
        if not acting_user.department:
            return False
        if target_user.department_id == acting_user.department_id and target_level == 4:
            return True
        return False

    return False


def can_view_monthly_reports(user):
    """
    Monthly attendance reports should be visible and downloaded ONLY by HR and above level
    (HR, Manager, Server Admin, Superadmin).
    """
    if not user or not user.is_authenticated:
        return False
    return get_user_level(user) <= 2


def can_review_leave_dept_level(user, leave_request):
    """
    Department Manager review step:
    Dept Manager of the applicant's department reviews the application.
    """
    if not user or not user.is_authenticated:
        return False
    if get_user_level(user) <= 2:
        return True
    if user.role == User.Role.DEPT_MANAGER:
        if user.department and leave_request.user.department:
            return user.department_id == leave_request.user.department_id
    return False


def can_approve_leave_final(user, leave_request):
    """
    Final approval from Manager (or HR / Superadmin / Server Admin) is necessary.
    """
    if not user or not user.is_authenticated:
        return False
    return get_user_level(user) <= 2
