from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from apps.attendance.models import LeaveRequest
from apps.departments.models import Department, Branch
from apps.hierarchy.permissions import get_user_level
from apps.tasks.models import Client, ClientAssignment
from apps.users.models import User

@login_required
def dashboard_router_view(request):
    """
    Intelligent router that directs the user to their role-dedicated dashboard.
    """
    user = request.user

    if user.role == User.Role.SUPERADMIN:
        return redirect('superadmin_dashboard')
    elif user.role == User.Role.SERVER_ADMIN:
        return redirect('serveradmin_dashboard')
    elif user.role == User.Role.MANAGER:
        return redirect('manager_dashboard')
    elif user.role == User.Role.HR:
        return redirect('hr_dashboard')
    elif user.role == User.Role.DEPT_MANAGER:
        return redirect('dept_manager_dashboard')
    else:
        return redirect('employee_dashboard')

@login_required
def superadmin_dashboard_view(request):
    total_users = User.objects.count()
    total_depts = Department.objects.count()
    total_branches = Branch.objects.count()
    
    # Role distribution breakdown
    role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
    role_dict = {item['role']: item['count'] for item in role_counts}
    
    departments = Department.objects.annotate(
        members_count=Count('users', distinct=True),
        branches_count=Count('branches', distinct=True)
    ).all()

    recent_users = User.objects.select_related('department', 'branch').order_by('-id')[:8]
    unassigned_or_staff_users = User.objects.filter(role=User.Role.STAFF).select_related('department', 'branch').order_by('-id')[:6]

    pending_executive_leaves_count = LeaveRequest.objects.filter(
        status=LeaveRequest.Status.PENDING_SUPERADMIN_APPROVAL
    ).count()

    return render(request, 'dashboards/superadmin.html', {
        'total_users': total_users,
        'total_depts': total_depts,
        'total_branches': total_branches,
        'role_dict': role_dict,
        'departments': departments,
        'recent_users': recent_users,
        'unassigned_or_staff_users': unassigned_or_staff_users,
        'pending_executive_leaves_count': pending_executive_leaves_count,
        'all_roles_list': User.Role.choices,
        'page_title': 'Superadmin & Executive System Control',
    })

@login_required
def serveradmin_dashboard_view(request):
    total_users = User.objects.count()
    total_depts = Department.objects.count()
    total_branches = Branch.objects.count()

    role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
    role_dict = {item['role']: item['count'] for item in role_counts}

    recent_users = User.objects.select_related('department', 'branch').order_by('-id')[:10]
    departments = Department.objects.annotate(
        members_count=Count('users', distinct=True),
        branches_count=Count('branches', distinct=True)
    ).all()

    return render(request, 'dashboards/serveradmin.html', {
        'total_users': total_users,
        'total_depts': total_depts,
        'total_branches': total_branches,
        'role_dict': role_dict,
        'recent_users': recent_users,
        'departments': departments,
        'page_title': 'Server & Infrastructure Administration Portal',
    })


@login_required
def manager_dashboard_view(request):
    user = request.user
    
    # Manager has dedicated branch creation & management capabilities
    dept = user.department
    if dept:
        managed_branches = Branch.objects.filter(department=dept)
        dept_members = User.objects.filter(department=dept).select_related('branch')
    else:
        managed_branches = Branch.objects.all()
        dept_members = User.objects.all().select_related('department', 'branch')

    dept_managers = dept_members.filter(role=User.Role.DEPT_MANAGER)
    staff_members = dept_members.exclude(role__in=[User.Role.SUPERADMIN, User.Role.SERVER_ADMIN, User.Role.MANAGER])
    
    all_depts = Department.objects.all()


    return render(request, 'dashboards/manager.html', {
        'managed_branches': managed_branches,
        'dept_members': dept_members,
        'dept_managers': dept_managers,
        'staff_members': staff_members,
        'current_dept': dept,
        'all_depts': all_depts,
        'page_title': 'Manager Operations & Branch Hub',
    })

@login_required
def hr_dashboard_view(request):
    total_employees = User.objects.exclude(role__in=[User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]).count()
    
    departments = Department.objects.annotate(
        members_count=Count('users', distinct=True),
        branches_count=Count('branches', distinct=True)
    ).all()

    role_counts = User.objects.values('role').annotate(count=Count('id')).order_by('-count')
    role_dict = {item['role']: item['count'] for item in role_counts}

    recent_employees = User.objects.exclude(
        role__in=[User.Role.SUPERADMIN, User.Role.SERVER_ADMIN]
    ).select_related('department', 'branch').order_by('-id')[:10]

    # Department managers eligible for assignment review
    dept_managers = User.objects.filter(role=User.Role.DEPT_MANAGER).select_related('department', 'branch')

    return render(request, 'dashboards/hr.html', {
        'total_employees': total_employees,
        'departments': departments,
        'role_dict': role_dict,
        'recent_employees': recent_employees,
        'dept_managers': dept_managers,
        'page_title': 'Human Resources Governance Center',
    })

