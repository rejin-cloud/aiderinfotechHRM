from apps.users.models import User

LEVEL_MAP = {
    User.Role.SUPERADMIN: 1,
    User.Role.SERVER_ADMIN: 1,
    User.Role.HR: 2,
    User.Role.MANAGER: 2,
    User.Role.DEPT_MANAGER: 3,
    User.Role.EXECUTIVE: 4,
    User.Role.INTERN: 4,
    User.Role.STAFF: 4,
}

def get_user_level(user):
    """Returns the integer system level (1 to 4) of a user."""
    if not user or not user.is_authenticated:
        return 99
    return LEVEL_MAP.get(user.role, 4)

def can_create_department(user):
    """Level 1 (Superadmin & Server Admin) only."""
    return get_user_level(user) == 1

def can_create_branch(user):
    """Level 1 (Superadmin & Server Admin) and Manager (Level 2)."""
    if not user or not user.is_authenticated:
        return False
    return get_user_level(user) == 1 or user.role == User.Role.MANAGER

def can_assign_role(user, target_role):
    """
    Checks if `user` has the authority to assign a user to `target_role`.
    - Level 1: Can assign any role (HR, Manager, etc.)
    - HR (Level 2): Can assign Dept Managers, Executives, Interns, Staff
    - Manager (Level 2): Can assign Dept Managers, Executives, Interns, Staff
    - Dept Manager (Level 3): Can assign/manage Executives, Interns, Staff
    - Level 4: No assignment authority
    """
    if not user or not user.is_authenticated:
        return False
    user_level = get_user_level(user)
    target_level = LEVEL_MAP.get(target_role, 4)

    if user_level == 1:
        return True
    elif user_level == 2:
        # HR and Manager can assign Level 3 and Level 4
        return target_level in [3, 4]
    elif user_level == 3:
        # Department Manager can only assign Level 4 (Exec, Intern, Staff)
        return target_level == 4
    return False

def can_manage_user(acting_user, target_user):
    """
    Determines if acting_user has operational authority over target_user.
    """
    if not acting_user or not acting_user.is_authenticated:
        return False
    
    # Self-editing basic profile is always allowed
    if acting_user.id == target_user.id:
        return True

    acting_level = get_user_level(acting_user)
    target_level = get_user_level(target_user)

    if acting_level == 1:
        return True
    
    if acting_level == 2:
        if acting_user.role == User.Role.HR:
            # HR can manage any user level 2 or lower (excluding Level 1)
            return target_level >= 2 and target_user.role not in [User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]
        elif acting_user.role == User.Role.MANAGER:
            # Manager can manage users in their department below Level 2, or general Level 3/4
            if acting_user.department and target_user.department:
                return acting_user.department_id == target_user.department_id and target_level > 2
            return target_level > 2

    if acting_level == 3:
        # Dept Manager can manage level 4 users in same department (and branch if specified)
        if target_level == 4:
            if acting_user.department and target_user.department:
                if acting_user.department_id != target_user.department_id:
                    return False
            if acting_user.branch and target_user.branch:
                if acting_user.branch_id != target_user.branch_id:
                    return False
            return True
        return False

    return False
