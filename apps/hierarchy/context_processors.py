from apps.hierarchy.permissions import can_create_department, can_create_branch, get_user_level
from apps.users.models import User
from apps.departments.models import Department, Branch

def rbac_context(request):
    """
    Context processor making RBAC flags, demo users, and navigation data available globally in templates.
    """
    if not request.user.is_authenticated:
        demo_accounts = User.objects.all().order_by('id')[:10]
        return {
            'is_authenticated': False,
            'demo_accounts': demo_accounts,
        }

    user = request.user
    user_level = get_user_level(user)
    
    # Pre-fetch demo accounts for quick switcher
    demo_accounts = User.objects.all().order_by('id')[:10]

    return {
        'is_authenticated': True,
        'current_user': user,
        'user_level': user_level,
        'can_create_dept_perm': can_create_department(user),
        'can_create_branch_perm': can_create_branch(user),
        'demo_accounts': demo_accounts,
        'all_roles_list': User.Role.choices,
        'stat_total_users': User.objects.count(),
        'stat_total_depts': Department.objects.count(),
        'stat_total_branches': Branch.objects.count(),
    }