@login_required
def dept_manager_dashboard_view(request):
    user = request.user
    dept = user.department
    branch = user.branch

    # Dept Manager oversees Executives, Interns, and Staff
    subordinates = User.objects.filter(
        role__in=[User.Role.EXECUTIVE, User.Role.INTERN, User.Role.STAFF]
    )
    if dept:
        subordinates = subordinates.filter(department=dept)
    if branch:
        subordinates = subordinates.filter(branch=branch)
    
    subordinates = subordinates.select_related('department', 'branch')

    total_subordinates = subordinates.count()
    executives_count = subordinates.filter(role=User.Role.EXECUTIVE).count()
    interns_count = subordinates.filter(role=User.Role.INTERN).count()
    staff_count = subordinates.filter(role=User.Role.STAFF).count()

    clients_count = 0
    recent_clients = []
    client_assignments_count = 0
    recent_client_assignments = []
    if dept and 'creative' in dept.name.lower():
        clients_count = Client.objects.filter(department=dept).count()
        recent_clients = Client.objects.filter(department=dept).order_by('-created_at')[:5]
        client_assignments_count = ClientAssignment.objects.filter(client__department=dept).count()
        recent_client_assignments = ClientAssignment.objects.filter(
            client__department=dept
        ).select_related('client', 'branch', 'executive', 'delegated_member').order_by('-created_at')[:5]

    return render(request, 'dashboards/dept_manager.html', {
        'subordinates': subordinates,
        'total_subordinates': total_subordinates,
        'executives_count': executives_count,
        'interns_count': interns_count,
        'staff_count': staff_count,
        'current_dept': dept,
        'current_branch': branch,
        'clients_count': clients_count,
        'recent_clients': recent_clients,
        'client_assignments_count': client_assignments_count,
        'recent_client_assignments': recent_client_assignments,
        'page_title': f'Department Manager Portal: {dept.name if dept else "General"}',
    })

@login_required
def employee_dashboard_view(request):
    user = request.user
    dept = user.department
    branch = user.branch

    # Company departments for company overview section
    company_departments = Department.objects.prefetch_related('branches').annotate(
        members_count=Count('users', distinct=True)
    ).order_by('name')

    # Department leadership contact point
    dept_manager = None
    if dept:
        dept_manager = User.objects.filter(
            department=dept,
            role__in=[User.Role.DEPT_MANAGER, User.Role.MANAGER]
        ).first()

    # HR Representative contact
    hr_rep = User.objects.filter(role=User.Role.HR).first()

    teammates = []
    if dept:
        teammates = User.objects.filter(department=dept).exclude(id=user.id).select_related('branch')[:8]

    # Creative tasks for this employee's branch
    from apps.tasks.models import Task
    branch_tasks = Task.objects.none()
    if dept:
        if branch:
            branch_tasks = Task.objects.filter(department=dept).filter(
                Q(branch=branch) | Q(branch__isnull=True)
            ).select_related('created_by', 'branch', 'assigned_to').prefetch_related('attachments').order_by('-created_at')
        else:
            branch_tasks = Task.objects.filter(department=dept, branch__isnull=True).select_related('created_by', 'branch', 'assigned_to').prefetch_related('attachments').order_by('-created_at')

    # Client assignments for this employee
    executive_client_assignments = []
    member_client_assignments = []
    if user.role == User.Role.EXECUTIVE:
        executive_client_assignments = ClientAssignment.objects.filter(
            Q(executive=user) | Q(branch=branch)
        ).select_related('client', 'branch', 'assigned_by', 'delegated_member').order_by('-created_at')
    else:
        member_client_assignments = ClientAssignment.objects.filter(
            delegated_member=user
        ).select_related('client', 'branch', 'assigned_by', 'executive').order_by('-created_at')

    return render(request, 'dashboards/employee.html', {
        'user_profile': user,
        'department': dept,
        'branch': branch,
        'dept_manager': dept_manager,
        'hr_rep': hr_rep,
        'company_departments': company_departments,
        'teammates': teammates,
        'branch_tasks': branch_tasks,
        'executive_client_assignments': executive_client_assignments,
        'member_client_assignments': member_client_assignments,
        'page_title': f'Employee Portal: {user.get_full_name() or user.username}',
    })

